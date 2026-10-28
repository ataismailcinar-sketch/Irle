# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / INTENT / NLU — Dil Modeli Olmadan Türkçe Anlama
=============================================================================
Regex kural motorundan daha esnek, dil modelinden çok daha hızlı ve tamamen
çevrimdışı bir anlama katmanı. Katmanlar:

  1. NORMALLEŞTİRME   İ/ı dönüşümü, kesme işaretli ekleri atma (chrome'u → chrome),
                      sayı kelimelerini rakama çevirme (yüzde kırk beş → yüzde 45)
  2. KAVRAMLAR        Her kelime ekleriyle birlikte bir kavrama eşlenir:
                      kıs / kısar mısın / kısıver / alçalt / düşür  →  AZALT
  3. NİYET PUANLAMA   Kavram kombinasyonları niyete dönüşür (SES + AZALT → ses_azalt).
                      Açıklanamayan kelime oranı güveni düşürür.
  4. BULANIK EŞLEŞME  Uygulama adları yazım/telaffuz hatasına dayanıklı (kroma → chrome)
  5. BAĞLAM           "biraz daha", "geri al", "onu kapat", "ne dedin"
  6. OLUMSUZLUK       "sesi kısma" → hiçbir şey yapma
  7. SOHBET           selam, nasılsın, teşekkür, şaka... (cevabı yanitlar.py üretir)

Sonuç bir `NluSonuc`: komut + güven (0-1). Güven yüksekse IntentModulu
komutu dil modeline sormadan çalıştırır; düşükse beyne bırakır.
=============================================================================
"""

from __future__ import annotations

import difflib
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

from irle.domain.commands import (
    CancelAllTimers, CloseApplication, CompositeCommand, CreateNote, DeleteNote,
    KillProcess, LockComputer, MediaControl, MuteVolume, OpenApplication,
    ReadClipboard, ScheduleCommand, SearchFile, SearchWeb, SetBrightness,
    SetVolume, Speak, TakeScreenshot, WindowControl,
)
from irle.domain.queries import (
    GetBatteryStatus, GetCurrentTime, GetNetworkStatus, GetSystemInfo, ListNotes,
)


# ===========================================================================
# Sonuç ve bağlam
# ===========================================================================

@dataclass(frozen=True)
class NluSonuc:
    komut: Any                      # Command/Query; sohbet için None
    guven: float                    # 0.0 – 1.0
    niyet: str
    tur: str = "komut"              # komut | sohbet | baglam | olumsuz
    kategori: str = "onay"          # yanitlar.py kategorisi
    alanlar: dict = field(default_factory=dict)


class Baglam:
    """Son birkaç dakikanın konuşma durumu."""

    def __init__(self, ttl_saniye: float = 180.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_saniye
        self._clock = clock
        self._son_komut: Any = None
        self._son_uygulama: Optional[tuple[str, str]] = None  # (görünen ad, ad)
        self._son_yanit: str = ""
        self._zaman = 0.0

    def _taze(self) -> bool:
        return self._clock() - self._zaman <= self._ttl

    @property
    def son_komut(self) -> Any:
        return self._son_komut if self._taze() else None

    @property
    def son_uygulama(self) -> Optional[tuple[str, str]]:
        return self._son_uygulama if self._taze() else None

    @property
    def son_yanit(self) -> str:
        return self._son_yanit if self._taze() else ""

    def komut_calisti(self, komut: Any, gorunen_ad: str = "") -> None:
        self._zaman = self._clock()
        if isinstance(komut, CompositeCommand) and komut.commands:
            for alt in komut.commands:
                self.komut_calisti(alt)
            return
        self._son_komut = komut
        if isinstance(komut, OpenApplication):
            self._son_uygulama = (gorunen_ad or komut.name, komut.name)

    def yanit_verildi(self, metin: str) -> None:
        self._zaman = self._clock()
        self._son_yanit = metin


# ===========================================================================
# 1. Normalleştirme
# ===========================================================================

def tr_kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


_BIRLER = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
_ONLAR = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60,
          "yetmiş": 70, "seksen": 80, "doksan": 90}
_SAYI_EKI = re.compile(r"(|y?[aeıiuü]|y?[ae]|[dt][ae]|[dt][ae]n|y?l[ae]|l[ıi]k|[şs][ae]r)")
_BIRIMLER = re.compile(r"(saniye|dakika|saat|dk|sn)")
_HARIC_SAYI = {"ona", "onu", "onun", "onlar", "onları", "onda", "ondan", "onla", "biri", "birini",
               "birisi", "bire", "altına", "altında", "altından", "üçgen"}


def _sayi_kelimesi(tok: str) -> Optional[tuple[int, str]]:
    """'kırka' → (40, 'a'). Sayı değilse None."""
    if tok in _HARIC_SAYI:
        return None
    for sozluk in (_ONLAR, _BIRLER):
        for kelime, deger in sozluk.items():
            if tok.startswith(kelime):
                ek = tok[len(kelime):]
                if _SAYI_EKI.fullmatch(ek):
                    return deger, ek
    if tok.startswith("yüz") and _SAYI_EKI.fullmatch(tok[3:]) and tok != "yüzde":
        return 100, tok[3:]
    return None


@dataclass
class Jeton:
    metin: str           # normalleşmiş kelime (sayılar rakam)
    ham: str             # sayı dönüşümünden önceki hali
    sayi: Optional[int] = None
    ek: str = ""         # sayı ekinden kalan (kırk-a → "a") → "-e/-a" hedef bildirir


def jetonla(metin: str) -> list[Jeton]:
    s = tr_kucuk(metin)
    s = re.sub(r"%\s*(\d+)", r"yüzde \1", s)
    s = re.sub(r"(\d+)\s*['’`´]\s*([a-zçğıöşü]+)", r"\1\2", s)   # 40'a → 40a
    s = re.sub(r"['’`´][a-zçğıöşü]*", "", s)                     # chrome'u → chrome
    s = re.sub(r"[^\w\s]", " ", s)
    ham = s.split()

    jetonlar: list[Jeton] = []
    i = 0
    while i < len(ham):
        tok = ham[i]
        m = re.fullmatch(r"(\d+)([a-zçğıöşü]*)", tok)
        if m:
            jetonlar.append(Jeton(m.group(1), tok, int(m.group(1)), m.group(2)))
            i += 1
            continue
        sk = _sayi_kelimesi(tok)
        if sk is not None:
            deger, ek = sk
            onceki = ham[i - 1] if i else ""
            sonraki = ham[i + 1] if i + 1 < len(ham) else ""
            sonraki_sayi = _sayi_kelimesi(sonraki) if sonraki else None
            # "bir" ve "yüz" çok anlamlı: sadece sayı bağlamında sayı say
            if tok.startswith(("bir", "yüz")) and not (
                    _BIRIMLER.match(sonraki or "-") or onceki == "yüzde" or sonraki_sayi):
                jetonlar.append(Jeton(tok, tok))
                i += 1
                continue
            # "kırk beş" → 45
            if deger >= 10 and ek == "" and sonraki_sayi and sonraki_sayi[0] < 10:
                deger += sonraki_sayi[0]
                ek = sonraki_sayi[1]
                tok = f"{tok} {sonraki}"
                i += 1
            jetonlar.append(Jeton(str(deger), tok, deger, ek))
            i += 1
            continue
        jetonlar.append(Jeton(tok, tok))
        i += 1
    return jetonlar


# ===========================================================================
# 2. Kavramlar (kelime başı eşleşmesi — Türkçe ekler sona gelir)
# ===========================================================================

def _k(desen: str) -> re.Pattern[str]:
    return re.compile(desen)


K = {
    "SES": _k(r"(ses(?!siz)|volume|hoparlör)"),
    "PARLAKLIK": _k(r"(parlakl|parlak|ışı[kğ]|aydınlık)"),
    "MEDYA": _k(r"(müzi[kğ]|şarkı|parça|video|medya|film|dizi|podcast|spotify)"),
    "ARTIR": _k(r"(art[ıt]?ır|arttır|yükselt|büyüt|çoğalt|kökle|aç(?!ıkla|ıklık|ılış)|aydınlat)"),
    "AZALT": _k(r"(azalt|kıs(?!a\b|ım)|düşür|alçalt|indir|küçült|karart)"),
    "SUSTUR": _k(r"(sustur|sessiz|mute|sus\Z)"),
    "KAPAT": _k(r"kapa[tn]"),
    "DURDUR": _k(r"(durdur|duraklat|pause|beklet|dur\Z|dursun)"),
    "OYNAT": _k(r"(oynat|çal(?!ış)|devam|play|resume)"),
    "SONRAKI": _k(r"(sonraki|geç(?!miş|en\Z|ti|ir)|atla|ileri|next)"),
    "ONCEKI": _k(r"(önceki|başa|previous|prev\Z)"),
    "AC": _k(r"(aç(?!ıkla|ıklık|ılış)|başlat|çalıştır|open)"),
    "SAAT": _k(r"(saat\Z|saati|saat kaç|zaman\Z)"),
    "TARIH": _k(r"(tarih|ayın\Z|günlerden)"),
    "SORU": _k(r"(kaç|ne\Z|nedir|neler|nasıl|mi\Z|mı\Z|mu\Z|mü\Z|söyle|oldu)"),
    "PIL": _k(r"(pil|batarya|şarj)"),
    "DONANIM": _k(r"(işlemci|cpu|ram\Z|ramı|bellek|disk|depolama|performans)"),
    "AG": _k(r"(internet|bağlantı|ping|ip\Z|wifi|wi)"),
    "NOT": _k(r"not(?!epad)"),
    "KAYDET": _k(r"(al\Z|alır|alsana|al[ıi]n|alabilir|kaydet|yaz|ekle|et\Z|eder|etsene|tut)"),
    "OKU": _k(r"(oku|listele|göster|neler|getir)"),
    "SIL": _k(r"(sil\Z|sile|sils|silin|silebilir|temizle|kaldır)"),
    "HEPSI": _k(r"(tüm|hepsi|bütün|hep\Z)"),
    "SON": _k(r"(son\Z|sonuncu|en son)"),
    "ARA": _k(r"(ara\Z|arar|arat|araştır|bul\Z|bulur|bulsana|search)"),
    "WEB": _k(r"(internet|google|web|tarayıcı|nette)"),
    "DOSYA": _k(r"(dosya|masaüstü|belge)"),
    "EKRAN": _k(r"ekran"),
    "GORUNTU": _k(r"(görüntü|resm|resim|fotoğraf|ss\Z|screenshot)"),
    "KILITLE": _k(r"kilitle"),
    "BILGISAYAR": _k(r"(bilgisayar|pc\Z|makine)"),
    "IPTAL": _k(r"(iptal|vazgeç)"),
    "ZAMANLAYICI": _k(r"(zamanlayıcı|sayaç|alarm|hatırlatıcı)"),
    "HATIRLAT": _k(r"(hatırlat|uyar)"),
    "SONRA": _k(r"sonra\Z"),
    "ZORLA": _k(r"(zorla|sonlandır|öldür|kill)"),
    "PENCERE": _k(r"pencere"),
    "TAM_EKRAN": _k(r"(tam\Z|maximize|büyüt)"),
    "KUCULT": _k(r"(küçült|minimize|aşağı)"),
    "ONE": _k(r"(öne|odakla|getir)"),
    "PANO": _k(r"pano"),
    "BIRAZ": _k(r"(biraz|azıcık|az\Z|tık\Z|hafif|birazcık)"),
    "COK": _k(r"(çok|epey|iyice|baya|bayağı|full|sonuna|tamamen|fazla)"),
    "YUZDE": _k(r"yüzde\Z"),
    "AYARLA": _k(r"(yap\Z|yapar|yapsana|ayarla|getir|olsun|çek\Z|çeker)"),
    "ZAMIR": _k(r"(onu\Z|şunu\Z|bunu\Z|o\Z|şu\Z|bu\Z)"),
}

# Kendi başına anlam taşımayan kelimeler (kapsama hesabında "açıklanmış" sayılır)
_DOLGU = {
    "abi", "kanka", "kanki", "knk", "reis", "kral", "kardeşim", "moruk", "bro", "dostum", "aga",
    "hacı", "baba", "panpa", "lan", "len", "ya", "yaa", "yaaa", "be", "hadi", "haydi", "lütfen",
    "lutfen", "rica", "ederim", "acaba", "bi", "bir", "şu", "şunu", "bu", "bunu", "o", "onu",
    "benim", "bana", "beni", "sen", "sana", "senin", "için", "de", "da", "ki", "ve", "bakalım",
    "artık", "hemen", "şimdi", "tamam", "okey", "ok", "hey", "efendim", "bey", "hanım",
    "misin", "mısın", "musun", "müsün", "misiniz", "mısınız", "musunuz", "müsünüz", "mi", "mı",
    "mu", "mü", "yap", "et", "eder", "edebilir", "edin", "ver", "verir", "olur", "bak", "bakar",
    "al", "biraz", "azıcık", "daha", "kadar", "durum", "durumda", "durumu", "dolu", "boş", "bugün", "şuan", "bi", "tane", "allah", "aşkına", "iyi", "güzel", "şey", "falan",
    "irle", "jarvis", "zahmet", "olmazsa", "mümkünse", "rica", "edermisin", "yapar", "yaparmısın",
}


# ===========================================================================
# 3. Uygulama / site kataloğu (bulanık eşleşme)
# ===========================================================================

_VARSAYILAN_UYGULAMALAR: dict[str, tuple[str, list[str]]] = {
    # ad: (görünen ad, takma adlar)
    "chrome": ("Chrome", ["chrome", "krom", "kroma", "google chrome", "tarayıcı", "tarayıcıyı"]),
    "spotify": ("Spotify", ["spotify", "spotifay", "spotfy", "spoti"]),
    "discord": ("Discord", ["discord", "diskord", "dıskord"]),
    "code": ("VS Code", ["vs code", "vscode", "visual studio code", "vs kod", "kod editörü"]),
    "notepad": ("Not Defteri", ["not defteri", "notepad", "notepat"]),
    "hesap": ("Hesap Makinesi", ["hesap makinesi", "hesap makinası", "calculator", "hesap"]),
    "explorer": ("Dosya Gezgini", ["dosya gezgini", "explorer", "dosyalar", "klasörler"]),
    "terminal": ("Terminal", ["terminal", "cmd", "komut istemi", "powershell", "konsol"]),
    "steam": ("Steam", ["steam", "stim"]),
    "whatsapp": ("WhatsApp", ["whatsapp", "vatsap", "watsap", "wp"]),
    "telegram": ("Telegram", ["telegram"]),
    "winword": ("Word", ["word", "vörd"]),
    "excel": ("Excel", ["excel", "eksel"]),
    "powerpnt": ("PowerPoint", ["powerpoint", "power point", "pawırpoint"]),
    "firefox": ("Firefox", ["firefox", "firefoks"]),
    "msedge": ("Edge", ["edge", "microsoft edge"]),
    "obs64": ("OBS", ["obs"]),
    "vlc": ("VLC", ["vlc"]),
    "rider64": ("Rider", ["rider"]),
    "devenv": ("Visual Studio", ["visual studio"]),
}

_VARSAYILAN_SITELER: dict[str, tuple[str, list[str]]] = {
    "https://www.youtube.com": ("YouTube", ["youtube", "yutup", "yutub", "youtub"]),
    "https://mail.google.com": ("Gmail", ["gmail", "mail", "e posta", "eposta"]),
    "https://www.instagram.com": ("Instagram", ["instagram", "insta"]),
    "https://x.com": ("X", ["twitter", "tivitır"]),
    "https://github.com": ("GitHub", ["github", "gitub", "githab"]),
    "https://web.whatsapp.com": ("WhatsApp Web", ["whatsapp web"]),
    "https://www.netflix.com": ("Netflix", ["netflix", "netfliks"]),
    "https://chat.openai.com": ("ChatGPT", ["chatgpt", "çet gpt", "chat gpt"]),
    "https://claude.ai": ("Claude", ["claude", "klod"]),
    "https://www.google.com/maps": ("Haritalar", ["harita", "haritalar", "google maps"]),
}


class _Katalog:
    def __init__(self, uygulamalar: dict, siteler: dict) -> None:
        self._girdiler: list[tuple[str, str, str]] = []   # (takma ad, hedef, görünen)
        for hedef, (gorunen, adlar) in {**uygulamalar, **siteler}.items():
            for ad in adlar:
                self._girdiler.append((tr_kucuk(ad), hedef, gorunen))
        # Uzun takma adlar önce (visual studio code > visual studio)
        self._girdiler.sort(key=lambda g: -len(g[0]))

    def bul(self, kelimeler: list[str], haric: set[int]) -> Optional[tuple[str, str, set[int]]]:
        """Kelime dizisinde bilinen bir uygulama/site arar → (hedef, görünen, kullanılan indeksler)."""
        aday_gruplari: list[tuple[str, set[int]]] = []
        n = len(kelimeler)
        for uz in (3, 2, 1):
            for i in range(n - uz + 1):
                idx = set(range(i, i + uz))
                if idx & haric:
                    continue
                aday_gruplari.append((" ".join(kelimeler[i:i + uz]), idx))

        en_iyi: Optional[tuple[float, str, str, set[int]]] = None
        for aday, idx in aday_gruplari:
            for ad, hedef, gorunen in self._girdiler:
                if aday == ad:
                    skor = 1.0
                elif len(ad) >= 4 and aday.startswith(ad) and len(aday) - len(ad) <= 3:
                    skor = 0.95          # spotifyı, chromeu (ek)
                elif len(ad) >= 4 and len(aday) >= 4:
                    skor = difflib.SequenceMatcher(None, aday, ad).ratio()
                    if skor < 0.82:
                        continue
                else:
                    continue
                if en_iyi is None or skor > en_iyi[0] or (skor == en_iyi[0] and len(idx) > len(en_iyi[3])):
                    en_iyi = (skor, hedef, gorunen, idx)
        if en_iyi is None:
            return None
        return en_iyi[1], en_iyi[2], en_iyi[3]


# ===========================================================================
# 4. Sohbet kalıpları (tüm cümle üzerinde)
# ===========================================================================

_SOHBET: list[tuple[str, re.Pattern[str]]] = [
    ("tesekkur", re.compile(r"\b(teşekkür\w*|sağ ?ol\w*|eyvallah|eyv|mersi|thanks|eline sağlık)\b")),
    ("nasilsin", re.compile(r"\b(nasılsın\w*|naber|nbr|ne haber|iyi misin|keyifler nasıl|ne var ne yok)\b")),
    ("selam", re.compile(r"\b(selam\w*|merhaba|mrb|slm|hey|günaydın|iyi akşamlar|iyi günler|aleyküm\w*|hello)\b")),
    ("veda", re.compile(r"\b(görüşürüz|hoşça kal|iyi geceler|bay bay|bb|kendine iyi bak)\b")),
    ("iltifat", re.compile(r"\b(aferin|harikasın|süpersin|helal|bravo|mükemmelsin|efsanesin|çok iyisin|seni seviyorum)\b")),
    ("hakaret", re.compile(r"\b(salak\w*|aptal\w*|gerizekalı\w*|beyinsiz\w*|işe yaramaz\w*|mal mısın)\b")),
    ("kimsin", re.compile(r"\b(kimsin|adın ne|ismin ne|sen nesin|kendini tanıt\w*)\b")),
    ("yetenek", re.compile(r"\b(ne(ler)? yapabilirsin|ne(ler)? biliyorsun|yardım|komutlar\w*|neler yaparsın)\b")),
    ("saka", re.compile(r"\b(şaka|fıkra|güldür)\w*\b")),
]

_BAGLAM_TEKRAR = {"daha", "biraz", "az", "azıcık", "tekrar", "yine", "aynı", "aynısı", "aynısını",
                  "yap", "bir", "bi", "de", "da", "devam", "birdaha", "tık", "çok", "bunu"}
_GERI_AL = re.compile(r"\b(geri al\w*|fazla oldu|çok oldu|abarttın|eski haline|geri getir|olmadı)\b")
_NE_DEDIN = re.compile(r"\b(ne dedin|tekrar söyle|tekrarla|tekrar eder misin|duyamadım|bir daha söyle|bi daha söyle|anlamadım)\b")

_OLUMSUZ_EK = re.compile(r"m[ae](y[ıi]n(?:[ıi]z)?|s[ıi]n|sana|sene|yal[ıi]m|yel[ıi]m)?")


# ===========================================================================
# 5. Ana sınıf
# ===========================================================================

class _Cozumleme:
    """Tek bir cümlenin jetonları + hangi jetonların açıklandığı."""

    def __init__(self, jetonlar: list[Jeton]) -> None:
        self.j = jetonlar
        self.kelimeler = [t.metin for t in jetonlar]
        self.metin = " ".join(self.kelimeler)
        self._kavram: dict[str, list[int]] = {}
        self.olumsuz: set[int] = set()
        for ad, desen in K.items():
            yerler = []
            for i, w in enumerate(self.kelimeler):
                m = desen.match(w)
                if m:
                    yerler.append(i)
                    if _OLUMSUZ_EK.fullmatch(w[m.end():]) and ad in (
                            "ARTIR", "AZALT", "SUSTUR", "KAPAT", "DURDUR", "OYNAT", "AC", "SIL", "KILITLE"):
                        self.olumsuz.add(i)
            if yerler:
                self._kavram[ad] = yerler
        # çok kelimeli kavramlar
        if re.search(r"\bekran görüntüsü\b|\bekran resmi\b", self.metin):
            self._kavram.setdefault("GORUNTU", [])

    def var(self, *kavramlar: str) -> bool:
        return all(k in self._kavram for k in kavramlar)

    def herhangi(self, *kavramlar: str) -> bool:
        return any(k in self._kavram for k in kavramlar)

    def yer(self, *kavramlar: str) -> set[int]:
        s: set[int] = set()
        for k in kavramlar:
            s.update(self._kavram.get(k, []))
        return s

    def sayilar(self) -> list[tuple[int, Jeton]]:
        return [(i, t) for i, t in enumerate(self.j) if t.sayi is not None]

    def kapsama(self, kullanilan: set[int]) -> float:
        if not self.j:
            return 0.0
        aciklanan = 0
        for i, w in enumerate(self.kelimeler):
            if i in kullanilan or w in _DOLGU or i in self.yer("SORU", "BIRAZ", "COK"):
                aciklanan += 1
        return aciklanan / len(self.j)


class TurkceNLU:
    """Dil modelsiz Türkçe niyet çözümleyici."""

    def __init__(self, uygulamalar: Optional[dict] = None, siteler: Optional[dict] = None) -> None:
        self._katalog = _Katalog(uygulamalar or _VARSAYILAN_UYGULAMALAR,
                                 siteler or _VARSAYILAN_SITELER)

    # ------------------------------------------------------------------

    def anla(self, metin: str, baglam: Optional[Baglam] = None) -> Optional[NluSonuc]:
        metin = (metin or "").strip()
        if not metin:
            return None

        parcalar = [p for p in re.split(r"\s+(?:ve\s+de|ardından|daha\s+sonra|sonra\s+da|ve)\s+|[,;]\s+",
                                        tr_kucuk(metin)) if p.strip()]
        # "5 dakika sonra X" bölünmesin: zamanlayıcı cümlesi tek parça kalır
        if len(parcalar) > 1 and not re.search(r"\d+\s*\w*\s+(saniye|dakika|saat)\s+sonra|"
                                                r"\b(dakika|saniye|saat)\s+sonra\b", tr_kucuk(metin)):
            alt = [self._tek(p, baglam) for p in parcalar]
            if all(a is not None and a.tur == "komut" and a.komut is not None for a in alt):
                return NluSonuc(
                    komut=CompositeCommand(commands=tuple(a.komut for a in alt)),  # type: ignore[union-attr]
                    guven=min(a.guven for a in alt),  # type: ignore[union-attr]
                    niyet="bilesik", kategori="onay",
                )
            return None  # karmaşık cümle → beyin ya da kural motoru

        return self._tek(metin, baglam)

    # ------------------------------------------------------------------

    def _tek(self, metin: str, baglam: Optional[Baglam]) -> Optional[NluSonuc]:
        c = _Cozumleme(jetonla(metin))
        if not c.j:
            return None

        adaylar: list[Optional[NluSonuc]] = [
            self._baglam(c, baglam),
            self._zamanlayici(c),
            self._ses(c, baglam),
            self._parlaklik(c, baglam),
            self._medya(c),
            self._not(c, metin),
            self._bilgi(c),
            self._ekran_sistem(c),
            self._pencere(c, baglam),
            self._uygulama(c),
            self._arama(c, metin),
            self._sohbet(c),
        ]
        adaylar_ = [a for a in adaylar if a is not None]
        if not adaylar_:
            return None
        en_iyi = max(adaylar_, key=lambda a: a.guven)

        # Olumsuz eylem ("sesi kısma") → hiçbir şey yapma
        if en_iyi.tur == "komut" and c.olumsuz:
            return NluSonuc(komut=None, guven=0.7, niyet="olumsuz", tur="olumsuz", kategori="olumsuz")
        return en_iyi

    @staticmethod
    def _sonuc(c: _Cozumleme, kullanilan: set[int], komut: Any, niyet: str, kategori: str,
               taban: float = 1.0, tur: str = "komut", **alanlar: Any) -> NluSonuc:
        guven = taban * (0.55 + 0.45 * c.kapsama(kullanilan))
        return NluSonuc(komut=komut, guven=round(guven, 3), niyet=niyet, tur=tur,
                        kategori=kategori, alanlar=alanlar)

    # ------------------------------------------------------------------
    # Sayı → seviye mi, değişim mi?
    # ------------------------------------------------------------------

    @staticmethod
    def _miktar(c: _Cozumleme, yon: int) -> tuple[Optional[int], Optional[int], set[int]]:
        """(level, delta, kullanılan) döndürür."""
        sayilar = c.sayilar()
        kullanilan = c.yer("YUZDE", "AYARLA", "BIRAZ", "COK")
        if sayilar:
            i, t = sayilar[0]
            kullanilan.add(i)
            n = max(0, min(100, t.sayi or 0))
            hedef_eki = t.ek in ("a", "e", "ya", "ye")
            if c.herhangi("YUZDE", "AYARLA") or hedef_eki or yon == 0:
                return n, None, kullanilan
            return None, yon * max(1, n), kullanilan
        if yon == 0:
            return None, None, kullanilan
        if c.var("COK"):
            adim = 30
        elif c.var("BIRAZ"):
            adim = 10
        else:
            adim = 15
        return None, yon * adim, kullanilan

    # ------------------------------------------------------------------
    # Niyetler
    # ------------------------------------------------------------------

    def _ses(self, c: _Cozumleme, b: Optional[Baglam]) -> Optional[NluSonuc]:
        konu = c.herhangi("SES", "SUSTUR") or (c.var("MEDYA") and c.herhangi("AZALT", "ARTIR") and not c.var("AC"))
        # Bağlamdan: "biraz daha kıs" → son komut ses ise sesi kıs
        baglamdan = (not konu and b is not None and isinstance(b.son_komut, SetVolume)
                     and c.herhangi("AZALT", "ARTIR") and not c.herhangi("PARLAKLIK", "MEDYA"))
        if not (konu or baglamdan):
            return None
        taban = 1.0 if konu else 0.9
        kullan = c.yer("SES", "MEDYA", "SUSTUR") if konu else set()

        if c.herhangi("SUSTUR") or (c.var("KAPAT") and c.var("SES")):
            return self._sonuc(c, kullan | c.yer("SUSTUR", "KAPAT"), MuteVolume(), "ses_sustur", "sustur", taban)

        yon = -1 if c.var("AZALT") else (1 if c.var("ARTIR") else 0)
        level, delta, k2 = self._miktar(c, yon)
        kullan |= k2 | c.yer("AZALT", "ARTIR")
        if level is not None:
            return self._sonuc(c, kullan, SetVolume(level=level), "ses_seviye", "ses_seviye", taban, n=level)
        if delta is not None:
            kat = "ses_azaldi" if delta < 0 else "ses_artti"
            return self._sonuc(c, kullan, SetVolume(delta=delta), kat, kat, taban, n=abs(delta))
        return None

    def _parlaklik(self, c: _Cozumleme, b: Optional[Baglam]) -> Optional[NluSonuc]:
        konu = c.var("PARLAKLIK") or (c.var("EKRAN") and c.herhangi("AZALT", "ARTIR") and not c.var("GORUNTU"))
        baglamdan = (not konu and b is not None and isinstance(b.son_komut, SetBrightness)
                     and c.herhangi("AZALT", "ARTIR") and not c.herhangi("SES", "MEDYA"))
        if not (konu or baglamdan):
            return None
        taban = 1.0 if konu else 0.9
        yon = -1 if c.var("AZALT") else (1 if c.var("ARTIR") else 0)
        level, delta, kullan = self._miktar(c, yon)
        kullan |= c.yer("PARLAKLIK", "EKRAN", "AZALT", "ARTIR")
        if level is not None:
            return self._sonuc(c, kullan, SetBrightness(level=level), "parlaklik_seviye", "parlaklik_seviye",
                               taban, n=level)
        if delta is not None:
            kat = "parlaklik_azaldi" if delta < 0 else "parlaklik_artti"
            return self._sonuc(c, kullan, SetBrightness(delta=delta), kat, kat, taban)
        return None

    def _medya(self, c: _Cozumleme) -> Optional[NluSonuc]:
        medya = c.var("MEDYA")
        kullan = c.yer("MEDYA")
        if c.var("SONRAKI") and (medya or len(c.j) <= 3):
            return self._sonuc(c, kullan | c.yer("SONRAKI"), MediaControl(action="next"), "medya_sonraki",
                               "medya_sonraki", 1.0 if medya else 0.9)
        if c.var("ONCEKI") and (medya or len(c.j) <= 3):
            return self._sonuc(c, kullan | c.yer("ONCEKI"), MediaControl(action="previous"), "medya_onceki",
                               "medya_onceki", 1.0 if medya else 0.9)
        if c.herhangi("DURDUR") and (medya or len(c.j) <= 3) and not c.herhangi("ZAMANLAYICI", "IPTAL"):
            return self._sonuc(c, kullan | c.yer("DURDUR"), MediaControl(action="play_pause"), "medya_durdur",
                               "medya_durdu", 1.0 if medya else 0.85)
        if medya and c.var("KAPAT") and not c.var("SES"):
            return self._sonuc(c, kullan | c.yer("KAPAT"), MediaControl(action="play_pause"), "medya_durdur",
                               "medya_durdu", 0.9)
        if c.var("OYNAT") and (medya or len(c.j) <= 3):
            return self._sonuc(c, kullan | c.yer("OYNAT"), MediaControl(action="play_pause"), "medya_oynat",
                               "medya_oynuyor", 1.0 if medya else 0.85)
        if medya and c.var("AC") and not c.var("SES") and self._katalog.bul(c.kelimeler, set()) is None:
            # "müzik aç" (uygulama adı yoksa) → oynat
            return self._sonuc(c, kullan | c.yer("AC"), MediaControl(action="play_pause"), "medya_oynat",
                               "medya_oynuyor", 0.85)
        return None

    def _not(self, c: _Cozumleme, ham: str) -> Optional[NluSonuc]:
        if not c.var("NOT"):
            return None
        if c.herhangi("AC", "KAPAT") and self._katalog.bul(c.kelimeler, c.yer("AC", "KAPAT")):
            return None  # "not defterini aç" → uygulama
        kullan = c.yer("NOT")
        if c.var("SIL"):
            mod = "all" if c.var("HEPSI") else "last"
            return self._sonuc(c, kullan | c.yer("SIL", "HEPSI", "SON"), DeleteNote(mode=mod), "not_sil", "onay")
        if c.var("OKU") or (c.var("SORU") and not c.var("KAYDET")):
            return self._sonuc(c, kullan | c.yer("OKU", "SORU"), ListNotes(limit=3), "not_oku", "onay")

        alt = tr_kucuk(ham)
        m = (re.search(r"\bnot\s+(?:al|et|tut|yaz|ekle|kaydet)\w*\s*[:,]?\s*(.+)$", alt)
             or re.search(r"^(?:şunu\s+|şöyle\s+)?(.+?)\s+(?:diye\s+)?not\s+(?:al|et|tut|yaz|ekle|kaydet)\w*\s*$", alt)
             or re.search(r"\bnot\w*\s*:\s*(.+)$", alt))
        if not m:
            return None
        metin = re.sub(r"^(şunu|şöyle|bunu)\s+", "", m.group(1).strip(" .,:;"))
        if len(metin) < 2:
            return None
        # Not içeriği "açıklanmış" sayılır → güven yüksek
        return NluSonuc(komut=CreateNote(text=metin), guven=0.97, niyet="not_al", kategori="not_alindi")

    def _bilgi(self, c: _Cozumleme) -> Optional[NluSonuc]:
        if c.var("SAAT") and not c.herhangi("HATIRLAT", "ZAMANLAYICI", "SONRA"):
            return self._sonuc(c, c.yer("SAAT", "SORU", "TARIH"), GetCurrentTime(), "saat", "onay")
        if c.var("TARIH") and (c.var("SORU") or len(c.j) <= 2) and not c.var("NOT"):
            return self._sonuc(c, c.yer("TARIH", "SORU"), GetCurrentTime(), "tarih", "onay", 0.95)
        if c.var("PIL"):
            return self._sonuc(c, c.yer("PIL", "SORU"), GetBatteryStatus(), "pil", "onay")
        if c.var("DONANIM") and not c.herhangi("SIL", "AC"):
            konular = []
            for w in c.kelimeler:
                if w.startswith(("işlemci", "cpu", "performans")):
                    konular.append("cpu")
                elif w.startswith(("ram", "bellek")):
                    konular.append("ram")
                elif w.startswith(("disk", "depolama")):
                    konular.append("disk")
            return self._sonuc(c, c.yer("DONANIM", "SORU"), GetSystemInfo(topics=tuple(dict.fromkeys(konular))),
                               "sistem", "onay", 0.95)
        if c.var("AG") and (c.var("SORU") or c.herhangi("AG")) and not c.herhangi("ARA", "AC"):
            ping = any(w.startswith(("ping", "hız", "gecikme", "bağlantı")) for w in c.kelimeler)
            return self._sonuc(c, c.yer("AG", "SORU"), GetNetworkStatus(include_ping=ping), "ag", "onay", 0.9)
        if c.var("PANO") and (c.var("OKU") or c.var("SORU")):
            return self._sonuc(c, c.yer("PANO", "OKU", "SORU"), ReadClipboard(), "pano", "onay", 0.95)
        return None

    def _ekran_sistem(self, c: _Cozumleme) -> Optional[NluSonuc]:
        if c.var("GORUNTU") and (c.var("EKRAN") or "ss" in c.kelimeler):
            return self._sonuc(c, c.yer("EKRAN", "GORUNTU", "KAYDET", "AYARLA"), TakeScreenshot(),
                               "ekran_goruntusu", "ekran_goruntusu")
        if c.var("KILITLE"):
            return self._sonuc(c, c.yer("KILITLE", "BILGISAYAR", "EKRAN"), LockComputer(), "kilitle", "kilitlendi")
        return None

    def _zamanlayici(self, c: _Cozumleme) -> Optional[NluSonuc]:
        if c.herhangi("ZAMANLAYICI", "HATIRLAT") and c.herhangi("IPTAL", "SIL", "KAPAT", "DURDUR") \
                and not c.sayilar():
            return self._sonuc(c, c.yer("ZAMANLAYICI", "HATIRLAT", "IPTAL", "SIL", "KAPAT", "DURDUR", "HEPSI"),
                               CancelAllTimers(), "zamanlayici_iptal", "onay")

        # "<N> <birim> sonra <iş>"  /  "<iş> <N> <birim> sonra"  /  "yarım saat sonra ..."
        metin = c.metin
        m = re.search(r"\b(?:(\d+)\s+|(yarım)\s+)?(saniye|dakika|saat|dk|sn)\w*\s+(?:sonra|içinde)\b", metin)
        if not m:
            m2 = re.search(r"\b(\d+)\s+(saniye|dakika|saat|dk|sn)\w*\b", metin)
            if not (m2 and c.herhangi("HATIRLAT", "ZAMANLAYICI")):
                return None
            sayi, yarim, birim = m2.group(1), None, m2.group(2)
            span = m2.span()
        else:
            sayi, yarim, birim = m.group(1), m.group(2), m.group(3)
            span = m.span()
        carpan = {"saniye": 1, "sn": 1, "dakika": 60, "dk": 60, "saat": 3600}[birim]
        miktar = 0.5 if yarim else float(sayi or 1)
        sure = int(miktar * carpan)
        if sure <= 0:
            return None
        is_metni = (metin[:span[0]] + " " + metin[span[1]:]).strip()
        is_metni = re.sub(r"\b(bana|lütfen|abi|kanka|bir|bi|alarm|zamanlayıcı\w*|kur\w*)\b", " ", is_metni)
        is_metni = re.sub(r"\s+", " ", is_metni).strip()
        if not is_metni:
            is_metni = "süre doldu"
        return NluSonuc(komut=ScheduleCommand(delay_seconds=sure, inner_command_text=is_metni),
                        guven=0.95, niyet="zamanlayici", kategori="onay")

    def _pencere(self, c: _Cozumleme, b: Optional[Baglam]) -> Optional[NluSonuc]:
        # "onu kapat" → son açılan uygulama
        if c.var("KAPAT") and b is not None and b.son_uygulama and not c.herhangi("SES", "BILGISAYAR", "MEDYA") \
                and (c.var("ZAMIR") or len(c.j) == 1):
            gorunen, ad = b.son_uygulama
            return self._sonuc(c, c.yer("KAPAT", "ZAMIR"), CloseApplication(name=gorunen), "uygulama_kapat",
                               "uygulama_kapandi", 0.95, ad=gorunen)

        bulunan = self._katalog.bul(c.kelimeler, c.yer("SES"))
        if c.var("ZORLA") and bulunan:
            hedef, gorunen, idx = bulunan
            return self._sonuc(c, idx | c.yer("ZORLA", "KAPAT"), KillProcess(process_name=hedef),
                               "islem_sonlandir", "uygulama_kapandi", ad=gorunen)
        eylem = None
        if c.var("KUCULT") and not c.herhangi("SES", "PARLAKLIK"):
            eylem = "minimize"
        elif c.var("TAM_EKRAN") and (c.var("EKRAN") or c.var("PENCERE")) and not c.var("GORUNTU"):
            eylem = "maximize"
        elif c.var("ONE") and (c.var("PENCERE") or bulunan) and not c.herhangi("AC", "OKU"):
            eylem = "focus"
        if eylem and bulunan:
            hedef, gorunen, idx = bulunan
            return self._sonuc(c, idx | c.yer("KUCULT", "TAM_EKRAN", "EKRAN", "PENCERE", "ONE", "AYARLA"),
                               WindowControl(app_name=gorunen, action=eylem), "pencere", "onay", ad=gorunen)
        return None

    def _uygulama(self, c: _Cozumleme) -> Optional[NluSonuc]:
        if not c.herhangi("AC", "KAPAT") or c.herhangi("SES", "PARLAKLIK", "BILGISAYAR"):
            return None
        if c.var("NOT") and self._katalog.bul(c.kelimeler, set()) is None:
            return None
        if c.var("MEDYA") and not c.var("KAPAT") and self._katalog.bul(c.kelimeler, set()) is None:
            return None
        fiil = c.yer("AC", "KAPAT")
        bulunan = self._katalog.bul(c.kelimeler, fiil)
        kapat = c.var("KAPAT") and not c.var("AC")
        if bulunan:
            hedef, gorunen, idx = bulunan
            kullan = idx | fiil
            if kapat:
                return self._sonuc(c, kullan, CloseApplication(name=gorunen), "uygulama_kapat",
                                   "uygulama_kapandi", ad=gorunen)
            return self._sonuc(c, kullan, OpenApplication(name=hedef), "uygulama_ac", "uygulama_acildi",
                               ad=gorunen)
        if kapat:
            return None
        # Bilinmeyen ad: "X aç" → X (katalogda olabilir) ama güven düşük
        fiil_i = min(c.yer("AC"))
        onceki = [w for i, w in enumerate(c.kelimeler[:fiil_i]) if w not in _DOLGU]
        if 1 <= len(onceki) <= 2:
            ad = " ".join(onceki)
            return NluSonuc(komut=OpenApplication(name=ad), guven=0.7, niyet="uygulama_ac",
                            kategori="uygulama_acildi", alanlar={"ad": ad})
        return None

    def _arama(self, c: _Cozumleme, ham: str) -> Optional[NluSonuc]:
        if not c.var("ARA"):
            return None
        alt = tr_kucuk(ham)
        alt = re.sub(r"['’][a-zçğıöşü]+", "", alt)
        if c.var("DOSYA"):
            m = re.search(r"(?:masaüstünde|dosyalarda|bilgisayarda)\s+(.+?)\s+(?:adlı\s+|isimli\s+)?(?:dosya\w*\s+)?(?:ara|bul)\w*", alt) \
                or re.search(r"(.+?)\s+(?:adlı\s+|isimli\s+)?dosya\w*\s+(?:ara|bul)\w*", alt)
            if m:
                terim = re.sub(r"^(şu|bir|bi)\s+", "", m.group(1).strip())
                return NluSonuc(komut=SearchFile(term=terim), guven=0.92, niyet="dosya_ara", kategori="onay")
            return None
        m = (re.search(r"(?:google|internet|web|nette|tarayıcı)\w*\s+(.+?)\s+(?:ara|arat|araştır)\w*\s*$", alt)
             or re.search(r"^(.+?)\s+(?:diye\s+)?(?:google\w*|internet\w*|web\w*|nette)?\s*(?:ara|arat|araştır)\w*\s*$", alt))
        if not m:
            return None
        sorgu = re.sub(r"\b(abi|kanka|lütfen|bana|bi|bir|şunu|şu)\b", " ", m.group(1))
        sorgu = re.sub(r"\b(google|internet|web|nette)\w*\b", " ", sorgu)
        sorgu = re.sub(r"\s+", " ", sorgu).strip()
        if len(sorgu) < 2:
            return None
        guven = 0.95 if c.var("WEB") else 0.82
        return NluSonuc(komut=SearchWeb(query=sorgu), guven=guven, niyet="web_ara", kategori="web_arama")

    def _sohbet(self, c: _Cozumleme) -> Optional[NluSonuc]:
        for niyet, desen in _SOHBET:
            m = desen.search(c.metin)
            if not m:
                continue
            kullan = {i for i, w in enumerate(c.kelimeler)
                      if desen.search(w) or w in m.group(0).split()}
            return self._sonuc(c, kullan | c.yer("SORU"), None, niyet, niyet, 1.0, tur="sohbet")
        return None

    def _baglam(self, c: _Cozumleme, b: Optional[Baglam]) -> Optional[NluSonuc]:
        if b is None:
            return None
        if _NE_DEDIN.search(c.metin) and b.son_yanit:
            return NluSonuc(komut=Speak(text=b.son_yanit), guven=0.95, niyet="ne_dedin", tur="baglam",
                            kategori="tekrar")

        son = b.son_komut
        # "geri al", "fazla oldu" → son değişimi tersine çevir
        if _GERI_AL.search(c.metin):
            ters = _ters(son)
            if ters is None:
                return NluSonuc(komut=None, guven=0.8, niyet="geri_al", tur="baglam", kategori="tekrar_yok")
            return NluSonuc(komut=ters, guven=0.92, niyet="geri_al", tur="baglam", kategori=_kategori(ters))

        # "biraz daha", "tekrar", "bir daha"
        icerik = [w for w in c.kelimeler if w not in _DOLGU or w in ("daha", "tekrar", "yine")]
        if icerik and set(c.kelimeler) <= _BAGLAM_TEKRAR | _DOLGU \
                and any(w in ("daha", "tekrar", "yine", "aynı", "aynısı", "aynısını", "devam") for w in c.kelimeler):
            tekrar = _tekrarlanabilir(son)
            if tekrar is None:
                return NluSonuc(komut=None, guven=0.8, niyet="tekrar", tur="baglam", kategori="tekrar_yok")
            return NluSonuc(komut=tekrar, guven=0.92, niyet="tekrar", tur="baglam", kategori=_kategori(tekrar))
        return None


# ===========================================================================
# Yardımcılar
# ===========================================================================

def _tekrarlanabilir(k: Any) -> Any:
    if isinstance(k, (SetVolume, SetBrightness)) and k.delta is not None:
        return k
    if isinstance(k, MediaControl) and k.action in ("next", "previous"):
        return k
    return None


def _ters(k: Any) -> Any:
    if isinstance(k, (SetVolume, SetBrightness)) and k.delta is not None:
        return type(k)(delta=-k.delta)
    if isinstance(k, MediaControl) and k.action in ("next", "previous"):
        return MediaControl(action="previous" if k.action == "next" else "next")
    if isinstance(k, MuteVolume):
        return MuteVolume()
    return None


def _kategori(k: Any) -> str:
    """Bir komut için varsayılan onay cevabı kategorisi."""
    if isinstance(k, SetVolume):
        if k.level is not None:
            return "ses_seviye"
        return "ses_azaldi" if (k.delta or 0) < 0 else "ses_artti"
    if isinstance(k, SetBrightness):
        if k.level is not None:
            return "parlaklik_seviye"
        return "parlaklik_azaldi" if (k.delta or 0) < 0 else "parlaklik_artti"
    if isinstance(k, MuteVolume):
        return "sustur"
    if isinstance(k, MediaControl):
        return {"next": "medya_sonraki", "previous": "medya_onceki"}.get(k.action, "medya_durdu")
    if isinstance(k, OpenApplication):
        return "uygulama_acildi"
    if isinstance(k, (CloseApplication, KillProcess)):
        return "uygulama_kapandi"
    if isinstance(k, CreateNote):
        return "not_alindi"
    if isinstance(k, TakeScreenshot):
        return "ekran_goruntusu"
    if isinstance(k, LockComputer):
        return "kilitlendi"
    if isinstance(k, SearchWeb):
        return "web_arama"
    return "onay"


def komut_kategorisi(k: Any) -> str:
    return _kategori(k)

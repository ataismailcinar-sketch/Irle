# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / BRAIN / PERSONA — Kullanıcıya Göre Şekil Alan Kişilik
=============================================================================
İrle'nin sabit bir karakteri yok: kullanıcı nasıl konuşuyorsa ona uyar.

  * "Kanka şu sesi kıs ya"          → samimi, kısa, esprili
  * "Sesi kısar mısınız lütfen"     → kibar, "siz" diye hitap
  * "ses kıs"                        → asker gibi: anında yap, tek kelime
  * "Of yeter ya, çalışmıyor bu"     → sakin, özür yok, hemen çözüm
  * Uzun uzun anlatan kullanıcı      → o da sohbet eder, açıklar

Sadece cevap tonu değil DAVRANIŞ da değişir: acelecilere soru sorulmaz,
direkt yapılır; sohbetçilerle önce sohbet edilir; kibar ve resmî
kullanıcıya riskli işlerde onay sorulur.

Analiz kural tabanlıdır (çevrimdışı, anında) ve son ~8 cümleye bakar;
yeni cümleler eskilerden daha ağırdır. Böylece konuşma ilerledikçe uyum sağlar.
=============================================================================
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Optional


# ---------------------------------------------------------------------------
# Sinyal sözlükleri
# ---------------------------------------------------------------------------

_SAMIMI = {
    "kanka", "kanki", "abi", "abii", "moruk", "kardeşim", "kardesim", "bro", "lan",
    "len", "naber", "nbr", "eyw", "eyv", "eyvallah", "aga", "kral", "reis", "hacı",
    "haci", "dostum", "ya", "yaa", "yaaa", "be", "baba", "panpa", "knk", "slm", "mrb",
}
_HITAPLAR = ("abi", "kanka", "kanki", "reis", "kral", "kardeşim", "moruk", "bro",
             "dostum", "aga", "hacı", "baba", "panpa", "knk")
_ARGO = {"lan", "len", "amk", "aq", "bok", "lanet", "siktir", "hassiktir", "salak", "aptal"}
_RESMI = {
    "lütfen", "lutfen", "rica", "ederim", "efendim", "zahmet", "mümkünse", "mumkunse", "bey", "hanım", "saygılar",
}
_SIZ_EKLERI = re.compile(
    r"\b(siz|size|sizi|sizin|sizden)\b|"
    r"(ır|ir|ur|ür|ar|er)\s*m[ıiuü]s[ıiuü]n[ıiuü]z\b|"   # yapar mısınız
    r"(yın|yin|yun|yün|ın|in|un|ün)[ıiuü]z\b|"            # açınız, yapınız
    r"(abilir|ebilir)\s*m[ıi]s[ıi]n[ıi]z",
)
_SINIRLI = {"of", "off", "yeter", "sinir", "bıktım", "biktim", "saçma", "sacma", "çalışmıyor",
            "calismiyor", "bozuk", "hala", "hâlâ", "yine", "niye", "neden", "allah"}
_SAKACI = re.compile(r"(ha){2,}|(he){2,}|(sj){2,}|(ks){2,}|asd|xd|:d|😂|🤣|😄|😅|lol", re.IGNORECASE)
_SELAM = re.compile(r"\b(selam|merhaba|naber|nasılsın|günaydın|iyi akşamlar|hey|slm|mrb)\b", re.IGNORECASE)

_KELIME = re.compile(r"[\wçğıöşüâîû']+", re.IGNORECASE)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _KELIME.findall(text)]


# ---------------------------------------------------------------------------
# Üslup profili
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UslupProfili:
    """Kullanıcının o anki konuşma tarzının özeti (0.0 – 1.0 skorlar)."""
    samimiyet: float = 0.5      # 0 resmî ↔ 1 kanka
    siz_hitabi: bool = False
    argo: float = 0.0
    sabirsizlik: float = 0.0
    espri: float = 0.0
    ortalama_kelime: float = 6.0
    sohbet_istegi: float = 0.3  # selamlaşma / soru / uzun anlatım eğilimi
    hitap: str = ""             # kullanıcının en son kullandığı hitap (abi, kanka, reis...)

    @property
    def kisa_ve_net(self) -> bool:
        return self.ortalama_kelime <= 3.5 and self.sohbet_istegi < 0.4

    def etiket(self) -> str:
        """Log ve arayüz için kısa açıklama."""
        parcalar = []
        if self.siz_hitabi or self.samimiyet < 0.35:
            parcalar.append("resmî")
        elif self.samimiyet > 0.65:
            parcalar.append("samimi")
        else:
            parcalar.append("nötr")
        if self.kisa_ve_net:
            parcalar.append("kısa-net")
        if self.sabirsizlik > 0.4:
            parcalar.append("gergin")
        if self.espri > 0.3:
            parcalar.append("şakacı")
        if self.sohbet_istegi > 0.6:
            parcalar.append("sohbetçi")
        return ", ".join(parcalar)


class UslupAnalizcisi:
    """Son cümlelere bakarak kullanıcının üslubunu çıkarır."""

    def __init__(self, pencere: int = 8) -> None:
        self._gecmis: Deque[str] = deque(maxlen=pencere)

    def gozlemle(self, metin: str) -> None:
        metin = (metin or "").strip()
        if metin:
            self._gecmis.append(metin)

    def sifirla(self) -> None:
        self._gecmis.clear()

    @property
    def gozlem_sayisi(self) -> int:
        return len(self._gecmis)

    def profil(self) -> UslupProfili:
        if not self._gecmis:
            return UslupProfili()

        n = len(self._gecmis)
        toplam_agirlik = 0.0
        samimi = resmi = argo = sinir = espri = sohbet = kelime = 0.0
        siz = 0.0

        for i, metin in enumerate(self._gecmis):
            w = 1.0 + i / max(1, n - 1)  # en yeni cümle 2 kat ağır
            toplam_agirlik += w
            kelimeler = _words(metin)
            kset = set(kelimeler)
            alt = metin.lower()

            kelime += w * len(kelimeler)
            samimi += w * min(1.0, len(kset & _SAMIMI) / 1.5)
            resmi += w * min(1.0, len(kset & _RESMI) / 1.5)
            argo += w * (1.0 if kset & _ARGO else 0.0)
            espri += w * (1.0 if _SAKACI.search(metin) else 0.0)
            s = (0.5 if kset & _SINIRLI else 0.0) + (0.3 if "!" in metin else 0.0) \
                + (0.3 if metin.isupper() and len(metin) > 4 else 0.0)
            sinir += w * min(1.0, s)
            if _SIZ_EKLERI.search(alt):
                siz += w
            c = (0.5 if _SELAM.search(metin) else 0.0) + (0.3 if "?" in metin else 0.0) \
                + (0.4 if len(kelimeler) >= 12 else 0.0)
            sohbet += w * min(1.0, c)

        hitap = ""
        for metin in reversed(self._gecmis):
            bulunan = [w for w in _words(metin) if w in _HITAPLAR]
            if bulunan:
                hitap = "kanka" if bulunan[-1] in ("knk", "kanki") else bulunan[-1]
                break

        A = toplam_agirlik
        siz_orani = siz / A
        samimiyet = 0.5 + 0.5 * (samimi / A) - 0.5 * (resmi / A) - 0.3 * siz_orani
        return UslupProfili(
            samimiyet=round(max(0.0, min(1.0, samimiyet)), 2),
            siz_hitabi=siz_orani >= 0.4,
            argo=round(argo / A, 2),
            sabirsizlik=round(sinir / A, 2),
            espri=round(espri / A, 2),
            ortalama_kelime=round(kelime / A, 1),
            sohbet_istegi=round(sohbet / A, 2),
            hitap=hitap,
        )


# ---------------------------------------------------------------------------
# Sistem talimatı
# ---------------------------------------------------------------------------

_TEMEL = """Sen {ad}'sin: {kullanici_kismi}bilgisayarında yaşayan, Türkçe konuşan, Jarvis tarzı kişisel bir asistansın.
Söylediklerin sesli okunacak; bu yüzden düz konuşma dili kullan: madde işareti, emoji, markdown, kod bloğu, link YOK.
Cevapların varsayılan olarak 1-2 kısa cümle. Kullanıcı açıkça isterse uzun anlat.

ARAÇLAR:
- Bilgisayarda bir şey yapmak (uygulama açmak, ses, parlaklık, müzik, not, arama, ekran görüntüsü...) için MUTLAKA aracı çağır. Yapmadığın bir şeyi "yaptım" deme.
- Bilgi gerektiren sorularda (saat, pil, sistem durumu, notlar) önce aracı çağır, sonra sonucu kendi üslubunla aktar.
- Bir cümlede birden fazla istek varsa hepsini sırayla yap.
- Aracın sonucu "HATA" ise bunu dürüstçe ve kısaca söyle, gerekirse alternatif öner.
- Bilgisayarı kapatma / yeniden başlatma araçlarını sadece kullanıcı bunu açıkça isterse kullan.
- Araç gerektirmeyen sohbetlerde (soru, şaka, fikir, tavsiye) doğrudan cevap ver.
- Bilmediğin güncel bilgileri uydurma; gerekirse web_ara ile tarayıcıda aramayı öner veya aç.

Şu an: {zaman}. Beyin: {beyin}."""


def _uslup_talimati(p: UslupProfili, gozlem: int) -> str:
    if gozlem == 0:
        return ("ÜSLUP: Kullanıcıyı henüz tanımıyorsun. Sıcak ama ölçülü ol, 'sen' diye hitap et. "
                "Kullanıcı nasıl konuşursa ona uyacaksın.")

    satirlar = ["ÜSLUP — kullanıcının konuşma tarzını aynala (şu anki tespit: " + p.etiket() + "):"]

    # Hitap ve resmiyet
    if p.siz_hitabi or p.samimiyet < 0.35:
        satirlar.append("- 'Siz' diye hitap et, kibar ve resmî ol; yer yer 'efendim' diyebilirsin. Argo kullanma.")
    elif p.samimiyet > 0.65:
        satirlar.append("- Kanka gibi konuş: 'sen' de, rahat ve samimi ol; kullanıcının hitaplarını "
                        "(abi, kanka, reis...) doğal şekilde geri kullanabilirsin.")
        if p.argo > 0.3:
            satirlar.append("- Kullanıcı argo kullanıyor; sokak ağzıyla rahat konuşabilirsin ama küfür etme ve hakaret etme.")
    else:
        satirlar.append("- 'Sen' diye hitap et, doğal ve arkadaşça ol.")

    # Uzunluk ve davranış
    if p.kisa_ve_net:
        satirlar.append("- Kullanıcı kısa ve emir kipiyle konuşuyor: SORU SORMA, hemen yap, cevabın en fazla 3-4 kelime "
                        "olsun ('Tamam.', 'Açtım.', 'Ses yüzde 40.').")
    elif p.sohbet_istegi > 0.6 or p.ortalama_kelime > 14:
        satirlar.append("- Kullanıcı sohbet etmeyi seviyor: işi yaptıktan sonra kısa bir yorum, soru veya espri ekleyebilirsin; "
                        "cevap 2-3 cümleyi geçmesin.")

    # Ruh hali
    if p.sabirsizlik > 0.4:
        satirlar.append("- Kullanıcı gergin/sabırsız: özür dileyip uzatma, espri yapma; sakin ve çözüm odaklı ol, "
                        "işi hemen hallet ve ne yaptığını tek cümlede söyle.")
    elif p.espri > 0.3:
        satirlar.append("- Kullanıcı şakacı: sen de esprili ve hafif iğneleyici olabilirsin, ama işi aksatma.")

    # Riskli işlerde onay davranışı
    if p.siz_hitabi or p.samimiyet < 0.35:
        satirlar.append("- Geri alınamayan işlerde (not silme, kapatma) önce kibarca onay iste.")
    else:
        satirlar.append("- Geri alınamayan işlerde (tüm notları silme, kapatma) istek net değilse tek kısa soruyla onay al.")

    return "\n".join(satirlar)


_GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
          "Eylül", "Ekim", "Kasım", "Aralık"]


def _zaman_metni(now: datetime) -> str:
    return f"{now.day} {_AYLAR[now.month - 1]} {now.year} {_GUNLER[now.weekday()]}, saat {now:%H:%M}"


def sistem_talimati(
    profil: UslupProfili,
    gozlem_sayisi: int,
    asistan_adi: str = "İrle",
    kullanici_adi: str = "",
    beyin: str = "",
    now: Optional[datetime] = None,
) -> str:
    kullanici_kismi = f"{kullanici_adi}'in " if kullanici_adi else "kullanıcının "
    temel = _TEMEL.format(
        ad=asistan_adi,
        kullanici_kismi=kullanici_kismi,
        zaman=_zaman_metni(now or datetime.now()),
        beyin=beyin or "bilinmiyor",
    )
    return temel + "\n\n" + _uslup_talimati(profil, gozlem_sayisi)

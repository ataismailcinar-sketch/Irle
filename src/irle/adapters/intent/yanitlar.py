# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / INTENT / YANITLAR — Dil modeli olmadan üsluba uyan cevaplar
=============================================================================
Her cevap tipinin dört "ağzı" var:

    kisa   → acele eden / kısa konuşan / gergin kullanıcı:  "Kıstım."
    notr   → varsayılan:                                     "Sesi biraz kıstım."
    samimi → kanka / abi diyen kullanıcı:                    "Tamamdır abi, kıstım."
    resmi  → "siz" diyen, lütfen'li kullanıcı:               "Sesi kıstım efendim."

`{h}` → kullanıcının kendi hitabı (" abi", " kanka" ya da boş)
`{ad}`, `{n}`, `{detay}` → komuta göre doldurulur.

Aynı cevabı üst üste tekrar etmemek için son seçilen varyant hatırlanır.
=============================================================================
"""

from __future__ import annotations

import random
from typing import Any, Optional

from irle.adapters.brain.persona import UslupProfili


def agiz_sec(profil: UslupProfili) -> str:
    if profil.sabirsizlik > 0.4:
        return "kisa"
    # "Siz" diyen kullanıcı kısa konuşsa da resmî cevap bekler
    if profil.siz_hitabi or profil.samimiyet < 0.35:
        return "resmi"
    # "kanka/abi" diyen kullanıcı kısa konuşsa da samimi cevap bekler (samimi şablonlar zaten kısa)
    if profil.samimiyet > 0.65 or profil.hitap:
        return "samimi"
    if profil.kisa_ve_net:
        return "kisa"
    return "notr"


_S: dict[str, dict[str, list[str]]] = {
    # --- Genel ---------------------------------------------------------
    "onay": {
        "kisa": ["Tamam.", "Oldu.", "Hallettim."],
        "notr": ["Tamamdır.", "Hallettim.", "Oldu bu iş."],
        "samimi": ["Tamamdır{h}.", "Hallettim{h}.", "Bitti bile{h}."],
        "resmi": ["Tamamdır efendim.", "Hallettim efendim.", "İsteğiniz yerine getirildi."],
    },
    "hata": {
        "kisa": ["Olmadı: {detay}.", "Yapamadım: {detay}."],
        "notr": ["Bunu yapamadım, {detay}.", "Olmadı, {detay}."],
        "samimi": ["Olmadı{h}, {detay}.", "Bu sefer beceremedim{h}, {detay}."],
        "resmi": ["Maalesef yapamadım efendim, {detay}.", "Üzgünüm, işlem başarısız oldu: {detay}."],
    },
    "anlamadim": {
        "kisa": ["Anlamadım.", "Tekrar?"],
        "notr": ["Bunu anlayamadım, bir daha söyler misin?", "Tam anlayamadım, başka türlü söyler misin?"],
        "samimi": ["Bunu çözemedim{h}, bi daha söyle?", "Anlamadım{h}, başka türlü desene."],
        "resmi": ["Kusura bakmayın, anlayamadım. Tekrar eder misiniz?",
                  "Özür dilerim, ne istediğinizi tam anlayamadım."],
    },
    "dinliyorum": {
        "kisa": ["Efendim?", "Dinliyorum."],
        "notr": ["Dinliyorum.", "Buyur?"],
        "samimi": ["Söyle{h}?", "Buyur{h}?"],
        "resmi": ["Buyurun efendim?", "Sizi dinliyorum."],
    },
    "olumsuz": {   # "sesi kısma" gibi olumsuz cümle
        "kisa": ["Tamam, dokunmuyorum."],
        "notr": ["Tamam, öyle bırakıyorum."],
        "samimi": ["Tamam{h}, ellemiyorum."],
        "resmi": ["Anlaşıldı efendim, değişiklik yapmıyorum."],
    },
    "tekrar_yok": {
        "kisa": ["Tekrarlanacak bir şey yok."],
        "notr": ["Tekrar edebileceğim bir komut yok."],
        "samimi": ["Neyi tekrarlayayım{h}, daha bir şey yapmadık ki."],
        "resmi": ["Tekrarlayabileceğim bir işlem bulunmuyor efendim."],
    },

    # --- Ses / parlaklık / medya --------------------------------------
    "ses_artti": {
        "kisa": ["Açtım.", "Artırdım."],
        "notr": ["Sesi açtım.", "Ses artırıldı."],
        "samimi": ["Açtım{h}, coştur.", "Tamamdır{h}, ses yükseldi."],
        "resmi": ["Sesi artırdım efendim.", "Ses seviyesini yükselttim."],
    },
    "ses_azaldi": {
        "kisa": ["Kıstım.", "Azalttım."],
        "notr": ["Sesi kıstım.", "Ses azaltıldı."],
        "samimi": ["Kıstım{h}.", "Tamamdır{h}, kıstım."],
        "resmi": ["Sesi kıstım efendim.", "Ses seviyesini düşürdüm."],
    },
    "ses_seviye": {
        "kisa": ["Ses yüzde {n}.", "Yüzde {n}."],
        "notr": ["Sesi yüzde {n} yaptım.", "Ses yüzde {n} oldu."],
        "samimi": ["Ses yüzde {n}{h}.", "Yüzde {n} yaptım{h}."],
        "resmi": ["Ses seviyesini yüzde {n} olarak ayarladım efendim."],
    },
    "sustur": {
        "kisa": ["Sustu.", "Sessiz."],
        "notr": ["Sesi kapattım.", "Sessize aldım."],
        "samimi": ["Sus pus{h}.", "Sessize aldım{h}."],
        "resmi": ["Sesi kapattım efendim."],
    },
    "parlaklik_artti": {
        "kisa": ["Açtım.", "Parlaklık arttı."],
        "notr": ["Ekranı biraz aydınlattım.", "Parlaklığı artırdım."],
        "samimi": ["Aydınlattım{h}.", "Işıkları açtım{h}."],
        "resmi": ["Parlaklığı artırdım efendim."],
    },
    "parlaklik_azaldi": {
        "kisa": ["Kıstım.", "Parlaklık azaldı."],
        "notr": ["Ekranı biraz kararttım.", "Parlaklığı azalttım."],
        "samimi": ["Kıstım{h}, gözlerin dinlensin.", "Kararttım{h}."],
        "resmi": ["Parlaklığı azalttım efendim."],
    },
    "parlaklik_seviye": {
        "kisa": ["Parlaklık yüzde {n}."],
        "notr": ["Parlaklığı yüzde {n} yaptım."],
        "samimi": ["Parlaklık yüzde {n}{h}."],
        "resmi": ["Parlaklığı yüzde {n} olarak ayarladım efendim."],
    },
    "medya_durdu": {
        "kisa": ["Durdu.", "Durdurdum."],
        "notr": ["Durdurdum.", "Müzik durdu."],
        "samimi": ["Durdurdum{h}.", "Mola verdik{h}."],
        "resmi": ["Oynatmayı durdurdum efendim."],
    },
    "medya_oynuyor": {
        "kisa": ["Çalıyor.", "Devam."],
        "notr": ["Devam ediyor.", "Çalıyor."],
        "samimi": ["Çalıyor{h}, keyfine bak.", "Devam{h}."],
        "resmi": ["Oynatmaya devam ediyor efendim."],
    },
    "medya_sonraki": {
        "kisa": ["Geçtim.", "Sonraki."],
        "notr": ["Sonrakine geçtim.", "Şarkıyı geçtim."],
        "samimi": ["Geçtim{h}, bu daha iyidir.", "Sıradaki gelsin{h}."],
        "resmi": ["Bir sonrakine geçtim efendim."],
    },
    "medya_onceki": {
        "kisa": ["Geri aldım.", "Önceki."],
        "notr": ["Öncekine döndüm."],
        "samimi": ["Geri sardım{h}."],
        "resmi": ["Bir öncekine döndüm efendim."],
    },

    # --- Uygulama / sistem --------------------------------------------
    "uygulama_acildi": {
        "kisa": ["{ad} açılıyor.", "Açıyorum."],
        "notr": ["{ad} açılıyor.", "Tamam, {ad} geliyor."],
        "samimi": ["{ad} geliyor{h}.", "Açıyorum{h}, {ad} hazır birazdan."],
        "resmi": ["{ad} uygulamasını açıyorum efendim."],
    },
    "uygulama_kapandi": {
        "kisa": ["Kapattım.", "{ad} kapandı."],
        "notr": ["{ad} kapatıldı."],
        "samimi": ["Kapattım{h}, {ad} gitti."],
        "resmi": ["{ad} uygulamasını kapattım efendim."],
    },
    "not_alindi": {
        "kisa": ["Not aldım.", "Kaydettim."],
        "notr": ["Not aldım.", "Tamam, not ettim."],
        "samimi": ["Not ettim{h}, unutturmam.", "Yazdım{h}."],
        "resmi": ["Notunuzu kaydettim efendim."],
    },
    "ekran_goruntusu": {
        "kisa": ["Çektim.", "Ekran görüntüsü alındı."],
        "notr": ["Ekran görüntüsünü aldım."],
        "samimi": ["Çektim{h}, resim hazır."],
        "resmi": ["Ekran görüntüsünü kaydettim efendim."],
    },
    "kilitlendi": {
        "kisa": ["Kilitledim."],
        "notr": ["Ekranı kilitledim."],
        "samimi": ["Kilitledim{h}, görüşürüz."],
        "resmi": ["Ekranı kilitledim efendim."],
    },
    "web_arama": {
        "kisa": ["Arıyorum."],
        "notr": ["Tarayıcıda açıyorum."],
        "samimi": ["Bakıyorum{h}, tarayıcıda açtım."],
        "resmi": ["Arama sonuçlarını tarayıcıda açıyorum efendim."],
    },

    # --- Sohbet --------------------------------------------------------
    "selam": {
        "kisa": ["Selam.", "Buradayım."],
        "notr": ["Selam{ad_virgul}! Ne yapalım?", "Merhaba{ad_virgul}, buradayım."],
        "samimi": ["Selam{h}! Ne yapıyoruz bugün?", "Oo hoş geldin{h}! Emret."],
        "resmi": ["Merhaba efendim, size nasıl yardımcı olabilirim?", "Hoş geldiniz efendim."],
    },
    "nasilsin": {
        "kisa": ["İyiyim. Sen?", "Çalışıyorum, iyi."],
        "notr": ["İyiyim, işlemcim serin, belleğim taze. Sen nasılsın?"],
        "samimi": ["Bomba gibiyim{h}! Sende ne var ne yok?", "İyidir{h}, sen nasılsın?"],
        "resmi": ["Teşekkür ederim, gayet iyiyim. Siz nasılsınız efendim?"],
    },
    "tesekkur": {
        "kisa": ["Rica ederim.", "Ne demek."],
        "notr": ["Rica ederim.", "Ne demek, her zaman."],
        "samimi": ["Ne demek{h}, lafı mı olur.", "Eyvallah{h}."],
        "resmi": ["Rica ederim efendim.", "Ne demek, her zaman hizmetinizdeyim."],
    },
    "iltifat": {
        "kisa": ["Sağ ol."],
        "notr": ["Teşekkürler, elimden geleni yapıyorum."],
        "samimi": ["Utandırma{h}.", "Biliyorum{h}, ama yine de sağ ol."],
        "resmi": ["Çok naziksiniz efendim, teşekkür ederim."],
    },
    "hakaret": {
        "kisa": ["Tamam. Ne lazım?"],
        "notr": ["Kırıldım ama geçer. Neyi düzelteyim?"],
        "samimi": ["Sakin{h}, bi nefes al. Neyi düzeltelim?"],
        "resmi": ["Bir sorun varsa söyleyin, düzeltmeye çalışayım efendim."],
    },
    "kimsin": {
        "kisa": ["Ben {asistan}, asistanınım."],
        "notr": ["Ben {asistan}. Bilgisayarında yaşayan asistanın; uygulama açarım, ses ayarlarım, not alırım, hatırlatırım."],
        "samimi": ["Ben {asistan}{h}, bu bilgisayarın Jarvis'i. Sen söyle, ben yapayım."],
        "resmi": ["Ben {asistan}, kişisel asistanınızım efendim."],
    },
    "yetenek": {
        "kisa": ["Uygulama, ses, müzik, not, hatırlatma, ekran görüntüsü, arama."],
        "notr": ["Uygulama açıp kapatabilirim, sesi ve parlaklığı ayarlarım, müziği yönetirim, not alırım, "
                 "hatırlatıcı kurarım, ekran görüntüsü alırım, internette ararım."],
        "samimi": ["Neler neler{h}: uygulama açarım, sesi ayarlarım, şarkı geçerim, not alırım, "
                   "'beş dakika sonra çayı hatırlat' dersen hatırlatırım."],
        "resmi": ["Uygulamaları yönetebilir, ses ve parlaklığı ayarlayabilir, not alabilir ve hatırlatıcı "
                  "kurabilirim efendim."],
    },
    "saka": {
        "kisa": ["{saka}"],
        "notr": ["{saka}"],
        "samimi": ["{saka}"],
        "resmi": ["Müsaadenizle: {saka}"],
    },
    "veda": {
        "kisa": ["Görüşürüz.", "Hoşça kal."],
        "notr": ["Görüşürüz, ben buradayım.", "Hoşça kal!"],
        "samimi": ["Görüşürüz{h}, kendine iyi bak!", "Eyvallah{h}, ben buradayım."],
        "resmi": ["İyi günler efendim, ihtiyacınız olursa buradayım."],
    },
}

_SAKALAR = [
    "Bilgisayar neden üşümüş? Çünkü pencereleri açık kalmış.",
    "Programcı neden denize girmez? Çünkü dalgaları debug edemez.",
    "Temel bilgisayar almış. Fare çıkmış, kediyi de almış ki dengelesin.",
    "Bir yazılımcıya markete git, ekmek al, yumurta varsa on tane al demişler. On ekmekle dönmüş.",
    "Wi-fi şifresini sordum, 'büyük harfle' dediler. Hâlâ deniyorum: B-Ü-Y-Ü-K-H-A-R-F-L-E.",
    "Bugünkü hava durumu: yüzde yüz ihtimalle bilgisayarın başındasın.",
    "Klavye ile fare kavga etmiş. Fare kaçmış, klavye tuşlara basmış.",
    "Kodum ilk denemede çalıştı. Şaka şaka, bu bir şakaydı zaten.",
]


class YanitUretici:
    """Kategoriye ve kullanıcının üslubuna göre cevap metni üretir."""

    def __init__(self, asistan_adi: str = "İrle", kullanici_adi: str = "",
                 rng: Optional[random.Random] = None) -> None:
        self._asistan = asistan_adi
        self._kullanici = kullanici_adi
        self._rng = rng or random.Random()
        self._son: dict[str, str] = {}

    def uret(self, kategori: str, profil: UslupProfili, **alanlar: Any) -> str:
        sablonlar = _S.get(kategori) or _S["onay"]
        agiz = agiz_sec(profil)
        secenekler = sablonlar.get(agiz) or sablonlar["notr"]
        if len(secenekler) > 1 and self._son.get(kategori) in secenekler:
            secenekler = [s for s in secenekler if s != self._son[kategori]]
        sablon = self._rng.choice(secenekler)
        self._son[kategori] = sablon

        degerler = {
            "h": f" {profil.hitap}" if profil.hitap else "",
            "asistan": self._asistan,
            "ad_virgul": f" {self._kullanici}" if self._kullanici else "",
            "ad": "", "n": "", "detay": "",
            "saka": self._rng.choice(_SAKALAR),
        }
        degerler.update({k: v for k, v in alanlar.items() if v is not None})
        metin = sablon.format(**degerler)
        return metin[0].upper() + metin[1:] if metin else metin

    @staticmethod
    def kategoriler() -> list[str]:
        return list(_S)

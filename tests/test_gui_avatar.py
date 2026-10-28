# -*- coding: utf-8 -*-
"""TEST — Kıpçak maskeli avatar: yardımcı fonksiyonlar + (ekran varsa) durum makinesi."""

import pytest

from modules.gui_avatar import DURUM_RENK, _ayna, _icinde, _AVANTAY, _MASKE, karistir


def test_karistir():
    assert karistir("#000000", "#ffffff", 0) == "#000000"
    assert karistir("#000000", "#ffffff", 1) == "#ffffff"
    assert karistir("#000000", "#ffffff", 0.5) == "#808080"
    assert karistir("#000000", "#ffffff", 7) == "#ffffff"   # sınırlanır


def test_ayna():
    assert _ayna([100, 5, 150, 6]) == [220, 5, 170, 6]


def test_icinde():
    kare = [0, 0, 10, 0, 10, 10, 0, 10]
    assert _icinde(5, 5, kare) and not _icinde(15, 5, kare)
    assert _icinde(160, 200, _MASKE)              # yüzün ortası maskede
    assert _icinde(90, 200, _AVANTAY) and not _icinde(90, 200, _MASKE)   # yan: zincir zırh


@pytest.fixture
def avatar():
    tk = pytest.importorskip("tkinter")
    try:
        kok = tk.Tk()
    except tk.TclError:
        pytest.skip("ekran yok")
    kok.withdraw()
    from modules.gui_avatar import KipcakMaske
    a = KipcakMaske(kok, boyut=200)
    yield a
    a.durdur()
    kok.destroy()


def test_tum_durumlar_cizilir(avatar):
    for d in DURUM_RENK:
        avatar.durum(d)
        for _ in range(5):
            avatar._guncelle(0.04)
        assert avatar.mevcut_durum == d


def test_bilinmeyen_durum_yok_sayilir(avatar):
    avatar.durum("uçuyor")
    assert avatar.mevcut_durum == "dinliyor"


def test_hata_onceki_duruma_doner(avatar):
    avatar.durum("konusuyor")
    avatar.durum("hata")
    for _ in range(50):            # 2 sn
        avatar._guncelle(0.04)
    assert avatar.mevcut_durum == "konusuyor"


def test_takili_dusunme_dinlemeye_doner(avatar):
    avatar.durum("dusunuyor")
    for _ in range(27):
        avatar._guncelle(1.0)
    assert avatar.mevcut_durum == "dinliyor"


def test_agiz_gercek_ses_seviyesini_izler(avatar):
    class Sahte:
        deger = 0.0
        def seviye(self):
            return self.deger
    olcer = Sahte()
    avatar._olcer = olcer
    avatar.durum("konusuyor")
    for _ in range(10):
        avatar._guncelle(0.04)
    kapali = avatar._agiz_acik
    olcer.deger = 1.0
    for _ in range(10):
        avatar._guncelle(0.04)
    assert kapali < 0.05 and avatar._agiz_acik > 0.95
    y1, y2 = avatar.coords(avatar._agiz)[1::2]
    assert (y2 - y1) > 10 * avatar._s     # ağız gerçekten açıldı


def test_olcer_yoksa_ritimle_konusur(avatar):
    class Yok:
        def seviye(self):
            return None
    avatar._olcer = Yok()
    avatar.durum("konusuyor")
    degerler = []
    for _ in range(40):
        avatar._guncelle(0.04)
        degerler.append(avatar._agiz_acik)
    assert max(degerler) > 0.5 and min(degerler[5:]) > 0.1

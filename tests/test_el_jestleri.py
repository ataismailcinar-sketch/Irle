# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Elle fare kontrolü: jestler, tıklama/sürükleme, kaydırma, derinlik itmesi
=============================================================================
Kamera yok: tests/el_pozlari.py sentetik MediaPipe el noktaları üretir.
30 FPS kare akışı simüle edilir.
"""

from __future__ import annotations

import pytest

from tests.el_pozlari import acik, bozkurt, el, iki_parmak, yumruk
from irle.adapters.vision.el_jestleri import ElAyarlari, ElKontrolcu

DT = 1 / 30


def akis(k, kareler, t0=0.0):
    """kareler: poz listesi → (çıktılar, tüm olaylar)"""
    ciktilar, olaylar = [], []
    for i, poz in enumerate(kareler):
        c = k.isle(poz, t0 + i * DT)
        ciktilar.append(c)
        olaylar += [o[0] for o in c.olaylar]
    return ciktilar, olaylar


def sabit(poz, n):
    return [poz] * n


# ---------------------------------------------------------------------------
# İmleç
# ---------------------------------------------------------------------------

def test_imlec_ayna_ve_yon():
    k = ElKontrolcu()
    sol = k.isle(acik(merkez=(0.3, 0.5)), 0).imlec
    sag = k.isle(acik(merkez=(0.7, 0.5)), DT).imlec
    assert sol[0] > sag[0]           # görüntüde sola = kullanıcının sağı (ayna)
    ust = k.isle(acik(merkez=(0.5, 0.3)), 2 * DT).imlec
    alt = k.isle(acik(merkez=(0.5, 0.7)), 3 * DT).imlec
    assert ust[1] < alt[1]


def test_imlec_parmak_kivrilinca_kaymaz():
    k = ElKontrolcu()
    a = k.isle(acik(), 0).imlec
    b = k.isle(el(kapali=("yuzuk",)), DT).imlec     # parmak oynadı, avuç yerinde
    assert abs(a[0] - b[0]) < 0.02 and abs(a[1] - b[1]) < 0.02


def test_uzaktayken_kontrol_kutusu_kuculur():
    """Aynı görüntü kayması, el uzaktayken (küçük avuç) imleci daha çok oynatır."""
    yakin, uzak = ElKontrolcu(), ElKontrolcu()
    y1 = yakin.isle(acik(merkez=(0.45, 0.5), olcek=0.18), 0).imlec[0]
    y2 = yakin.isle(acik(merkez=(0.55, 0.5), olcek=0.18), DT).imlec[0]
    u1 = uzak.isle(acik(merkez=(0.45, 0.5), olcek=0.07), 0).imlec[0]
    u2 = uzak.isle(acik(merkez=(0.55, 0.5), olcek=0.07), DT).imlec[0]
    assert abs(u1 - u2) > abs(y1 - y2)


# ---------------------------------------------------------------------------
# Tıklama / sürükleme / sağ tık
# ---------------------------------------------------------------------------

def test_kisa_pinch_tek_tiklama():
    k = ElKontrolcu()
    _, olaylar = akis(k, sabit(acik(), 5) + sabit(el(pinch="isaret"), 4) + sabit(acik(), 5))
    assert olaylar == ["tikla"]


def test_tiklama_birlestirme_oncesi_konuma_yapilir():
    k = ElKontrolcu()
    ciktilar, _ = akis(k, sabit(acik(merkez=(0.5, 0.5)), 6))
    hedef = ciktilar[-1].imlec
    # birleştirirken el biraz kaydı (gerçekte de olur)
    kareler = [el(pinch="isaret", merkez=(0.5 + 0.004 * i, 0.5)) for i in range(4)] + sabit(acik(), 3)
    ciktilar2, _ = akis(k, kareler, t0=6 * DT)
    tik = [o for c in ciktilar2 for o in c.olaylar if o[0] == "tikla"][0]
    assert abs(tik[1][0] - hedef[0]) < 0.01 and abs(tik[1][1] - hedef[1]) < 0.01
    # birleştirme sürerken imleç kilitli
    assert all(c.imlec == ciktilar2[0].imlec for c in ciktilar2[:4])


def test_uzun_pinch_surukle_birak():
    k = ElKontrolcu()
    tutma = [el(pinch="isaret", merkez=(0.5 - 0.01 * i, 0.5)) for i in range(25)]   # 0.8 sn
    ciktilar, olaylar = akis(k, sabit(acik(), 5) + tutma + sabit(acik(), 4))
    assert olaylar == ["basili_tut", "birak"]
    surukleme = [c for c in ciktilar if c.jest == "surukleme"]
    assert surukleme and surukleme[-1].imlec[0] > surukleme[0].imlec[0]   # sürüklerken imleç hareket eder


def test_sag_tik():
    k = ElKontrolcu()
    _, olaylar = akis(k, sabit(acik(), 5) + sabit(el(pinch="orta"), 6) + sabit(acik(), 5))
    assert olaylar == ["sag_tikla"]


def test_sag_tik_tekrari_bekleme_ister():
    k = ElKontrolcu()
    dongu = sabit(el(pinch="orta"), 2) + sabit(acik(), 2)
    _, olaylar = akis(k, dongu * 3)        # 0.4 sn içinde 3 kez
    assert olaylar.count("sag_tikla") == 1


def test_el_kaybolursa_surukleme_birakilir():
    k = ElKontrolcu()
    _, olaylar = akis(k, sabit(acik(), 3) + sabit(el(pinch="isaret"), 20))
    assert olaylar == ["basili_tut"]
    assert [o[0] for o in k.isle(None, 10.0).olaylar] == ["birak"]


# ---------------------------------------------------------------------------
# Kaydırma, yumruk, bozkurt
# ---------------------------------------------------------------------------

def test_iki_parmak_kaydirma_yonu():
    k = ElKontrolcu()
    yukari = [iki_parmak(merkez=(0.5, 0.7 - 0.01 * i)) for i in range(15)]
    ciktilar, _ = akis(k, yukari)
    toplam = sum(o[1] for c in ciktilar for o in c.olaylar if o[0] == "kaydir")
    assert toplam > 0 and all(c.imlec is None for c in ciktilar)    # imleç durur
    k2 = ElKontrolcu()
    asagi = [iki_parmak(merkez=(0.5, 0.5 + 0.01 * i)) for i in range(15)]
    ciktilar2, _ = akis(k2, asagi)
    assert sum(o[1] for c in ciktilar2 for o in c.olaylar if o[0] == "kaydir") < 0


def test_hizli_imlec_hareketi_kaydirma_degildir():
    k = ElKontrolcu()
    _, olaylar = akis(k, [acik(merkez=(0.5, 0.8 - 0.05 * i)) for i in range(10)])
    assert "kaydir" not in olaylar


def test_yumruk_imleci_birakir():
    k = ElKontrolcu()
    ciktilar, olaylar = akis(k, sabit(acik(), 3) + [yumruk(merkez=(0.2 + 0.05 * i, 0.5)) for i in range(5)])
    assert all(c.imlec is None for c in ciktilar[3:]) and olaylar == []


def test_bozkurt_bir_saniye_mod_degistirir_bir_kez():
    k = ElKontrolcu()
    _, olaylar = akis(k, sabit(bozkurt(), 45))      # 1.5 sn
    assert olaylar == ["mod_degistir"]
    _, olaylar2 = akis(k, sabit(bozkurt(), 10), t0=2.0)   # kısa: tetiklemez
    assert olaylar2 == []


# ---------------------------------------------------------------------------
# Derinlik itmesi
# ---------------------------------------------------------------------------

def test_hizli_itme_tiklar_ve_onceki_konuma():
    k = ElKontrolcu()
    ciktilar, _ = akis(k, sabit(acik(merkez=(0.5, 0.5), olcek=0.12), 30))
    hedef = ciktilar[-1].imlec
    # 0.2 sn içinde %25 büyü (kameraya it), bu sırada el biraz aşağı kayar
    itme = [acik(merkez=(0.5, 0.5 + 0.01 * i), olcek=0.12 * (1 + 0.05 * i)) for i in range(1, 7)]
    geri = [acik(merkez=(0.5, 0.5), olcek=0.12)] * 10
    ciktilar2, olaylar = akis(k, itme + geri, t0=1.0)
    assert olaylar == ["tikla"]
    tik = [o for c in ciktilar2 for o in c.olaylar][0][1]
    assert abs(tik[1] - hedef[1]) < 0.02          # kayma öncesi konuma tıklandı
    assert max(c.derinlik for c in ciktilar2) > 1.15


def test_yavas_yaklasma_tiklamaz():
    k = ElKontrolcu()
    kareler = [acik(olcek=0.12 * (1 + 0.004 * i)) for i in range(150)]   # 5 sn'de %60 büyüme
    _, olaylar = akis(k, kareler)
    assert olaylar == []


def test_itme_kapatilabilir():
    k = ElKontrolcu(ElAyarlari(itme_aktif=False))
    akis(k, sabit(acik(olcek=0.12), 30))
    _, olaylar = akis(k, [acik(olcek=0.12 * (1 + 0.05 * i)) for i in range(1, 7)], t0=1.0)
    assert olaylar == []


def test_tekrarlanan_itme_beklemeli():
    k = ElKontrolcu()
    akis(k, sabit(acik(olcek=0.12), 30))
    itme = [acik(olcek=0.12 * (1 + 0.06 * i)) for i in range(1, 5)] + sabit(acik(olcek=0.12), 3)
    _, olaylar = akis(k, itme * 2, t0=1.0)          # iki itme 0.23 sn arayla
    assert olaylar.count("tikla") == 1


def test_eksik_nokta_el_yok_sayilir():
    k = ElKontrolcu()
    c = k.isle([(0.5, 0.5)] * 5, 0)
    assert c.jest == "yok" and c.imlec is None


def test_mediapipe_nesneleri_de_kabul_edilir():
    from types import SimpleNamespace
    k = ElKontrolcu()
    poz = [SimpleNamespace(x=x, y=y, z=0.0) for x, y in acik()]
    assert k.isle(poz, 0).jest == "imlec"


def test_yumruk_kavrama_imlec_kaldigi_yerden_devam_eder():
    k = ElKontrolcu()
    ciktilar, _ = akis(k, sabit(acik(merkez=(0.5, 0.5)), 3))
    donan = ciktilar[-1].imlec
    akis(k, [yumruk(merkez=(0.5 + 0.04 * i, 0.5)) for i in range(5)], t0=3 * DT)   # eli sola taşı
    c = k.isle(acik(merkez=(0.7, 0.5)), 9 * DT)
    assert abs(c.imlec[0] - donan[0]) < 0.01            # zıplamadı
    c2 = k.isle(acik(merkez=(0.65, 0.5)), 10 * DT)
    assert c2.imlec[0] > c.imlec[0]                       # hareket normal devam ediyor

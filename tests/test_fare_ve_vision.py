# -*- coding: utf-8 -*-
"""TEST — Fare yöneticisi (sıralı işçi) ve görüntü modülünün el olayı üretimi."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from tests.el_pozlari import acik, bozkurt, el


class SahteFare:
    def __init__(self):
        self.kayit = []

    def size(self):
        return (1000, 500)

    def moveTo(self, x, y, _pause=False):
        self.kayit.append(("move", round(x), round(y)))

    def click(self):
        self.kayit.append(("click",))

    def rightClick(self):
        self.kayit.append(("right",))

    def mouseDown(self):
        self.kayit.append(("down",))

    def mouseUp(self):
        self.kayit.append(("up",))

    def scroll(self, n):
        self.kayit.append(("scroll", n))


class SahteBus:
    def __init__(self):
        self.yayinlanan = []

    def subscribe(self, *a):
        pass

    def publish(self, ad, data=None):
        self.yayinlanan.append((ad, data))


@pytest.fixture
def fare_yon(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyautogui", types.ModuleType("pyautogui"))
    sys.modules.pop("modules.aksiyon.fare_yoneticisi", None)
    from modules.aksiyon import fare_yoneticisi as fy
    fare = SahteFare()
    return fy, fy.FareYoneticisi(SahteBus(), fare=fare), fare


def test_sadece_son_konum_uygulanir(fare_yon):
    fy, m, fare = fare_yon
    for x in (0.1, 0.2, 0.3):
        m._vision_el_kontrol({"data": {"x": x, "y": 0.5, "olaylar": []}})
    m._bir_tur()
    hareketler = [k for k in fare.kayit if k[0] == "move"]
    assert len(hareketler) == 1 and hareketler[0][1] == 300     # 0.3 * 1000


def test_olaylar_sirayla_ve_kilit_konumunda(fare_yon):
    fy, m, fare = fare_yon
    m._vision_el_kontrol({"data": {"x": 0.9, "y": 0.9, "olaylar": [["tikla", (0.2, 0.4)]]}})
    m._vision_el_kontrol({"data": {"x": None, "y": None, "olaylar": [["sag_tikla", None], ["kaydir", -2]]}})
    m._bir_tur()
    assert fare.kayit[:4] == [("move", 200, 200), ("click",), ("right",), ("scroll", -2 * fy._CENTIK)]
    assert fare.kayit[-1][0] == "move"          # sonra imleç en son hedefe


def test_surukleme_ve_birak(fare_yon):
    fy, m, fare = fare_yon
    m._vision_el_kontrol({"data": {"x": 0.5, "y": 0.5, "olaylar": [["basili_tut", (0.5, 0.5)]]}})
    m._bir_tur()
    m._vision_el_kontrol({"data": {"x": 0.6, "y": 0.5, "olaylar": [["birak", None]]}})
    m._bir_tur()
    adlar = [k[0] for k in fare.kayit]
    assert adlar.index("down") < adlar.index("up")


def test_kapanirken_basili_tus_kalmaz(fare_yon):
    fy, m, fare = fare_yon
    m._uygula("basili_tut", None)
    m.durdur()
    assert ("up",) in fare.kayit


# ---------------------------------------------------------------------------
# Görüntü modülü: el noktalarından olay üretimi (kamera/MediaPipe çalıştırmadan)
# ---------------------------------------------------------------------------

@pytest.fixture
def vision():
    pytest.importorskip("cv2")
    pytest.importorskip("mediapipe")
    from modules.vision_modulu import VisionModulu
    bus = SahteBus()
    v = VisionModulu(bus)
    v.pencere_acik = False
    return v, bus


def noktalar(poz):
    return [SimpleNamespace(x=x, y=y, z=0.0) for x, y in poz]


def test_vision_imlec_ve_tiklama_olayi(vision):
    v, bus = vision
    t = 0.0
    for poz in [acik()] * 5 + [el(pinch="isaret")] * 3 + [acik()] * 3:
        v._el_isle(noktalar(poz), t)
        t += 1 / 30
    el_olaylari = [d for ad, d in bus.yayinlanan if ad == "el_hareketi_algilandi"]
    assert el_olaylari and el_olaylari[0]["x"] is not None
    tum = [o[0] for d in el_olaylari for o in d["olaylar"]]
    assert tum == ["tikla"]


def test_vision_bozkurt_beklemeye_alir_ve_olay_kesilir(vision):
    v, bus = vision
    t = 0.0
    for _ in range(30):                          # 1 sn bozkurt
        v._el_isle(noktalar(bozkurt()), t)
        t += 1 / 30
    assert v.aktif_mod == "beklemede"
    assert any(ad == "tts_konuş" for ad, _ in bus.yayinlanan)
    bus.yayinlanan.clear()
    for _ in range(5):
        v._el_isle(noktalar(acik()), t)
        t += 1 / 30
    assert not [1 for ad, _ in bus.yayinlanan if ad == "el_hareketi_algilandi"]


def test_vision_rehber_cizimi_hata_vermez(vision):
    import numpy as np
    v, bus = vision
    v._el_isle(noktalar(acik()), 0.0)
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    v._rehber_ciz(img)
    assert img.sum() > 0

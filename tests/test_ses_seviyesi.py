# -*- coding: utf-8 -*-
"""TEST — Dudak senkronu için ses şiddeti eğrisi."""

import math

import numpy as np
import pytest

from irle.infra.ses_seviyesi import SesSeviyesi


def _ses(hz=16000):
    """0.5 sn yüksek ton + 0.5 sn sessizlik + 0.5 sn kısık ton (int16)."""
    t = np.arange(int(hz * 0.5)) / hz
    yuksek = (np.sin(2 * math.pi * 220 * t) * 20000).astype(np.int16)
    sessiz = np.zeros(int(hz * 0.5), dtype=np.int16)
    kisik = (np.sin(2 * math.pi * 220 * t) * 5000).astype(np.int16)
    return np.concatenate([yuksek, sessiz, kisik])


def test_egri_sekli():
    egri = SesSeviyesi.egri_hesapla(_ses(), 16000, 40)
    assert len(egri) == 60                       # 1.5 sn * 40 Hz
    assert all(0 <= v <= 1 for v in egri)
    yuksek, sessiz, kisik = egri[2:18], egri[22:38], egri[42:58]
    assert min(yuksek) > 0.9
    assert max(sessiz) == 0.0
    assert 0.3 < sum(kisik) / len(kisik) < max(yuksek)


def test_bos_ve_sessiz():
    assert SesSeviyesi.egri_hesapla([], 16000) == []
    assert set(SesSeviyesi.egri_hesapla(np.zeros(1600), 16000)) == {0.0}


def test_zamanlama():
    t = [100.0]
    s = SesSeviyesi(pencere_hz=40, gecikme_saniye=0.1, clock=lambda: t[0])
    assert s.seviye() is None                     # hiç ses yok
    s.baslat(_ses(), 16000)
    assert s.seviye() == 0.0                      # ses kartı gecikmesi
    t[0] = 100.1 + 0.2
    assert s.seviye() > 0.9                       # yüksek bölüm
    t[0] = 100.1 + 0.75
    assert s.seviye() == 0.0                      # sessiz bölüm
    t[0] = 100.1 + 1.6
    assert s.seviye() == 0.0                      # cümle arası boşluk: kapalı ağız
    t[0] = 100.1 + 2.5
    assert s.seviye() is None                     # konuşma bitti → avatar ritme döner


def test_float_ses_de_olur():
    egri = SesSeviyesi.egri_hesapla(np.ones(1600, dtype=np.float32) * 0.5, 16000, 40)
    assert egri and min(egri) > 0.9

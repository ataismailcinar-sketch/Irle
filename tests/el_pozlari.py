# -*- coding: utf-8 -*-
"""Testler için sentetik MediaPipe el noktaları (21 nokta, normalleştirilmiş görüntü koordinatı)."""

# Yerel el koordinatları: bilek (0,0), parmaklar yukarı (negatif y). Birim ≈ avuç boyu.
_ACIK = {
    0: (0.0, 0.0),
    1: (-0.35, -0.25), 2: (-0.55, -0.45), 3: (-0.70, -0.65), 4: (-0.80, -0.85),
    5: (-0.25, -1.00), 6: (-0.28, -1.40), 7: (-0.30, -1.65), 8: (-0.32, -1.90),
    9: (0.00, -1.05), 10: (0.00, -1.50), 11: (0.00, -1.78), 12: (0.00, -2.00),
    13: (0.22, -1.00), 14: (0.25, -1.40), 15: (0.27, -1.65), 16: (0.28, -1.85),
    17: (0.42, -0.90), 18: (0.48, -1.20), 19: (0.52, -1.40), 20: (0.55, -1.58),
}
_PARMAK = {"isaret": (5, 6, 7, 8), "orta": (9, 10, 11, 12), "yuzuk": (13, 14, 15, 16), "serce": (17, 18, 19, 20)}


def el(kapali=(), pinch=None, merkez=(0.5, 0.6), olcek=0.13):
    """kapali: kıvrık parmaklar; pinch: 'isaret' ya da 'orta' (başparmak o parmağın ucuna)."""
    n = dict(_ACIK)
    for ad in kapali:
        mcp, pip, dip, uc = _PARMAK[ad]
        mx, my = n[mcp]
        n[dip] = (mx, my - 0.25)
        n[uc] = (mx, my + 0.05)          # uç avuca döndü (bileğe PIP'ten yakın)
    if pinch:
        ux, uy = n[_PARMAK[pinch][3]]
        n[4] = (ux - 0.02, uy + 0.03)
    # avuç ortası (0,5,9,13,17 ortalaması) merkeze gelsin
    ox = sum(n[i][0] for i in (0, 5, 9, 13, 17)) / 5
    oy = sum(n[i][1] for i in (0, 5, 9, 13, 17)) / 5
    return [(merkez[0] + (n[i][0] - ox) * olcek, merkez[1] + (n[i][1] - oy) * olcek) for i in range(21)]


def acik(**k):
    return el(**k)


def yumruk(**k):
    return el(kapali=("isaret", "orta", "yuzuk", "serce"), **k)


def iki_parmak(**k):
    return el(kapali=("yuzuk", "serce"), **k)


def bozkurt(**k):
    return el(kapali=("orta", "yuzuk"), **k)

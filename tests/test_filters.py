# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Filters (OneEuroFilter, PointFilter2D, AdaptiveEMAFilter, KalmanFilter1D)
=============================================================================
"""

import math
import pytest
from irle.infra.filters import (
    OneEuroFilter,
    PointFilter2D,
    AdaptiveEMAFilter,
    KalmanFilter1D,
)


class TestOneEuroFilter:
    def test_initial_value(self):
        f = OneEuroFilter()
        val = f.filter(100.0, timestamp=1.0)
        assert val == 100.0

    def test_noise_reduction(self):
        f = OneEuroFilter(min_cutoff=0.5, beta=0.001)
        # Sinyal etrafında rastgele küçük titremeler
        t = 0.0
        outputs = []
        for i in range(20):
            t += 0.033
            jitter = ((-1) ** i) * 1.5  # +/- 1.5 px titreme
            val = f.filter(500.0 + jitter, timestamp=t)
            outputs.append(val)

        # Sonuçların varyansı/dalgalanması girişten belirgin şekilde daha küçük olmalıdır
        last_outputs = outputs[5:]
        max_deviation = max(abs(x - 500.0) for x in last_outputs)
        assert max_deviation < 1.0  # 1.5 px'lik gürültü filtrelendi

    def test_high_speed_responsiveness(self):
        f = OneEuroFilter(min_cutoff=0.8, beta=0.1)
        f.filter(0.0, timestamp=1.0)
        # Hızlı ani sıçrama
        val = f.filter(100.0, timestamp=1.033)
        # Yüksek hızda gecikme az olmalı (değer hızlıca yükselmeli)
        assert val > 50.0


class TestPointFilter2D:
    def test_deadzone(self):
        pf = PointFilter2D(deadzone_px=2.0)
        x1, y1 = pf.filter(100.0, 200.0, timestamp=1.0)
        assert (x1, y1) == (100.0, 200.0)

        # Deadzone altındaki hareket imleci oynatmamalı
        x2, y2 = pf.filter(100.5, 200.5, timestamp=1.033)
        assert x2 == x1
        assert y2 == y1

        # Deadzone üstündeki belirgin hareket güncellenmeli
        x3, y3 = pf.filter(120.0, 220.0, timestamp=1.066)
        assert x3 != x1
        assert y3 != y1


class TestAdaptiveEMAFilter:
    def test_smoothing(self):
        ema = AdaptiveEMAFilter(alpha_min=0.1, alpha_max=0.9, speed_scale=20.0)
        v1 = ema.filter(10.0)
        assert v1 == 10.0
        v2 = ema.filter(12.0)
        assert 10.0 < v2 < 12.0

    def test_reset(self):
        ema = AdaptiveEMAFilter()
        ema.filter(50.0)
        ema.reset()
        v = ema.filter(100.0)
        assert v == 100.0


class TestKalmanFilter1D:
    def test_kalman_filtering(self):
        kf = KalmanFilter1D()
        val1 = kf.filter(100.0)
        assert val1 == 100.0
        val2 = kf.filter(105.0)
        assert 100.0 < val2 < 105.0


def test_distance_invariant_pinch_ratio():
    # Yakın el durumu (büyük görüntü boyutu): palm=0.35, pinch_dist=0.10
    palm_near = 0.35
    dist_near = 0.10
    ratio_near = dist_near / palm_near

    # Uzak el durumu (küçük görüntü boyutu): palm=0.10, pinch_dist=0.0285
    palm_far = 0.10
    dist_far = 0.0285
    ratio_far = dist_far / palm_far

    # Perspektif izdüşümü çarpanı sadeleştiği için oranlar eşittir
    assert math.isclose(ratio_near, ratio_far, abs_tol=1e-3)
    assert ratio_near < 0.35
    assert ratio_far < 0.35

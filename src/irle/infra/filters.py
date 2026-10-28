# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / FILTERS — Sinyal ve İmleç Yumuşatma Filtreleri
=============================================================================
Gürültülü sensör ve kamera verilerini (MediaPipe landmarkları, fare koordinatları)
pürüzsüzleştirmek ve titremeyi (jitter) önlemek için filtreleme sınıfları.

İçerik:
  1. OneEuroFilter (1€ Filter - Casiez et al., CHI 2012):
     İnsan-bilgisayar etkileşiminde endüstri standardı. Düşük hızlarda
     titremeyi sıfırlarken, yüksek hızlarda sıfır gecikme (lag) sunar.
  2. PointFilter2D: (X, Y) koordinat çifti için 1€ filtresi ve deadzone.
  3. AdaptiveEMAFilter (Hız uyarlamalı Üstel Hareketli Ortalama)
  4. KalmanFilter1D (1 Boyutlu Kalman Filtresi)
=============================================================================
"""

from __future__ import annotations

import math
import time
from typing import Optional, Tuple


class OneEuroFilter:
    """
    1€ Filtresi (One Euro Filter)
    Düşük hızda titremeyi (jitter), yüksek hızda gecikmeyi (lag) önler.
    
    Parametreler:
        min_cutoff (float): Düşük hızlardaki minimum kesme frekansı (Hz).
                            Değer küçüldükçe el dururken titreme daha çok yok olur (örn. 0.5 - 1.0).
        beta (float): Hıza bağlı frekans artış katsayısı.
                      Değer büyüdükçe hızlı hareketlerde gecikme azalır (örn. 0.005 - 0.05).
        d_cutoff (float): Türevin kesme frekansı (Hz) (varsayılan: 1.0).
    """

    def __init__(
        self,
        min_cutoff: float = 0.8,
        beta: float = 0.015,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)

        self._x_prev: Optional[float] = None
        self._dx_prev: float = 0.0
        self._t_prev: Optional[float] = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, timestamp: Optional[float] = None) -> float:
        t = timestamp if timestamp is not None else time.perf_counter()

        if self._x_prev is None:
            self._x_prev = x
            self._dx_prev = 0.0
            self._t_prev = t
            return x

        dt = t - (self._t_prev if self._t_prev is not None else t)
        if dt <= 1e-6:
            dt = 1e-4  # Sıfıra bölme ve zamansal kararsızlığı önle

        # 1. Hızı (türevi) hesapla ve filtrele
        dx = (x - self._x_prev) / dt
        edx = self._dx_prev + self._alpha(self.d_cutoff, dt) * (dx - self._dx_prev)

        # 2. Hıza bağlı dinamik kesme frekansı
        cutoff = self.min_cutoff + self.beta * abs(edx)

        # 3. Asıl sinyali filtrele
        filtered_x = self._x_prev + self._alpha(cutoff, dt) * (x - self._x_prev)

        self._x_prev = filtered_x
        self._dx_prev = edx
        self._t_prev = t

        return filtered_x

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None


class PointFilter2D:
    """
    (X, Y) koordinat çiftini eşzamanlı pürüzsüzleştiren OneEuroFilter yöneticisi.
    Ölü bölge (deadzone) eşiği ile mikroskobik titremeleri tamamen keser.
    """

    def __init__(
        self,
        min_cutoff: float = 0.8,
        beta: float = 0.02,
        deadzone_px: float = 1.5,
    ) -> None:
        self.filter_x = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.filter_y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.deadzone_px = deadzone_px
        self._last_out_x: Optional[float] = None
        self._last_out_y: Optional[float] = None

    def filter(self, x: float, y: float, timestamp: Optional[float] = None) -> Tuple[float, float]:
        t = timestamp if timestamp is not None else time.perf_counter()
        smooth_x = self.filter_x.filter(x, t)
        smooth_y = self.filter_y.filter(y, t)

        if self._last_out_x is None or self._last_out_y is None:
            self._last_out_x = smooth_x
            self._last_out_y = smooth_y
            return smooth_x, smooth_y

        dist = math.hypot(smooth_x - self._last_out_x, smooth_y - self._last_out_y)
        if dist < self.deadzone_px:
            # Titreme eşiğinin altında; imleci kıpırdatma
            return self._last_out_x, self._last_out_y

        self._last_out_x = smooth_x
        self._last_out_y = smooth_y
        return smooth_x, smooth_y

    def reset(self) -> None:
        self.filter_x.reset()
        self.filter_y.reset()
        self._last_out_x = None
        self._last_out_y = None


class AdaptiveEMAFilter:
    """
    Hıza duyarlı adaptif Üstel Hareketli Ortalama (EMA).
    Hız arttıkça alpha büyür (az gecikme), hız azaldıkça alpha küçülür (yüksek yumuşatma).
    """

    def __init__(
        self,
        alpha_min: float = 0.15,
        alpha_max: float = 0.85,
        speed_scale: float = 40.0,
    ) -> None:
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.speed_scale = speed_scale
        self._prev_val: Optional[float] = None

    def filter(self, val: float) -> float:
        if self._prev_val is None:
            self._prev_val = val
            return val

        diff = abs(val - self._prev_val)
        # Hıza bağlı dinamik alpha katsayısı
        ratio = min(1.0, diff / max(self.speed_scale, 1e-4))
        alpha = self.alpha_min + (self.alpha_max - self.alpha_min) * ratio

        smoothed = self._prev_val + alpha * (val - self._prev_val)
        self._prev_val = smoothed
        return smoothed

    def reset(self) -> None:
        self._prev_val = None


class KalmanFilter1D:
    """
    1 Boyutlu Kalman Filtresi (sabit konum + gürültü modeli).
    """

    def __init__(
        self,
        process_variance: float = 1e-4,
        measurement_variance: float = 1e-2,
    ) -> None:
        self.q = process_variance
        self.r = measurement_variance
        self.x = 0.0  # Durum tahmini
        self.p = 1.0  # Hata kovaryansı
        self.k = 0.0  # Kalman kazancı
        self._initialized = False

    def filter(self, measurement: float) -> float:
        if not self._initialized:
            self.x = measurement
            self.p = 1.0
            self._initialized = True
            return measurement

        # Tahmin adımı
        self.p = self.p + self.q

        # Güncelleme adımı
        self.k = self.p / (self.p + self.r)
        self.x = self.x + self.k * (measurement - self.x)
        self.p = (1.0 - self.k) * self.p

        return self.x

    def reset(self) -> None:
        self._initialized = False
        self.x = 0.0
        self.p = 1.0

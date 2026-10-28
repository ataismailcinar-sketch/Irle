# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / SES SEVİYESİ — Dudak senkronu için çalan sesin şiddet eğrisi
=============================================================================
TTS bir ses parçasını çalmadan hemen önce `baslat(ses, örnekleme_hızı)` çağırır.
Ses 25 ms'lik pencerelere bölünüp her pencerenin şiddeti (RMS) 0-1 arasına
ölçeklenir. Avatar her karede `seviye()` ile o anki değeri okur.

Olay otobüsü kullanılmaz (saniyede 40 olay gereksiz yük olurdu): aynı süreçteki
tek bir paylaşımlı nesne yeter. Thread-safe.
=============================================================================
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Sequence


class SesSeviyesi:

    def __init__(self, pencere_hz: int = 40, gecikme_saniye: float = 0.08,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._hz = pencere_hz
        self._gecikme = gecikme_saniye   # ses kartının çalmaya başlama gecikmesi
        self._clock = clock
        self._lock = threading.Lock()
        self._egri: list[float] = []
        self._t0 = 0.0
        self._bosluk = 0.5   # eğri bittikten sonra "sessiz" sayılacak süre

    @staticmethod
    def egri_hesapla(ses: Sequence[float] | object, sample_rate: int, pencere_hz: int = 40) -> list[float]:
        """int16/float ses dizisinden 0-1 arası şiddet eğrisi."""
        import numpy as np
        a = np.asarray(ses, dtype=np.float32).reshape(-1)
        if a.size == 0 or sample_rate <= 0:
            return []
        if np.abs(a).max() > 1.5:          # int16 ölçeği
            a = a / 32768.0
        boy = max(1, int(sample_rate / pencere_hz))
        n = int(np.ceil(a.size / boy))
        a = np.pad(a, (0, n * boy - a.size))
        rms = np.sqrt((a.reshape(n, boy) ** 2).mean(axis=1))
        tavan = float(np.percentile(rms, 95)) if n > 3 else float(rms.max())
        if tavan < 1e-4:
            return [0.0] * n
        seviye = np.clip(rms / tavan, 0.0, 1.0)
        seviye[seviye < 0.08] = 0.0         # sessizlik kapısı
        return [float(x) for x in np.sqrt(seviye)]   # kulağa daha doğal

    def baslat(self, ses: object, sample_rate: int) -> None:
        egri = self.egri_hesapla(ses, sample_rate, self._hz)
        with self._lock:
            self._egri = egri
            self._t0 = self._clock() + self._gecikme

    def durdur(self) -> None:
        """Çalma bitti. Eğri bir süre daha tutulur ki cümle arası boşlukta ağız kapalı dursun."""

    def kes(self) -> None:
        """Konuşma yarıda kesildi: eğriyi hemen sil (ağız anında kapansın)."""
        with self._lock:
            self._egri = []

    def seviye(self) -> Optional[float]:
        """Şu an çalan sesin şiddeti; çalan ses yoksa None."""
        with self._lock:
            if not self._egri:
                return None
            gecen = self._clock() - self._t0
            if gecen < 0:
                return 0.0
            i = int(gecen * self._hz)
            if i >= len(self._egri):
                # Cümleler arası kısa boşluk: ağız kapalı kalsın (sahte ritme geçmesin)
                return 0.0 if gecen < len(self._egri) / self._hz + self._bosluk else None
            return self._egri[i]


# Süreç genelinde tek ölçer (TTS yazar, avatar okur)
seviye_olcer = SesSeviyesi()

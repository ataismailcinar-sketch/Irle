# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / ECHO GUARD — İrle konuşurken mikrofonu sağır yap
=============================================================================
Mikrofon sürekli açık olduğu için İrle'nin hoparlörden çıkan sesi tekrar
mikrofona girip "kullanıcı komutu" sanılıyordu. Dil modeli varken bu,
asistanın kendi cevabına cevap verdiği sonsuz bir döngüye dönüşebilir.

TTS başlarken `started()`, bitince `finished()` çağrılır. `active` True
olduğu sürece ses modülü gelen blokları çöpe atar. Konuşma bittikten sonra
kısa bir "kuyruk" süresi (yankı/oda reverb'i için) daha sağır kalınır.
TTS bir hata yüzünden `finished` göndermezse `max_hold` sonra kilit kendini açar.
=============================================================================
"""

from __future__ import annotations

import threading
import time
from typing import Callable


class EchoGuard:

    def __init__(self, tail_seconds: float = 0.6, max_hold_seconds: float = 30.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._tail = tail_seconds
        self._max_hold = max_hold_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._pending = 0
        self._last_change = 0.0
        self._quiet_until = 0.0

    def started(self, text: str = "x") -> None:
        if not (text or "").strip():
            return
        with self._lock:
            self._pending += 1
            self._last_change = self._clock()

    def finished(self) -> None:
        with self._lock:
            self._pending = max(0, self._pending - 1)
            now = self._clock()
            self._last_change = now
            self._quiet_until = now + self._tail

    @property
    def active(self) -> bool:
        with self._lock:
            now = self._clock()
            if self._pending > 0:
                if now - self._last_change > self._max_hold:
                    self._pending = 0  # takılı kalmış kilit
                    return False
                return True
            return now < self._quiet_until

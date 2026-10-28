# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / SPEECH CAPTURE — Handler Konuşmalarını Geçici Olarak Yakalama
=============================================================================
Handler'lar (pil, saat, notlar...) sonucu doğrudan TtsRequested ile
seslendiriyor. Beyin bir aracı çalıştırdığında bu konuşmanın sese gitmesini
istemeyiz: sonucu model alıp kullanıcının üslubuyla kendisi söyleyecek.

Kullanım:
    with capture_speech() as captured:
        command_bus.dispatch(GetBatteryStatus())
    captured.texts   # ["Pil yüzdesi 80, şarjda."]

Yakalama thread-local'dır: sadece aynı thread'de yapılan publish'leri etkiler.
=============================================================================
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Optional

_local = threading.local()


@dataclass
class CapturedSpeech:
    texts: list[str] = field(default_factory=list)
    notifications: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@contextmanager
def capture_speech() -> Iterator[CapturedSpeech]:
    previous: Optional[CapturedSpeech] = getattr(_local, "active", None)
    buf = CapturedSpeech()
    _local.active = buf
    try:
        yield buf
    finally:
        _local.active = previous


def active_capture() -> Optional[CapturedSpeech]:
    return getattr(_local, "active", None)

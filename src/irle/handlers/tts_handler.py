# -*- coding: utf-8 -*-
"""
Konuşma (Speak) komutunu TtsRequested event'ine dönüştürür.
"""

from __future__ import annotations

import logging
from typing import Any

from irle.domain.commands import Speak
from irle.domain.events import TtsRequested

logger = logging.getLogger("irle.handlers.tts")


class TtsHandler:
    """Speak komutunu TtsRequested event'i olarak yayınlar."""

    def __init__(self, event_bus: Any) -> None:
        self._bus = event_bus

    def handle_speak(self, cmd: Speak) -> None:
        logger.info("Konuşma isteği: %r", cmd.text)
        try:
            self._bus.publish(TtsRequested(text=cmd.text))
        except Exception as exc:
            logger.error("TTS event yayınlanamadı: %s", exc)

# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Speech & STT Adapters (Google, Whisper, Fallback, SesModulu)
=============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch

from irle.adapters.speech.stt_adapter import (
    BaseSTTProvider,
    GoogleSTTProvider,
    WhisperSTTProvider,
    FallbackSTTProvider,
)
from irle.domain.events import SpeechRecognized
from irle.infra.event_bus import TypedEventBus
from modules.ses_modulu import SesModulu


class DummyProvider(BaseSTTProvider):
    def __init__(self, result=None, should_raise=False):
        self.result = result
        self.should_raise = should_raise
        self.called = False

    def transcribe(self, audio_bytes, sample_rate=16000, sample_width=2, language="tr-TR"):
        self.called = True
        if self.should_raise:
            raise RuntimeError("Primary failed")
        return self.result


def test_fallback_provider_uses_primary_when_successful():
    primary = DummyProvider(result="merhaba irle")
    fallback = DummyProvider(result="fallback sonuc")
    stt = FallbackSTTProvider(primary=primary, fallback=fallback)

    res = stt.transcribe(b"1234")
    assert res == "merhaba irle"
    assert primary.called is True
    assert fallback.called is False


def test_fallback_provider_switches_on_error():
    primary = DummyProvider(should_raise=True)
    fallback = DummyProvider(result="kurtarilan metin")
    stt = FallbackSTTProvider(primary=primary, fallback=fallback)

    res = stt.transcribe(b"1234")
    assert res == "kurtarilan metin"
    assert primary.called is True
    assert fallback.called is True


def test_ses_modulu_asenkron_cozumle():
    bus = TypedEventBus()
    events = []
    bus.subscribe(SpeechRecognized, lambda e: events.append(e))

    dummy_stt = DummyProvider(result="bilgisayarı kapat")
    ses_modulu = SesModulu(bus, stt_provider=dummy_stt)

    # Doğrudan asenkron çözümleme çağrısı
    ses_modulu._asenkron_cozumle(b"fake_audio_bytes")

    assert len(events) == 1
    assert events[0].text == "bilgisayarı kapat"

    ses_modulu.durdur()
    bus.shutdown()

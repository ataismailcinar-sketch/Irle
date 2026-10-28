# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Integration (Ses -> Intent -> Command -> Handler)
=============================================================================
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from irle.infra.event_bus import TypedEventBus
from irle.app.command_registry import build_command_bus
from irle.app.settings import Settings
from modules.intent_modulu import IntentModulu
from irle.domain.events import SpeechRecognized, TtsRequested, CommandCompleted


@pytest.fixture
def system_setup():
    bus = TypedEventBus()
    settings = Settings()
    cmd_bus = build_command_bus(bus, settings)
    intent = IntentModulu(bus, cmd_bus)
    intent.baslat()
    
    yield bus, cmd_bus, intent
    
    intent.durdur()
    bus.shutdown()


def test_integration_merhaba(system_setup):
    bus, cmd_bus, intent = system_setup
    tts_events = []
    completed_events = []
    
    bus.subscribe(TtsRequested, lambda e: tts_events.append(e))
    bus.subscribe(CommandCompleted, lambda e: completed_events.append(e))
    
    # Act
    bus.publish(SpeechRecognized(text="merhaba"))
    
    # Wait for async thread pool processing
    time.sleep(0.2)
    
    # Assert
    # Selam artık üsluba uygun hazır cevaplardan biriyle karşılanıyor
    assert len(tts_events) == 1
    assert tts_events[0].text

    assert [e.command_type for e in completed_events] == ["Speak"]


def test_integration_bilgisayari_kapat(system_setup):
    bus, cmd_bus, intent = system_setup
    completed_events = []
    
    bus.subscribe(CommandCompleted, lambda e: completed_events.append(e))
    
    with patch("subprocess.run") as mock_run:
        # Act
        bus.publish(SpeechRecognized(text="bilgisayarı kapat"))
        
        # Wait
        time.sleep(0.2)
        
        # Assert
        mock_run.assert_called_once()
        # Komut + İrle'nin sesli cevabı (Speak)
        assert [e.command_type for e in completed_events] == ["ShutdownComputer", "Speak"]


def test_integration_uygulama_ac(system_setup):
    bus, cmd_bus, intent = system_setup
    completed_events = []
    
    bus.subscribe(CommandCompleted, lambda e: completed_events.append(e))
    
    with patch("irle.handlers.app_handler._baslat") as mock_baslat:
        # Act
        bus.publish(SpeechRecognized(text="not defteri aç"))

        # Wait
        time.sleep(0.2)

        # Assert — kabuk kullanmadan, doğru exe ile
        mock_baslat.assert_called_once_with("notepad.exe")
        assert [e.command_type for e in completed_events] == ["OpenApplication", "Speak"]

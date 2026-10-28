# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — TypedEventBus (src/irle/infra/event_bus.py)
=============================================================================
Subscribe/publish semantics, thread pool davranışı, compat shim ve
shutdown davranışını test eder.
"""

import time
import threading
import pytest

from irle.infra.event_bus import TypedEventBus
from irle.domain.events import (
    Event,
    SpeechRecognized,
    TtsRequested,
    CommandCompleted,
    Notification,
)


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def wait_for(condition_fn, timeout: float = 2.0, interval: float = 0.05) -> bool:
    """Koşul doğru olana kadar bekle. Timeout aşılırsa False döner."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


# ---------------------------------------------------------------------------
# Temel Subscribe / Publish
# ---------------------------------------------------------------------------

class TestTemelPublishSubscribe:

    def test_handler_cagirilir(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe(SpeechRecognized, lambda e: received.append(e))
        bus.publish(SpeechRecognized(text="merhaba"))
        assert wait_for(lambda: len(received) == 1)
        assert received[0].text == "merhaba"
        bus.shutdown()

    def test_birden_fazla_handler(self):
        bus = TypedEventBus()
        log1, log2 = [], []
        bus.subscribe(SpeechRecognized, lambda e: log1.append(e.text))
        bus.subscribe(SpeechRecognized, lambda e: log2.append(e.text))
        bus.publish(SpeechRecognized(text="test"))
        assert wait_for(lambda: len(log1) == 1 and len(log2) == 1)
        bus.shutdown()

    def test_yanlis_tipi_almaz(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe(TtsRequested, lambda e: received.append(e))
        bus.publish(SpeechRecognized(text="konuş"))  # farklı tip
        time.sleep(0.15)
        assert len(received) == 0  # TtsRequested bekleniyordu
        bus.shutdown()

    def test_birden_fazla_event_tipi(self):
        bus = TypedEventBus()
        speech_log, tts_log = [], []
        bus.subscribe(SpeechRecognized, lambda e: speech_log.append(e))
        bus.subscribe(TtsRequested, lambda e: tts_log.append(e))
        bus.publish(SpeechRecognized(text="s1"))
        bus.publish(TtsRequested(text="t1"))
        assert wait_for(lambda: len(speech_log) == 1 and len(tts_log) == 1)
        bus.shutdown()


# ---------------------------------------------------------------------------
# Kalıtım (isinstance) Testi
# ---------------------------------------------------------------------------

class TestKalitim:

    def test_taban_sinif_abonesi_alt_sinifi_alir(self):
        """Event taban sınıfına abone olan handler tüm event'leri almalı."""
        bus = TypedEventBus()
        received = []
        bus.subscribe(Event, lambda e: received.append(type(e).__name__))
        bus.publish(SpeechRecognized(text="x"))
        bus.publish(TtsRequested(text="y"))
        assert wait_for(lambda: len(received) >= 2)
        assert "SpeechRecognized" in received
        assert "TtsRequested" in received
        bus.shutdown()


# ---------------------------------------------------------------------------
# String Compat API
# ---------------------------------------------------------------------------

class TestStringCompat:

    def test_subscribe_str_publish_str(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe_str("ses_algilandi", lambda m: received.append(m["data"]["metin"]))
        bus.publish_str("ses_algilandi", {"metin": "test"})
        assert wait_for(lambda: len(received) == 1)
        assert received[0] == "test"
        bus.shutdown()

    def test_publish_str_bos_data(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe_str("bos_event", lambda m: received.append(m))
        bus.publish_str("bos_event")  # data=None
        assert wait_for(lambda: len(received) == 1)
        assert received[0]["data"] == {}
        bus.shutdown()

    def test_typed_publish_tetikler_legacy(self):
        """Typed event yayınlayınca LEGACY_NAME ile kayıtlı string handler da çağrılmalı."""
        bus = TypedEventBus()
        legacy_received = []
        bus.subscribe_str("ses_algilandi", lambda m: legacy_received.append(m))
        bus.publish(SpeechRecognized(text="köprü testi"))
        assert wait_for(lambda: len(legacy_received) == 1)
        data = legacy_received[0]["data"]
        assert data.get("metin") == "köprü testi"
        bus.shutdown()

    def test_legacy_subscribe_and_publish_with_strings(self):
        """String tabanlı subscribe/publish desteği test edilir."""
        bus = TypedEventBus()
        received = []
        bus.subscribe("uygulama_ac", lambda m: received.append(m))
        bus.publish("uygulama_ac", {"uygulama": "notepad"})
        assert wait_for(lambda: len(received) == 1)
        assert received[0]["data"]["uygulama"] == "notepad"
        bus.shutdown()


# ---------------------------------------------------------------------------
# Hata İzolasyonu
# ---------------------------------------------------------------------------

class TestHataIzolasyonu:

    def test_hata_veren_handler_diger_handleri_bloklamaz(self):
        bus = TypedEventBus()
        good_log = []

        def bad_handler(e):
            raise ValueError("Kasıtlı hata!")

        bus.subscribe(SpeechRecognized, bad_handler)
        bus.subscribe(SpeechRecognized, lambda e: good_log.append(e.text))
        bus.publish(SpeechRecognized(text="hata testi"))
        assert wait_for(lambda: len(good_log) == 1)
        assert good_log[0] == "hata testi"
        bus.shutdown()


# ---------------------------------------------------------------------------
# Thread Güvenliği
# ---------------------------------------------------------------------------

class TestThreadGuvenlik:

    def test_ayni_anda_cok_publish(self):
        bus = TypedEventBus(max_workers=8)
        received = []
        lock = threading.Lock()

        def handler(e):
            with lock:
                received.append(e.text)

        bus.subscribe(SpeechRecognized, handler)

        threads = [
            threading.Thread(target=bus.publish, args=(SpeechRecognized(text=f"msg{i}"),))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert wait_for(lambda: len(received) == 20, timeout=5.0)
        bus.shutdown()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

class TestShutdown:

    def test_shutdown_sonrasi_publish_calismiyor(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe(SpeechRecognized, lambda e: received.append(e))
        bus.shutdown()
        bus.publish(SpeechRecognized(text="bu alınmamalı"))
        time.sleep(0.2)
        assert len(received) == 0

    def test_shutdown_alias(self):
        """Alias metodlar çalışıyor mu?"""
        bus = TypedEventBus()
        received = []
        bus.subscribe_legacy("eski_event", lambda m: received.append(m))
        bus.publish_legacy("eski_event", {"key": "val"})
        assert wait_for(lambda: len(received) == 1)
        bus.shutdown()


# ---------------------------------------------------------------------------
# Çoklu Publish
# ---------------------------------------------------------------------------

class TestCokluPublish:

    def test_ayni_event_birden_fazla_kez(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe(Notification, lambda e: received.append(e.message))
        for i in range(5):
            bus.publish(Notification(title="test", message=f"msg{i}"))
        assert wait_for(lambda: len(received) == 5)
        bus.shutdown()

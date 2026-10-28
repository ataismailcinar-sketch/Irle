# -*- coding: utf-8 -*-
"""
=============================================================================
INFRA / EVENT BUS — Geliştirilmiş Pub/Sub Mesaj Otobüsü
=============================================================================
Eski `core/event_bus.py` yerine geçer. İki önemli iyileştirme:

1. **Bounded thread pool**: Her publish için `threading.Thread().start()`
   yerine `ThreadPoolExecutor(max_workers)` kullanılır. Sınırsız thread
   patlaması önlenir.

2. **Typed event API**: Typed `Event` nesneleri ile çalışan `subscribe` /
   `publish` yanında, eski string tabanlı API için geriye dönük uyumlu
   `subscribe_str` / `publish_str` metodları bulunur.

Kullanım (Yeni API):
    from src.irle.infra.event_bus import TypedEventBus
    from src.irle.domain.events import SpeechRecognized

    bus = TypedEventBus()
    bus.subscribe(SpeechRecognized, lambda e: print(e.text))
    bus.publish(SpeechRecognized(text="merhaba"))
    bus.shutdown()

Kullanım (Eski Uyumluluk — string tabanlı):
    bus.subscribe_str("ses_algilandi", handler_fn)
    bus.publish_str("ses_algilandi", {"metin": "merhaba"})
=============================================================================
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Type, TypeVar

from irle.domain.events import CommandFailed, Event, Notification, TtsRequested
from irle.infra.speech_capture import active_capture

logger = logging.getLogger("irle.infra.event_bus")

# TypeVar: handler'ın alacağı event tipini kısıtlar
E = TypeVar("E", bound=Event)

# Handler tipleri
EventHandler = Callable[[Event], None]
StringHandler = Callable[[dict], None]


class TypedEventBus:
    """
    Irle'nin typed + string uyumlu merkezi mesaj otobüsü.

    Attributes:
        max_workers: Thread pool büyüklüğü. Her publish çağrısı en fazla
                     bu kadar paralel handler çalıştırabilir.
    """

    def __init__(self, max_workers: int = 4) -> None:
        # Typed subscribers: Event sınıfı → handler listesi
        self._typed_subs: dict[type, list[EventHandler]] = defaultdict(list)

        # String subscribers: event adı → handler listesi (eski API)
        self._str_subs: dict[str, list[StringHandler]] = defaultdict(list)

        # Thread-pool — sınırsız thread açılmasını önler
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="irle-bus",
        )

        # Abone listelerini korumak için lock
        self._lock = threading.Lock()

        self._shutdown_flag = False

    # ------------------------------------------------------------------
    # Typed API
    # ------------------------------------------------------------------

    def subscribe(self, event_type: type[E] | str, handler: Callable) -> None:
        """Belirli bir Event tipine veya legacy string adına abone ol.

        Args:
            event_type: Dinlenecek event sınıfı (örn: SpeechRecognized) veya string adı.
            handler:    Event örneği veya dict alacak çağrılabilir.
        """
        if isinstance(event_type, str):
            self.subscribe_str(event_type, handler)
            return

        with self._lock:
            self._typed_subs[event_type].append(handler)  # type: ignore[arg-type]
        logger.debug(
            "Typed abone kaydedildi → %s | handler: %s",
            event_type.__name__,
            getattr(handler, "__qualname__", repr(handler)),
        )

    def publish(self, event: Event | str, data: dict | None = None) -> None:
        """Bir Event örneği veya legacy string event yayınla.

        Handler'lar thread pool'da çalıştırılır. Yayıncı bloklanmaz.
        Event tipine tam eşleşme + kalıtım (isinstance) ile abone bulunur.

        Ek olarak, event'in `LEGACY_NAME` alanı dolu ise string handler'lar
        da otomatik çağrılır (geriye dönük uyumluluk).
        """
        if isinstance(event, str):
            self.publish_str(event, data)
            return

        if self._shutdown_flag:
            logger.warning("Kapatılmış bus üzerinde publish: %s", type(event).__name__)
            return

        # Beyin bir araç çalıştırıyorsa handler'ın konuşmasını yakala, sese gönderme
        capture = active_capture()
        if capture is not None:
            if isinstance(event, TtsRequested):
                capture.texts.append(event.text)
                return
            if isinstance(event, Notification):
                capture.notifications.append(event.message)
            elif isinstance(event, CommandFailed):
                capture.errors.append(event.error)

        # Typed handlers — kalıtım dahil
        handlers: list[EventHandler] = []
        with self._lock:
            for etype, hlist in self._typed_subs.items():
                if isinstance(event, etype):
                    handlers.extend(hlist)

        for h in handlers:
            self._executor.submit(self._safe_call_typed, h, event)

        # Eski string API köprüsü
        legacy_name = getattr(event.__class__, "LEGACY_NAME", None)
        if isinstance(legacy_name, str) and legacy_name:
            # event alanlarını eski dict formatına çevir
            if hasattr(event, "to_legacy_dict"):
                legacy_data = event.to_legacy_dict()
            else:
                legacy_data = {
                    k: v
                    for k, v in event.__dict__.items()
                    if k not in ("timestamp",)
                }
            self.publish_str(legacy_name, legacy_data)

    # ------------------------------------------------------------------
    # String API (Geriye Dönük Uyumluluk)
    # ------------------------------------------------------------------

    def subscribe_str(self, event_name: str, handler: StringHandler) -> None:
        """Eski string tabanlı event adına abone ol.

        Args:
            event_name: Olay adı (örn: "ses_algilandi").
            handler:    `{"event": ..., "data": {...}}` sözlüğü alacak callable.
        """
        with self._lock:
            self._str_subs[event_name].append(handler)
        logger.debug(
            "String abone kaydedildi → '%s' | handler: %s",
            event_name,
            getattr(handler, "__qualname__", repr(handler)),
        )

    def publish_str(self, event_name: str, data: dict | None = None) -> None:
        """Eski string tabanlı event yayınla.

        Args:
            event_name: Olay adı.
            data:       Event verisi.
        """
        if self._shutdown_flag:
            return

        if data is None:
            data = {}

        mesaj = {"event": event_name, "data": data}
        logger.debug("String event yayınlandı → %s", mesaj)

        with self._lock:
            handlers = list(self._str_subs.get(event_name, []))

        if not handlers:
            logger.debug("'%s' için abone bulunamadı.", event_name)
            return

        for h in handlers:
            self._executor.submit(self._safe_call_str, h, mesaj)

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------

    def _safe_call_typed(self, handler: EventHandler, event: Event) -> None:
        try:
            handler(event)
        except Exception:
            logger.exception(
                "Typed handler hatası — handler: %s | event: %s",
                getattr(handler, "__qualname__", repr(handler)),
                type(event).__name__,
            )

    def _safe_call_str(self, handler: StringHandler, mesaj: dict) -> None:
        try:
            handler(mesaj)
        except Exception:
            logger.exception(
                "String handler hatası — handler: %s | event: %s",
                getattr(handler, "__qualname__", repr(handler)),
                mesaj.get("event"),
            )

    # ------------------------------------------------------------------
    # Yaşam Döngüsü
    # ------------------------------------------------------------------

    def shutdown(self, wait: bool = True) -> None:
        """Thread pool'u düzgünce kapat.

        Args:
            wait: True ise tüm handler'ların bitmesi beklenir.
        """
        self._shutdown_flag = True
        self._executor.shutdown(wait=wait)
        logger.info("EventBus kapatıldı.")

    # ------------------------------------------------------------------
    # Eski API Uyumluluk Alias'ları
    # ------------------------------------------------------------------

    def subscribe_legacy(self, event_name: str, handler: StringHandler) -> None:
        """Alias: subscribe_str ile aynı. Eski kod tabanı için."""
        self.subscribe_str(event_name, handler)

    def publish_legacy(self, event_name: str, data: dict | None = None) -> None:
        """Alias: publish_str ile aynı. Eski kod tabanı için."""
        self.publish_str(event_name, data)

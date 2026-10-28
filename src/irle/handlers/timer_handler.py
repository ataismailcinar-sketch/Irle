# -*- coding: utf-8 -*-
"""
Zamanlayıcı ve hatırlatıcılar.

    "5 dakika sonra müziği durdur"      → 5 dk sonra MediaControl çalışır
    "10 dakika sonra çayı hatırlat"     → komut değilse hatırlatma olarak söylenir
    "zamanlayıcıyı iptal et"            → hepsi iptal

Not: ScheduleCommand ve CancelAllTimers kural motorunda vardı ama hiçbir
handler'a bağlı değildi; komutlar sessizce yok sayılıyordu.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable, Optional

from irle.domain.commands import CancelAllTimers, ScheduleCommand, Speak
from irle.domain.events import Notification, TtsRequested

logger = logging.getLogger("irle.handlers.timer")

_HATIRLAT = re.compile(r"\b(bana\s+)?(hatırlat\w*|söyle\w*|haber\s+ver\w*|uyar\w*)\b", re.IGNORECASE)
_MAX_GECIKME = 24 * 3600


def _sure_metni(saniye: int) -> str:
    if saniye % 3600 == 0:
        return f"{saniye // 3600} saat"
    if saniye % 60 == 0:
        return f"{saniye // 60} dakika"
    if saniye > 60:
        return f"{saniye // 60} dakika {saniye % 60} saniye"
    return f"{saniye} saniye"


class TimerHandler:

    def __init__(self, event_bus: Any, dispatch: Callable[[Any], Any],
                 parse: Callable[[str], Any], timer_factory: Any = threading.Timer) -> None:
        self._bus = event_bus
        self._dispatch = dispatch
        self._parse = parse
        self._timer_factory = timer_factory
        self._timers: list[Any] = []
        self._lock = threading.Lock()

    @property
    def active_count(self) -> int:
        with self._lock:
            self._timers = [t for t in self._timers if getattr(t, "is_alive", lambda: True)()]
            return len(self._timers)

    def handle_schedule(self, cmd: ScheduleCommand) -> dict:
        delay = int(cmd.delay_seconds)
        if delay <= 0 or delay > _MAX_GECIKME:
            raise ValueError(f"Geçersiz süre: {delay} saniye")
        metin = cmd.inner_command_text.strip()
        if not metin:
            raise ValueError("Zamanlanacak bir şey söylenmedi")

        inner = None if _HATIRLAT.search(metin) else self._parse(metin)
        if inner is None or isinstance(inner, (ScheduleCommand, CancelAllTimers)):
            hatirlatma = _HATIRLAT.sub("", metin).strip(" ,.") or metin
            inner = Speak(text=f"Hatırlatma: {hatirlatma}")
            tur = "hatırlatma"
        else:
            tur = type(inner).__name__

        timer = self._timer_factory(delay, self._fire, args=(inner,))
        timer.daemon = True
        with self._lock:
            self._timers.append(timer)
        timer.start()

        sure = _sure_metni(delay)
        logger.info("⏰ %s sonra: %s (%s)", sure, metin, tur)
        self._speak(f"Tamam, {sure} sonra " + ("hatırlatacağım." if tur == "hatırlatma" else "yapacağım."))
        return {"sure_saniye": delay, "tur": tur}

    def handle_cancel_all(self, cmd: CancelAllTimers) -> dict:
        with self._lock:
            timers, self._timers = self._timers, []
        for t in timers:
            try:
                t.cancel()
            except Exception:
                pass
        n = len(timers)
        self._speak("Tüm zamanlayıcılar iptal edildi." if n else "İptal edilecek zamanlayıcı yok.")
        return {"iptal_edilen": n}

    # ------------------------------------------------------------------

    def _fire(self, inner: Any) -> None:
        logger.info("⏰ Zamanlayıcı tetiklendi → %s", type(inner).__name__)
        try:
            self._dispatch(inner)
        except Exception as exc:
            logger.error("Zamanlanmış komut çalıştırılamadı: %s", exc)
        try:
            self._bus.publish(Notification(title="Zamanlayıcı", message=str(getattr(inner, "text", "")) or type(inner).__name__))
        except Exception:
            pass

    def _speak(self, text: str) -> None:
        try:
            self._bus.publish(TtsRequested(text=text))
        except Exception:
            pass

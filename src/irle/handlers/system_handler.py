# -*- coding: utf-8 -*-
"""
Sistem gücü komutları: kapatma, yeniden başlatma, kilitleme.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from irle.domain.commands import (
    CancelShutdown,
    LockComputer,
    RestartComputer,
    ShutdownComputer,
)
from irle.domain.events import Notification

logger = logging.getLogger("irle.handlers.system")

# Windows ctypes — opsiyonel (test ortamında olmayabilir)
try:
    import ctypes
    _CTYPES_OK = True
except ImportError:
    _CTYPES_OK = False


class SystemHandler:
    """ShutdownComputer, RestartComputer, LockComputer, CancelShutdown işler."""

    def __init__(self, event_bus: Any) -> None:
        self._bus = event_bus

    # ------------------------------------------------------------------

    def handle_shutdown(self, cmd: ShutdownComputer) -> None:
        delay = cmd.delay_seconds
        logger.info("Bilgisayar kapatılıyor (%d saniye sonra)...", delay)
        try:
            subprocess.run(
                ["shutdown", "/s", "/t", str(delay)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._notify(f"Bilgisayar {delay} saniye sonra kapanacak.")
        except Exception as exc:
            logger.error("Kapatma komutu başarısız: %s", exc)

    def handle_restart(self, cmd: RestartComputer) -> None:
        delay = cmd.delay_seconds
        logger.info("Bilgisayar yeniden başlatılıyor (%d saniye sonra)...", delay)
        try:
            subprocess.run(
                ["shutdown", "/r", "/t", str(delay)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._notify(f"Bilgisayar {delay} saniye sonra yeniden başlatılacak.")
        except Exception as exc:
            logger.error("Yeniden başlatma komutu başarısız: %s", exc)

    def handle_lock(self, cmd: LockComputer) -> None:
        logger.info("Ekran kilitleniyor...")
        try:
            if _CTYPES_OK:
                ctypes.windll.user32.LockWorkStation()
            else:
                subprocess.run(
                    ["rundll32.exe", "user32.dll,LockWorkStation"],
                    check=False,
                )
        except Exception as exc:
            logger.error("Kilitleme başarısız: %s", exc)

    def handle_cancel_shutdown(self, cmd: CancelShutdown) -> None:
        logger.info("Kapatma/yeniden başlatma iptal ediliyor...")
        try:
            subprocess.run(
                ["shutdown", "/a"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._notify("Kapatma işlemi iptal edildi.")
        except Exception as exc:
            logger.error("İptal komutu başarısız: %s", exc)

    # ------------------------------------------------------------------

    def _notify(self, message: str) -> None:
        try:
            self._bus.publish(Notification(title="Sistem", message=message))
        except Exception:
            pass

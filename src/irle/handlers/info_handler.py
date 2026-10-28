# -*- coding: utf-8 -*-
"""
Sistem bilgi sorguları: pil, CPU/RAM, disk, ağ, saat.
"""

from __future__ import annotations

import logging
import socket
import subprocess
from datetime import datetime
from typing import Any

from irle.domain.events import Notification, TtsRequested
from irle.domain.queries import (
    GetBatteryStatus,
    GetCurrentTime,
    GetNetworkStatus,
    GetSystemInfo,
)

logger = logging.getLogger("irle.handlers.info")

_AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
_GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False
    logger.warning("psutil kurulu değil — sistem bilgisi sınırlı.")


class InfoHandler:
    """Sistem durumu sorgularını işler, sonuçları TTS ile bildirir."""

    def __init__(self, event_bus: Any) -> None:
        self._bus = event_bus

    # ------------------------------------------------------------------

    def handle_battery(self, query: GetBatteryStatus) -> dict:
        if not _PSUTIL_OK:
            self._speak("Pil bilgisi alınamıyor, psutil kurulu değil.")
            return {}
        try:
            batt = psutil.sensors_battery()
            if batt is None:
                self._speak("Bu cihazda pil algılanamadı.")
                return {}
            percent = int(batt.percent)
            plugged = "şarjda" if batt.power_plugged else "şarjda değil"
            msg = f"Pil yüzdesi {percent}, {plugged}."
            logger.info(msg)
            self._speak(msg)
            return {"percent": percent, "plugged": batt.power_plugged}
        except Exception as exc:
            logger.error("Pil bilgisi alınamadı: %s", exc)
            return {}

    def handle_system_info(self, query: GetSystemInfo) -> dict:
        if not _PSUTIL_OK:
            self._speak("Sistem bilgisi alınamıyor, psutil kurulu değil.")
            return {}

        parts = []
        result: dict = {}
        topics = query.topics or ("cpu", "ram", "disk")

        try:
            if "cpu" in topics:
                cpu = psutil.cpu_percent(interval=0.5)
                parts.append(f"İşlemci kullanımı %{cpu:.0f}")
                result["cpu"] = cpu

            if "ram" in topics:
                mem = psutil.virtual_memory()
                ram_pct = mem.percent
                parts.append(f"RAM %{ram_pct:.0f}")
                result["ram"] = ram_pct

            if "disk" in topics:
                disk = psutil.disk_usage("/")
                free_gb = disk.free / (1024 ** 3)
                parts.append(f"Disk boş alan {free_gb:.1f} GB")
                result["disk_free_gb"] = free_gb

            if "gpu" in topics:
                parts.append("GPU bilgisi şu an desteklenmiyor.")

            msg = ", ".join(parts) + "." if parts else "Bilgi alınamadı."
            self._speak(msg)
        except Exception as exc:
            logger.error("Sistem bilgisi alınamadı: %s", exc)

        return result

    def handle_network(self, query: GetNetworkStatus) -> dict:
        result: dict = {}
        parts = []

        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            parts.append(f"IP adresiniz {ip}")
            result["ip"] = ip
        except Exception:
            parts.append("IP adresi alınamadı")

        if query.include_ping:
            try:
                out = subprocess.run(
                    ["ping", "-n", "1", "8.8.8.8"],
                    capture_output=True, text=True, timeout=5
                )
                if "ms" in out.stdout:
                    # "Ortalama = Xms" satırını bul
                    for line in out.stdout.splitlines():
                        if "Ortalama" in line or "Average" in line or "ms" in line.lower():
                            parts.append(f"Gecikme: {line.strip()}")
                            break
                else:
                    parts.append("Ping başarısız")
            except Exception as exc:
                parts.append(f"Ping hatası: {exc}")

        msg = ", ".join(parts) + "."
        self._speak(msg)
        return result

    def handle_time(self, query: GetCurrentTime) -> dict:
        now = datetime.now()
        saat = now.strftime("%H:%M")
        # %B Windows'ta sistem diline göre İngilizce ("October") çıkabiliyordu
        tarih = f"{now.day} {_AYLAR[now.month - 1]} {now.year} {_GUNLER[now.weekday()]}"
        msg = f"Saat {saat}, tarih {tarih}."
        logger.info(msg)
        self._speak(msg)
        return {"time": saat, "date": tarih}

    # ------------------------------------------------------------------

    def _speak(self, text: str) -> None:
        try:
            self._bus.publish(TtsRequested(text=text))
        except Exception:
            pass

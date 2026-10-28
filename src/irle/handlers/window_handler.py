# -*- coding: utf-8 -*-
"""
Pencere ve süreç yönetimi: öne getir, tam ekran, küçült, kapat, zorla sonlandır.

Not: WindowControl ve KillProcess kural motorunda vardı ama hiçbir handler'a
bağlı değildi; komutlar sessizce yok sayılıyordu.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from irle.domain.commands import KillProcess, WindowControl
from irle.domain.events import TtsRequested

logger = logging.getLogger("irle.handlers.window")

try:
    import pywinctl
    _PYWINCTL_OK = True
except Exception:
    _PYWINCTL_OK = False

try:
    import psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False

# Bunlar öldürülürse Windows çöker / oturum kapanır
_KORUNAN = {
    "system", "idle", "smss", "csrss", "wininit", "winlogon", "services", "lsass",
    "svchost", "dwm", "fontdrvhost", "registry", "memcompression", "lsaiso",
    "sihost", "ctfmon", "conhost", "runtimebroker", "searchhost", "startmenuexperiencehost",
}

_EYLEMLER = {
    "focus": ("activate", "öne getirildi"),
    "maximize": ("maximize", "tam ekran yapıldı"),
    "minimize": ("minimize", "küçültüldü"),
    "close": ("close", "kapatıldı"),
}


def _sade(ad: str) -> str:
    ad = ad.lower().strip()
    return ad[:-4] if ad.endswith(".exe") else ad


class WindowHandler:

    def __init__(self, event_bus: Any, windows_api: Any = None, process_api: Any = None) -> None:
        self._bus = event_bus
        self._win = windows_api if windows_api is not None else (pywinctl if _PYWINCTL_OK else None)
        self._ps = process_api if process_api is not None else (psutil if _PSUTIL_OK else None)

    def handle_window(self, cmd: WindowControl) -> dict:
        if cmd.action not in _EYLEMLER:
            raise ValueError(f"Bilinmeyen pencere işlemi: {cmd.action}")
        if self._win is None:
            raise RuntimeError("pywinctl kurulu değil, pencere kontrolü yapılamıyor")

        ad = cmd.app_name.strip()
        hedef = ad.lower()
        pencereler = [w for w in self._win.getAllWindows()
                      if hedef in (getattr(w, "title", "") or "").lower()]
        if not pencereler:
            self._speak(f"{ad} penceresini bulamadım.")
            return {"bulunan": 0}

        metot, fiil = _EYLEMLER[cmd.action]
        hedefler = pencereler if cmd.action == "close" else pencereler[:1]
        for w in hedefler:
            getattr(w, metot)()
        self._speak(f"{ad} {fiil}.")
        return {"bulunan": len(pencereler), "islem": cmd.action}

    def handle_kill(self, cmd: KillProcess) -> dict:
        if self._ps is None:
            raise RuntimeError("psutil kurulu değil, işlem sonlandırılamıyor")
        hedef = _sade(cmd.process_name)
        if len(hedef) < 3:
            raise ValueError("İşlem adı çok kısa, yanlış şeyi kapatmamak için durdum")
        if hedef in _KORUNAN:
            raise ValueError(f"{hedef} bir Windows sistem işlemi, kapatmam tehlikeli")

        benim_pid = os.getpid()
        oldurulen = 0
        for p in self._ps.process_iter(["pid", "name"]):
            try:
                ad = _sade(p.info.get("name") or "")
                if not ad or ad in _KORUNAN or p.info.get("pid") == benim_pid:
                    continue
                if ad == hedef or ad.startswith(hedef):
                    p.kill()
                    oldurulen += 1
            except Exception:
                continue

        self._speak(f"{cmd.process_name} kapatıldı." if oldurulen
                    else f"{cmd.process_name} adında çalışan bir işlem bulamadım.")
        return {"sonlandirilan": oldurulen}

    def _speak(self, text: str) -> None:
        try:
            self._bus.publish(TtsRequested(text=text))
        except Exception:
            pass

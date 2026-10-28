# -*- coding: utf-8 -*-
"""
Uygulama açma / kapatma komutları.
Mevcut UygulamaYoneticisi mantığını yeni typed katmana taşır.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import webbrowser
from typing import Any

from irle.domain.commands import CloseApplication, OpenApplication
from irle.domain.events import Notification

logger = logging.getLogger("irle.handlers.app")

# UygulamaTarayici opsiyonel — pywin32 gerektirir
try:
    from modules.uygulama_tarayici import UygulamaTarayici
    _tarayici = UygulamaTarayici()
    _TARAYICI_OK = True
except Exception:
    _tarayici = None
    _TARAYICI_OK = False
    logger.warning("UygulamaTarayici yüklenemedi — yalnızca config tabanlı eşleşme kullanılacak.")

# pywinctl opsiyonel
try:
    import pywinctl
    _PYWINCTL_OK = True
except ImportError:
    _PYWINCTL_OK = False

# Varsayılan uygulama → exe eşlemeleri (config'den de gelir)
_DEFAULT_APP_COMMANDS: dict[str, str] = {
    "notepad":   "notepad.exe",
    "hesap":     "calc.exe",
    "explorer":  "explorer.exe",
    "chrome":    "chrome.exe",
    "terminal":  "cmd.exe",
    "spotify":   "spotify.exe",
    "discord":   "discord.exe",
    "steam":     "steam.exe",
    "code":      "code.exe",
}


class AppHandler:
    """OpenApplication ve CloseApplication komutlarını işler."""

    def __init__(self, event_bus: Any, extra_app_commands: dict | None = None) -> None:
        self._bus = event_bus
        self._app_commands = dict(_DEFAULT_APP_COMMANDS)
        if extra_app_commands:
            self._app_commands.update(extra_app_commands)

        # Bayrak thread başlamadan ÖNCE ayarlanmalı; aksi halde tarama hızlı
        # biterse True değeri burada tekrar False'a çekiliyordu.
        self._katalog_hazir = False
        if _TARAYICI_OK and _tarayici is not None:
            import threading
            t = threading.Thread(
                target=self._katalog_hazirla, daemon=True, name="AppScanner"
            )
            t.start()

    def _katalog_hazirla(self) -> None:
        try:
            if _tarayici:
                sayi = _tarayici.tara()
                self._katalog_hazir = True
                logger.info("Uygulama kataloğu hazır → %d uygulama.", sayi)
        except Exception as exc:
            logger.error("Katalog tarama hatası: %s", exc)
            self._katalog_hazir = True

    # ------------------------------------------------------------------

    def handle_open(self, cmd: OpenApplication) -> None:
        name = cmd.name.strip().lower()
        logger.info("Uygulama açılıyor: '%s'", name)

        # Web sitesi ("youtube aç" → https://www.youtube.com)
        if re.match(r"https?://[\w.\-]+(/[\w\-./?=&%]*)?$", name):
            webbrowser.open(cmd.name.strip())
            self._notify(f"{cmd.name} açılıyor.")
            return

        exe = self._exe_bul(name)
        if not exe:
            raise FileNotFoundError(f"{cmd.name} uygulamasını bulamadım")

        if not _guvenli_hedef_mi(exe):
            logger.warning("Şüpheli uygulama hedefi reddedildi: %r", exe)
            raise ValueError(f"'{cmd.name}' güvenli bir uygulama adı değil, çalıştırmadım")

        try:
            _baslat(exe)
        except FileNotFoundError:
            raise FileNotFoundError(f"{cmd.name} uygulamasını bulamadım") from None
        logger.info("Başlatıldı: '%s'", exe)
        self._notify(f"{cmd.name} açılıyor.")

    def handle_close(self, cmd: CloseApplication) -> None:
        name = cmd.name.strip()
        logger.info("Uygulama kapatılıyor: '%s'", name)

        # 1) Pencere başlığından (büyük/küçük harf duyarsız)
        if _PYWINCTL_OK:
            try:
                hedef = name.lower()
                windows = [w for w in pywinctl.getAllWindows()
                           if hedef in (getattr(w, "title", "") or "").lower()]
                for win in windows:
                    win.close()
                if windows:
                    return
            except Exception as exc:
                logger.error("Pencere kapatma hatası: %s", exc)

        # 2) Pencere bulunamazsa işlem adından nazikçe sonlandır
        #    (Spotify'ın pencere başlığı çalan şarkının adıdır, başlıkta "Spotify" geçmez)
        if _kapat_islem(self._islem_adi(name)):
            return
        raise FileNotFoundError(f"{name} açık değil gibi görünüyor")

    def _islem_adi(self, name: str) -> str:
        anahtar = name.strip().lower()
        exe = self._app_commands.get(anahtar, anahtar)
        return os.path.splitext(os.path.basename(exe))[0].lower()

    # ------------------------------------------------------------------

    def _exe_bul(self, name: str) -> str | None:
        # 1. Katalog
        if self._katalog_hazir and _tarayici:
            try:
                _, yol = _tarayici.bul(name)
                if yol:
                    return yol
            except Exception:
                pass

        # 2. Tam eşleşme
        if name in self._app_commands:
            return self._app_commands[name]

        # 3. Kısmi eşleşme
        for key, val in self._app_commands.items():
            if key in name or name in key:
                return val

        # 4. Direkt çalıştır
        logger.info("Direkt çalıştırma deneniyor: '%s'", name)
        return name

    def _notify(self, message: str) -> None:
        try:
            self._bus.publish(Notification(title="Uygulama", message=message))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Güvenli başlatma
# ---------------------------------------------------------------------------

# Sadece harf/rakam/boşluk/nokta/tire/alt çizgi — &, |, >, ;, ", ` gibi kabuk karakterleri yok
_GUVENLI_AD = re.compile(r"[\w .\-+]+")


def _guvenli_hedef_mi(hedef: str) -> bool:
    """Var olan bir dosya yolu ya da kabuk karakteri içermeyen düz bir ad mı?"""
    hedef = (hedef or "").strip()
    if not hedef:
        return False
    if os.path.isabs(hedef) and os.path.exists(hedef):
        return True
    return bool(_GUVENLI_AD.fullmatch(hedef))


def _kapat_islem(ad: str) -> int:
    """psutil ile adı eşleşen işlemleri terminate eder (kill değil). Kapatılan sayısı."""
    if len(ad) < 3:
        return 0
    try:
        import psutil
    except ImportError:
        return 0
    sayi = 0
    for p in psutil.process_iter(["pid", "name"]):
        try:
            pad = os.path.splitext((p.info.get("name") or "").lower())[0]
            if pad == ad or (len(ad) >= 4 and pad.startswith(ad)):
                if p.info.get("pid") != os.getpid():
                    p.terminate()
                    sayi += 1
        except Exception:
            continue
    return sayi


def _baslat(hedef: str) -> None:
    """Kabuk (shell=True) KULLANMADAN başlatır.

    Windows'ta os.startfile → ShellExecute: .exe, .lnk ve "chrome.exe" gibi
    App Paths kayıtlı adları çözer; bulunamazsa FileNotFoundError fırlatır.
    """
    if sys.platform == "win32":
        os.startfile(hedef)  # type: ignore[attr-defined]
    else:
        subprocess.Popen([hedef], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

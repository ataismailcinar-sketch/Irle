# -*- coding: utf-8 -*-
"""
Ekran ve pano komutları: screenshot, clipboard, dosya arama, klasör oluşturma.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from irle.domain.commands import (
    ClearClipboard,
    CreateFolder,
    ReadClipboard,
    SearchFile,
    TakeScreenshot,
)
from irle.domain.events import Notification, TtsRequested

logger = logging.getLogger("irle.handlers.screen")

try:
    import pyautogui
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False
    logger.warning("pyautogui kurulu değil — TakeScreenshot devre dışı.")

try:
    import pyperclip
    _PYPERCLIP_OK = True
except ImportError:
    _PYPERCLIP_OK = False
    logger.warning("pyperclip kurulu değil — Clipboard işlemleri devre dışı.")

_SCREENSHOT_DIR = "data/screenshots"


class ScreenHandler:
    """Ekran ve pano komutlarını işler."""

    def __init__(self, event_bus: Any) -> None:
        self._bus = event_bus
        os.makedirs(_SCREENSHOT_DIR, exist_ok=True)

    # ------------------------------------------------------------------

    def handle_screenshot(self, cmd: TakeScreenshot) -> None:
        if not _PYAUTOGUI_OK:
            raise RuntimeError("pyautogui kurulu değil, ekran görüntüsü alınamıyor")

        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = cmd.save_path or os.path.join(_SCREENSHOT_DIR, f"ss_{ts}.png")
            img = pyautogui.screenshot()
            img.save(path)
            logger.info("Ekran görüntüsü kaydedildi: %s", path)
            self._notify(f"Kaydedildi: {path}")
        except Exception as exc:
            logger.error("Screenshot alınamadı: %s", exc)
            raise RuntimeError("ekran görüntüsü alınamadı") from exc

    def handle_read_clipboard(self, cmd: ReadClipboard) -> str | None:
        if not _PYPERCLIP_OK:
            self._speak("Pano okunamıyor, pyperclip kurulu değil.")
            return None
        try:
            text = pyperclip.paste()
            if text:
                self._speak(f"Panoda şu var: {text[:200]}")
            else:
                self._speak("Pano boş.")
            return text
        except Exception as exc:
            logger.error("Pano okunamadı: %s", exc)
            return None

    def handle_clear_clipboard(self, cmd: ClearClipboard) -> None:
        if not _PYPERCLIP_OK:
            self._speak("Pano temizlenemiyor, pyperclip kurulu değil.")
            return
        try:
            pyperclip.copy("")
            logger.info("Pano temizlendi.")
            self._speak("Pano temizlendi.")
        except Exception as exc:
            logger.error("Pano temizlenemedi: %s", exc)

    def handle_search_file(self, cmd: SearchFile) -> list[str]:
        term = cmd.term.lower()
        search_dir = getattr(cmd, "directory", None) or os.path.expanduser("~\\Desktop")
        logger.info("Dosya aranıyor: '%s' → %s", term, search_dir)

        found: list[str] = []
        try:
            for root, _dirs, files in os.walk(search_dir):
                for f in files:
                    if term in f.lower():
                        found.append(os.path.join(root, f))
                        if len(found) >= 5:
                            break
                if len(found) >= 5:
                    break
        except Exception as exc:
            logger.error("Dosya arama hatası: %s", exc)

        if found:
            self._speak(f"{len(found)} dosya bulundu: {os.path.basename(found[0])}")
        else:
            self._speak(f"'{cmd.term}' adında dosya bulunamadı.")
        return found

    def handle_create_folder(self, cmd: CreateFolder) -> None:
        name = cmd.name.strip()
        path = os.path.join(os.path.expanduser("~\\Desktop"), name)
        try:
            os.makedirs(path, exist_ok=True)
            logger.info("Klasör oluşturuldu: %s", path)
            self._speak(f"'{name}' klasörü oluşturuldu.")
        except Exception as exc:
            logger.error("Klasör oluşturulamadı: %s", exc)
            raise RuntimeError(f"'{name}' klasörü oluşturulamadı") from exc

    # ------------------------------------------------------------------

    def _speak(self, text: str) -> None:
        try:
            self._bus.publish(TtsRequested(text=text))
        except Exception:
            pass

    def _notify(self, message: str) -> None:
        try:
            self._bus.publish(Notification(title="Ekran", message=message))
        except Exception:
            pass

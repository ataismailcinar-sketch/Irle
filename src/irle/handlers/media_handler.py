# -*- coding: utf-8 -*-
"""
Medya / ses / parlaklık komutları.
"""

from __future__ import annotations

import logging
from typing import Any

from irle.domain.commands import MediaControl, MuteVolume, SetBrightness, SetVolume

logger = logging.getLogger("irle.handlers.media")

# Opsiyonel Windows bağımlılıkları
try:
    import pyautogui
    _PYAUTOGUI_OK = True
except ImportError:
    _PYAUTOGUI_OK = False
    logger.warning("pyautogui kurulu değil — MediaControl/Volume devre dışı.")

try:
    import screen_brightness_control as sbc
    _SBC_OK = True
except ImportError:
    _SBC_OK = False
    logger.warning("screen-brightness-control kurulu değil — SetBrightness devre dışı.")

# pyautogui klavye kısayolları için medya tuşları
_MEDIA_KEYS = {
    "play_pause": "playpause",
    "next":       "nexttrack",
    "previous":   "prevtrack",
    "stop":       "stop",
}


class MediaHandler:
    """Ses, parlaklık ve medya kontrol komutlarını işler."""

    def __init__(self, event_bus: Any) -> None:
        self._bus = event_bus

    # ------------------------------------------------------------------
    # Ses
    # ------------------------------------------------------------------

    def handle_volume(self, cmd: SetVolume) -> None:
        if not _PYAUTOGUI_OK:
            raise RuntimeError("pyautogui kurulu değil, ses ayarlanamıyor")

        if cmd.level is not None:
            # Mutlak seviye ayarla — pyautogui'nin doğrudan % API'si yok,
            # önce mute kaldır ve ~100 kez basarak normalize et (fallback).
            # Gerçek uygulama için pycaw/comtypes kullanılabilir.
            logger.info("Ses seviyesi %d%% olarak ayarlanıyor (yaklaşık).", cmd.level)
            # Basit yaklaşım: sesi sıfırla, sonra hedef kadar artır
            for _ in range(50):
                pyautogui.press("volumedown")
            steps = int(cmd.level / 2)
            for _ in range(steps):
                pyautogui.press("volumeup")
        elif cmd.delta is not None:
            key = "volumeup" if cmd.delta > 0 else "volumedown"
            presses = abs(cmd.delta) // 2 or 1
            logger.info("Ses %s (%d adım).", "artırılıyor" if cmd.delta > 0 else "azaltılıyor", presses)
            for _ in range(presses):
                pyautogui.press(key)

    def handle_mute(self, cmd: MuteVolume) -> None:
        if not _PYAUTOGUI_OK:
            raise RuntimeError("pyautogui kurulu değil, mute yapılamıyor")
        logger.info("Ses susturuluyor / açılıyor.")
        pyautogui.press("volumemute")

    # ------------------------------------------------------------------
    # Parlaklık
    # ------------------------------------------------------------------

    def handle_brightness(self, cmd: SetBrightness) -> None:
        if not _SBC_OK:
            raise RuntimeError("screen-brightness-control kurulu değil, parlaklık ayarlanamıyor")

        try:
            current = sbc.get_brightness(display=0)
            current_val = current[0] if isinstance(current, list) else current

            if cmd.level is not None:
                target = max(0, min(100, cmd.level))
            elif cmd.delta is not None:
                target = max(0, min(100, current_val + cmd.delta))
            else:
                return

            logger.info("Parlaklık %d%%'e ayarlanıyor (şu an %d%%).", target, current_val)
            sbc.set_brightness(target, display=0)
        except Exception as exc:
            logger.error("Parlaklık ayarlanamadı: %s", exc)
            raise RuntimeError("bu ekranın parlaklığı ayarlanamıyor") from exc

    # ------------------------------------------------------------------
    # Medya
    # ------------------------------------------------------------------

    def handle_media(self, cmd: MediaControl) -> None:
        if not _PYAUTOGUI_OK:
            raise RuntimeError("pyautogui kurulu değil, medya kontrolü yapılamıyor")

        key = _MEDIA_KEYS.get(cmd.action)
        if key:
            logger.info("Medya tuşu: %s (%s)", key, cmd.action)
            pyautogui.press(key)
        else:
            raise ValueError(f"Bilinmeyen medya işlemi: {cmd.action}")

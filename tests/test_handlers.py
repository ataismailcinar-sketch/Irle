# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Handlers (src/irle/handlers/*)
=============================================================================
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from irle.infra.event_bus import TypedEventBus
from irle.domain.commands import (
    ShutdownComputer, RestartComputer, LockComputer, CancelShutdown,
    SetVolume, MuteVolume, SetBrightness, MediaControl,
    OpenApplication, CloseApplication,
    CreateNote, DeleteNote, Speak, SearchWeb,
    TakeScreenshot, ReadClipboard, ClearClipboard, SearchFile, CreateFolder,
)
from irle.domain.queries import (
    ListNotes, GetBatteryStatus, GetSystemInfo, GetNetworkStatus, GetCurrentTime
)
from irle.domain.events import TtsRequested, Notification

from irle.handlers.system_handler import SystemHandler
from irle.handlers.media_handler import MediaHandler
from irle.handlers.app_handler import AppHandler
from irle.handlers.notes_handler import NotesHandler
from irle.handlers.info_handler import InfoHandler
from irle.handlers.screen_handler import ScreenHandler
from irle.handlers.tts_handler import TtsHandler
from irle.handlers.web_handler import WebHandler


@pytest.fixture
def bus():
    bus_inst = TypedEventBus()
    yield bus_inst
    bus_inst.shutdown()


# ---------------------------------------------------------------------------
# SystemHandler Tests
# ---------------------------------------------------------------------------

def test_system_handler_shutdown(bus):
    handler = SystemHandler(bus)
    with patch("subprocess.run") as mock_run:
        handler.handle_shutdown(ShutdownComputer(delay_seconds=30))
        mock_run.assert_called_once_with(
            ["shutdown", "/s", "/t", "30"],
            check=True,
            stdout=subprocess_devnull(),
            stderr=subprocess_devnull(),
        )


def test_system_handler_restart(bus):
    handler = SystemHandler(bus)
    with patch("subprocess.run") as mock_run:
        handler.handle_restart(RestartComputer(delay_seconds=45))
        mock_run.assert_called_once_with(
            ["shutdown", "/r", "/t", "45"],
            check=True,
            stdout=subprocess_devnull(),
            stderr=subprocess_devnull(),
        )


def test_system_handler_lock(bus):
    handler = SystemHandler(bus)
    # Patch user32.LockWorkStation or subprocess.run depending on availability
    with patch("subprocess.run") as mock_run, \
         patch("irle.handlers.system_handler._CTYPES_OK", False):
        handler.handle_lock(LockComputer())
        mock_run.assert_called_once()


def test_system_handler_cancel(bus):
    handler = SystemHandler(bus)
    with patch("subprocess.run") as mock_run:
        handler.handle_cancel_shutdown(CancelShutdown())
        mock_run.assert_called_once_with(
            ["shutdown", "/a"],
            check=True,
            stdout=subprocess_devnull(),
            stderr=subprocess_devnull(),
        )


def subprocess_devnull():
    import subprocess
    return subprocess.DEVNULL


# ---------------------------------------------------------------------------
# MediaHandler Tests
# ---------------------------------------------------------------------------

def test_media_handler_volume_delta(bus):
    handler = MediaHandler(bus)
    with patch("pyautogui.press") as mock_press, \
         patch("irle.handlers.media_handler._PYAUTOGUI_OK", True):
        handler.handle_volume(SetVolume(delta=10))
        # 10 // 2 = 5 presses
        assert mock_press.call_count == 5
        mock_press.assert_called_with("volumeup")


def test_media_handler_mute(bus):
    handler = MediaHandler(bus)
    with patch("pyautogui.press") as mock_press, \
         patch("irle.handlers.media_handler._PYAUTOGUI_OK", True):
        handler.handle_mute(MuteVolume())
        mock_press.assert_called_once_with("volumemute")


def test_media_handler_brightness_level(bus):
    handler = MediaHandler(bus)
    with patch("screen_brightness_control.set_brightness") as mock_set, \
         patch("screen_brightness_control.get_brightness", return_value=[50]), \
         patch("irle.handlers.media_handler._SBC_OK", True):
        handler.handle_brightness(SetBrightness(level=80))
        mock_set.assert_called_once_with(80, display=0)


def test_media_handler_media_control(bus):
    handler = MediaHandler(bus)
    with patch("pyautogui.press") as mock_press, \
         patch("irle.handlers.media_handler._PYAUTOGUI_OK", True):
        handler.handle_media(MediaControl(action="next"))
        mock_press.assert_called_once_with("nexttrack")


# ---------------------------------------------------------------------------
# AppHandler Tests
# ---------------------------------------------------------------------------

def test_app_handler_open(bus):
    handler = AppHandler(bus)
    with patch("irle.handlers.app_handler._baslat") as mock_baslat:
        handler.handle_open(OpenApplication(name="notepad"))
        mock_baslat.assert_called_once_with("notepad.exe")


def test_app_handler_open_kabuk_enjeksiyonu_reddedilir(bus):
    handler = AppHandler(bus)
    with patch("irle.handlers.app_handler._baslat") as mock_baslat:
        with pytest.raises(ValueError):
            handler.handle_open(OpenApplication(name="calc & del important.txt"))
        mock_baslat.assert_not_called()


def test_app_handler_open_site(bus):
    handler = AppHandler(bus)
    with patch("irle.handlers.app_handler.webbrowser.open") as mock_open, \
         patch("irle.handlers.app_handler._baslat") as mock_baslat:
        handler.handle_open(OpenApplication(name="https://www.youtube.com"))
        mock_open.assert_called_once_with("https://www.youtube.com")
        mock_baslat.assert_not_called()


def test_app_handler_open_bulunamazsa_hata(bus):
    handler = AppHandler(bus)
    with patch("irle.handlers.app_handler._baslat", side_effect=FileNotFoundError):
        with pytest.raises(FileNotFoundError):
            handler.handle_open(OpenApplication(name="yokboyleprogram"))


def test_app_handler_close(bus):
    handler = AppHandler(bus)
    mock_window = MagicMock()
    mock_window.title = "Adsız - Notepad"
    fake_winctl = MagicMock()
    fake_winctl.getAllWindows.return_value = [mock_window]
    with patch("irle.handlers.app_handler.pywinctl", fake_winctl, create=True), \
         patch("irle.handlers.app_handler._PYWINCTL_OK", True):
        handler.handle_close(CloseApplication(name="notepad"))
        mock_window.close.assert_called_once()


def test_app_handler_close_pencere_yoksa_islemden(bus):
    handler = AppHandler(bus)
    fake_winctl = MagicMock()
    fake_winctl.getAllWindows.return_value = []
    with patch("irle.handlers.app_handler.pywinctl", fake_winctl, create=True), \
         patch("irle.handlers.app_handler._PYWINCTL_OK", True), \
         patch("irle.handlers.app_handler._kapat_islem", return_value=1) as mock_kapat:
        handler.handle_close(CloseApplication(name="spotify"))
        mock_kapat.assert_called_once_with("spotify")


# ---------------------------------------------------------------------------
# NotesHandler Tests
# ---------------------------------------------------------------------------

def test_notes_handler(bus, tmp_path):
    notes_file = tmp_path / "notes_test.json"
    handler = NotesHandler(bus, notes_file=str(notes_file))

    # Add Note
    handler.handle_create(CreateNote(text="Süreç test ediliyor"))
    assert len(handler._notes) == 1
    assert handler._notes[0]["metin"] == "Süreç test ediliyor"

    # List Notes
    notes = handler.handle_list(ListNotes(limit=1))
    assert len(notes) == 1
    assert notes[0]["metin"] == "Süreç test ediliyor"

    # Delete Note
    handler.handle_delete(DeleteNote(mode="last"))
    assert len(handler._notes) == 0


# ---------------------------------------------------------------------------
# InfoHandler Tests
# ---------------------------------------------------------------------------

def test_info_handler_battery(bus):
    handler = InfoHandler(bus)
    mock_batt = MagicMock(percent=85, power_plugged=True)
    with patch("psutil.sensors_battery", return_value=mock_batt), \
         patch("irle.handlers.info_handler._PSUTIL_OK", True):
        res = handler.handle_battery(GetBatteryStatus())
        assert res == {"percent": 85, "plugged": True}


def test_info_handler_system_info(bus):
    handler = InfoHandler(bus)
    with patch("psutil.cpu_percent", return_value=12.5), \
         patch("psutil.virtual_memory", return_value=MagicMock(percent=45.0)), \
         patch("psutil.disk_usage", return_value=MagicMock(free=100 * (1024**3))), \
         patch("irle.handlers.info_handler._PSUTIL_OK", True):
        res = handler.handle_system_info(GetSystemInfo(topics=("cpu", "ram", "disk")))
        assert res["cpu"] == 12.5
        assert res["ram"] == 45.0
        assert abs(res["disk_free_gb"] - 100.0) < 0.1


def test_info_handler_time(bus):
    handler = InfoHandler(bus)
    res = handler.handle_time(GetCurrentTime())
    assert "time" in res
    assert "date" in res


# ---------------------------------------------------------------------------
# ScreenHandler Tests
# ---------------------------------------------------------------------------

def test_screen_handler_screenshot(bus, tmp_path):
    handler = ScreenHandler(bus)
    save_file = tmp_path / "ss.png"
    mock_img = MagicMock()
    with patch("pyautogui.screenshot", return_value=mock_img) as mock_ss, \
         patch("irle.handlers.screen_handler._PYAUTOGUI_OK", True):
        handler.handle_screenshot(TakeScreenshot(save_path=str(save_file)))
        mock_ss.assert_called_once()
        mock_img.save.assert_called_once_with(str(save_file))


def test_screen_handler_clipboard(bus):
    handler = ScreenHandler(bus)
    with patch("pyperclip.paste", return_value="pano verisi") as mock_paste, \
         patch("pyperclip.copy") as mock_copy, \
         patch("irle.handlers.screen_handler._PYPERCLIP_OK", True):
        res = handler.handle_read_clipboard(ReadClipboard())
        assert res == "pano verisi"

        handler.handle_clear_clipboard(ClearClipboard())
        mock_copy.assert_called_once_with("")


# ---------------------------------------------------------------------------
# TtsHandler Tests
# ---------------------------------------------------------------------------

def test_tts_handler(bus):
    handler = TtsHandler(bus)
    events = []
    bus.subscribe(TtsRequested, lambda e: events.append(e))

    handler.handle_speak(Speak(text="Deneme"))

    import time
    time.sleep(0.1)
    assert len(events) == 1
    assert events[0].text == "Deneme"


# ---------------------------------------------------------------------------
# WebHandler Tests
# ---------------------------------------------------------------------------

def test_web_handler(bus):
    handler = WebHandler(bus)
    with patch("webbrowser.open") as mock_open:
        handler.handle_search(SearchWeb(query="pycon"))
        mock_open.assert_called_once_with("https://www.google.com/search?q=pycon")

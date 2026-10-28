# -*- coding: utf-8 -*-
"""
=============================================================================
APP / COMMAND REGISTRY — Command Bus ve Handler Bağlantıları
=============================================================================
Tüm domain komutlarını ve sorgularını ilgili handler metotlarına bağlar.
"""

from __future__ import annotations

from typing import Any

from irle.infra.command_bus import CommandBus
from irle.domain.commands import (
    ShutdownComputer, RestartComputer, LockComputer, CancelShutdown,
    SetVolume, MuteVolume, SetBrightness, MediaControl,
    OpenApplication, CloseApplication,
    CreateNote, DeleteNote,
    SearchWeb, Speak,
    TakeScreenshot, ReadClipboard, ClearClipboard, SearchFile, CreateFolder,
    CompositeCommand, ScheduleCommand, CancelAllTimers, WindowControl, KillProcess,
)
from irle.domain.queries import (
    ListNotes, GetBatteryStatus, GetSystemInfo, GetNetworkStatus, GetCurrentTime
)

from irle.handlers.system_handler import SystemHandler
from irle.handlers.media_handler import MediaHandler
from irle.handlers.app_handler import AppHandler
from irle.handlers.notes_handler import NotesHandler
from irle.handlers.info_handler import InfoHandler
from irle.handlers.screen_handler import ScreenHandler
from irle.handlers.tts_handler import TtsHandler
from irle.handlers.web_handler import WebHandler
from irle.handlers.timer_handler import TimerHandler
from irle.handlers.window_handler import WindowHandler
from irle.adapters.intent.rule_engine import RuleEngine


def build_command_bus(event_bus: Any, settings: Any = None) -> CommandBus:
    """
    Tüm handler'ları CommandBus'a kaydeden fabrika fonksiyonu.

    Args:
        event_bus: Olayları yayınlamak için TypedEventBus örneği.
        settings:  (Opsiyonel) Ortam ayarlarını içeren Settings nesnesi.
    """
    bus = CommandBus(event_bus)

    # Handler'ları oluştur
    system_handler = SystemHandler(event_bus)
    media_handler = MediaHandler(event_bus)

    extra_app_commands = settings.app_commands if settings else None
    app_handler = AppHandler(event_bus, extra_app_commands=extra_app_commands)

    notes_file = settings.notes_file if settings else "data/notlar.json"
    notes_handler = NotesHandler(event_bus, notes_file=notes_file)

    info_handler = InfoHandler(event_bus)
    screen_handler = ScreenHandler(event_bus)
    tts_handler = TtsHandler(event_bus)
    web_handler = WebHandler(event_bus)

    # 1. Sistem Gücü Komutları
    bus.register(ShutdownComputer, system_handler.handle_shutdown)
    bus.register(RestartComputer, system_handler.handle_restart)
    bus.register(LockComputer, system_handler.handle_lock)
    bus.register(CancelShutdown, system_handler.handle_cancel_shutdown)

    # 2. Medya / Ses / Parlaklık Komutları
    bus.register(SetVolume, media_handler.handle_volume)
    bus.register(MuteVolume, media_handler.handle_mute)
    bus.register(SetBrightness, media_handler.handle_brightness)
    bus.register(MediaControl, media_handler.handle_media)

    # 3. Uygulama Yönetim Komutları
    bus.register(OpenApplication, app_handler.handle_open)
    bus.register(CloseApplication, app_handler.handle_close)

    # 4. Not Komut ve Sorguları
    bus.register(CreateNote, notes_handler.handle_create)
    bus.register(DeleteNote, notes_handler.handle_delete)
    bus.register(ListNotes, notes_handler.handle_list)

    # 5. Bilgi ve Durum Sorguları
    bus.register(GetBatteryStatus, info_handler.handle_battery)
    bus.register(GetSystemInfo, info_handler.handle_system_info)
    bus.register(GetNetworkStatus, info_handler.handle_network)
    bus.register(GetCurrentTime, info_handler.handle_time)

    # 6. Ekran ve Pano Komutları
    bus.register(TakeScreenshot, screen_handler.handle_screenshot)
    bus.register(ReadClipboard, screen_handler.handle_read_clipboard)
    bus.register(ClearClipboard, screen_handler.handle_clear_clipboard)
    bus.register(SearchFile, screen_handler.handle_search_file)
    bus.register(CreateFolder, screen_handler.handle_create_folder)

    # 7. Konuşma ve Arama Komutları
    bus.register(Speak, tts_handler.handle_speak)
    bus.register(SearchWeb, web_handler.handle_search)

    # 8. Zamanlayıcı / hatırlatıcı ve pencere/süreç yönetimi
    #    (Kural motoru bu komutları üretiyordu ama handler kayıtlı değildi.)
    timer_handler = TimerHandler(event_bus, dispatch=bus.dispatch, parse=RuleEngine().parse)
    bus.register(ScheduleCommand, timer_handler.handle_schedule)
    bus.register(CancelAllTimers, timer_handler.handle_cancel_all)
    window_handler = WindowHandler(event_bus)
    bus.register(WindowControl, window_handler.handle_window)
    bus.register(KillProcess, window_handler.handle_kill)

    # 9. Otonom ReAct ve Çok Adımlı Bileşik Komutlar
    from irle.app.task_planner import ReActTaskPlanner
    react_planner = ReActTaskPlanner(bus, event_bus)
    bus.register(CompositeCommand, react_planner.execute_plan)

    return bus

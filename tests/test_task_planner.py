# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Task Planner & ReAct Execution & Tool Registry
=============================================================================
"""

import pytest
from unittest.mock import MagicMock, patch

from irle.app.task_planner import (
    ToolRegistry,
    CompoundIntentDecomposer,
    ReActTaskPlanner,
)
from irle.domain.commands import (
    OpenApplication,
    SetVolume,
    CompositeCommand,
    Speak,
)
from irle.domain.queries import GetCurrentTime
from irle.domain.events import SpeechRecognized, IntentResolved, CommandCompleted
from irle.adapters.intent.rule_engine import RuleEngine
from irle.infra.event_bus import TypedEventBus
from irle.app.command_registry import build_command_bus
from irle.app.settings import Settings
from modules.intent_modulu import IntentModulu


class TestToolRegistry:
    def test_default_tools(self):
        reg = ToolRegistry()
        tools = reg.list_tools()
        names = [t["name"] for t in tools]
        assert "open_application" in names
        assert "set_volume" in names
        assert "get_battery_status" in names
        assert "get_current_time" in names

    def test_tool_factory(self):
        reg = ToolRegistry()
        tool = reg.get_tool("open_application")
        assert tool is not None
        cmd = tool.factory(name="chrome")
        assert isinstance(cmd, OpenApplication)
        assert cmd.name == "chrome"


class TestCompoundIntentDecomposer:
    def test_decompose_and_parse_success(self):
        engine = RuleEngine()
        decomposer = CompoundIntentDecomposer(engine)

        res = decomposer.decompose_and_parse("spotify aç ve sesi kıs")
        assert isinstance(res, CompositeCommand)
        assert len(res.commands) == 2
        assert isinstance(res.commands[0], OpenApplication)
        assert res.commands[0].name == "spotify"
        assert isinstance(res.commands[1], SetVolume)
        assert res.commands[1].delta == -10

    def test_decompose_with_ardindan(self):
        engine = RuleEngine()
        decomposer = CompoundIntentDecomposer(engine)

        res = decomposer.decompose_and_parse("not defteri aç ardından saat kaç")
        assert isinstance(res, CompositeCommand)
        assert len(res.commands) == 2
        assert isinstance(res.commands[0], OpenApplication)
        assert isinstance(res.commands[1], GetCurrentTime)

    def test_single_command_returns_none(self):
        engine = RuleEngine()
        decomposer = CompoundIntentDecomposer(engine)
        # Tekil komut composite olmamalı
        res = decomposer.decompose_and_parse("spotify aç")
        assert res is None


class TestReActTaskPlanner:
    def test_execute_plan(self):
        event_bus = TypedEventBus()
        cmd_bus = build_command_bus(event_bus)
        planner = ReActTaskPlanner(cmd_bus, event_bus)

        cmd1 = OpenApplication(name="notepad")
        cmd2 = SetVolume(delta=-10)
        composite = CompositeCommand(commands=(cmd1, cmd2))

        with patch("irle.handlers.app_handler._baslat"), \
             patch("irle.handlers.media_handler.pyautogui", MagicMock(), create=True), \
             patch("irle.handlers.media_handler._PYAUTOGUI_OK", True):
            steps = planner.execute_plan(composite)

        assert len(steps) == 2
        assert steps[0].action == cmd1
        assert "Adım 1/2" in steps[0].thought
        assert steps[1].action == cmd2
        assert "Adım 2/2" in steps[1].thought


def test_integration_compound_command():
    bus = TypedEventBus()
    settings = Settings()
    cmd_bus = build_command_bus(bus, settings)
    intent = IntentModulu(bus, cmd_bus)
    intent.baslat()

    resolved_events = []
    bus.subscribe(IntentResolved, lambda e: resolved_events.append(e))

    import time
    with patch("irle.handlers.app_handler._baslat"), \
         patch("irle.handlers.media_handler.pyautogui", MagicMock(), create=True), \
         patch("irle.handlers.media_handler._PYAUTOGUI_OK", True):
        bus.publish(SpeechRecognized(text="spotify aç ve sesi kıs"))
        time.sleep(0.3)

    assert len(resolved_events) == 1
    assert resolved_events[0].command_type == "CompositeCommand"

    intent.durdur()
    bus.shutdown()

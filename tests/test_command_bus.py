# -*- coding: utf-8 -*-
"""
=============================================================================
TEST — Command Bus (src/irle/infra/command_bus.py)
=============================================================================
"""

import pytest
from typing import Any

from irle.infra.command_bus import CommandBus
from irle.infra.event_bus import TypedEventBus
from irle.domain.commands import Command, Speak
from irle.domain.events import CommandCompleted, CommandFailed


class DummyCommand(Command):
    pass


class DummyCommandWithParams(Command):
    def __init__(self, value: int):
        self.value = value


def test_command_bus_registration_and_dispatch():
    # Arrange
    bus = TypedEventBus()
    cmd_bus = CommandBus(bus)
    called = []

    def dummy_handler(cmd: DummyCommand):
        called.append(cmd)

    # Act
    cmd_bus.register(DummyCommand, dummy_handler)
    cmd = DummyCommand()
    cmd_bus.dispatch(cmd)

    # Assert
    assert cmd in called
    bus.shutdown()


def test_command_bus_publishes_completed_event():
    # Arrange
    bus = TypedEventBus()
    cmd_bus = CommandBus(bus)
    completed_events = []

    def dummy_handler(cmd: DummyCommand):
        pass

    bus.subscribe(CommandCompleted, lambda e: completed_events.append(e))
    cmd_bus.register(DummyCommand, dummy_handler)

    # Act
    cmd_bus.dispatch(DummyCommand())

    # Assert
    # EventBus processes handlers inside a thread pool, wait a bit
    import time
    time.sleep(0.1)

    assert len(completed_events) == 1
    assert completed_events[0].command_type == "DummyCommand"
    bus.shutdown()


def test_command_bus_handles_missing_handler():
    # Arrange
    bus = TypedEventBus()
    cmd_bus = CommandBus(bus)
    failed_events = []

    bus.subscribe(CommandFailed, lambda e: failed_events.append(e))

    # Act
    cmd_bus.dispatch(DummyCommand())

    # Assert
    import time
    time.sleep(0.1)

    assert len(failed_events) == 1
    assert failed_events[0].command_type == "DummyCommand"
    assert "Handler kayıtlı değil" in failed_events[0].error
    bus.shutdown()


def test_command_bus_exception_isolation():
    # Arrange
    bus = TypedEventBus()
    cmd_bus = CommandBus(bus)
    failed_events = []

    def failing_handler(cmd: DummyCommand):
        raise ValueError("Handler failed on purpose")

    bus.subscribe(CommandFailed, lambda e: failed_events.append(e))
    cmd_bus.register(DummyCommand, failing_handler)

    # Act
    cmd_bus.dispatch(DummyCommand())

    # Assert
    import time
    time.sleep(0.1)

    assert len(failed_events) == 1
    assert failed_events[0].command_type == "DummyCommand"
    assert "Handler failed on purpose" in failed_events[0].error
    bus.shutdown()

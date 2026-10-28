# -*- coding: utf-8 -*-
"""
=============================================================================
APP / TASK PLANNER — Otonom Görev Ayrıştırma ve ReAct Döngüsü
=============================================================================
Kullanıcının kompleks, çok adımlı Türkçe komutlarını (örn: "Spotify'ı aç ve sesi kıs")
alt görevlere bölen, araçları (Function Calling / Tool Registry) yöneten
ve ReAct (Reasoning and Acting) döngüsüyle sırayla yürüten servis katmanı.

Onion Architecture Kuralı:
  - Bu servis Application katmanında yer alır.
  - OS kütüphanelerine (pyautogui, subprocess vb.) DOĞRUDAN BAĞLANMAZ.
  - Yalnızca Domain Commands/Queries ve CommandBus üzerinden işlem yapar.
=============================================================================
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from irle.domain.commands import (
    CloseApplication,
    Command,
    CompositeCommand,
    CreateFolder,
    CreateNote,
    DeleteNote,
    MediaControl,
    MuteVolume,
    OpenApplication,
    SearchWeb,
    SetBrightness,
    SetVolume,
    ShutdownComputer,
    Speak,
    TakeScreenshot,
)
from irle.domain.queries import (
    GetBatteryStatus,
    GetCurrentTime,
    GetNetworkStatus,
    GetSystemInfo,
    ListNotes,
    Query,
)

logger = logging.getLogger("irle.app.task_planner")


# ---------------------------------------------------------------------------
# 1. Tool / Function Calling Tanımı ve Kayıt Defteri (Registry)
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """Bir asistan aracının (Function Calling) şeması."""
    name: str
    description: str
    parameters: Dict[str, Any]
    factory: Callable[..., Any]


class ToolRegistry:
    """
    Sistemdeki Command ve Query modellerini harici LLM / ReAct ajanları için
    çağrılabilir fonksiyon araçları (Function Calling) olarak sunan defter.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Ajanlar ve LLM'ler için OpenAPI / Function Calling uyumlu araç listesi."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in self._tools.values()
        ]

    def _register_default_tools(self) -> None:
        # Uygulama Araçları
        self.register(ToolDefinition(
            name="open_application",
            description="Belirtilen uygulamayı başlatır (örn: 'spotify', 'chrome', 'notepad').",
            parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            factory=lambda **kwargs: OpenApplication(name=kwargs["name"]),
        ))
        self.register(ToolDefinition(
            name="close_application",
            description="Çalışan bir uygulamayı kapatır.",
            parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            factory=lambda **kwargs: CloseApplication(name=kwargs["name"]),
        ))

        # Medya ve Ses Araçları
        self.register(ToolDefinition(
            name="set_volume",
            description="Sistem ses seviyesini ayarlar veya artırıp/azaltır.",
            parameters={"type": "object", "properties": {"level": {"type": "integer"}, "delta": {"type": "integer"}}},
            factory=lambda **kwargs: SetVolume(level=kwargs.get("level"), delta=kwargs.get("delta")),
        ))
        self.register(ToolDefinition(
            name="mute_volume",
            description="Sesi susturur veya sesi açar (toggle).",
            parameters={"type": "object", "properties": {}},
            factory=lambda **kwargs: MuteVolume(),
        ))
        self.register(ToolDefinition(
            name="media_control",
            description="Medya oynatıcısını kontrol eder (play_pause, next, previous).",
            parameters={"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]},
            factory=lambda **kwargs: MediaControl(action=kwargs["action"]),
        ))

        # Ekran ve Not Araçları
        self.register(ToolDefinition(
            name="set_brightness",
            description="Ekran parlaklığını ayarlar.",
            parameters={"type": "object", "properties": {"level": {"type": "integer"}, "delta": {"type": "integer"}}},
            factory=lambda **kwargs: SetBrightness(level=kwargs.get("level"), delta=kwargs.get("delta")),
        ))
        self.register(ToolDefinition(
            name="create_note",
            description="Yeni bir not kaydeder.",
            parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            factory=lambda **kwargs: CreateNote(text=kwargs["text"]),
        ))
        self.register(ToolDefinition(
            name="take_screenshot",
            description="Ekran görüntüsü alır.",
            parameters={"type": "object", "properties": {}},
            factory=lambda **kwargs: TakeScreenshot(),
        ))

        # Sorgu Araçları
        self.register(ToolDefinition(
            name="get_battery_status",
            description="Cihazın pil ve şarj durumunu sorgular.",
            parameters={"type": "object", "properties": {}},
            factory=lambda **kwargs: GetBatteryStatus(),
        ))
        self.register(ToolDefinition(
            name="get_current_time",
            description="Şu anki saati sorgular.",
            parameters={"type": "object", "properties": {}},
            factory=lambda **kwargs: GetCurrentTime(),
        ))
        self.register(ToolDefinition(
            name="search_web",
            description="Web üzerinde Google araması yapar.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            factory=lambda **kwargs: SearchWeb(query=kwargs["query"]),
        ))


# ---------------------------------------------------------------------------
# 2. Türkçe Bileşik Komut Ayrıştırıcı (Compound Intent Decomposer)
# ---------------------------------------------------------------------------

class CompoundIntentDecomposer:
    """
    Türkçe bağlaçlarla ('ve', 'ardından', 'sonra', 've de') birbirine bağlanmış
    cümleleri tespit edip tek tek alt hedeflere ayrıştırır.
    """

    # Bağlaç regex'i
    CONJUNCTION_PATTERN = re.compile(
        r"(?:\s+(?:ve\s+de|ardından|daha\s+sonra|sonra|ve)\s+|[,;]\s+)",
        re.IGNORECASE,
    )

    def __init__(self, rule_engine: Any) -> None:
        self.rule_engine = rule_engine

    def decompose_and_parse(self, text: str) -> Optional[CompositeCommand]:
        """
        Gelen metin birden fazla komut içeriyorsa bir CompositeCommand döndürür;
        aksi halde (tekil komut veya anlaşılamayan) None döner.
        """
        text = text.strip()
        if not text:
            return None

        # Bağlaçlarla parçala
        parts = [p.strip() for p in self.CONJUNCTION_PATTERN.split(text) if p.strip()]
        if len(parts) <= 1:
            return None

        parsed_commands: List[Command] = []
        for part in parts:
            cmd = self.rule_engine.parse(part)
            if cmd is None:
                # Alt parçalardan biri kural motoruyla eşleşmedi
                return None
            parsed_commands.append(cmd)

        if len(parsed_commands) >= 2:
            logger.info("Bileşik komut başarıyla ayrıştırıldı: %d alt komut", len(parsed_commands))
            return CompositeCommand(commands=tuple(parsed_commands))

        return None


# ---------------------------------------------------------------------------
# 3. ReAct (Reasoning and Acting) Döngüsü
# ---------------------------------------------------------------------------

@dataclass
class ReActStep:
    thought: str
    action: Command
    observation: Optional[Any] = None


class ReActTaskPlanner:
    """
    ReAct (Reasoning and Acting) Otonom Yürütücü.
    Kompleks planı alt adımlara böler, her adım öncesinde muhakeme (Reasoning/Thought) yapar,
    aksiyonu (Action) CommandBus üzerinden yürütür, sonucu gözlemler (Observation)
    ve nihai görevi tamamlar.
    """

    def __init__(self, command_bus: Any, event_bus: Any = None) -> None:
        self.command_bus = command_bus
        self.event_bus = event_bus

    def execute_plan(self, composite_cmd: CompositeCommand) -> List[ReActStep]:
        """
        CompositeCommand içerisindeki tüm alt adımları ReAct döngüsüyle sırayla yürütür.
        """
        steps: List[ReActStep] = []
        total = len(composite_cmd.commands)

        logger.info("ReAct Planlayıcı başlatıldı: %d adım yürütülecek.", total)

        for idx, cmd in enumerate(composite_cmd.commands, start=1):
            cmd_name = type(cmd).__name__
            thought = f"Adım {idx}/{total}: {cmd_name} komutunun çalıştırılması gerekiyor."
            logger.info("🤔 Düşünce (Thought): %s", thought)

            # Aksiyonu yürüt
            logger.info("⚡ Aksiyon (Action): %s yürütülüyor...", cmd)
            result = self.command_bus.dispatch(cmd)

            # Gözlem
            observation = f"{cmd_name} tamamlandı. Sonuç: {result}"
            logger.info("👁️ Gözlem (Observation): %s", observation)

            step = ReActStep(thought=thought, action=cmd, observation=result)
            steps.append(step)

        logger.info("✅ ReAct Planı başarıyla tamamlandı (%d/%d adım).", len(steps), total)
        return steps

# -*- coding: utf-8 -*-
"""
=============================================================================
APP / BRAIN SERVICE — İrle'nin Beyni
=============================================================================
Akış (tek kullanıcı cümlesi için):

    kullanıcı metni
        │  üslup analizcisi gözlemler
        ▼
    [sistem talimatı + kısa geçmiş + metin]  ──►  LLM (Groq / Ollama)
        │                                            │
        │   ◄── araç çağrısı (ses_ayarla, not_al...) ┘
        ▼
    tools.build_command → CommandBus.dispatch   (handler konuşması yakalanır)
        │
        └── sonuç modele geri verilir → model son cevabı kendi üslubuyla yazar

Model hiçbir zaman doğrudan OS'a dokunmaz; sadece tipli komut üretir.
=============================================================================
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Optional

from irle.adapters.brain import tools as tool_mod
from irle.adapters.brain.llm_client import LLMError, LLMReply
from irle.adapters.brain.persona import UslupAnalizcisi, sistem_talimati
from irle.infra.speech_capture import capture_speech

logger = logging.getLogger("irle.app.brain")

_GUC_ISTEGI = re.compile(
    r"(kapat|kapan|yeniden\s*başlat|restart|reboot|shut\s*down|power\s*off)", re.IGNORECASE)


@dataclass(frozen=True)
class BrainResult:
    reply: str
    executed: tuple[str, ...] = ()
    provider: str = ""


class BrainService:
    """Kullanıcının cümlesini anlayıp araçları çalıştıran ve cevap üreten servis."""

    def __init__(
        self,
        llm: Any,
        command_bus: Any,
        analyzer: Optional[UslupAnalizcisi] = None,
        asistan_adi: str = "İrle",
        kullanici_adi: str = "",
        max_history_turns: int = 8,
        max_tool_rounds: int = 4,
    ) -> None:
        self._llm = llm
        self._cmd_bus = command_bus
        self.analyzer = analyzer or UslupAnalizcisi()
        self._asistan_adi = asistan_adi
        self._kullanici_adi = kullanici_adi
        self._max_rounds = max_tool_rounds
        # (rol, metin) — sadece kullanıcı cümleleri ve son cevaplar; araç detayı tutulmaz
        self._history: Deque[dict] = deque(maxlen=max_history_turns * 2)
        self._lock = threading.Lock()  # aynı anda tek düşünce

    # ------------------------------------------------------------------

    def observe_fast_path(self, user_text: str, summary: str) -> None:
        """Regex hızlı yolundan geçen komutları da geçmişe yaz (bağlam kopmasın)."""
        self.analyzer.gozlemle(user_text)
        with self._lock:
            self._history.append({"role": "user", "content": user_text})
            self._history.append({"role": "assistant", "content": f"(yapıldı: {summary})"})

    def handle(self, user_text: str) -> BrainResult:
        """Bir cümleyi işler. Beyne hiç ulaşılamazsa LLMError fırlatır."""
        user_text = user_text.strip()
        self.analyzer.gozlemle(user_text)

        with self._lock:
            system = sistem_talimati(
                self.analyzer.profil(),
                self.analyzer.gozlem_sayisi,
                asistan_adi=self._asistan_adi,
                kullanici_adi=self._kullanici_adi,
                beyin=self._provider_label(),
            )
            messages: list[dict] = [{"role": "system", "content": system}, *self._history,
                                    {"role": "user", "content": user_text}]
            specs = tool_mod.tool_specs()
            executed: list[str] = []
            reply: Optional[LLMReply] = None

            for _round in range(self._max_rounds + 1):
                # Son turda araç vermeyiz → model bir cevap yazmak zorunda kalır
                reply = self._llm.chat(messages, specs if _round < self._max_rounds else None)
                if not reply.tool_calls:
                    break

                messages.append({
                    "role": "assistant",
                    "content": reply.text or "",
                    "tool_calls": [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.name,
                                      "arguments": json.dumps(c.arguments, ensure_ascii=False)}}
                        for c in reply.tool_calls
                    ],
                })
                for call in reply.tool_calls:
                    observation = self._run_tool(call.name, call.arguments, user_text)
                    if not observation.startswith("HATA"):
                        executed.append(call.name)
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": observation})

            text = (reply.text if reply else "").strip()
            if not text:
                text = "Tamamdır." if executed else "Bunu tam anlayamadım, bir daha söyler misin?"

            self._history.append({"role": "user", "content": user_text})
            self._history.append({"role": "assistant", "content": text})

            provider = getattr(reply, "provider", "") if reply else ""
            logger.info("🧠 [%s | %s] %r → %r (araçlar: %s)", provider,
                        self.analyzer.profil().etiket(), user_text, text, ", ".join(executed) or "-")
            return BrainResult(reply=text, executed=tuple(executed), provider=provider)

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
        self.analyzer.sifirla()

    # ------------------------------------------------------------------

    def _run_tool(self, name: str, args: dict, user_text: str) -> str:
        if tool_mod.is_dangerous(name) and not _GUC_ISTEGI.search(user_text):
            logger.warning("Tehlikeli araç açık istek olmadan reddedildi: %s", name)
            return ("HATA: Kullanıcı bunu açıkça istemedi, çalıştırılmadı. "
                    "Gerçekten istiyorsa açıkça söylemesini rica et.")
        try:
            command = tool_mod.build_command(name, args)
        except ValueError as exc:
            return f"HATA: {exc}"

        logger.info("⚡ Araç: %s %s → %s", name, args, type(command).__name__)
        with capture_speech() as captured:
            try:
                result = self._cmd_bus.dispatch(command)
            except Exception as exc:  # CommandBus zaten yakalıyor; yine de güvenlik
                return f"HATA: {exc}"

        if captured.errors:
            return "HATA: " + "; ".join(captured.errors)
        parts = [*captured.texts, *captured.notifications]
        if isinstance(result, (dict, list)) and result:
            parts.append(json.dumps(result, ensure_ascii=False, default=str)[:600])
        return " | ".join(p for p in parts if p) or "Tamamlandı."

    def _provider_label(self) -> str:
        providers = getattr(self._llm, "providers", None)
        if providers:
            return " → ".join(providers)
        return getattr(self._llm, "name", "")

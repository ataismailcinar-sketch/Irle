# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / BRAIN / LLM CLIENT — Hibrit Dil Modeli İstemcisi
=============================================================================
İki tür "beyin" aynı arayüzle konuşur:

  * Bulut  → Groq (ücretsiz katman, kredi kartı gerekmez)
  * Yerel  → Ollama (tamamen çevrimdışı, bilgisayarında çalışır)

İkisi de OpenAI uyumlu `/chat/completions` uç noktası sunduğu için tek bir
istemci sınıfı (`OpenAICompatClient`) yeterli. `HybridLLMClient` sırayla
dener: internet varsa ve kota dolmadıysa bulut, yoksa yerel model.

Harici bağımlılık YOK — sadece standart kütüphane (urllib).
=============================================================================
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

logger = logging.getLogger("irle.adapters.brain.llm")


# ---------------------------------------------------------------------------
# Veri modelleri
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    """Modelin çağırmak istediği tek bir araç."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMReply:
    """Modelin tek turdaki cevabı."""
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    provider: str = ""


class LLMError(Exception):
    """Sağlayıcıya ulaşılamadı veya geçersiz cevap döndü."""

    def __init__(self, message: str, retryable: bool = True, cooldown: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable
        # False → tek seferlik hata (ör. modelin bozuk araç çağrısı); sağlayıcı dinlenmeye alınmaz
        self.cooldown = cooldown


class LLMClient(Protocol):
    name: str

    def chat(self, messages: Sequence[dict], tools: Sequence[dict] | None = None) -> LLMReply:
        ...


# ---------------------------------------------------------------------------
# OpenAI uyumlu istemci (Groq, Ollama, OpenRouter, LM Studio ...)
# ---------------------------------------------------------------------------

class OpenAICompatClient:
    """OpenAI uyumlu `/chat/completions` uç noktasıyla konuşan istemci."""

    def __init__(
        self,
        name: str,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 30.0,
        temperature: float = 0.6,
        transport: Any = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        # Testlerde ağ yerine sahte transport verilebilir: (url, payload, headers, timeout) -> dict
        self._transport = transport or _http_post_json

    def chat(self, messages: Sequence[dict], tools: Sequence[dict] | None = None) -> LLMReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = self._transport(f"{self.base_url}/chat/completions", payload, headers, self.timeout)
        return _parse_reply(data, self.name)


def _http_post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        # 429 = kota doldu, 5xx = sunucu sorunu → başka sağlayıcıya geç
        # 400 = genelde modelin araç çağrısını bozması → yine de diğerini dene
        raise LLMError(f"HTTP {exc.code}: {detail}", retryable=True,
                       cooldown=exc.code in (401, 403, 404, 408, 429) or exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMError(f"Bağlantı yok: {exc}", retryable=True) from exc
    except json.JSONDecodeError as exc:
        raise LLMError(f"Geçersiz JSON: {exc}") from exc


def _parse_reply(data: dict, provider: str) -> LLMReply:
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Beklenmeyen cevap biçimi: {str(data)[:200]}") from exc

    calls: list[ToolCall] = []
    for i, raw in enumerate(message.get("tool_calls") or []):
        fn = raw.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                logger.warning("Araç argümanları çözülemedi: %r", args[:200])
                args = {}
        calls.append(ToolCall(
            id=raw.get("id") or f"call_{i}",
            name=fn.get("name", ""),
            arguments=args if isinstance(args, dict) else {},
        ))

    text = message.get("content") or ""
    return LLMReply(text=_strip_think(text).strip(), tool_calls=tuple(calls), provider=provider)


def _strip_think(text: str) -> str:
    """Bazı yerel modellerin (qwen3, deepseek) <think>...</think> bloğunu atar."""
    while "<think>" in text and "</think>" in text:
        start = text.index("<think>")
        end = text.index("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text


# ---------------------------------------------------------------------------
# Hibrit istemci
# ---------------------------------------------------------------------------

@dataclass
class _ProviderState:
    client: Any
    down_until: float = 0.0
    failures: int = 0


class HybridLLMClient:
    """
    Sağlayıcıları sırayla dener. Biri hata verirse bir süre "dinlenmeye"
    alınır (her istekte boşuna internet beklememek için) ve sıradakine geçilir.
    """

    name = "hibrit"

    def __init__(self, clients: Sequence[Any], cooldown_seconds: float = 120.0,
                 clock: Any = time.monotonic) -> None:
        if not clients:
            raise ValueError("En az bir LLM istemcisi gerekli.")
        self._states = [_ProviderState(c) for c in clients]
        self._cooldown = cooldown_seconds
        self._clock = clock
        self.last_provider: str = ""

    @property
    def providers(self) -> list[str]:
        return [s.client.name for s in self._states]

    def chat(self, messages: Sequence[dict], tools: Sequence[dict] | None = None) -> LLMReply:
        now = self._clock()
        errors: list[str] = []

        # Önce dinlenmede olmayanlar, sonra (hepsi düştüyse) dinlenmedekiler
        ordered = [s for s in self._states if s.down_until <= now] + \
                  [s for s in self._states if s.down_until > now]

        for state in ordered:
            try:
                reply = state.client.chat(messages, tools)
                if state.failures:
                    logger.info("%s tekrar erişilebilir.", state.client.name)
                state.failures = 0
                state.down_until = 0.0
                self.last_provider = state.client.name
                return reply
            except LLMError as exc:
                state.failures += 1
                if exc.cooldown:
                    state.down_until = self._clock() + self._cooldown
                errors.append(f"{state.client.name}: {exc}")
                logger.warning("Beyin sağlayıcısı başarısız (%s): %s", state.client.name, exc)

        raise LLMError("Hiçbir beyne ulaşılamadı → " + " | ".join(errors))

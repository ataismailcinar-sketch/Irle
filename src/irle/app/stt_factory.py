# -*- coding: utf-8 -*-
"""
=============================================================================
APP / STT FACTORY — Ayarlara göre "kulağı" kurar
=============================================================================
  hibrit → Groq Whisper (anahtar varsa) → yerel Whisper (kuruluysa) → Google
  yerel  → sadece yerel Whisper (tamamen çevrimdışı)
  groq   → Groq Whisper → Google
  google → sadece Google (eski davranış)

Yerel model arka planda önceden yüklenir; ilk cümlede beklemezsin.
=============================================================================
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Any

from irle.adapters.speech.stt_adapter import (
    BaseSTTProvider, GoogleSTTProvider, GroqWhisperSTT, HybridSTT, LocalWhisperSTT,
)

logger = logging.getLogger("irle.app.stt_factory")


def _faster_whisper_var() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _google() -> BaseSTTProvider | None:
    try:
        return GoogleSTTProvider()
    except Exception as exc:  # SpeechRecognition kurulu değil
        logger.warning("Google STT kullanılamıyor: %s", exc)
        return None


def build_stt(settings: Any, preload: bool = True) -> BaseSTTProvider:
    mode = (getattr(settings, "stt_mode", "hibrit") or "hibrit").lower()
    groq_key = getattr(settings, "groq_api_key", "")

    groq = GroqWhisperSTT(groq_key, model=settings.groq_stt_model) if groq_key else None
    yerel = (LocalWhisperSTT(settings.whisper_model, device=settings.whisper_device)
             if _faster_whisper_var() else None)

    if mode == "yerel":
        secilen = [yerel]
        if yerel is None:
            logger.warning("Kulak 'yerel' seçildi ama faster-whisper kurulu değil → "
                           "pip install faster-whisper. Şimdilik Google kullanılacak.")
            secilen = [_google()]
    elif mode == "groq":
        secilen = [groq, _google()]
    elif mode == "google":
        secilen = [_google()]
    else:  # hibrit
        secilen = [groq, yerel, _google()]
        if yerel is None:
            logger.info("faster-whisper kurulu değil → internetsiz konuşma tanıma yok "
                        "(pip install faster-whisper).")

    providers = [p for p in secilen if p is not None]
    if not providers:
        raise RuntimeError("Hiçbir konuşma tanıma motoru kullanılamıyor "
                           "(SpeechRecognition veya faster-whisper kurun).")

    if preload and yerel is not None and yerel in providers:
        yerel.hazirla_arka_planda()

    stt = HybridSTT(providers)
    logger.info("🎧 Kulak hazır (%s): %s", mode, " → ".join(stt.providers))
    return stt

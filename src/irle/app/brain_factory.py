# -*- coding: utf-8 -*-
"""
=============================================================================
APP / BRAIN FACTORY — Ayarlara göre beyni kurar
=============================================================================
  hibrit → Groq (anahtar varsa) önce, ulaşılamazsa Ollama
  bulut  → sadece Groq
  yerel  → sadece Ollama (tamamen çevrimdışı)
  kapali → beyin yok, eski regex kural motoru tek başına çalışır
=============================================================================
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from irle.adapters.brain.llm_client import HybridLLMClient, OpenAICompatClient
from irle.app.brain_service import BrainService

logger = logging.getLogger("irle.app.brain_factory")


def build_brain(settings: Any, command_bus: Any) -> Optional[BrainService]:
    mode = (settings.brain_mode or "hibrit").lower()
    if mode in ("kapali", "kapalı", "off", "yok"):
        logger.info("Beyin kapalı — sadece kural motoru kullanılacak.")
        return None

    cloud = None
    if settings.groq_api_key:
        cloud = OpenAICompatClient(
            name=f"groq:{settings.groq_model}",
            base_url=settings.groq_base_url,
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            timeout=settings.cloud_timeout,
        )
    local = OpenAICompatClient(
        name=f"ollama:{settings.ollama_model}",
        base_url=settings.ollama_url,
        model=settings.ollama_model,
        timeout=settings.local_timeout,
    )

    if mode == "bulut":
        if cloud is None:
            logger.warning("Bulut modu seçildi ama GROQ_API_KEY yok → yerel modele düşülüyor.")
            clients = [local]
        else:
            clients = [cloud]
    elif mode == "yerel":
        clients = [local]
    else:  # hibrit
        clients = [c for c in (cloud, local) if c is not None]
        if cloud is None:
            logger.info("GROQ_API_KEY yok → hibrit mod sadece yerel Ollama ile çalışacak.")

    llm = HybridLLMClient(clients)
    logger.info("🧠 Beyin hazır (%s): %s", mode, " → ".join(llm.providers))
    return BrainService(
        llm,
        command_bus,
        asistan_adi=settings.assistant_name,
        kullanici_adi=settings.user_name,
    )

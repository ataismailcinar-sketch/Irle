# -*- coding: utf-8 -*-
"""
=============================================================================
DOMAIN / QUERIES — Typed Sorgu Modelleri
=============================================================================
Query nesneleri sistem durumunu *okuma* talebi belirtir; herhangi bir
yan etki içermez. Handler'lar bu nesneleri alıp uygun veri ile yanıtlar.

Kural:
  - Tüm Query'ler `Query` taban sınıfından türetilir.
  - İsimler İngilizce, GetXxx / ListXxx formatında.
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Taban sınıf
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    """Tüm sorguların taban sınıfı. Yan etki içermez."""


# ---------------------------------------------------------------------------
# Sistem / Donanım
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetBatteryStatus(Query):
    """Pil yüzdesi ve şarj durumunu sorgula."""


@dataclass(frozen=True)
class GetSystemInfo(Query):
    """CPU, RAM, GPU, disk bilgilerini sorgula.

    Args:
        topics: Hangi konular isteniyor.
                Boşsa tüm bilgiler döner.
                Örn: ["cpu", "ram"], ["gpu"], ["disk"]
    """
    topics: tuple[str, ...] = ()


@dataclass(frozen=True)
class GetNetworkStatus(Query):
    """Ağ durumu ve IP adresini sorgula.

    Args:
        include_ping: True ise gecikme ölçümü yapılır.
    """
    include_ping: bool = False


# ---------------------------------------------------------------------------
# Notlar
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ListNotes(Query):
    """Kayıtlı notları listele.

    Args:
        limit: Kaç not gösterilsin (varsayılan: 3).
    """
    limit: int = 3


# ---------------------------------------------------------------------------
# Uygulama Kataloğu
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetAppCatalog(Query):
    """Bilinen/başlatılabilir uygulama listesini getir."""


# ---------------------------------------------------------------------------
# Konuşma Geçmişi
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetConversationHistory(Query):
    """Konuşma geçmişini getir.

    Args:
        limit: Kaç kayıt gösterilsin (varsayılan: 10).
    """
    limit: int = 10


# ---------------------------------------------------------------------------
# Kontrolcü (Telefon)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetControllerStatus(Query):
    """Telefon kontrolcüsünün bağlantı durumunu sorgula."""


# ---------------------------------------------------------------------------
# Saat / Zaman
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetCurrentTime(Query):
    """Şu anki saati sorgula."""


@dataclass(frozen=True)
class GetCurrentDate(Query):
    """Şu anki tarihi sorgula."""


# ---------------------------------------------------------------------------
# Pano
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GetClipboardContent(Query):
    """Pano içeriğini sorgula (okuma amacıyla)."""

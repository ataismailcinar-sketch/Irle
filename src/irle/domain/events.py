# -*- coding: utf-8 -*-
"""
=============================================================================
DOMAIN / EVENTS — Typed Event Modelleri
=============================================================================
Event nesneleri sistemde gerçekleşen bir olayı bildirir.
Modüller arası iletişim event bus üzerinden bu nesnelerle sağlanır.

Kural:
  - Tüm Event'ler `Event` taban sınıfından türetilir.
  - İsimler geçmişte kalmış fiil + isim yapısında (SpeechRecognized, vb.)
  - `@dataclass(frozen=True)` → değiştirilemez mesaj zarfları.
  - Eski string tabanlı event adlarıyla uyumluluk için her sınıfın
    `LEGACY_NAME` sınıf değişkeni vardır.
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import datetime


# ---------------------------------------------------------------------------
# Taban sınıf
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """Tüm olayların taban sınıfı."""

    # Olayın oluştuğu zaman damgası — varsayılan olarak şu an.
    timestamp: datetime.datetime = field(
        default_factory=datetime.datetime.now,
        compare=False,
    )

    #: Eski string tabanlı bus ile uyumluluk için. Alt sınıflar override eder.
    #: Eski string tabanlı bus ile uyumluluk için. Alt sınıflar override eder.
    LEGACY_NAME: str = field(default="", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Eski string tabanlı bus ile uyumluluk için veri sözlüğü."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if k not in ("timestamp",)
        }


# ---------------------------------------------------------------------------
# Ses / Konuşma
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpeechRecognized(Event):
    """Mikrofon metne dönüştürüldü ve metni hazır."""
    text: str = ""
    LEGACY_NAME: str = field(default="ses_algilandi", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"metin": self.text}


@dataclass(frozen=True)
class SpeechRecognitionFailed(Event):
    """Ses tanıma başarısız oldu."""
    reason: str = ""
    LEGACY_NAME: str = field(default="ses_hata", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"hata": self.reason}


# ---------------------------------------------------------------------------
# Intent / Niyet Çözümleme
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntentResolved(Event):
    """Ses metninden niyet başarıyla çözümlendi, komut hazır."""
    source_text: str = ""
    command_type: str = ""   # komutun sınıf adı (örn: "OpenApplication")
    LEGACY_NAME: str = field(default="niyet_cozumlendi", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"metin": self.source_text, "komut": self.command_type}


@dataclass(frozen=True)
class IntentUnresolved(Event):
    """Niyet çözümlenemedi — hiçbir kural eşleşmedi."""
    source_text: str = ""
    LEGACY_NAME: str = field(default="niyet_cozumlenemedi", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"metin": self.source_text}


# ---------------------------------------------------------------------------
# Komut Yaşam Döngüsü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandRequested(Event):
    """Bir komut yürütme talebi oluştu."""
    command_type: str = ""
    LEGACY_NAME: str = field(default="komut_talep_edildi", init=False, repr=False, compare=False)


@dataclass(frozen=True)
class CommandCompleted(Event):
    """Komut başarıyla tamamlandı."""
    command_type: str = ""
    result: Any = field(default=None, compare=False)
    LEGACY_NAME: str = field(default="komut_tamamlandi", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"komut": self.command_type, "sonuc": self.result}


@dataclass(frozen=True)
class CommandFailed(Event):
    """Komut yürütme başarısız oldu."""
    command_type: str = ""
    error: str = ""
    LEGACY_NAME: str = field(default="komut_basarisiz", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"komut": self.command_type, "hata": self.error}


# ---------------------------------------------------------------------------
# TTS (Text-to-Speech)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TtsRequested(Event):
    """TTS motoru bir metni seslendirmesi için çağrıldı."""
    text: str = ""
    LEGACY_NAME: str = field(default="tts_konuş", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"metin": self.text}


@dataclass(frozen=True)
class TtsCompleted(Event):
    """TTS motoru seslendirmeyi tamamladı."""
    text: str = ""
    LEGACY_NAME: str = field(default="tts_tamamlandi", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"metin": self.text}


# ---------------------------------------------------------------------------
# Asistan Yanıtı
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssistantReplied(Event):
    """Asistan kullanıcıya yanıt verdi (GUI güncellemesi için)."""
    action: str = ""       # "konuş" | "uygulama_ac" | ...
    reply_text: str = ""
    LEGACY_NAME: str = field(default="asistan_yanit_verdi", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"aksiyon": self.action, "yanit": self.reply_text}


# ---------------------------------------------------------------------------
# Bildirim
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Notification(Event):
    """Kullanıcıya genel amaçlı bildirim."""
    title: str = ""
    message: str = ""
    level: str = "info"  # "info" | "warning" | "error"
    LEGACY_NAME: str = field(default="bildirim", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"baslik": self.title, "mesaj": self.message, "seviye": self.level}


# ---------------------------------------------------------------------------
# Kontrolcü (Telefon)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ControllerConnected(Event):
    """Telefon kontrolcüsü bağlandı."""
    device_id: str = ""
    ip_address: str = ""
    LEGACY_NAME: str = field(default="kontrolcu_baglandi", init=False, repr=False, compare=False)


@dataclass(frozen=True)
class ControllerDisconnected(Event):
    """Telefon kontrolcüsü bağlantısı kesildi."""
    device_id: str = ""
    LEGACY_NAME: str = field(default="kontrolcu_ayrildi", init=False, repr=False, compare=False)


# ---------------------------------------------------------------------------
# Bellek
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemorySaveRequested(Event):
    """Konuşma belleğine yeni kayıt eklenmesi talep edildi."""
    role: str = ""    # "kullanici" | "asistan"
    text: str = ""
    LEGACY_NAME: str = field(default="bellek_kaydet", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"rol": self.role, "metin": self.text}


# ---------------------------------------------------------------------------
# Uygulama
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplicationOpenRequested(Event):
    """Uygulama açma talebi (eski event bus uyumluluğu için)."""
    app_name: str = ""
    source_text: str = ""
    LEGACY_NAME: str = field(default="uygulama_ac", init=False, repr=False, compare=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        return {"uygulama": self.app_name, "kaynak": self.source_text}

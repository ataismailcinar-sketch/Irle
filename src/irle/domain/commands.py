# -*- coding: utf-8 -*-
"""
=============================================================================
DOMAIN / COMMANDS — Typed Komut Modelleri
=============================================================================
Her Command nesnesi bir *niyet*i temsil eder. Hiçbir OS işlemi içermez.
Handler'lar bu nesneleri alıp ilgili işlemi gerçekleştirir.

Kural:
  - Tüm Command'lar `Command` taban sınıfından türetilir.
  - `@dataclass(frozen=True)` → değiştirilemez, hashlenebilir.
  - İsimler İngilizce ve emir kipinde: OpenApplication, Speak, SetVolume...
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Taban sınıf
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Command:
    """Tüm komutların taban sınıfı. İş mantığı içermez."""


@dataclass(frozen=True)
class CompositeCommand(Command):
    """
    Sıralı yürütülecek birden fazla komutu temsil eden bileşik komut.
    Örnek: "Spotify'ı aç ve sesi kıs" -> CompositeCommand((OpenApplication("spotify"), SetVolume(delta=-10)))
    """
    commands: tuple[Command, ...]


# ---------------------------------------------------------------------------
# Konuşma / Ses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Speak(Command):
    """TTS motoru üzerinden metni seslendir."""
    text: str


# ---------------------------------------------------------------------------
# Uygulama Yönetimi
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OpenApplication(Command):
    """Belirtilen uygulamayı başlat.

    Args:
        name: Uygulamanın adı veya yürütülebilir dosya adı
              (örn: "notepad", "chrome", "spotify").
    """
    name: str


@dataclass(frozen=True)
class CloseApplication(Command):
    """Belirtilen uygulamayı kapat."""
    name: str


# ---------------------------------------------------------------------------
# Ses Kontrolü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetVolume(Command):
    """Sistem ses seviyesini ayarla.

    Args:
        level: Mutlak seviye (0-100). Belirtilmezse delta kullanılır.
        delta: Göreli değişim (+/-). level ile birlikte kullanılmaz.
    """
    level: Optional[int] = None
    delta: Optional[int] = None

    def __post_init__(self) -> None:
        if self.level is None and self.delta is None:
            raise ValueError("SetVolume: level veya delta belirtilmelidir.")
        if self.level is not None and not (0 <= self.level <= 100):
            raise ValueError(f"SetVolume.level {self.level} geçersiz (0-100 arası olmalı).")


@dataclass(frozen=True)
class MuteVolume(Command):
    """Sesi sustur (toggle)."""


# ---------------------------------------------------------------------------
# Parlaklık Kontrolü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetBrightness(Command):
    """Ekran parlaklığını ayarla.

    Args:
        level: Mutlak seviye (0-100). Belirtilmezse delta kullanılır.
        delta: Göreli değişim (+/-). level ile birlikte kullanılmaz.
    """
    level: Optional[int] = None
    delta: Optional[int] = None

    def __post_init__(self) -> None:
        if self.level is None and self.delta is None:
            raise ValueError("SetBrightness: level veya delta belirtilmelidir.")


# ---------------------------------------------------------------------------
# Medya Kontrolü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MediaControl(Command):
    """Medya oynatıcıyı kontrol et.

    Args:
        action: "play_pause" | "next" | "previous" | "volume_up" | "volume_down"
    """
    action: str  # "play_pause" | "next" | "previous" | "volume_up" | "volume_down"


# ---------------------------------------------------------------------------
# Fare Kontrolü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MouseMove(Command):
    """Fareyi göreli olarak hareket ettir."""
    dx: float
    dy: float


@dataclass(frozen=True)
class MouseClick(Command):
    """Fare tuşuna tıkla."""
    button: str = "left"  # "left" | "right" | "middle"


# ---------------------------------------------------------------------------
# Not İşlemleri
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreateNote(Command):
    """Yeni not oluştur."""
    text: str


@dataclass(frozen=True)
class DeleteNote(Command):
    """Not sil.

    Args:
        mode: "last" → son notu sil, "all" → tüm notları sil.
    """
    mode: str = "last"  # "last" | "all"


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchWeb(Command):
    """Varsayılan tarayıcıda web araması yap."""
    query: str


# ---------------------------------------------------------------------------
# Sistem Gücü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShutdownComputer(Command):
    """Bilgisayarı kapat."""
    delay_seconds: int = 60


@dataclass(frozen=True)
class RestartComputer(Command):
    """Bilgisayarı yeniden başlat."""
    delay_seconds: int = 60


@dataclass(frozen=True)
class LockComputer(Command):
    """Ekranı kilitle."""


@dataclass(frozen=True)
class CancelShutdown(Command):
    """Planlanmış kapatmayı iptal et."""


# ---------------------------------------------------------------------------
# Pencere Yönetimi
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowControl(Command):
    """Pencereyi kontrol et.

    Args:
        app_name: Hedef uygulamanın adı (kısmi eşleşme kabul edilir).
        action:   "focus" | "maximize" | "minimize" | "close"
    """
    app_name: str
    action: str  # "focus" | "maximize" | "minimize" | "close"


@dataclass(frozen=True)
class KillProcess(Command):
    """İşlemi zorla sonlandır."""
    process_name: str


# ---------------------------------------------------------------------------
# Ekran Görüntüsü
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TakeScreenshot(Command):
    """Ekran görüntüsü al.

    Args:
        save_path: Kaydedilecek dosya yolu. None → masaüstü (varsayılan).
    """
    save_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Pano
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReadClipboard(Command):
    """Pano içeriğini oku ve seslendir."""


@dataclass(frozen=True)
class ClearClipboard(Command):
    """Panoyu temizle."""


# ---------------------------------------------------------------------------
# Dosya İşlemleri
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SearchFile(Command):
    """Masaüstünde dosya ara."""
    term: str


@dataclass(frozen=True)
class CreateFolder(Command):
    """Masaüstünde klasör oluştur."""
    name: str


# ---------------------------------------------------------------------------
# Zamanlayıcı
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScheduleCommand(Command):
    """Belirtilen süre sonra bir komutu çalıştır."""
    delay_seconds: int
    inner_command_text: str  # parse edilecek orijinal metin


@dataclass(frozen=True)
class CancelAllTimers(Command):
    """Tüm aktif zamanlayıcıları iptal et."""

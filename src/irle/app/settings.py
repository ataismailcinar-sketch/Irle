# -*- coding: utf-8 -*-
"""
=============================================================================
APP / SETTINGS — Uygulama Yapılandırması
=============================================================================
Tüm ayarlar ortam değişkenlerinden okunur. Kaynak kodda sır (secret)
saklanmaz.

Ortam değişkenleri (hepsi opsiyonel):
    IRLE_TTS_RATE         — TTS konuşma hızı kelime/dakika (varsayılan: 165)
    IRLE_TTS_VOLUME       — TTS ses seviyesi 0.0-1.0 (varsayılan: 1.0)
    IRLE_TTS_VOICE_NAME   — Tercih edilen ses adı (boşsa sistem varsayılanı)
    IRLE_SILENT_MODE      — "true"/"1" ise TTS sessize alınır
    IRLE_MEMORY_FILE      — Konuşma belleği dosya yolu
    IRLE_MEMORY_MAX       — Maksimum bellek kaydı (varsayılan: 500)
    IRLE_CAMERA_ID        — Kamera indeksi (varsayılan: 0)
    IRLE_LOG_LEVEL        — Log seviyesi: DEBUG/INFO/WARNING (varsayılan: INFO)
    IRLE_SPEECH_LANG      — Ses tanıma dili (varsayılan: tr-TR)

  Beyin (hibrit dil modeli):
    IRLE_BEYIN_MODU       — hibrit | bulut | yerel | kapali (varsayılan: hibrit)
    GROQ_API_KEY          — Groq ücretsiz anahtarı (console.groq.com); yoksa sadece yerel
    IRLE_GROQ_MODEL       — varsayılan: llama-3.3-70b-versatile
    IRLE_OLLAMA_URL       — varsayılan: http://localhost:11434/v1
    IRLE_OLLAMA_MODEL     — varsayılan: qwen2.5:7b
    IRLE_ASISTAN_ADI      — varsayılan: İrle
    IRLE_KULLANICI_ADI    — Asistanın sana hitap edeceği ad (opsiyonel)
    IRLE_SES_MOTORU       — auto | piper | pyttsx3 (varsayılan: auto)
    IRLE_PIPER_SES        — Piper ses adı ya da .onnx yolu (boşsa data/sesler'deki ilk Türkçe ses)
    IRLE_PIPER_HIZ        — Konuşma hızı çarpanı, 1.0 normal, 1.2 hızlı (varsayılan: 1.0)
    IRLE_KULAK            — hibrit | yerel | groq | google (varsayılan: hibrit)
    IRLE_WHISPER_MODEL    — yerel Whisper modeli: tiny/base/small/medium/turbo (varsayılan: small)
    IRLE_WHISPER_CIHAZ    — auto | cuda | cpu (varsayılan: auto)
    IRLE_KESME            — İrle konuşurken "dur/sus" ile kesme (varsayılan: true)
    IRLE_UYANDIRMA        — Uyandırma kelimesi (ör. "irle"); boşsa her cümle işlenir
    IRLE_UYANDIRMA_PENCERE— Cevaptan sonra kelimesiz devam süresi, sn (varsayılan: 20)

  Bu değişkenler proje kökündeki `.env` dosyasından da okunur.

Kullanım:
    from irle.app.settings import Settings
    s = Settings()          # ortam değişkenlerinden yükler
    print(s.tts_rate)       # 165
=============================================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").lower()
    if val in ("true", "1", "yes", "evet"):
        return True
    if val in ("false", "0", "no", "hayır", ""):
        return default
    return default


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float) -> float:
    val = os.getenv(key, "")
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


@dataclass
class Settings:
    """Irle uygulama ayarları — ortam değişkenlerinden yüklenir."""

    # ------------------------------------------------------------------
    # TTS
    # ------------------------------------------------------------------
    tts_rate: int = field(default_factory=lambda: _env_int("IRLE_TTS_RATE", 165))
    tts_volume: float = field(default_factory=lambda: _env_float("IRLE_TTS_VOLUME", 1.0))
    tts_voice_name: str = field(default_factory=lambda: os.getenv("IRLE_TTS_VOICE_NAME", ""))
    tts_silent_mode: bool = field(default_factory=lambda: _env_bool("IRLE_SILENT_MODE", False))

    # ------------------------------------------------------------------
    # Ses Tanıma
    # ------------------------------------------------------------------
    speech_language: str = field(default_factory=lambda: os.getenv("IRLE_SPEECH_LANG", "tr-TR"))
    speech_noise_calibration_seconds: int = field(
        default_factory=lambda: _env_int("IRLE_NOISE_CALIB", 1)
    )
    speech_timeout_seconds: int = field(
        default_factory=lambda: _env_int("IRLE_SPEECH_TIMEOUT", 5)
    )
    speech_phrase_seconds: int = field(
        default_factory=lambda: _env_int("IRLE_SPEECH_PHRASE", 10)
    )

    # ------------------------------------------------------------------
    # Bellek
    # ------------------------------------------------------------------
    memory_file: str = field(
        default_factory=lambda: os.getenv("IRLE_MEMORY_FILE", "data/konusmalar.json")
    )
    memory_max_records: int = field(default_factory=lambda: _env_int("IRLE_MEMORY_MAX", 500))

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------
    camera_id: int = field(default_factory=lambda: _env_int("IRLE_CAMERA_ID", 0))
    vision_confidence: float = field(
        default_factory=lambda: _env_float("IRLE_VISION_CONFIDENCE", 0.5)
    )
    vision_debug: bool = field(default_factory=lambda: _env_bool("IRLE_VISION_DEBUG", True))

    # ------------------------------------------------------------------
    # Genel
    # ------------------------------------------------------------------
    log_level: str = field(default_factory=lambda: os.getenv("IRLE_LOG_LEVEL", "INFO"))
    notes_file: str = field(
        default_factory=lambda: os.getenv("IRLE_NOTES_FILE", "data/notlar.json")
    )

    # ------------------------------------------------------------------
    # Beyin (hibrit LLM)
    # ------------------------------------------------------------------
    brain_mode: str = field(
        default_factory=lambda: os.getenv("IRLE_BEYIN_MODU", "hibrit").strip().lower()
    )
    groq_api_key: str = field(
        default_factory=lambda: os.getenv("GROQ_API_KEY", "") or os.getenv("IRLE_GROQ_API_KEY", "")
    )
    groq_model: str = field(
        default_factory=lambda: os.getenv("IRLE_GROQ_MODEL", "llama-3.3-70b-versatile")
    )
    groq_base_url: str = field(
        default_factory=lambda: os.getenv("IRLE_GROQ_URL", "https://api.groq.com/openai/v1")
    )
    ollama_url: str = field(
        default_factory=lambda: os.getenv("IRLE_OLLAMA_URL", "http://localhost:11434/v1")
    )
    ollama_model: str = field(default_factory=lambda: os.getenv("IRLE_OLLAMA_MODEL", "qwen2.5:7b"))
    cloud_timeout: float = field(default_factory=lambda: _env_float("IRLE_BULUT_TIMEOUT", 12.0))
    local_timeout: float = field(default_factory=lambda: _env_float("IRLE_YEREL_TIMEOUT", 90.0))
    # Ses (TTS)
    tts_engine: str = field(default_factory=lambda: os.getenv("IRLE_SES_MOTORU", "auto").strip().lower())
    piper_voice: str = field(default_factory=lambda: os.getenv("IRLE_PIPER_SES", "").strip())
    piper_speed: float = field(default_factory=lambda: _env_float("IRLE_PIPER_HIZ", 1.0))
    # Kulak (konuşmayı metne çevirme)
    stt_mode: str = field(default_factory=lambda: os.getenv("IRLE_KULAK", "hibrit").strip().lower())
    whisper_model: str = field(default_factory=lambda: os.getenv("IRLE_WHISPER_MODEL", "small"))
    whisper_device: str = field(default_factory=lambda: os.getenv("IRLE_WHISPER_CIHAZ", "auto"))
    groq_stt_model: str = field(
        default_factory=lambda: os.getenv("IRLE_GROQ_STT_MODEL", "whisper-large-v3-turbo")
    )
    barge_in: bool = field(default_factory=lambda: _env_bool("IRLE_KESME", True))
    wake_word: str = field(default_factory=lambda: os.getenv("IRLE_UYANDIRMA", "").strip())
    wake_window: float = field(default_factory=lambda: _env_float("IRLE_UYANDIRMA_PENCERE", 20.0))
    assistant_name: str = field(default_factory=lambda: os.getenv("IRLE_ASISTAN_ADI", "İrle"))
    user_name: str = field(default_factory=lambda: os.getenv("IRLE_KULLANICI_ADI", ""))

    # ------------------------------------------------------------------
    # Uygulama Komutları (sabit liste — ortam değişkeniyle override edilmez)
    # ------------------------------------------------------------------
    app_commands: dict[str, str] = field(default_factory=lambda: {
        "notepad":  "notepad.exe",
        "hesap":    "calc.exe",
        "explorer": "explorer.exe",
        "chrome":   "chrome.exe",
        "terminal": "cmd.exe",
    })

    def __repr__(self) -> str:
        return (
            f"Settings("
            f"tts_rate={self.tts_rate}, "
            f"tts_silent_mode={self.tts_silent_mode}, "
            f"speech_language={self.speech_language!r}, "
            f"log_level={self.log_level!r}, "
            f"brain_mode={self.brain_mode!r}, "
            f"groq_api_key={'***' if self.groq_api_key else '(yok)'}"
            f")"
        )


def load_dotenv(path: str = ".env") -> int:
    """Basit .env okuyucu (harici paket gerektirmez).

    Satır biçimi: ANAHTAR=deger  (# ile başlayan satırlar yorum).
    Zaten tanımlı ortam değişkenlerinin üzerine YAZMAZ.

    Returns:
        Yüklenen değişken sayısı.
    """
    if not os.path.exists(path):
        return 0
    loaded = 0
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.lower().startswith("export "):
                key = key[7:].strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            if key and key not in os.environ:
                os.environ[key] = value
                loaded += 1
    return loaded

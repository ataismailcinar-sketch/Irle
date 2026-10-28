# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / SPEECH / STT ADAPTER — Konuşma Tanıma (Hibrit Kulak)
=============================================================================
Sağlayıcılar:
  - GroqWhisperSTT     → Groq'un ücretsiz Whisper large-v3-turbo'su (internet)
  - LocalWhisperSTT    → faster-whisper, bilgisayarında çalışır (çevrimdışı)
  - GoogleSTTProvider  → eski Google Speech (internet, anahtarsız)
  - HybridSTT          → sırayla dener; ulaşılamayanı bir süre dinlenmeye alır

Önemli kural: bir sağlayıcı "konuşma yok" (None) derse SONRAKİNE GEÇİLMEZ.
Yoksa her kapı gıcırtısı üç servise birden gönderilirdi. Sadece sağlayıcının
kendisi çalışmazsa (internet yok, model yok, kota doldu) sıradakine geçilir.

Whisper'ın Türkçe "halüsinasyonları" süzülür: sessizlikte "Altyazı M.K.",
"İzlediğiniz için teşekkürler", "Abone olmayı unutmayın" gibi metinler uydurur.
=============================================================================
"""

from __future__ import annotations

import abc
import io
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from typing import Any, Callable, Optional, Sequence

logger = logging.getLogger("irle.adapters.speech.stt")


class STTUnavailable(Exception):
    """Sağlayıcı şu an kullanılamıyor (internet yok, model yok, kota doldu...)."""


class BaseSTTProvider(abc.ABC):
    """Tüm STT motorlarının uyması gereken temel arayüz (Interface)."""

    name: str = "stt"

    @abc.abstractmethod
    def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        sample_width: int = 2,
        language: str = "tr-TR",
    ) -> Optional[str]:
        """Ham ses verisini metne dönüştürür. Konuşma yoksa None döner."""


# ---------------------------------------------------------------------------
# Halüsinasyon süzgeci
# ---------------------------------------------------------------------------

_HALUSINASYON = re.compile(
    r"(altyaz[ıi]|alt yaz[ıi]|izledi[gğ]iniz i[cç]in|abone ol|"
    r"kanal[ıi]ma|be[gğ]enmeyi unutma|bir sonraki videoda|videoyu be[gğ]en|"
    r"subtitles|amara\.org|transcribed by|thanks for watching|\[m[uü]zik\]|\(m[uü]zik\)|"
    r"\[alk[ıi][sş]\]|^\W*$)",
    re.IGNORECASE,
)


def halusinasyon_mu(metin: str) -> bool:
    metin = (metin or "").strip()
    if not metin:
        return True
    if _HALUSINASYON.search(metin):
        return True
    # "Teşekkürler. Teşekkürler. Teşekkürler." gibi tekrar döngüleri
    kelimeler = re.findall(r"\w+", metin.lower())
    if len(kelimeler) >= 6 and len(set(kelimeler)) <= len(kelimeler) // 3:
        return True
    return False


def _segmentleri_suz(segmentler: Sequence[Any], no_speech_esik: float = 0.6,
                     logprob_esik: float = -1.0) -> str:
    """Whisper segmentlerinden güvenilir olanları birleştirir (dict ya da nesne)."""
    parcalar = []
    for s in segmentler:
        al = (lambda k, v=None: s.get(k, v)) if isinstance(s, dict) else (lambda k, v=None: getattr(s, k, v))
        metin = (al("text", "") or "").strip()
        nsp = al("no_speech_prob", 0.0) or 0.0
        lp = al("avg_logprob", 0.0) or 0.0
        if nsp > no_speech_esik and lp < logprob_esik:
            continue
        if metin and not halusinasyon_mu(metin):
            parcalar.append(metin)
    return " ".join(parcalar).strip()


def _wav_bayt(audio_bytes: bytes, sample_rate: int, sample_width: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(audio_bytes)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Google (eski, anahtarsız)
# ---------------------------------------------------------------------------

class GoogleSTTProvider(BaseSTTProvider):
    """Google Speech Recognition sağlayıcısı."""

    name = "google"

    def __init__(self) -> None:
        import speech_recognition as sr
        self._recognizer = sr.Recognizer()

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2,
                   language: str = "tr-TR") -> Optional[str]:
        import speech_recognition as sr
        audio_data = sr.AudioData(audio_bytes, sample_rate, sample_width)
        try:
            text = self._recognizer.recognize_google(audio_data, language=language)
            return text.strip() if text else None
        except sr.UnknownValueError:
            logger.debug("Google STT: Ses anlaşılamadı.")
            return None
        except sr.RequestError as exc:
            logger.error(f"Google STT servis hatası: {exc}")
            raise STTUnavailable(f"google: {exc}") from exc
        except Exception as exc:
            logger.error(f"Google STT genel hatası: {exc}")
            return None


# ---------------------------------------------------------------------------
# Groq Whisper (ücretsiz bulut)
# ---------------------------------------------------------------------------

class GroqWhisperSTT(BaseSTTProvider):
    """Groq Whisper large-v3-turbo — ücretsiz katman, çok iyi Türkçe."""

    name = "groq-whisper"

    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo",
                 base_url: str = "https://api.groq.com/openai/v1", timeout: float = 10.0,
                 transport: Optional[Callable[[str, bytes, dict, float], dict]] = None) -> None:
        if not api_key:
            raise ValueError("Groq Whisper için GROQ_API_KEY gerekli")
        self._key = api_key
        self._model = model
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._timeout = timeout
        self._transport = transport or _post_multipart

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2,
                   language: str = "tr-TR") -> Optional[str]:
        alanlar = {
            "model": self._model,
            "language": language.split("-")[0],
            "response_format": "verbose_json",
            "temperature": "0",
        }
        govde, sinir = _multipart(alanlar, "ses.wav", _wav_bayt(audio_bytes, sample_rate, sample_width))
        headers = {"Authorization": f"Bearer {self._key}",
                   "Content-Type": f"multipart/form-data; boundary={sinir}"}
        data = self._transport(self._url, govde, headers, self._timeout)
        segmentler = data.get("segments")
        metin = _segmentleri_suz(segmentler) if segmentler is not None else (data.get("text") or "").strip()
        if halusinasyon_mu(metin):
            return None
        return metin


def _multipart(alanlar: dict, dosya_adi: str, dosya: bytes) -> tuple[bytes, str]:
    sinir = "irle" + uuid.uuid4().hex
    parcalar: list[bytes] = []
    for k, v in alanlar.items():
        parcalar.append(f'--{sinir}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parcalar.append(
        f'--{sinir}\r\nContent-Disposition: form-data; name="file"; filename="{dosya_adi}"\r\n'
        f"Content-Type: audio/wav\r\n\r\n".encode() + dosya + b"\r\n")
    parcalar.append(f"--{sinir}--\r\n".encode())
    return b"".join(parcalar), sinir


def _post_multipart(url: str, govde: bytes, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=govde, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detay = ""
        try:
            detay = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise STTUnavailable(f"HTTP {exc.code}: {detay}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise STTUnavailable(f"bağlantı yok: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise STTUnavailable(f"geçersiz cevap: {exc}") from exc


# ---------------------------------------------------------------------------
# Yerel Whisper (faster-whisper, çevrimdışı)
# ---------------------------------------------------------------------------

class LocalWhisperSTT(BaseSTTProvider):
    """
    faster-whisper ile tamamen çevrimdışı tanıma.

    device="auto": önce ekran kartı (CUDA) denenir; CUDA kütüphaneleri yoksa
    otomatik olarak işlemciye (int8) geçilir. Model ilk kullanımda internetten
    bir kez indirilir, sonra önbellekten (~/.cache/huggingface) yüklenir.
    """

    name = "yerel-whisper"

    def __init__(self, model_size: str = "small", device: str = "auto",
                 beam_size: int = 3, model_factory: Optional[Callable[..., Any]] = None) -> None:
        self.model_size = model_size
        self.device = device
        self.beam_size = beam_size
        self._factory = model_factory
        self._model: Any = None
        self._aktif_cihaz = ""
        self._hata: Optional[str] = None
        self._lock = threading.Lock()

    # -- yükleme --------------------------------------------------------

    def _yukle(self, cihaz: str) -> Any:
        if cihaz == "cuda":
            _nvidia_dll_yollarini_ekle()
        factory = self._factory
        if factory is None:
            from faster_whisper import WhisperModel  # type: ignore
            factory = WhisperModel
        compute = "int8_float16" if cihaz == "cuda" else "int8"
        return factory(self.model_size, device=cihaz, compute_type=compute)

    def hazirla(self) -> bool:
        """Modeli yükler (arka planda önceden çağrılabilir). Başarılıysa True."""
        with self._lock:
            if self._model is not None:
                return True
            if self._hata is not None:
                return False
            adaylar = ["cuda", "cpu"] if self.device == "auto" else [self.device]
            son_hata = ""
            for cihaz in adaylar:
                try:
                    t0 = time.monotonic()
                    self._model = self._yukle(cihaz)
                    self._aktif_cihaz = cihaz
                    logger.info("🎧 Yerel Whisper hazır: %s / %s (%.1f sn)", self.model_size, cihaz,
                                time.monotonic() - t0)
                    return True
                except ImportError as exc:
                    self._hata = "faster-whisper kurulu değil (pip install faster-whisper)"
                    logger.warning("Yerel Whisper kullanılamıyor: %s", self._hata)
                    return False
                except Exception as exc:
                    son_hata = f"{cihaz}: {exc}"
                    logger.info("Whisper %s üzerinde yüklenemedi (%s)%s", cihaz, exc,
                                ", işlemciye geçiliyor" if cihaz == "cuda" else "")
            self._hata = son_hata or "model yüklenemedi"
            logger.warning("Yerel Whisper kullanılamıyor: %s", self._hata)
            return False

    def hazirla_arka_planda(self) -> None:
        threading.Thread(target=self.hazirla, name="WhisperLoader", daemon=True).start()

    # -- tanıma ---------------------------------------------------------

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2,
                   language: str = "tr-TR") -> Optional[str]:
        if not self.hazirla():
            raise STTUnavailable(self._hata or "yerel model yok")
        import numpy as np
        ses = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_rate != 16000:
            # basit yeniden örnekleme (doğrusal) — Whisper 16 kHz ister
            hedef = int(len(ses) * 16000 / sample_rate)
            ses = np.interp(np.linspace(0, len(ses), hedef, endpoint=False), np.arange(len(ses)), ses)
            ses = ses.astype(np.float32)
        try:
            segmentler, _ = self._model.transcribe(
                ses, language=language.split("-")[0], beam_size=self.beam_size,
                vad_filter=True, condition_on_previous_text=False, temperature=0.0,
            )
            segmentler = list(segmentler)
        except Exception as exc:
            # Ekran kartı kütüphanesi (cuBLAS/cuDNN) sorunları ilk tanımada çıkar → işlemciye geç
            if self._aktif_cihaz == "cuda" and re.search(r"cu(blas|dnn|da)|dll", str(exc), re.IGNORECASE):
                logger.warning("Whisper ekran kartında çalışmadı (%s), işlemciye geçiliyor.", exc)
                with self._lock:
                    self._model = self._yukle("cpu")
                    self._aktif_cihaz = "cpu"
                return self.transcribe(audio_bytes, sample_rate, sample_width, language)
            raise STTUnavailable(f"yerel whisper hatası: {exc}") from exc
        metin = _segmentleri_suz(segmentler)
        return None if halusinasyon_mu(metin) else metin


def _nvidia_dll_yollarini_ekle() -> None:
    """Windows: pip ile kurulan nvidia-cublas-cu12 / nvidia-cudnn-cu12 DLL'lerini bulunur yap."""
    import os
    import sys
    if sys.platform != "win32":
        return
    import importlib.util
    for paket in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime"):
        try:
            spec = importlib.util.find_spec(paket)
        except (ImportError, ValueError):
            continue
        for kok in (spec.submodule_search_locations or []) if spec else []:
            bin_dizin = os.path.join(kok, "bin")
            if os.path.isdir(bin_dizin):
                try:
                    os.add_dll_directory(bin_dizin)  # type: ignore[attr-defined]
                except OSError:
                    pass
                os.environ["PATH"] = bin_dizin + os.pathsep + os.environ.get("PATH", "")


# Eski ad (geriye dönük uyumluluk)
class WhisperSTTProvider(LocalWhisperSTT):
    def __init__(self, model_size: str = "base", use_api: bool = False, api_key: Optional[str] = None) -> None:
        super().__init__(model_size=model_size, device="cpu")


# ---------------------------------------------------------------------------
# Hibrit
# ---------------------------------------------------------------------------

class HybridSTT(BaseSTTProvider):
    """Sağlayıcıları sırayla dener; çalışmayanı `cooldown` saniye dinlenmeye alır."""

    name = "hibrit"

    def __init__(self, providers: Sequence[BaseSTTProvider], cooldown_seconds: float = 120.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if not providers:
            raise ValueError("En az bir STT sağlayıcısı gerekli")
        self._providers = list(providers)
        self._down_until = {id(p): 0.0 for p in self._providers}
        self._cooldown = cooldown_seconds
        self._clock = clock
        self.last_provider = ""

    @property
    def providers(self) -> list[str]:
        return [getattr(p, "name", type(p).__name__) for p in self._providers]

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2,
                   language: str = "tr-TR") -> Optional[str]:
        now = self._clock()
        sirali = [p for p in self._providers if self._down_until[id(p)] <= now] + \
                 [p for p in self._providers if self._down_until[id(p)] > now]
        hatalar = []
        for p in sirali:
            ad = getattr(p, "name", type(p).__name__)
            try:
                metin = p.transcribe(audio_bytes, sample_rate, sample_width, language)
                self._down_until[id(p)] = 0.0
                self.last_provider = ad
                if metin:
                    logger.debug("STT [%s] → %r", ad, metin)
                return metin or None          # konuşma yoksa diğerlerine SORMA
            except Exception as exc:
                self._down_until[id(p)] = self._clock() + self._cooldown
                hatalar.append(f"{ad}: {exc}")
                logger.warning("Kulak sağlayıcısı başarısız (%s): %s", ad, exc)
        logger.error("Hiçbir kulak çalışmadı → %s", " | ".join(hatalar))
        return None


class FallbackSTTProvider(BaseSTTProvider):
    """
    Birincil STT sağlayıcısı (örn: Whisper veya Google) başarısız olduğunda
    otomatik olarak ikincil sağlayıcıya geçer.
    """

    def __init__(self, primary: BaseSTTProvider, fallback: BaseSTTProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000, sample_width: int = 2,
                   language: str = "tr-TR") -> Optional[str]:
        try:
            result = self.primary.transcribe(audio_bytes, sample_rate, sample_width, language)
            if result:
                return result
        except Exception as exc:
            logger.warning("Birincil STT motoru başarısız (%s), fallback motora geçiliyor...", exc)

        logger.debug("Fallback STT motoru çalıştırılıyor...")
        return self.fallback.transcribe(audio_bytes, sample_rate, sample_width, language)

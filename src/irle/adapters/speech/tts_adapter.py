# -*- coding: utf-8 -*-
"""
=============================================================================
ADAPTERS / SPEECH / TTS ADAPTER — İrle'nin Sesi
=============================================================================
  - PiperTTS     → doğal Türkçe nöral ses, tamamen çevrimdışı (önerilen)
  - Pyttsx3TTS   → Windows'un kendi sesi (SAPI5), yedek

İkisi de aynı arayüzü sunar: `konus(metin)` metni seslendirir ve çalma
bitene kadar BLOKLAR (yankı kilidinin doğru çalışması için önemli).

`metni_hazirla` sesli okumaya uygun hale getirir: emoji/markdown temizliği,
"%45" → "yüzde 45", "12:08" → "12 08", kısaltmalar...
=============================================================================
"""

from __future__ import annotations

import glob
import logging
import os
import re
import threading
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("irle.adapters.speech.tts")


# ---------------------------------------------------------------------------
# Metin hazırlama
# ---------------------------------------------------------------------------

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\U00002B00-\U00002BFF️‍]+")
_KISALTMA = {
    r"\bvb\.": "ve benzeri", r"\bvs\.": "vesaire", r"\bdk\b": "dakika", r"\bsn\b": "saniye",
    r"\bGB\b": "gigabayt", r"\bMB\b": "megabayt", r"\bCPU\b": "işlemci", r"\bRAM\b": "ram",
    r"\bPC\b": "bilgisayar", r"\bVS Code\b": "vi es kod", r"\bİrle\b": "İrle",
}


def metni_hazirla(metin: str) -> str:
    s = metin or ""
    s = re.sub(r"https?://\S+", "", s)                    # linkler okunmaz
    s = re.sub(r"```.*?```", " ", s, flags=re.DOTALL)      # kod blokları
    s = re.sub(r"[*_`#>|~]+", " ", s)                      # markdown
    s = _EMOJI.sub(" ", s)
    s = re.sub(r"%\s*(\d+(?:[.,]\d+)?)", r"yüzde \1", s)
    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", r"yüzde \1", s)
    s = re.sub(r"\b(\d{1,2}):(\d{2})\b",
               lambda m: f"{int(m.group(1))} {int(m.group(2)) if m.group(2) != '00' else ''}".strip(), s)
    s = re.sub(r"(\d)\.(\d)", r"\1 nokta \2", s)          # 1.5 → 1 nokta 5
    s = re.sub(r"(\d),(\d)", r"\1 virgül \2", s)
    for desen, yerine in _KISALTMA.items():
        s = re.sub(desen, yerine, s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Piper
# ---------------------------------------------------------------------------

VARSAYILAN_PIPER_SESLERI = ("tr_TR-fahrettin-medium", "tr_TR-fettah-medium", "tr_TR-dfki-medium")
SES_DIZINI = os.path.join("data", "sesler")


def piper_modeli_bul(tercih: str = "", dizin: str = SES_DIZINI) -> Optional[str]:
    """Kullanılacak .onnx dosyasını bulur.

    tercih: tam dosya yolu, ses adı ("tr_TR-fahrettin-medium") ya da boş (ilk bulunan Türkçe ses).
    """
    if tercih and tercih.endswith(".onnx") and os.path.isfile(tercih):
        return tercih
    adaylar = [tercih] if tercih else []
    adaylar += [a for a in VARSAYILAN_PIPER_SESLERI if a not in adaylar]
    for ad in adaylar:
        yol = os.path.join(dizin, f"{ad}.onnx")
        if os.path.isfile(yol) and os.path.isfile(yol + ".json"):
            return yol
    for yol in sorted(glob.glob(os.path.join(dizin, "tr_TR-*.onnx"))):
        if os.path.isfile(yol + ".json"):
            return yol
    return None


class PiperTTS:
    name = "piper"

    def __init__(self, model_yolu: str, hiz: float = 1.0, ses_seviyesi: float = 1.0,
                 voice_loader: Optional[Callable[[str], Any]] = None,
                 player: Optional[Callable[[Any, int], None]] = None,
                 stopper: Optional[Callable[[], None]] = None) -> None:
        self._kesildi = threading.Event()
        self._stopper = stopper or _sounddevice_durdur
        self.model_yolu = model_yolu
        self.hiz = max(0.5, min(2.0, hiz or 1.0))
        self.ses_seviyesi = max(0.0, min(1.0, ses_seviyesi))
        if voice_loader is None:
            from piper import PiperVoice  # type: ignore
            voice_loader = PiperVoice.load
        self._voice = voice_loader(model_yolu)
        self._player = player or _sounddevice_cal
        try:
            from piper import SynthesisConfig  # type: ignore
            self._config = SynthesisConfig(length_scale=1.0 / self.hiz, volume=self.ses_seviyesi)
        except Exception:
            self._config = None
        logger.info("🔊 Piper sesi hazır: %s", os.path.basename(model_yolu))

    def parcalar(self, metin: str) -> Iterable[tuple[Any, int]]:
        """Cümle cümle (ses_dizisi_int16, örnekleme_hızı) üretir."""
        for chunk in self._voice.synthesize(metin, syn_config=self._config):
            yield chunk.audio_int16_array, chunk.sample_rate

    def konus(self, metin: str) -> None:
        self._kesildi.clear()
        for ses, hz in self.parcalar(metin):
            if self._kesildi.is_set():
                break
            self._player(ses, hz)
            if self._kesildi.is_set():
                break

    def durdur(self) -> None:
        """Başka thread'den çağrılabilir: çalan cümleyi keser, kalanları atlar."""
        self._kesildi.set()
        try:
            self._stopper()
        except Exception as exc:
            logger.debug("Ses durdurulamadı: %s", exc)
        from irle.infra.ses_seviyesi import seviye_olcer
        seviye_olcer.kes()


def _sounddevice_durdur() -> None:
    import sounddevice as sd  # type: ignore
    sd.stop()


def _sounddevice_cal(ses: Any, sample_rate: int) -> None:
    import sounddevice as sd  # type: ignore
    from irle.infra.ses_seviyesi import seviye_olcer
    seviye_olcer.baslat(ses, sample_rate)     # avatarın dudak senkronu için
    try:
        sd.play(ses, sample_rate)
        sd.wait()
    finally:
        seviye_olcer.durdur()


# ---------------------------------------------------------------------------
# pyttsx3 (Windows SAPI5)
# ---------------------------------------------------------------------------

def turkce_ses_mi(ses: Any) -> bool:
    """pyttsx3 ses nesnesi Türkçe mi? (ad, id veya dil koduna bakar)"""
    metin = f"{getattr(ses, 'name', '')} {getattr(ses, 'id', '')}".lower()
    if any(k in metin for k in ("turkish", "türkçe", "turkce", "tolga", "tr-tr", "tr_tr")):
        return True
    for dil in getattr(ses, "languages", None) or []:
        if isinstance(dil, bytes):
            dil = dil.decode("utf-8", "ignore")
        if str(dil).lower().lstrip("\x05").startswith("tr"):
            return True
    return False


class Pyttsx3TTS:
    name = "pyttsx3"

    def __init__(self, hiz_kelime: int = 165, ses_seviyesi: float = 1.0, ses_adi: str = "",
                 engine_factory: Optional[Callable[[], Any]] = None) -> None:
        if engine_factory is None:
            import pyttsx3  # type: ignore
            engine_factory = pyttsx3.init
        self._motor = engine_factory()
        self._motor.setProperty("rate", hiz_kelime)
        self._motor.setProperty("volume", ses_seviyesi)
        sesler = self._motor.getProperty("voices") or []
        secilen = None
        if ses_adi:
            secilen = next((v for v in sesler if ses_adi.lower() in v.name.lower()), None)
        if secilen is None:
            secilen = next((v for v in sesler if turkce_ses_mi(v)), None)
        if secilen is not None:
            self._motor.setProperty("voice", secilen.id)
            logger.info("🔊 Windows sesi: %s", secilen.name)
        else:
            logger.warning("Yüklü Türkçe Windows sesi yok; Türkçe aksanlı okunacak. "
                           "Daha iyisi için Piper sesi indir: python tools/hazirlik_kontrol.py --indir")

    def konus(self, metin: str) -> None:
        self._motor.say(metin)
        self._motor.runAndWait()

    def durdur(self) -> None:
        try:
            self._motor.stop()
        except Exception as exc:
            logger.debug("Windows sesi durdurulamadı: %s", exc)


# ---------------------------------------------------------------------------
# Seçim
# ---------------------------------------------------------------------------

def ses_motoru_kur(motor: str = "auto", piper_ses: str = "", piper_hiz: float = 1.0,
                   hiz_kelime: int = 165, ses_seviyesi: float = 1.0, windows_ses_adi: str = "") -> Any:
    """auto: Piper sesi diskte ve paket kuruluysa Piper, değilse pyttsx3."""
    motor = (motor or "auto").lower()
    if motor in ("auto", "piper"):
        yol = piper_modeli_bul(piper_ses)
        if yol is None:
            (logger.warning if motor == "piper" else logger.info)(
                "Piper Türkçe sesi bulunamadı (%s). İndirmek için: python tools/hazirlik_kontrol.py --indir",
                SES_DIZINI)
        else:
            try:
                return PiperTTS(yol, hiz=piper_hiz, ses_seviyesi=ses_seviyesi)
            except ImportError:
                logger.info("piper-tts kurulu değil (pip install piper-tts) → Windows sesi kullanılacak.")
            except Exception as exc:
                logger.warning("Piper başlatılamadı (%s) → Windows sesi kullanılacak.", exc)
    return Pyttsx3TTS(hiz_kelime=hiz_kelime, ses_seviyesi=ses_seviyesi, ses_adi=windows_ses_adi)

"""
=============================================================================
TTS MODÜLÜ — Sesli Çıktı Katmanı
=============================================================================
Bu modülün TEK sorumluluğu:
    1. "tts_konuş" eventini dinlemek.
    2. Metni sesli okumak — Piper (doğal Türkçe, çevrimdışı) ya da yedek
       olarak Windows sesi (pyttsx3).
    3. Konuşma bitince "tts_bitti" eventi yayınlamak (yankı kilidi ve GUI için).

Motor seçimi (.env → IRLE_SES_MOTORU):
    auto    → data/sesler/ içinde Türkçe Piper sesi varsa Piper, yoksa Windows sesi
    piper   → Piper zorunlu (yoksa uyarı + Windows sesi)
    pyttsx3 → her zaman Windows sesi

Ses motorları thread-safe olmadığından tüm konuşmalar tek bir thread'de,
sırayla yapılır.
=============================================================================
"""

import logging
import os
import queue
import threading

import config
from irle.adapters.speech.tts_adapter import metni_hazirla, ses_motoru_kur, turkce_ses_mi

logger = logging.getLogger("TtsModulu")

# Geriye dönük uyumluluk (tools/hazirlik_kontrol.py ve eski kod bu adı kullanıyordu)
_turkce_ses_mi = turkce_ses_mi


class TtsModulu:
    """Metni sese çeviren çıktı modülü."""

    def __init__(self, event_bus, settings=None):
        self.bus = event_bus
        self._settings = settings
        self._motor = None
        self._motor_hazir = threading.Event()
        self._kuyruk: "queue.Queue[str | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._tts_dongusu, name="TtsModuluThread", daemon=True)
        self.bus.subscribe("tts_konuş", self._konusma_istegi_alindi)
        self.bus.subscribe("konusmayi_kes", self._kes)

    @property
    def motor_adi(self) -> str:
        return getattr(self._motor, "name", "-")

    def baslat(self) -> None:
        """TTS thread'ini başlatır ve motorun hazır olmasını bekler."""
        self._thread.start()
        self._motor_hazir.wait(timeout=15)  # Piper modeli yüklenirken bekle
        logger.info("TTS Modülü başlatıldı (motor: %s).", self.motor_adi)

    def durdur(self) -> None:
        self._kuyruk.put(None)
        logger.info("TTS Modülü durduruldu.")

    def _konusma_istegi_alindi(self, mesaj: dict) -> None:
        metin = mesaj.get("data", {}).get("metin", "")
        if getattr(config, "SESSİZ_MOD", False):
            # Sessiz mod: hemen bitti de ki mikrofon kilidi açılsın
            self.bus.publish("tts_bitti", {"metin": metin})
            return
        if metin:
            self._kuyruk.put(metin)

    def _kes(self, mesaj: dict) -> None:
        """Kullanıcı araya girdi ("dur", "sus"...): çalanı kes, sıradakileri at."""
        atlanan = []
        try:
            while True:
                m = self._kuyruk.get_nowait()
                if m is None:                 # kapatma sinyalini kaybetme
                    self._kuyruk.put(None)
                    break
                atlanan.append(m)
        except queue.Empty:
            pass
        if self._motor is not None and hasattr(self._motor, "durdur"):
            self._motor.durdur()
        # Her atlanan cümle için "bitti" — yankı kilidi sayacı dengede kalsın
        for m in atlanan:
            self.bus.publish("tts_bitti", {"metin": m})
        logger.info("✋ Konuşma kesildi (%d cümle atlandı).", len(atlanan))

    def _motoru_kur(self):
        s = self._settings
        hiz_kelime = getattr(config, "TTS_HIZ", 165)
        ses_seviyesi = getattr(config, "TTS_VOLUME", 1.0)
        windows_ses = getattr(config, "TTS_SES_ADI", None) or ""
        if s is not None:
            return ses_motoru_kur(
                motor=s.tts_engine, piper_ses=s.piper_voice, piper_hiz=s.piper_speed,
                hiz_kelime=hiz_kelime, ses_seviyesi=ses_seviyesi,
                windows_ses_adi=windows_ses or s.tts_voice_name,
            )
        return ses_motoru_kur(motor=os.getenv("IRLE_SES_MOTORU", "auto"), hiz_kelime=hiz_kelime,
                              ses_seviyesi=ses_seviyesi, windows_ses_adi=windows_ses)

    def _tts_dongusu(self) -> None:
        try:
            self._motor = self._motoru_kur()
        except Exception as exc:
            logger.error("Hiçbir ses motoru başlatılamadı: %s — İrle sadece yazıyla cevap verecek.", exc)
            self._motor = None
        self._motor_hazir.set()

        while True:
            metin = self._kuyruk.get()
            if metin is None:
                break
            okunacak = metni_hazirla(metin)
            logger.info(f"TTS konuşuyor → '{metin}'")
            try:
                if self._motor is not None and okunacak:
                    self._motor.konus(okunacak)
            except Exception as e:
                logger.error(f"TTS hatası: {e}")
            finally:
                # Konuşma bitti (ya da hata) — mikrofon kilidi ve GUI haberdar edilsin
                self.bus.publish("tts_bitti", {"metin": metin})

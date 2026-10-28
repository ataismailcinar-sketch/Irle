"""
=============================================================================
MAIN — Sistem Giriş Noktası (V2.1)
=============================================================================
Değişiklikler:
    - beyin_modulu → llm_modulu ile değiştirildi (Gemini + fallback)
    - tts_modulu, bellek_modulu, gui_modulu eklendi
    - GUI ana thread'de çalıştığı için en son başlatılıyor
    - v2.1: telefon_kontrolcu modülü eklendi
    - v2.2: hibrit beyin (Groq ücretsiz bulut + Ollama yerel), üsluba uyan kişilik
    - v2.3: dil modelsiz Türkçe anlama motoru, bağlam, uyandırma kelimesi, yankı kilidi
    - v2.4: hibrit kulak (Groq Whisper → yerel faster-whisper → Google)
    - v2.5: doğal Türkçe ses (Piper, çevrimdışı) + Windows sesi yedeği; Kıpçak maskeli animasyonlu yüz

Yeni bir modül eklemek için:
    1. modules/ altına dosyasını oluştur
    2. Burada import et, nesnesini oluştur, moduller listesine ekle
    3. BAŞKA HİÇBİR DOSYAYA dokunmana gerek yok
=============================================================================
"""

import logging
import sys
import os

# TensorFlow uyarılarını (oneDNN vb.) tamamen sustur
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

# Add 'src' directory to Python path for setuptools layout
src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Çekirdek
from irle.infra.event_bus import TypedEventBus
from irle.app.settings import Settings, load_dotenv
from irle.app.command_registry import build_command_bus
from irle.app.brain_factory import build_brain
from irle.app.stt_factory import build_stt

# .env (GROQ_API_KEY vb.) — modüller import edilmeden önce yüklenmeli
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# Modüller
from modules.ses_modulu          import SesModulu
from modules.intent_modulu       import IntentModulu
from modules.aksiyon.aksiyon_modulu import AksiyonModulu
from modules.tts_modulu          import TtsModulu
from modules.bellek_modulu       import BellekModulu
from modules.gui_modulu          import GuiModulu
from modules.vision_modulu       import VisionModulu
from modules.telefon_kontrolcu   import TelefonKontrolcuModulu

logger = logging.getLogger("Main")


def main():
    settings  = Settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("=" * 60)
    logger.info("  IRLE v2.5 — Modüler AI Asistan Sistemi Başlatılıyor...")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Çekirdeği oluştur
    # ------------------------------------------------------------------
    bus       = TypedEventBus()
    cmd_bus   = build_command_bus(bus, settings)
    beyin     = build_brain(settings, cmd_bus)   # 🧠 Hibrit beyin (Groq + Ollama)

    # ------------------------------------------------------------------
    # 2. Modülleri oluştur
    #    Her modül bu satırda kendi subscribe() çağrılarını yapar.
    # ------------------------------------------------------------------
    ses       = SesModulu(bus, stt_provider=build_stt(settings), kesme=settings.barge_in)   # 🎧 Groq → yerel Whisper → Google
    intent    = IntentModulu(bus, cmd_bus, brain=beyin, settings=settings)
    aksiyon   = AksiyonModulu(bus)
    tts       = TtsModulu(bus, settings)   # 🔊 Piper (doğal Türkçe) → Windows sesi
    bellek    = BellekModulu(bus)
    vision    = VisionModulu(bus)
    telefon   = TelefonKontrolcuModulu(bus)   # 📱 Telefon kontrolcü
    gui       = GuiModulu(bus, telefon)       # ⚠️ En son oluşturulmalı

    # ------------------------------------------------------------------
    # 3. Arka plan modüllerini başlat (GUI hariç — o main thread ister)
    # ------------------------------------------------------------------
    arka_plan_moduller = [ses, intent, aksiyon, tts, bellek, vision, telefon]

    for modul in arka_plan_moduller:
        modul.baslat()

    logger.info("=" * 60)
    logger.info("  Tüm modüller hazır. GUI başlatılıyor...")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 4. GUI'yi başlat — bu çağrı pencerenin kapanmasına kadar BLOKLAR.
    #    Kullanıcı pencereyi kapatınca burası devam eder.
    # ------------------------------------------------------------------
    try:
        gui.baslat()   # ← mainloop() burada çalışır
    except KeyboardInterrupt:
        pass
    finally:
        # ------------------------------------------------------------------
        # 5. Zarif kapatma — ters sırayla durdur
        # ------------------------------------------------------------------
        logger.info("Sistem kapatılıyor...")
        for modul in reversed(arka_plan_moduller):
            modul.durdur()
        logger.info("Tüm modüller durduruldu. Güle güle!")
        sys.exit(0)


if __name__ == "__main__":
    main()

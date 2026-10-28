"""
=============================================================================
SES MODÜLÜ — Mikrofon Girdi Katmanı
=============================================================================
Bu modülün TEK sorumluluğu:
    1. Mikrofonu arka planda (ayrı bir thread'de) sürekli dinlemek.
    2. Konuşmayı metne çevirmek.
    3. Çekirdeğe (EventBus) "ses_algilandi" eventi göndermek.

Bu modül, Beyin Modülü'nün ya da herhangi başka bir modülün var olduğundan
TAMAMEN HABERSİZDİR. Sadece EventBus'ı bilir.

Teknik Not: PyAudio Python 3.14 için henüz hazır wheel sunmadığından
sounddevice + scipy kullanılmaktadır. SpeechRecognition'a ses verisi
AudioData nesnesi olarak manuel şekilde iletilir.
=============================================================================
"""

import threading
import logging
import queue
import concurrent.futures
from typing import Optional
import numpy as np
import sounddevice as sd

import config
from irle.adapters.speech.stt_adapter import BaseSTTProvider, GoogleSTTProvider
from irle.domain.events import SpeechRecognized
from irle.infra.echo_guard import EchoGuard
from irle.infra.kesme_dinleyici import KesmeDinleyici
from irle.infra.ses_seviyesi import seviye_olcer
from irle.adapters.intent.kesme import kesme_karari
from collections import deque

logger = logging.getLogger("SesModulu")

# Örnekleme hızı ve blok boyutu — sounddevice için sabit ayarlar
ORNEKLEME_HIZI = 16000   # Google STT için ideal frekans (Hz)
BLOK_BOYUTU   = 4000     # Her seferinde işlenecek örnek sayısı (~0.25 saniye, daha hassas VAD)
SES_ESIGI     = 220      # Konuşma tespit eşiği (RMS/Mean)
SESSİZLİK_LIMIT = 3      # 3 blok (~0.75 sn) sessizlik olunca konuşma bitti sayılır
MIN_KONUSMA_BLOK = 2     # en az 2 sesli blok (~0.5 sn); daha kısası tıkırtı/öksürük sayılır


class SesModulu:
    """
    Mikrofonu sounddevice ile arka planda sürekli dinleyen,
    VAD (Voice Activity Detection) ile dinamik konuşma sonu tespiti yapan,
    asenkron STT havuzu ile metne çevirip EventBus'a yayınlayan modül.
    """

    def __init__(self, event_bus, stt_provider: Optional[BaseSTTProvider] = None, kesme: bool = True):
        """
        Args:
            event_bus: Sistemin merkezi EventBus nesnesi.
            stt_provider: Opsiyonel STT sağlayıcısı (main.py hibrit kulağı verir;
                          verilmezse eski davranış: GoogleSTTProvider).
        """
        self.bus = event_bus
        self.stt_provider = stt_provider or GoogleSTTProvider()

        # sounddevice callback'inden ana thread'e ham ses bloklarını taşımak için thread-safe kuyruk
        self._ses_kuyrugu: queue.Queue = queue.Queue()

        # Asenkron STT çözümleme iş parçacığı havuzu (mikrofonu bloklamaz)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="STTWorker")

        # İrle konuşurken kendi sesini komut sanmasın (yankı kilidi)
        self.yanki_kilidi = EchoGuard()
        self.bus.subscribe("tts_konuş", self._tts_basladi)
        self.bus.subscribe("tts_bitti", self._tts_bitti)

        # İrle konuşurken "dur / sus" ya da "İrle, ..." ile araya girme
        self._kesme_acik = kesme
        self._kesme = KesmeDinleyici(temel_esik=SES_ESIGI)
        self._soylenenler: deque = deque(maxlen=4)

        self._calisiyor = False
        self._thread = threading.Thread(
            target=self._dinleme_dongusu,
            name="SesModuluThread",
            daemon=True,
        )

    def baslat(self) -> None:
        """Modülü başlatır."""
        self._calisiyor = True
        self._thread.start()
        logger.info("Ses Modülü başlatıldı. Mikrofon dinleniyor...")

    def durdur(self) -> None:
        """Modülü zarif şekilde durdurur."""
        self._calisiyor = False
        self._executor.shutdown(wait=False)
        logger.info("Ses Modülü durdurma sinyali aldı.")

    def _bildir(self, olay: str) -> None:
        """Arayüz için hafif sinyal (avatar 'duyuyor' / 'dinliyor')."""
        try:
            self.bus.publish(olay, {})
        except Exception:
            pass

    def _tts_basladi(self, mesaj: dict) -> None:
        metin = mesaj.get("data", {}).get("metin", "")
        if metin:
            self._soylenenler.append(metin)
        self.yanki_kilidi.started(metin)

    def _tts_bitti(self, mesaj: dict) -> None:
        self.yanki_kilidi.finished()

    def _ses_callback(self, indata: np.ndarray, frames: int,
                      time_info, status) -> None:
        """
        sounddevice her ses bloğunu aldığında bu fonksiyonu çağırır.
        Blokları ana dinleme döngüsüne aktarmak için kuyruğa yazar.
        (Bu fonksiyon ayrı bir ses thread'inde çalışır — bloklamaz.)
        """
        if status:
            logger.warning(f"Ses callback durumu: {status}")
        # Ses verisinin bir kopyasını kuyruğa ekle
        self._ses_kuyrugu.put(indata.copy())

    def _asenkron_cozumle(self, ses_bayt: bytes) -> None:
        """STT çözümlemesini arka plan worker thread'inde çalıştırır."""
        try:
            metin = self.stt_provider.transcribe(
                ses_bayt,
                sample_rate=ORNEKLEME_HIZI,
                sample_width=2,
                language=config.SES_DILI,
            )
            if metin:
                logger.info(f"Ses algılandı → '{metin}'")
                self.bus.publish(SpeechRecognized(text=metin))
            else:
                self._bildir("konusma_bitti")   # gürültüydü, arayüz dinlemeye dönsün
        except Exception as e:
            logger.error(f"Ses tanıma hatası: {e}")

    def _kesme_cozumle(self, ses_bayt: bytes) -> None:
        """İrle konuşurken yakalanan parça: dur mu, yeni komut mu, yankı mı?"""
        try:
            metin = self.stt_provider.transcribe(ses_bayt, sample_rate=ORNEKLEME_HIZI, sample_width=2,
                                                 language=config.SES_DILI)
        except Exception as e:
            logger.debug(f"Kesme tanıma hatası: {e}")
            return
        if not metin:
            return
        karar = kesme_karari(metin, list(self._soylenenler))
        if karar is None:
            logger.debug("Konuşurken duyulan yok sayıldı (yankı/alakasız): %r", metin)
            return
        tur, komut = karar
        logger.info("✋ Araya girildi (%s): %r", tur, metin)
        self.bus.publish("konusmayi_kes", {"metin": metin})
        if tur == "komut" and komut:
            self.bus.publish(SpeechRecognized(text=komut))

    def _dinleme_dongusu(self) -> None:
        """
        Arka planda çalışan VAD destekli ana dinleme döngüsü.
        Konuşma algılandığında blokları toplar; kullanıcı sustuğunda (~0.75s)
        10 saniye beklemeden anında asenkron STT kuyruğuna gönderir.
        """
        logger.info("Ses akışı başlatılıyor...")

        # sounddevice akışını başlat — callback her blokta tetiklenir.
        with sd.InputStream(
            samplerate=ORNEKLEME_HIZI,
            channels=1,               # Tek kanal (mono) mikrofon
            dtype="int16",            # 16-bit PCM — STT uyumlu format
            blocksize=BLOK_BOYUTU,
            callback=self._ses_callback,
        ):
            logger.info("Kalibrasyon yapılıyor (1 saniye sessiz kalın)...")
            import time
            time.sleep(1)
            while not self._ses_kuyrugu.empty():
                self._ses_kuyrugu.get_nowait()

            logger.info("Komut bekleniyor...")

            konusma_var = False
            sessizlik_blok_sayisi = 0
            sesli_blok = 0
            toplanan = []
            pre_roll = None

            while self._calisiyor:
                try:
                    blok = self._ses_kuyrugu.get(timeout=0.5)
                except queue.Empty:
                    continue

                # İrle konuşuyorsa normal dinleme kapalı (yankı döngüsünü önler);
                # sadece araya girme ("dur", "İrle ...") için ayrı, temkinli bir dinleme yapılır.
                if self.yanki_kilidi.active:
                    konusma_var = False
                    sessizlik_blok_sayisi = 0
                    toplanan = []
                    pre_roll = None
                    if self._kesme_acik:
                        parca = self._kesme.besle(blok, float(np.abs(blok).mean()), seviye_olcer.seviye())
                        if parca:
                            self._executor.submit(self._kesme_cozumle, np.concatenate(parca, axis=0).tobytes())
                    continue
                self._kesme.sifirla()

                enerji = float(np.abs(blok).mean())

                if enerji >= SES_ESIGI:
                    if not konusma_var:
                        logger.debug("Konuşma başladı (VAD)...")
                        self._bildir("konusma_basladi")
                        konusma_var = True
                        sesli_blok = 0
                        toplanan = []
                        if pre_roll is not None:
                            toplanan.append(pre_roll)
                    sessizlik_blok_sayisi = 0
                    sesli_blok += 1
                    toplanan.append(blok)
                else:
                    if konusma_var:
                        sessizlik_blok_sayisi += 1
                        toplanan.append(blok)

                        # Kullanıcı konuşmayı bitirdi mi? (~0.75 sn sessizlik veya max 10 sn sınır)
                        if sessizlik_blok_sayisi >= SESSİZLİK_LIMIT or len(toplanan) >= 40:
                            if sesli_blok < MIN_KONUSMA_BLOK:
                                logger.debug("Çok kısa ses (%d blok), yok sayıldı.", sesli_blok)
                                self._bildir("konusma_bitti")
                            else:
                                logger.info(f"Konuşma tamamlandı (VAD, {len(toplanan)} blok). Çözümlemeye aktarılıyor...")
                                ham_ses = np.concatenate(toplanan, axis=0)
                                ses_bayt = ham_ses.tobytes()

                                # Asenkron çözümlemeye gönder - mikrofon döngüsü bloklanmaz!
                                self._executor.submit(self._asenkron_cozumle, ses_bayt)

                            konusma_var = False
                            sessizlik_blok_sayisi = 0
                            toplanan = []
                    else:
                        # Konuşma henüz yokken son bloğu pre-roll olarak sakla
                        pre_roll = blok

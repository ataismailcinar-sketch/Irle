"""
=============================================================================
CORE / EVENT BUS — Sistemin Kalbi
=============================================================================
Bu dosya, hiçbir iş mantığı içermez. Tek görevi şudur:
    - Modüllerin belirli "event" adlarına abone (subscribe) olmasını sağlamak.
    - Bir modül bir event yayınladığında (publish), o event'e abone olan
      TÜM modülleri haberdar etmek.

Bu sayede modüller birbirlerinin varlığından tamamen habersizdir.
Ses modülü, Beyin modülünün var olup olmadığını bilmez;
sadece bir event yayınlar ve işi biter.
=============================================================================
"""

import threading
import logging
from collections import defaultdict
from typing import Callable

# Loglama ayarı: Sistemdeki tüm hareketler konsola yazdırılır.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("EventBus")


class EventBus:
    """
    Pub/Sub (Yayın/Abone) mimarisini uygulayan merkezi mesaj otobüsü.

    Kullanım:
        bus = EventBus()
        bus.subscribe("event_adi", handler_fonksiyonu)
        bus.publish("event_adi", {"data": "..."})
    """

    def __init__(self):
        # Her event adına karşılık bir handler listesi tutar.
        # defaultdict sayesinde olmayan bir key için otomatik boş liste döner.
        self._aboneler: dict[str, list[Callable]] = defaultdict(list)

        # Thread güvenliği için kilit (lock) mekanizması.
        # Birden fazla thread aynı anda abone listesini değiştirmeye çalışırsa
        # veri bozulmasını önler.
        self._kilit = threading.Lock()

    def subscribe(self, event_adi: str, handler: Callable) -> None:
        """
        Bir modülün belirli bir event'i dinlemesini sağlar.

        Args:
            event_adi: Dinlenecek event'in adı (örn: "ses_algilandi")
            handler:   Event tetiklendiğinde çağrılacak fonksiyon.
        """
        with self._kilit:
            self._aboneler[event_adi].append(handler)
        logger.info(f"Yeni abone kaydedildi → Event: '{event_adi}' | Handler: '{handler.__qualname__}'")

    def publish(self, event_adi: str, data: dict = None) -> None:
        """
        Bir event yayınlar. Bu event'e abone olan tüm handler'lar
        AYRI THREAD'LERDE çalıştırılır — bu sayede yayıncı bloklanmaz.

        Args:
            event_adi: Yayınlanacak event'in adı (örn: "uygulama_ac")
            data:      Event ile birlikte taşınan veri sözlüğü.
        """
        if data is None:
            data = {}

        # Mesaj zarfı oluştur: event adı + veri
        mesaj = {"event": event_adi, "data": data}
        logger.info(f"Event yayınlandı → {mesaj}")

        # Abone listesinin anlık bir kopyasını al (thread güvenliği için)
        with self._kilit:
            handler_listesi = list(self._aboneler.get(event_adi, []))

        if not handler_listesi:
            logger.warning(f"'{event_adi}' event'ine abone olan kimse bulunamadı.")
            return

        # Her handler'ı ayrı bir thread'de çalıştır.
        # Bu sayede bir handler'ın yavaş çalışması diğerlerini engellemez.
        for handler in handler_listesi:
            t = threading.Thread(
                target=self._handler_calistir,
                args=(handler, mesaj),
                daemon=True,  # Ana program kapanınca bu thread'ler de kapanır.
            )
            t.start()

    def _handler_calistir(self, handler: Callable, mesaj: dict) -> None:
        """
        Handler'ı güvenli bir şekilde çalıştırır.
        Hata oluşursa sistemi çökertemez, sadece loglar.
        """
        try:
            handler(mesaj)
        except Exception as e:
            logger.error(
                f"Handler çalıştırılırken hata oluştu! "
                f"Handler: '{handler.__qualname__}' | Hata: {e}"
            )

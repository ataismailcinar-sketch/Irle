import logging
from modules.aksiyon.uygulama_yoneticisi import UygulamaYoneticisi
from modules.aksiyon.fare_yoneticisi import FareYoneticisi

logger = logging.getLogger("AksiyonModulu")

class AksiyonModulu:
    """
    Sistem ve fiziksel aksiyonları yöneten ana modül (Facade).
    Uygulama açma ve Fare kontrolü gibi alt yöneticileri koordine eder.
    """
    def __init__(self, event_bus):
        self.bus = event_bus
        self.uygulama_yoneticisi = UygulamaYoneticisi(self.bus)
        self.fare_yoneticisi = FareYoneticisi(self.bus)
        
    def baslat(self) -> None:
        """Tüm alt yöneticileri başlatır."""
        logger.info("Aksiyon Modülü (Facade) başlatılıyor...")
        self.uygulama_yoneticisi.baslat()
        self.fare_yoneticisi.baslat()

    def durdur(self) -> None:
        """Tüm alt yöneticileri durdurur."""
        logger.info("Aksiyon Modülü (Facade) durduruluyor...")
        self.uygulama_yoneticisi.durdur()
        self.fare_yoneticisi.durdur()

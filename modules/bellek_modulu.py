"""
=============================================================================
BELLEK MODÜLÜ — Konuşma Geçmişi Katmanı
=============================================================================
Bu modülün TEK sorumluluğu:
    1. "bellek_kaydet" eventini dinlemek.
    2. Konuşmaları data/konusmalar.json dosyasına kaydetmek.
    3. Oturum başlangıcında geçmiş konuşmaları yüklemek.

Her kayıt şu formatta tutulur:
    {
        "zaman": "2026-04-09T10:35:00",
        "rol": "kullanici" | "asistan",
        "metin": "..."
    }
=============================================================================
"""

import json
import logging
import os
from datetime import datetime
import config

logger = logging.getLogger("BellekModulu")


class BellekModulu:
    """
    Konuşmaları JSON dosyasına kaydeden ve yükleyen bellek modülü.
    """

    def __init__(self, event_bus):
        self.bus = event_bus
        self._gecmis: list[dict] = []

        # data/ klasörünü oluştur (yoksa)
        os.makedirs(os.path.dirname(config.BELLEK_DOSYASI), exist_ok=True)

        # "bellek_kaydet" eventine abone ol
        self.bus.subscribe("bellek_kaydet", self._kaydet)

    def baslat(self) -> None:
        """Mevcut geçmişi diskten yükle."""
        self._gecmisi_yukle()
        logger.info(
            f"Bellek Modülü başlatıldı. "
            f"{len(self._gecmis)} önceki kayıt yüklendi."
        )

    def durdur(self) -> None:
        """Modül kapanırken geçmişi diske yaz."""
        self._gecmisi_kaydet()
        logger.info("Bellek Modülü durduruldu. Geçmiş kaydedildi.")

    def gecmis_al(self, son_n: int = 10) -> list[dict]:
        """
        Son N konuşmayı döndürür.
        LLM modülü bağlam oluşturmak için bu metodu kullanabilir.
        """
        return self._gecmis[-son_n:]

    def _kaydet(self, mesaj: dict) -> None:
        """
        EventBus'tan gelen "bellek_kaydet" eventini işler.
        
        Beklenen data formatı:
            {"rol": "kullanici" | "asistan", "metin": "..."}
        """
        data = mesaj.get("data", {})
        rol   = data.get("rol", "bilinmiyor")
        metin = data.get("metin", "")

        if not metin:
            return

        kayit = {
            "zaman": datetime.now().isoformat(timespec="seconds"),
            "rol":   rol,
            "metin": metin,
        }

        self._gecmis.append(kayit)
        logger.debug(f"Belleğe eklendi → [{rol}]: '{metin}'")

        # Maksimum kayıt sayısını aş → en eski kayıtları sil
        if len(self._gecmis) > config.BELLEK_MAX_KAYIT:
            self._gecmis = self._gecmis[-config.BELLEK_MAX_KAYIT:]

        # Her kayıt sonrası diske yaz (veri kaybı olmasın)
        self._gecmisi_kaydet()

    def _gecmisi_yukle(self) -> None:
        """JSON dosyasından geçmişi yükler."""
        if not os.path.exists(config.BELLEK_DOSYASI):
            logger.info("Geçmiş dosyası bulunamadı, yeni bir oturum başlatılıyor.")
            return

        try:
            with open(config.BELLEK_DOSYASI, "r", encoding="utf-8") as f:
                self._gecmis = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Geçmiş yüklenirken hata: {e}. Boş geçmişle başlanıyor.")
            self._gecmis = []

    def _gecmisi_kaydet(self) -> None:
        """Geçmişi JSON dosyasına yazar."""
        try:
            with open(config.BELLEK_DOSYASI, "w", encoding="utf-8") as f:
                json.dump(self._gecmis, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Geçmiş kaydedilirken hata: {e}")

"""
=============================================================================
BEYİN MODÜLÜ — Karar Katmanı
=============================================================================
Bu modülün TEK sorumluluğu:
    1. EventBus üzerinden "ses_algilandi" eventini dinlemek.
    2. Gelen metni basit kurallarla (if-else) yorumlamak.
    3. Yoruma göre bir aksiyon eventi yayınlamak ("uygulama_ac" gibi).

Bu modül; Ses Modülü'nün ya da Aksiyon Modülü'nün var olduğundan
TAMAMEN HABERSİZDİR. Sadece EventBus'ı bilir.

NOT: İleride bu if-else bloğu, yerel bir LLM (Ollama, LM Studio vb.)
ile kolayca değiştirilebilir. Mimari değişmez, sadece bu dosya güncellenir.
=============================================================================
"""

import logging
import config

logger = logging.getLogger("BeyinModulu")


class BeyinModulu:
    """
    Gelen ses metnini yorumlayan ve aksiyon üreten karar modülü.
    """

    def __init__(self, event_bus):
        """
        Args:
            event_bus: Sistemin merkezi EventBus nesnesi.
        """
        self.bus = event_bus

        # Abone ol: "ses_algilandi" eventi geldiğinde _ses_islendi metodu çağrılsın.
        # Bu satır, Ses Modülü ile Beyin Modülü arasındaki tek bağlantıdır —
        # ve bu bağlantı bile dolaylıdır; EventBus üzerinden kurulur.
        self.bus.subscribe("ses_algilandi", self._ses_islendi)

    def baslat(self) -> None:
        """
        Bu modülün başlatılması için özel bir thread gerekmez;
        zaten EventBus thread'leri üzerinden çalışır.
        main.py ile uyumlu olmak için bu metot mevcuttur.
        """
        logger.info("Beyin Modülü başlatıldı. 'ses_algilandi' eventi bekleniyor...")

    def durdur(self) -> None:
        """Modülü zarif şekilde durdurur (gerekirse override edilebilir)."""
        logger.info("Beyin Modülü durduruldu.")

    def _ses_islendi(self, mesaj: dict) -> None:
        """
        EventBus'tan gelen "ses_algilandi" eventini işler.
        Bu metot, EventBus tarafından otomatik bir thread'de çağrılır.

        Args:
            mesaj: {"event": "ses_algilandi", "data": {"metin": "..."}}
        """
        metin = mesaj.get("data", {}).get("metin", "")

        # Büyük/küçük harf ayarını uygula
        if not config.BUYUK_HARF_DUYARLI:
            metin = metin.lower()

        logger.info(f"Metin yorumlanıyor → '{metin}'")

        # ---------------------------------------------------------------
        # KURAL MOTORU — if-else bloğu
        # ---------------------------------------------------------------
        # Her koşul, belirli anahtar kelimelere göre çalışır.
        # Yeni komut eklemek için buraya yeni bir elif bloğu yeterlidir.
        # İleride bu bölüm bir LLM çağrısıyla değiştirilebilir.
        # ---------------------------------------------------------------

        if any(k in metin for k in ["not defteri", "notepad", "not defterni"]):
            self._aksiyon_gonder("notepad", metin)

        elif any(k in metin for k in ["hesap", "hesap makinesi", "calculator"]):
            self._aksiyon_gonder("hesap", metin)

        elif any(k in metin for k in ["dosya", "explorer", "klasör"]):
            self._aksiyon_gonder("explorer", metin)

        elif any(k in metin for k in ["chrome", "tarayıcı", "internet"]):
            self._aksiyon_gonder("chrome", metin)

        elif any(k in metin for k in ["terminal", "komut", "cmd"]):
            self._aksiyon_gonder("terminal", metin)

        else:
            # Hiçbir kural eşleşmedi — bilinmeyen komut.
            logger.warning(f"Komut tanınamadı: '{metin}'")

    def _aksiyon_gonder(self, uygulama: str, kaynak_metin: str) -> None:
        """
        Karar verildi: EventBus'a "uygulama_ac" eventini yayınla.

        Args:
            uygulama:    Açılacak uygulamanın konfigürasyon anahtarı.
            kaynak_metin: Kararın alındığı orijinal metin (loglama için).
        """
        logger.info(f"Karar verildi → '{uygulama}' açılacak. (Kaynak: '{kaynak_metin}')")
        self.bus.publish(
            "uygulama_ac",
            {"uygulama": uygulama, "kaynak": kaynak_metin},
        )

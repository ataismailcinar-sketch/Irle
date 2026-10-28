import subprocess
import logging
import threading

import config
from modules.uygulama_tarayici import UygulamaTarayici

logger = logging.getLogger("UygulamaYoneticisi")

class UygulamaYoneticisi:
    def __init__(self, event_bus):
        self.bus = event_bus
        self._tarayici = UygulamaTarayici()
        self._katalog_hazir = False

        self.bus.subscribe("uygulama_ac", self._uygulama_ac)

    def baslat(self) -> None:
        t = threading.Thread(target=self._katalogu_hazirla, daemon=True, name="AppScanner")
        t.start()
        logger.info("Uygulama Yöneticisi başlatıldı. Katalog taranıyor...")

    def durdur(self) -> None:
        logger.info("Uygulama Yöneticisi durduruldu.")

    def _katalogu_hazirla(self):
        try:
            sayi = self._tarayici.tara()
            self._katalog_hazir = True
            logger.info(f"✅ Uygulama kataloğu hazır → {sayi} uygulama indekslendi.")
        except Exception as e:
            logger.error(f"Uygulama taraması sırasında hata: {e}")
            self._katalog_hazir = True

    def _uygulama_ac(self, mesaj: dict) -> None:
        uygulama_adi = mesaj.get("data", {}).get("uygulama", "").strip()

        if not uygulama_adi:
            logger.error("'uygulama_ac' eventi boş 'uygulama' alanıyla geldi!")
            return

        logger.info(f"Uygulama aranıyor: '{uygulama_adi}'")

        exe_yolu = self._exe_bul(uygulama_adi)

        if not exe_yolu:
            logger.error(
                f"'{uygulama_adi}' için hiçbir yöntemle exe bulunamadı. "
                f"Uygulama yüklü olmayabilir."
            )
            self.bus.publish("tts_konuş", {
                "metin": f"Üzgünüm, {uygulama_adi} uygulamasını bulamadım."
            })
            return

        logger.info(f"Uygulama başlatılıyor → '{exe_yolu}'")

        try:
            subprocess.Popen(
                exe_yolu,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"✅ '{exe_yolu}' başarıyla başlatıldı.")

        except FileNotFoundError:
            logger.error(f"'{exe_yolu}' bulunamadı.")
        except PermissionError:
            logger.error(f"'{exe_yolu}' için yeterli izin yok.")
        except Exception as e:
            logger.error(f"Uygulama başlatılırken beklenmedik hata: {e}")

    def _exe_bul(self, uygulama_adi: str) -> str | None:
        if self._katalog_hazir:
            isim, yol = self._tarayici.bul(uygulama_adi)
            if yol:
                return yol
        else:
            logger.warning("Katalog henüz hazır değil, fallback'e geçiliyor.")

        uygulama_kck = uygulama_adi.lower()
        sistem_komutu = config.UYGULAMA_KOMUTLARI.get(uygulama_kck)
        if sistem_komutu:
            logger.info(f"Config fallback eşleşmesi: '{uygulama_adi}' → '{sistem_komutu}'")
            return sistem_komutu

        for anahtar, komut in config.UYGULAMA_KOMUTLARI.items():
            if anahtar in uygulama_kck or uygulama_kck in anahtar:
                logger.info(f"Config kısmi eşleşme: '{uygulama_adi}' → '{komut}'")
                return komut

        logger.info(f"Direkt çalıştırma deneniyor: '{uygulama_adi}'")
        return uygulama_adi

"""
=============================================================================
UYGULAMA TARAYICI — PC'deki Yüklü Uygulamaları Keşfeder
=============================================================================
Bu modülün TEK sorumluluğu:
    1. Windows kayıt defterinden ve Start Menu'den yüklü uygulamaları bulmak.
    2. Uygulama adı → exe yolu eşlemesi tutmak.
    3. Verilen bir arama metnine en yakın uygulamayı bulmak (fuzzy match).

EventBus ile DOĞRUDAN ilgisi yoktur. AksiyonModulu bu sınıfı kullanır.
=============================================================================
"""

import winreg
import os
import glob
import logging
from difflib import SequenceMatcher

logger = logging.getLogger("UygulamaTarayici")

# Windows kayıt defterinde yüklü programların bulunduğu yerler
REGISTRY_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]

# Start Menu kısayol klasörleri
START_MENU_PATHS = [
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
]

# Eşleşme için minimum benzerlik skoru (0.0 - 1.0)
MIN_BENZERLIK = 0.45


class UygulamaTarayici:
    """
    PC'deki yüklü uygulamaları tarar ve fuzzy-match ile bulur.

    Kullanım:
        tarayici = UygulamaTarayici()
        tarayici.tara()
        yol = tarayici.bul("spotify")  # → "C:\\Users\\...\\Spotify.exe" veya None
    """

    def __init__(self):
        # { "spotify": "C:\\...\\Spotify.exe", "chrome": "C:\\...\\chrome.exe", ... }
        self._uygulama_katalogu: dict[str, str] = {}

    # ------------------------------------------------------------------
    # GENEL API
    # ------------------------------------------------------------------

    def tara(self) -> int:
        """
        PC'yi tarar ve iç kataloğu doldurur.
        Returns:
            Bulunan uygulama sayısı.
        """
        self._uygulama_katalogu.clear()
        self._kayit_defterinden_tara()
        self._start_menu_tara()
        logger.info(f"Uygulama taraması tamamlandı → {len(self._uygulama_katalogu)} uygulama bulundu.")
        return len(self._uygulama_katalogu)

    def bul(self, arama: str) -> tuple[str, str] | tuple[None, None]:
        """
        Verilen arama metnine en yakın uygulamayı katalogda arar.

        Args:
            arama: Kullanıcının söylediği uygulama adı (örn: "spotify", "vs code")

        Returns:
            (uygulama_adi, exe_yolu) veya (None, None) bulunamazsa.
        """
        if not self._uygulama_katalogu:
            logger.warning("Katalog boş! Önce tara() çağrısı yapın.")
            return None, None

        arama_kck = arama.lower().strip()

        # 1. Tam eşleşme (hızlı yol)
        if arama_kck in self._uygulama_katalogu:
            return arama_kck, self._uygulama_katalogu[arama_kck]

        # 2. İçinde geçiyor mu?
        for isim, yol in self._uygulama_katalogu.items():
            if arama_kck in isim or isim in arama_kck:
                logger.info(f"İçerik eşleşmesi: '{arama}' → '{isim}'")
                return isim, yol

        # 3. Fuzzy match (en benzer)
        en_iyi_isim, en_iyi_yol, en_iyi_skor = None, None, 0.0
        for isim, yol in self._uygulama_katalogu.items():
            skor = SequenceMatcher(None, arama_kck, isim).ratio()
            if skor > en_iyi_skor:
                en_iyi_skor = skor
                en_iyi_isim = isim
                en_iyi_yol = yol

        if en_iyi_skor >= MIN_BENZERLIK:
            logger.info(f"Fuzzy eşleşme: '{arama}' → '{en_iyi_isim}' (skor: {en_iyi_skor:.2f})")
            return en_iyi_isim, en_iyi_yol

        logger.warning(f"Uygulama bulunamadı: '{arama}' (en iyi skor: {en_iyi_skor:.2f})")
        return None, None

    def katalog(self) -> dict[str, str]:
        """Mevcut kataloğun bir kopyasını döndürür."""
        return dict(self._uygulama_katalogu)

    # ------------------------------------------------------------------
    # ÖZEL YARDIMCI METODLAR
    # ------------------------------------------------------------------

    def _kayit_defterinden_tara(self):
        """Windows Registry'den yüklü programları tarar."""
        eklenen = 0
        for hive, path in REGISTRY_PATHS:
            try:
                key = winreg.OpenKey(hive, path)
            except OSError:
                continue

            i = 0
            while True:
                try:
                    alt_key_adi = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break

                try:
                    alt_key = winreg.OpenKey(key, alt_key_adi)
                    try:
                        isim = winreg.QueryValueEx(alt_key, "DisplayName")[0]
                    except OSError:
                        winreg.CloseKey(alt_key)
                        continue

                    exe_yolu = None
                    # InstallLocation'dan exe aramayı dene
                    try:
                        klasor = winreg.QueryValueEx(alt_key, "InstallLocation")[0]
                        if klasor and os.path.isdir(klasor):
                            exeler = glob.glob(os.path.join(klasor, "*.exe"))
                            if exeler:
                                exe_yolu = exeler[0]
                    except OSError:
                        pass

                    # DisplayIcon'dan dene
                    if not exe_yolu:
                        try:
                            ikon = winreg.QueryValueEx(alt_key, "DisplayIcon")[0]
                            ikon = ikon.split(",")[0].strip('"').strip()
                            if ikon.lower().endswith(".exe") and os.path.isfile(ikon):
                                exe_yolu = ikon
                        except OSError:
                            pass

                    winreg.CloseKey(alt_key)

                    if exe_yolu:
                        anahtar = isim.lower().strip()
                        self._uygulama_katalogu[anahtar] = exe_yolu
                        eklenen += 1

                except OSError:
                    continue

            winreg.CloseKey(key)

        logger.debug(f"Registry taraması: {eklenen} uygulama eklendi.")

    def _start_menu_tara(self):
        """Start Menu kısayollarından (.lnk) uygulamaları tarar."""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            kullanilabilir = True
        except Exception:
            kullanilabilir = False

        eklenen = 0
        for klasor in START_MENU_PATHS:
            if not os.path.isdir(klasor):
                continue

            for lnk in glob.glob(os.path.join(klasor, "**", "*.lnk"), recursive=True):
                dosya_adi = os.path.splitext(os.path.basename(lnk))[0].lower().strip()

                exe_yolu = None

                # win32com varsa link hedefini çöz
                if kullanilabilir:
                    try:
                        kisayol = shell.CreateShortCut(lnk)
                        hedef = kisayol.Targetpath
                        if hedef and hedef.lower().endswith(".exe") and os.path.isfile(hedef):
                            exe_yolu = hedef
                    except Exception:
                        pass

                # win32com yoksa sadece dosya adını katalogla (açarken lnk'yi çalıştırırız)
                if not exe_yolu:
                    exe_yolu = lnk  # .lnk doğrudan subprocess ile açılabilir

                if dosya_adi and dosya_adi not in self._uygulama_katalogu:
                    self._uygulama_katalogu[dosya_adi] = exe_yolu
                    eklenen += 1

        logger.debug(f"Start Menu taraması: {eklenen} uygulama eklendi.")

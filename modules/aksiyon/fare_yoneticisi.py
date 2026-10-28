"""
=============================================================================
FARE YÖNETİCİSİ — El / göz kontrolünü gerçek fareye uygular
=============================================================================
Görüntü modülü her karede bir "el_hareketi_algilandi" olayı yayınlar:
    {"x": 0-1 | None, "y": 0-1 | None, "olaylar": [["tikla", (x, y)], ["kaydir", 3], ...]}

Olay otobüsü olayları bir thread havuzunda işler; kareler SIRASIZ gelebilir ve
imleç titrer. Bu yüzden burada tek bir işçi thread'i vardır:
  • İmleç hareketi: sadece EN SON konum uygulanır (eski kareler atlanır)
  • Tıklama/sürükleme/kaydırma: hiçbiri kaybolmadan, geldiği sırayla uygulanır
=============================================================================
"""

import logging
import queue
import sys
import threading

import config
from irle.infra.filters import PointFilter2D

logger = logging.getLogger("FareYoneticisi")

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
except Exception:  # test ortamı / ekransız
    pyautogui = None

# Windows'ta bir tekerlek çentiği 120 birimdir
_CENTIK = 120 if sys.platform == "win32" else 1


class FareYoneticisi:
    def __init__(self, event_bus, fare=None):
        self.bus = event_bus
        self._fare = fare if fare is not None else pyautogui
        self.bus.subscribe("el_hareketi_algilandi", self._vision_el_kontrol)
        self.bus.subscribe("bakis_yonu_algilandi", self._vision_goz_kontrol)

        self._el_filtresi = PointFilter2D(min_cutoff=1.0, beta=0.03, deadzone_px=1.5)
        self._goz_filtresi = PointFilter2D(min_cutoff=0.5, beta=0.015, deadzone_px=3.0)

        self._kilit = threading.Lock()
        self._son_konum = None            # (x_px, y_px) — işlenmemiş en son hedef
        self._olaylar: "queue.Queue" = queue.Queue()
        self._uyandir = threading.Event()
        self._basili = False
        self._goz_tik = False
        self._calisiyor = False
        self._thread = threading.Thread(target=self._dongu, name="FareIscisi", daemon=True)

    def baslat(self) -> None:
        self._calisiyor = True
        self._thread.start()
        logger.info("Fare Yöneticisi başlatıldı.")

    def durdur(self) -> None:
        self._calisiyor = False
        self._uyandir.set()
        self._birak()
        logger.info("Fare Yöneticisi durduruldu.")

    # ------------------------------------------------------------------
    # Olay otobüsü tarafı (herhangi bir thread)
    # ------------------------------------------------------------------

    def _ekran(self):
        return self._fare.size() if self._fare is not None else (1920, 1080)

    def _vision_el_kontrol(self, mesaj: dict) -> None:
        data = mesaj.get("data", {})
        if data.get("mod") == "phone":            # eski biçim (geriye dönük uyumluluk)
            yon, miktar = data.get("yon"), data.get("miktar", 100)
            self._olaylar.put(("kaydir_ham", miktar if yon == "yukari" else -miktar))
            self._uyandir.set()
            return

        w, h = self._ekran()
        x, y = data.get("x"), data.get("y")
        if x is not None and y is not None:
            with self._kilit:
                self._son_konum = (x * w, y * h)
        for ad, arg in data.get("olaylar", []) or []:
            if isinstance(arg, (list, tuple)) and len(arg) == 2:
                arg = (arg[0] * w, arg[1] * h)
            self._olaylar.put((ad, arg))
        self._uyandir.set()

    def _vision_goz_kontrol(self, mesaj: dict) -> None:
        data = mesaj.get("data", {})
        w, h = self._ekran()
        if self._fare is None:
            return
        cx, cy = self._goz_filtresi.filter(data.get("x", 0.5) * w, data.get("y", 0.5) * h)
        self._fare.moveTo(cx, cy, _pause=False)
        tik = bool(data.get("click"))
        if tik and not self._goz_tik:
            self._fare.click()
        self._goz_tik = tik

    # ------------------------------------------------------------------
    # İşçi thread
    # ------------------------------------------------------------------

    def _dongu(self) -> None:
        while self._calisiyor:
            self._uyandir.wait(timeout=0.5)
            self._uyandir.clear()
            try:
                self._bir_tur()
            except Exception as exc:
                logger.error("Fare işlemi başarısız: %s", exc)

    def _bir_tur(self) -> None:
        if self._fare is None:
            return
        with self._kilit:
            hedef, self._son_konum = self._son_konum, None
        # Önce olaylar (tıklama konumu kendi kilit konumuyla gelir), sonra hareket
        while True:
            try:
                ad, arg = self._olaylar.get_nowait()
            except queue.Empty:
                break
            self._uygula(ad, arg)
        if hedef is not None:
            x, y = self._el_filtresi.filter(*hedef)
            self._fare.moveTo(x, y, _pause=False)

    def _konuma_git(self, arg) -> None:
        if isinstance(arg, (list, tuple)) and len(arg) == 2:
            self._fare.moveTo(arg[0], arg[1], _pause=False)
            self._el_filtresi.reset()

    def _uygula(self, ad: str, arg) -> None:
        if ad == "tikla":
            self._konuma_git(arg)
            self._fare.click()
            logger.info("El: tıklama")
        elif ad == "sag_tikla":
            self._fare.rightClick()
            logger.info("El: sağ tıklama")
        elif ad == "basili_tut":
            self._konuma_git(arg)
            self._fare.mouseDown()
            self._basili = True
            logger.info("El: sürükleme başladı")
        elif ad in ("birak", "birak_hepsi"):
            self._birak()
        elif ad == "kaydir":
            self._fare.scroll(int(arg) * _CENTIK)
        elif ad == "kaydir_ham":
            self._fare.scroll(int(arg))

    def _birak(self) -> None:
        if self._basili and self._fare is not None:
            try:
                self._fare.mouseUp()
            except Exception:
                pass
            logger.info("El: sürükleme bitti")
        self._basili = False

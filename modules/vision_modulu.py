"""
=============================================================================
GÖRÜNTÜ MODÜLÜ — Vision & Gesture Processing (MediaPipe Tasks API v0.10+)
=============================================================================
Bu modülün sorumlulukları:
    1. Kamerayı arka planda takip etmek.
    2. MediaPipe Tasks API ile El ve Yüz landmarklarını tespit etmek.
    3. İş Modları arasında geçiş yapmak (Bozkurt işareti -> El Modu).
    4. EventBus üzerinden olayları yayınlamak.
=============================================================================
"""

import threading
import logging
import time
import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

import config
from irle.adapters.vision.el_jestleri import ElAyarlari, ElKontrolcu

logger = logging.getLogger("VisionModulu")

# Model dosyaları
# NOT: MediaPipe'in C++ motoru Türkçe karakterli yolları ("Masaüstü") açamıyor.
# Bu yüzden model dosyası YOL olarak değil, BAYT olarak (model_asset_buffer) verilir;
# böylece proje klasörü nerede olursa olsun çalışır. Aranan yerler sırayla:
#   1. <proje>/data/models/          (python tools/hazirlik_kontrol.py --indir indirir)
#   2. C:\irle_models\                (eski kurulumlarla uyumluluk)
_PROJE_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIZINLERI = [os.path.join(_PROJE_KOKU, "data", "models"), r"C:\irle_models"]
HAND_MODEL_ADI = "hand_landmarker.task"
FACE_MODEL_ADI = "face_landmarker.task"


def model_oku(ad: str):
    """Model dosyasını bulup bayt olarak döndürür; yoksa None."""
    for dizin in MODEL_DIZINLERI:
        yol = os.path.join(dizin, ad)
        if os.path.isfile(yol):
            with open(yol, "rb") as f:
                return f.read()
    return None

def _kayitli_referans_avuc() -> float:
    """Önceki oto kalibrasyonun sonucu (data/calibration.json) — yoksa varsayılan."""
    try:
        import json
        with open("data/calibration.json", encoding="utf-8") as f:
            return float(json.load(f).get("EL_REFERANS_AVUC", 0.13))
    except Exception:
        return 0.13


# MediaPipe çizim araçları (Tasks API için)
mp_drawing = mp.solutions.drawing_utils if hasattr(mp, 'solutions') else None


class VisionModulu:
    def __init__(self, event_bus):
        self.bus = event_bus

        self.cap = None
        self._calisiyor = False
        self._thread = threading.Thread(
            target=self._vision_dongusu, name="VisionThread", daemon=True
        )

        # Durum Değişkenleri
        self.aktif_mod = "el"   # "el", "beklemede" veya "goz"
        self.el_modu_izinli = True
        self.pencere_acik = config.VISION_DEBUG

        # Oto Kalibrasyon
        self.bus.subscribe("oto_kalibrasyon_istegi", self._oto_kalibrasyon_baslat)
        self.bus.subscribe("vision_el_modu_toggle", self._toggle_el_modu)
        self._oto_kalibre_aktif = False
        self._oto_kalibre_baslangic = 0
        self._el_boyutlari = []

        # MediaPipe Tasks API — Landmarker nesneleri
        self._hand_landmarker = None
        self._face_landmarker = None
        self._hand_result = None
        self._face_result = None

        # Tasks sonuçları thread-safe erişim için lock
        self._result_lock = threading.Lock()

        # El jestleri motoru (tüm tıklama/sürükleme/kaydırma/derinlik mantığı burada)
        self._el = ElKontrolcu(ElAyarlari(
            itme_aktif=getattr(config, "PUSH_CLICK_AKTIF", True),
            referans_avuc=_kayitli_referans_avuc(),
        ))
        self._son_el = None

        # Tıklama ve mesafe bağımsız durum değişkenleri (eski; geriye dönük uyumluluk)
        self._is_clicked = False
        self._is_pinched = False
        self._son_pinch_orani = 1.0
        self._son_palm_size = 0.20

        # Push-to-Click (Air Tap / Z-Ekseni İtme)
        self._is_pushed = False
        self._locked_pos = None
        self._son_protrusion = 0.0

        # Dwell Click (Hedefte Durunca Otomatik Tıklama)
        self._dwell_start_time = 0.0
        self._dwell_last_pos = None
        self._dwell_clicked = False
        self._son_tiklama_nedeni = "Yok"

    # -----------------------------------------------------------------------
    # Oto Kalibrasyon
    # -----------------------------------------------------------------------

    def _oto_kalibrasyon_baslat(self, mesaj: dict):
        self._oto_kalibre_aktif = True
        self._el_boyutlari = []
        self._oto_kalibre_baslangic = time.time()
        self.bus.publish("tts_konuş", {
            "metin": "Elini kullanacağın mesafede açık tut, üç saniye ölçüyorum."
        })
        self.bus.publish("bildirim", {"mesaj": "Oto Kalibrasyon Başladı", "tip": "info"})
        logger.info("Oto Kalibrasyon başlatıldı.")

    def _toggle_el_modu(self, mesaj: dict):
        data = mesaj.get("data", {})
        aktif = data.get("aktif", True)
        if aktif:
            self.el_modu_izinli = True
            self.aktif_mod = "el"
            logger.info("El Modu AKTIF edildi.")
            self.bus.publish("bildirim", {"mesaj": "El Kontrol Modu Açıldı", "tip": "info"})
        else:
            self.el_modu_izinli = False
            self.aktif_mod = "kapali"
            logger.info("El Modu KAPATILDI.")
            self.bus.publish("bildirim", {"mesaj": "El Kontrol Modu Kapatıldı", "tip": "info"})


    def _kalibrasyon_kaydet(self, yumusatma, margin, pinch):
        try:
            import json
            calib_data = {
                "FARE_YUMUSATMA": yumusatma,
                "VISION_MARGIN": margin,
                "VISION_PINCH_THRESHOLD": pinch,
            }
            os.makedirs("data", exist_ok=True)
            with open("data/calibration.json", "w", encoding="utf-8") as f:
                json.dump(calib_data, f, indent=2)

            config.FARE_YUMUSATMA = yumusatma
            config.VISION_MARGIN = margin
            config.VISION_PINCH_THRESHOLD = pinch
            self.bus.publish("tts_konuş", {"metin": "Kalibrasyon tamamlandı. Ayarlarınız kaydedildi."})
            logger.info("Oto kalibrasyon tamamlandı ve data/calibration.json güncellendi.")
        except Exception as e:
            logger.error(f"Kalibrasyon kaydedilemedi: {e}")

    # -----------------------------------------------------------------------
    # Modül yaşam döngüsü
    # -----------------------------------------------------------------------

    def baslat(self):
        self._calisiyor = True
        self._thread.start()
        logger.info("Görüntü Modülü başlatıldı.")

    def durdur(self):
        self._calisiyor = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        logger.info("Görüntü Modülü durduruldu.")

    # -----------------------------------------------------------------------
    # Yardımcı hesaplamalar
    # -----------------------------------------------------------------------

    def _mesafe(self, p1, p2):
        """İki landmark noktası arasındaki Öklid mesafesini hesaplar."""
        return ((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2) ** 0.5

    # -----------------------------------------------------------------------
    # El kontrolü
    # -----------------------------------------------------------------------

    def _el_isle(self, landmarks, simdi: float) -> None:
        cikti = self._el.isle(landmarks, simdi)
        self._son_el = cikti

        # Oto kalibrasyon: 3 sn boyunca avuç boyunu ölç → kontrol kutusunu mesafene uydur
        if self._oto_kalibre_aktif and landmarks is not None:
            self._el_boyutlari.append(cikti.avuc)
            if time.time() - self._oto_kalibre_baslangic >= 3.0:
                self._oto_kalibre_aktif = False
                self._kalibrasyonu_bitir()

        olaylar = [list(o) for o in cikti.olaylar]
        if any(o[0] == "mod_degistir" for o in olaylar):
            self.aktif_mod = "beklemede" if self.aktif_mod == "el" else "el"
            acik = self.aktif_mod == "el"
            logger.info("Bozkurt: el kontrolü %s.", "AÇIK" if acik else "BEKLEMEDE")
            self.bus.publish("tts_konuş", {"metin": "El kontrolü açık." if acik else "El kontrolü beklemede."})
            olaylar = [o for o in olaylar if o[0] != "mod_degistir"]
            if not acik:
                olaylar.append(["birak_hepsi", None])   # basılı tuş kalmasın

        if self.aktif_mod != "el" and not any(o[0] == "birak_hepsi" for o in olaylar):
            return
        if cikti.imlec is None and not olaylar:
            return
        self.bus.publish("el_hareketi_algilandi", {
            "mod": "mouse",
            "x": cikti.imlec[0] if cikti.imlec else None,
            "y": cikti.imlec[1] if cikti.imlec else None,
            "olaylar": olaylar,
            "jest": cikti.jest,
        })

    def _kalibrasyonu_bitir(self) -> None:
        if not self._el_boyutlari:
            self.bus.publish("tts_konuş", {"metin": "Elini göremedim, kalibrasyon yapılamadı."})
            return
        ort = sorted(self._el_boyutlari)[len(self._el_boyutlari) // 2]   # medyan
        self._el.a.referans_avuc = float(ort)
        try:
            import json
            os.makedirs("data", exist_ok=True)
            with open("data/calibration.json", "w", encoding="utf-8") as f:
                json.dump({"EL_REFERANS_AVUC": round(float(ort), 4)}, f, indent=2)
        except Exception as e:
            logger.error(f"Kalibrasyon kaydedilemedi: {e}")
        logger.info("El kalibrasyonu: referans avuç boyu %.3f", ort)
        self.bus.publish("tts_konuş", {"metin": "Tamam, kontrol alanını bu mesafeye göre ayarladım."})

    def _rehber_ciz(self, img) -> None:
        """Kamera penceresine nasıl kullanılacağını ve o anki durumu yazar (ASCII: OpenCV Türkçe harf çizemez)."""
        h, w = img.shape[:2]
        c = self._son_el
        jest_adi = {
            "imlec": "IMLEC", "tik": "TIKLA", "surukleme": "SURUKLE", "sag_tik": "SAG TIK",
            "kaydirma": "KAYDIR", "yumruk": "DURDU (yumruk)", "itme": "ITME = TIKLA",
            "bozkurt": "BOZKURT (tut...)", "yok": "EL YOK",
        }.get(c.jest if c else "yok", "-")
        renk = (0, 255, 0) if self.aktif_mod == "el" else (0, 165, 255)
        cv2.rectangle(img, (0, 0), (w, 34), (20, 20, 20), -1)
        durum = "EL KONTROLU ACIK" if self.aktif_mod == "el" else "BEKLEMEDE (Bozkurt ile ac)"
        cv2.putText(img, f"{durum}  |  {jest_adi}", (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, renk, 2)

        # Derinlik çubuğu: 1.0 = normal mesafe, 1.15+ = itme (tıklama)
        if c and c.jest != "yok":
            d = max(0.7, min(1.4, c.derinlik))
            x0, y0, bw, bh = w - 40, 50, 18, h - 140
            cv2.rectangle(img, (x0, y0), (x0 + bw, y0 + bh), (80, 80, 80), 1)
            dolu = int((d - 0.7) / 0.7 * bh)
            cv2.rectangle(img, (x0, y0 + bh - dolu), (x0 + bw, y0 + bh),
                          (0, 0, 255) if c.derinlik >= self._el.a.itme_orani else (255, 200, 0), -1)
            esik_y = y0 + bh - int((self._el.a.itme_orani - 0.7) / 0.7 * bh)
            cv2.line(img, (x0 - 6, esik_y), (x0 + bw + 6, esik_y), (0, 0, 255), 2)
            cv2.putText(img, "DERINLIK", (x0 - 52, y0 + bh + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1)

        satirlar = [
            "Acik el: imlec (avuc ortasi)",
            "Bas+isaret kisa: TIKLA | uzun: SURUKLE",
            "Bas+orta parmak: SAG TIK",
            "Iki parmak yukari/asagi: KAYDIR",
            "Yumruk: imleci birak, eli tasi, ac",
            "Eli kameraya hizla it: TIKLA",
            "Bozkurt 1 sn: ac / kapat   |  ESC: pencere",
        ]
        y = h - 12 - 18 * (len(satirlar) - 1)
        cv2.rectangle(img, (0, y - 18), (330, h), (20, 20, 20), -1)
        for satir in satirlar:
            cv2.putText(img, satir, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1)
            y += 18

    def _bozkurt_mu(self, landmarks):
        """
        Bozkurt işareti tespiti (Tasks API NormalizedLandmark kullanır):
        - İşaret parmağı (8) yukarıda
        - Serçe parmak (20) yukarıda
        - Orta (12) ve Yüzük (16) parmak aşağıda
        """
        isaret_yukarda = landmarks[8].y < landmarks[6].y
        serce_yukarda  = landmarks[20].y < landmarks[18].y
        orta_asagida   = landmarks[12].y > landmarks[10].y
        yuzuk_asagida  = landmarks[16].y > landmarks[14].y
        return isaret_yukarda and serce_yukarda and orta_asagida and yuzuk_asagida

    # -----------------------------------------------------------------------
    # Callback'ler (LIVE_STREAM modu için — görüntü döngüsüyle senkron)
    # -----------------------------------------------------------------------

    def _hand_result_callback(self, result, output_image, timestamp_ms):
        with self._result_lock:
            self._hand_result = result

    def _face_result_callback(self, result, output_image, timestamp_ms):
        with self._result_lock:
            self._face_result = result

    # -----------------------------------------------------------------------
    # Ana görüntü döngüsü
    # -----------------------------------------------------------------------

    def _vision_dongusu(self):
        # --- MediaPipe Tasks API Başlatma ---
        try:
            el_modeli = model_oku(HAND_MODEL_ADI)
            if el_modeli is None:
                logger.error("El modeli bulunamadı (%s). İndirmek için: python tools/hazirlik_kontrol.py --indir",
                             " / ".join(MODEL_DIZINLERI))
                return

            hand_opts = mp_vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_buffer=el_modeli),
                running_mode=mp_vision.RunningMode.LIVE_STREAM,
                num_hands=1,
                min_hand_detection_confidence=config.VISION_CONFIDENCE,
                min_hand_presence_confidence=config.VISION_CONFIDENCE,
                min_tracking_confidence=config.VISION_CONFIDENCE,
                result_callback=self._hand_result_callback,
            )
            self._hand_landmarker = mp_vision.HandLandmarker.create_from_options(hand_opts)
            logger.info("HandLandmarker başlatıldı.")

            yuz_modeli = model_oku(FACE_MODEL_ADI)
            if yuz_modeli is not None:
                face_opts = mp_vision.FaceLandmarkerOptions(
                    base_options=mp_python.BaseOptions(model_asset_buffer=yuz_modeli),
                    running_mode=mp_vision.RunningMode.LIVE_STREAM,
                    num_faces=1,
                    output_face_blendshapes=False,
                    output_facial_transformation_matrixes=False,
                    min_face_detection_confidence=config.VISION_CONFIDENCE,
                    min_face_presence_confidence=config.VISION_CONFIDENCE,
                    min_tracking_confidence=config.VISION_CONFIDENCE,
                    result_callback=self._face_result_callback,
                )
                self._face_landmarker = mp_vision.FaceLandmarker.create_from_options(face_opts)
                logger.info("FaceLandmarker başlatıldı.")
        except Exception as e:
            logger.error(f"MediaPipe Tasks başlatılamadı: {e}")
            return

        # --- Kamera Başlatma ---
        self.cap = cv2.VideoCapture(config.KAMERA_ID)
        if not self.cap.isOpened():
            logger.error("Kamera açılamadı!")
            return

        prev_x, prev_y = 0.5, 0.5
        timestamp_ms = 0

        while self._calisiyor:
            success, image = self.cap.read()
            if not success:
                logger.warning("Kameradan görüntü alınamadı.")
                time.sleep(0.01)
                continue

            timestamp_ms += 33  # ~30 FPS

            # BGR → RGB dönüşümü + MediaPipe Image nesnesi
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)

            # Asenkron detect (callback'ler ayrı thread'den dönebilir)
            try:
                self._hand_landmarker.detect_async(mp_image, timestamp_ms)
                if self._face_landmarker:
                    self._face_landmarker.detect_async(mp_image, timestamp_ms)
            except Exception as e:
                logger.debug(f"Detect hatası: {e}")

            # Sonuçları güvenli şekilde al
            with self._result_lock:
                hand_result = self._hand_result
                face_result = self._face_result

            h, w, _ = image.shape

            # --- 1. EL İŞLEMLERİ (jest mantığı: irle.adapters.vision.el_jestleri) ---
            landmarks = None
            if self.el_modu_izinli and hand_result and hand_result.hand_landmarks:
                landmarks = hand_result.hand_landmarks[0]
            if self.el_modu_izinli:
                self._el_isle(landmarks, time.time())
            if self.pencere_acik and landmarks is not None:
                for lm in landmarks:
                    cv2.circle(image, (int(lm.x * w), int(lm.y * h)), 4, (0, 200, 255), -1)

            # --- 2. GÖZ İŞLEMLERİ ---
            if face_result and face_result.face_landmarks:
                face_lms = face_result.face_landmarks[0]

                # Göz kırpma (sol göz kapakları: 386 ve 374)
                if len(face_lms) > 386:
                    sol_ust = face_lms[386]
                    sol_alt = face_lms[374]
                    dist_blink = self._mesafe(sol_ust, sol_alt)
                    is_blink = dist_blink < 0.008

                    if self.aktif_mod == "goz":
                        # Sol iris (468)
                        if len(face_lms) > 468:
                            sol_iris = face_lms[468]
                            self.bus.publish("bakis_yonu_algilandi", {
                                "x": 1.0 - sol_iris.x,
                                "y": sol_iris.y,
                                "click": is_blink,
                            })

            # --- TEST PENCERESİ (Türkçe rehber + derinlik çubuğu) ---
            if self.pencere_acik:
                display_image = cv2.flip(image, 1)
                self._rehber_ciz(display_image)
                cv2.imshow("Irle El Kontrolu", display_image)
                if cv2.waitKey(1) & 0xFF == 27:  # ESC: pencereyi kapat (el kontrolü sürer)
                    self.pencere_acik = False
                    cv2.destroyAllWindows()

        # Temizlik
        if self._hand_landmarker:
            self._hand_landmarker.close()
        if self._face_landmarker:
            self._face_landmarker.close()
        self.cap.release()
        cv2.destroyAllWindows()

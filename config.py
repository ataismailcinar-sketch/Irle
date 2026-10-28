"""
=============================================================================
CONFIG — Merkezi Yapılandırma Dosyası (V2.0)
=============================================================================
"""

# --- SES MODÜLÜ AYARLARI ---------------------------------------------------
SES_DILI                  = "tr-TR"
GURULTU_KALIBRASYONU_SURESI = 1
SES_TIMEOUT_SURESI        = 5
SES_CUMLE_SURESI          = 10

# --- INTENT MODÜLÜ AYARLARI ------------------------------------------------

# Kural motorunun büyük/küçük harf duyarlılığı
BUYUK_HARF_DUYARLI = False

# --- TTS MODÜLÜ AYARLARI ---------------------------------------------------

# Konuşma hızı (kelime/dakika). Normal: 150, Hızlı: 200
TTS_HIZ = 165

# Ses seviyesi (0.0 ile 1.0 arasında)
TTS_VOLUME = 1.0

# Windows'ta Türkçe ses için tercih edilen ses adı.
# None bırakılırsa sistem varsayılanını kullanır.
# Mevcut sesleri görmek için modules/tts_modulu.py'yi test modunda çalıştırın.
TTS_SES_ADI = None

# Asistanın sesli konuşmasını tamamen kapatır. Sadece metin olarak yanıt verir.
SESSİZ_MOD = False

# --- BELLEĞİ MODÜLÜ AYARLARI -----------------------------------------------

# Konuşmaların kaydedileceği JSON dosyası
BELLEK_DOSYASI = "data/konusmalar.json"

# Bellekte tutulacak maksimum konuşma sayısı (eski kayıtlar silinir)
BELLEK_MAX_KAYIT = 500

# --- AKSİYON MODÜLÜ AYARLARI ------------------------------------------------

UYGULAMA_KOMUTLARI = {
    "notepad":  "notepad.exe",
    "hesap":    "calc.exe",
    "explorer": "explorer.exe",
    "chrome":   "chrome.exe",
    "terminal": "cmd.exe",
}

# --- GÖRÜNTÜ MODÜLÜ AYARLARI ------------------------------------------------

# Kullanılacak kamera indeksi (0 genelde varsayılandır)
KAMERA_ID = 0

# Tespit hassasiyeti (0.0 - 1.0)
VISION_CONFIDENCE = 0.5

# Test penceresi varsayılan olarak açık mı?
VISION_DEBUG = True

# El ve Göz modu ayarları
EL_MODU_AKTIF  = True
GOZ_MODU_AKTIF = False

# Fare hareket hızı ve hassasiyet ayarları (Kalibrasyon Aracı ile bulunan değerler)
FARE_YUMUSATMA = 0.35         # Otomatik ayarlandi
VISION_MARGIN = 0.05          # Otomatik ayarlandi
VISION_PINCH_THRESHOLD = 0.09 # Otomatik ayarlandi

# --- TIKLAMA YÖNTEMLERİ (DOĞAL ETKİLEŞİM) -----------------------------------
PUSH_CLICK_AKTIF  = True      # Ekrana doğru parmağı itince tıklama (Air Tap / Z-Push)
DWELL_CLICK_AKTIF = True      # Hedef üzerinde durunca otomatik tıklama
DWELL_SURESI      = 0.7       # Hedefte bekleme süresi (saniye)
PINCH_CLICK_AKTIF = True      # Başparmak ve işaret parmağı birleştirme (Pinch)


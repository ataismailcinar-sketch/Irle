# -*- coding: utf-8 -*-
"""
=============================================================================
İRLE HAZIRLIK KONTROLÜ — "Köye gitmeden önce" tek komut
=============================================================================
    python tools/hazirlik_kontrol.py            # her şeyi kontrol et
    python tools/hazirlik_kontrol.py --indir    # eksik Whisper modelini de indir

Kontrol eder:
  1. Python paketleri (mikrofon, TTS, faster-whisper ...)
  2. .env ve Groq anahtarı (internet varsa anahtarın çalıştığını da dener)
  3. Ollama çalışıyor mu, model çekilmiş mi
  4. Yerel Whisper modeli diskte mi (internetsiz çalışabilmek için ŞART)
  5. Doğal Türkçe ses (Piper) indirilmiş mi; Windows Türkçe sesi var mı
  6. Mikrofon görünüyor mu
=============================================================================
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.request

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [KOK, os.path.join(KOK, "src")]
os.chdir(KOK)

from irle.app.settings import Settings, load_dotenv  # noqa: E402

TAMAM, UYARI, HATA = "✅", "⚠️ ", "❌"
sorunlar: list[str] = []


def satir(durum: str, metin: str, oneri: str = "") -> None:
    print(f"  {durum} {metin}")
    if oneri:
        print(f"       → {oneri}")
    if durum != TAMAM and oneri:
        sorunlar.append(oneri)


def baslik(metin: str) -> None:
    print(f"\n{metin}")


def paket_var(ad: str) -> bool:
    return importlib.util.find_spec(ad) is not None


def get_json(url: str, headers: dict | None = None, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    indir = "--indir" in sys.argv
    load_dotenv(os.path.join(KOK, ".env"))
    s = Settings()
    print("=" * 62)
    print("  İRLE HAZIRLIK KONTROLÜ")
    print("=" * 62)
    print(f"  Beyin modu: {s.brain_mode}   Kulak modu: {s.stt_mode}")

    # 1 ----------------------------------------------------------------
    baslik("1) Python paketleri")
    for ad, aciklama, zorunlu in [
        ("sounddevice", "mikrofon", True), ("numpy", "ses işleme", True),
        ("pyttsx3", "konuşma (TTS)", True), ("speech_recognition", "Google kulak (yedek)", False),
        ("faster_whisper", "yerel kulak — internetsiz tanıma", False),
        ("pyautogui", "ses/medya tuşları", True), ("psutil", "sistem bilgisi", True),
        ("pywinctl", "pencere kontrolü", False), ("pyperclip", "pano", False),
        ("screen_brightness_control", "parlaklık", False),
    ]:
        if paket_var(ad):
            satir(TAMAM, f"{ad} ({aciklama})")
        else:
            satir(HATA if zorunlu else UYARI, f"{ad} yok ({aciklama})",
                  f"pip install {ad.replace('_', '-') if ad != 'speech_recognition' else 'SpeechRecognition'}")

    # 2 ----------------------------------------------------------------
    baslik("2) Ayarlar ve Groq (ücretsiz bulut)")
    if os.path.exists(os.path.join(KOK, ".env")):
        satir(TAMAM, ".env dosyası var")
    else:
        satir(UYARI, ".env dosyası yok", "copy env_ornek.txt .env  (sonra GROQ_API_KEY doldur)")
    if not s.groq_api_key:
        satir(UYARI, "GROQ_API_KEY boş — bulut beyin ve bulut kulak kapalı",
              "https://console.groq.com → API Keys → anahtarı .env'e yapıştır")
    else:
        try:
            modeller = get_json(s.groq_base_url.rstrip("/") + "/models",
                                {"Authorization": f"Bearer {s.groq_api_key}"})
            ids = {m.get("id") for m in modeller.get("data", [])}
            for m in (s.groq_model, s.groq_stt_model):
                satir(TAMAM if m in ids else UYARI, f"Groq modeli: {m}",
                      "" if m in ids else "Bu model listede yok; .env'de IRLE_GROQ_MODEL'i değiştir")
        except urllib.error.HTTPError as exc:
            satir(HATA, f"Groq anahtarı reddedildi (HTTP {exc.code})", "Anahtarı kontrol et / yenisini oluştur")
        except Exception:
            satir(UYARI, "Groq'a ulaşılamadı (internet yok?) — anahtar test edilemedi")

    # 3 ----------------------------------------------------------------
    baslik("3) Ollama (yerel beyin)")
    taban = s.ollama_url.rstrip("/").removesuffix("/v1")
    try:
        etiketler = get_json(taban + "/api/tags", timeout=3)
        adlar = [m.get("name", "") for m in etiketler.get("models", [])]
        istenen = s.ollama_model if ":" in s.ollama_model else s.ollama_model + ":latest"
        if istenen in adlar:
            satir(TAMAM, f"Ollama çalışıyor, {s.ollama_model} hazır")
        else:
            satir(HATA, f"Ollama çalışıyor ama {s.ollama_model} yok (var olanlar: {', '.join(adlar) or '-'})",
                  f"ollama pull {s.ollama_model}")
    except Exception:
        satir(HATA if s.brain_mode in ("yerel",) else UYARI, "Ollama'ya ulaşılamadı",
              "https://ollama.com'dan kur ve çalıştır, sonra: ollama pull " + s.ollama_model)

    # 4 ----------------------------------------------------------------
    baslik("4) Yerel Whisper (internetsiz kulak)")
    if not paket_var("faster_whisper"):
        satir(UYARI, "faster-whisper kurulu değil — internet yokken İrle seni DUYAMAZ",
              "pip install faster-whisper")
    else:
        from faster_whisper import WhisperModel  # type: ignore
        try:
            WhisperModel(s.whisper_model, device="cpu", compute_type="int8", local_files_only=True)
            satir(TAMAM, f"'{s.whisper_model}' modeli diskte, internetsiz çalışır")
        except Exception:
            if indir:
                print(f"       '{s.whisper_model}' indiriliyor (bir kez, birkaç yüz MB)...")
                try:
                    WhisperModel(s.whisper_model, device="cpu", compute_type="int8")
                    satir(TAMAM, f"'{s.whisper_model}' indirildi")
                except Exception as exc:
                    satir(HATA, f"İndirme başarısız: {exc}", "İnternet bağlantısını kontrol et")
            else:
                satir(HATA, f"'{s.whisper_model}' modeli henüz indirilmemiş",
                      "İnternet varken: python tools/hazirlik_kontrol.py --indir")
        # Ekran kartı
        try:
            import ctranslate2  # type: ignore
            n = ctranslate2.get_cuda_device_count()
            satir(TAMAM if n else UYARI, f"CUDA ekran kartı: {n} adet" + ("" if n else " (işlemci kullanılacak)"),
                  "" if n else "İsteğe bağlı hızlandırma: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 "
                  "(olmazsa işlemci de yeterli; small model ~1-2 sn)")
        except Exception:
            pass

    # 4b ---------------------------------------------------------------
    baslik("4b) El/yüz takibi modelleri (MediaPipe)")
    model_dizini = os.path.join(KOK, "data", "models")
    modeller = {
        "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                                "hand_landmarker/float16/latest/hand_landmarker.task",
        "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                                "face_landmarker/float16/latest/face_landmarker.task",
    }
    for ad, url in modeller.items():
        yol = os.path.join(model_dizini, ad)
        eski = os.path.join(r"C:\irle_models", ad)
        if os.path.isfile(yol) or os.path.isfile(eski):
            satir(TAMAM, f"{ad} hazır")
        elif indir:
            try:
                os.makedirs(model_dizini, exist_ok=True)
                with urllib.request.urlopen(url, timeout=60) as r, open(yol + ".part", "wb") as f:
                    f.write(r.read())
                os.replace(yol + ".part", yol)
                satir(TAMAM, f"{ad} indirildi")
            except Exception as exc:
                satir(HATA, f"{ad} indirilemedi: {exc}", "İnternet bağlantısını kontrol et")
        else:
            satir(UYARI, f"{ad} yok (el ile fare kontrolü çalışmaz)",
                  "İnternet varken: python tools/hazirlik_kontrol.py --indir")

    # 5 ----------------------------------------------------------------
    baslik("5) Türkçe ses (TTS)")
    from irle.adapters.speech.tts_adapter import SES_DIZINI, VARSAYILAN_PIPER_SESLERI, piper_modeli_bul
    if not paket_var("piper"):
        satir(UYARI, "piper-tts kurulu değil — doğal Türkçe ses yok, Windows sesi kullanılacak",
              "pip install piper-tts")
    else:
        yol = piper_modeli_bul(s.piper_voice)
        if yol:
            satir(TAMAM, f"Piper Türkçe sesi: {os.path.basename(yol)}")
        elif indir:
            from piper.download_voices import download_voice  # type: ignore
            from pathlib import Path
            os.makedirs(SES_DIZINI, exist_ok=True)
            adaylar = [s.piper_voice] if s.piper_voice and not s.piper_voice.endswith(".onnx") else []
            for ad in adaylar + [a for a in VARSAYILAN_PIPER_SESLERI if a not in adaylar]:
                print(f"       '{ad}' indiriliyor (~60 MB)...")
                try:
                    download_voice(ad, Path(SES_DIZINI))
                    satir(TAMAM, f"Piper sesi indirildi: {ad}")
                    break
                except Exception as exc:
                    print(f"       {ad} indirilemedi: {exc}")
            else:
                satir(HATA, "Hiçbir Türkçe Piper sesi indirilemedi", "İnternet bağlantısını kontrol et")
        else:
            satir(UYARI, "Piper Türkçe sesi indirilmemiş",
                  "İnternet varken: python tools/hazirlik_kontrol.py --indir")
    if paket_var("pyttsx3") and sys.platform == "win32":
        try:
            import pyttsx3  # type: ignore
            from irle.adapters.speech.tts_adapter import turkce_ses_mi as _turkce_ses_mi
            motor = pyttsx3.init()
            sesler = motor.getProperty("voices") or []
            tr = [v.name for v in sesler if _turkce_ses_mi(v)]
            if tr:
                satir(TAMAM, f"Türkçe ses: {tr[0]}")
            else:
                satir(UYARI, "Windows'ta Türkçe ses yok (Piper yoksa İngilizce aksanla okur)",
                      "Piper sesi indir ya da: Ayarlar → Saat ve dil → Konuşma → Ses ekle → Türkçe")
        except Exception as exc:
            satir(UYARI, f"TTS kontrol edilemedi: {exc}")

    # 6 ----------------------------------------------------------------
    baslik("6) Mikrofon")
    if paket_var("sounddevice"):
        try:
            import sounddevice as sd  # type: ignore
            girdi = sd.query_devices(kind="input")
            satir(TAMAM, f"Varsayılan mikrofon: {girdi['name']}")
        except Exception as exc:
            satir(HATA, f"Mikrofon bulunamadı: {exc}", "Windows ses ayarlarından mikrofonu etkinleştir")

    # ------------------------------------------------------------------
    print("\n" + "=" * 62)
    if not sorunlar:
        print("  Her şey hazır. İnternetsiz de çalışırsın. 🎉")
    else:
        print(f"  Yapılacaklar ({len(sorunlar)}):")
        for i, o in enumerate(dict.fromkeys(sorunlar), 1):
            print(f"   {i}. {o}")
    print("=" * 62)


if __name__ == "__main__":
    main()

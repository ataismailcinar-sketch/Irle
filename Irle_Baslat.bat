@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   IRLE v2.5 — Asistan Baslatiliyor...
echo ========================================================
echo.
if not exist ".env" (
    echo  [!] .env dosyasi yok. env_ornek.txt dosyasini .env olarak kopyalayip
    echo      GROQ_API_KEY degerini doldurursan bulut beyni de acilir.
    echo      Simdilik sadece yerel Ollama denenecek.
    echo.
)
echo  Beyin : Groq (internet varsa, ucretsiz) -^> Ollama (yerel, cevrimdisi)
echo  Kulak : Groq Whisper -^> yerel Whisper -^> Google
echo  Ses   : Piper (dogal Turkce) -^> Windows sesi
echo  Ilk kurulumda: python tools\hazirlik_kontrol.py --indir
echo  Telefon Kontrolcu: http://[BilgisayarIP]:5555
echo.

python main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Bir hata olustu. Hata loglarini yukaridan kontrol edebilirsiniz.
    pause
)

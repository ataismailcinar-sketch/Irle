@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set LOG=kurulum_log.txt

echo ============================================================
echo   IRLE KURULUM — tek tikla hazirlik
echo ============================================================
echo  Her sey %LOG% dosyasina yaziliyor (Claude okuyup duzeltebilsin).
echo.
echo IRLE kurulum %date% %time% > "%LOG%"

REM ---------------------------------------------------------------
echo [1/6] Python kontrol ediliyor...
python --version >> "%LOG%" 2>&1
if errorlevel 1 (
    echo  [X] Python bulunamadi. https://www.python.org adresinden kur, "Add to PATH" sec.
    echo PYTHON YOK >> "%LOG%"
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo      %%v

REM ---------------------------------------------------------------
echo [2/6] Paketler kuruluyor (birkac dakika surebilir)...
python -m pip install --upgrade pip >> "%LOG%" 2>&1
python -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    echo  [!] Bazi paketler kurulamadi. Ayrinti: %LOG%
    echo PIP HATA >> "%LOG%"
) else (
    echo      Tamam.
)

REM ---------------------------------------------------------------
echo [3/6] Ayar dosyasi (.env)...
if not exist ".env" (
    copy /y env_ornek.txt .env >nul
    echo      .env olusturuldu.
) else (
    echo      .env zaten var, dokunulmadi.
)
findstr /r /c:"^GROQ_API_KEY=..*" .env >nul 2>&1
if errorlevel 1 (
    echo.
    echo      Groq anahtari yok. Ucretsiz bulut beyin + bulut kulak icin:
    echo      https://console.groq.com  -^>  API Keys  -^>  Create API Key
    set "GROQKEY="
    set /p "GROQKEY=     Anahtari yapistir (bos birakip Enter = simdilik gec): "
    call :groq_yaz
)

REM ---------------------------------------------------------------
echo [4/6] Ollama (yerel beyin)...
set "OLLAMA=ollama"
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    ) else (
        echo      Ollama kurulu degil. Internetsiz beyin icin gerekli.
        choice /c EH /n /m "     Simdi winget ile kurulsun mu? [E/H] "
        if errorlevel 2 (
            set "OLLAMA="
        ) else (
            winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements >> "%LOG%" 2>&1
            set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
        )
    )
)
if defined OLLAMA (
    echo      qwen2.5:7b modeli cekiliyor - yaklasik 4.7 GB, ilk seferde uzun surer...
    "%OLLAMA%" pull qwen2.5:7b >> "%LOG%" 2>&1
    if errorlevel 1 (echo      [!] Model cekilemedi, ayrinti: %LOG%) else (echo      Tamam.)
) else (
    echo      Atlandi. Sonra: https://ollama.com  ve  ollama pull qwen2.5:7b
)

REM ---------------------------------------------------------------
echo [5/6] Whisper modeli ve Piper Turkce sesi indiriliyor...
python tools\hazirlik_kontrol.py --indir > kurulum_kontrol.txt 2>&1
type kurulum_kontrol.txt
type kurulum_kontrol.txt >> "%LOG%"

REM ---------------------------------------------------------------
echo.
echo [6/6] Testler calistiriliyor...
python -m pytest -q tests > kurulum_test.txt 2>&1
type kurulum_test.txt >> "%LOG%"
findstr /r /c:"passed" /c:"failed" /c:"error" kurulum_test.txt

echo.
echo ============================================================
echo   Bitti. Claude'a "kurulum bitti" yaz; loglara bakip
echo   sorun varsa duzeltir. Sonra Irle_Baslat.bat ile baslat.
echo ============================================================
pause
exit /b 0

:groq_yaz
if not defined GROQKEY (
    echo      Gecildi. Sonra .env icindeki GROQ_API_KEY= satirina yazabilirsin.
    goto :eof
)
powershell -NoProfile -Command "$k=$env:GROQKEY.Trim(); (Get-Content .env -Encoding UTF8) -replace '^GROQ_API_KEY=.*', ('GROQ_API_KEY=' + $k) | Set-Content .env -Encoding UTF8"
echo      Anahtar .env dosyasina yazildi.
echo GROQ ANAHTARI YAZILDI >> "%LOG%"
goto :eof

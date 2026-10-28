@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   IRLE Telefon Kontrolcu Baslatiliyor  ║
echo  ╚══════════════════════════════════════╝
echo.

python kontrolcu_app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  HATA: Baslatilamadi.
    echo  "pip install flask flask-socketio qrcode[pil] pillow pyautogui" deneyin.
    pause
)

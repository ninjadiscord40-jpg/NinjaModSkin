@echo off
chcp 65001 >nul
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed --name NinjaModSkin --add-data "config.json;." --hidden-import PySide6.QtSvg main.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)
echo.
echo Done: dist\NinjaModSkin\NinjaModSkin.exe
pause

@echo off
setlocal
set "PYTHON=python"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m pytest --version >nul 2>nul
  if not errorlevel 1 set "PYTHON=.venv\Scripts\python.exe"
)
%PYTHON% -m pytest || exit /b 1
%PYTHON% -m PyInstaller --noconfirm --clean --windowed --name TabletSpeed --icon assets\tabletspeed.ico --paths src main.py || exit /b 1
echo Build complete: dist\TabletSpeed\TabletSpeed.exe

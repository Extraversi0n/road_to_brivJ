@echo off
setlocal
set "PY=py -3"
set "NAME=IdleChampsOverlay"

%PY% -m pip install --upgrade pip pyinstaller certifi

%PY% -m PyInstaller ^
  --onefile --noconsole ^
  --name %NAME% ^
  --add-data "goldtruhe_icon.png;." ^
  --add-data "silbertruhe_icon.png;." ^
  --add-data "gems_icon.png;." ^
  --add-data "blacksmithcontract_icon.png;." ^
  progress_tracker_extended.py

echo(
echo EXE built at: dist\%NAME%.exe
pause

@echo off
setlocal
REM Build from this script’s folder
cd /d "%~dp0"

set "PY=py -3"
set "NAME=IdleChampsOverlay"

REM Deps (use requirements.txt if you have one)
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
REM or:
REM %PY% -m pip install pyinstaller pillow requests certifi

REM Build EXE (no icon data bundled; app loads icons from the log folder)
%PY% -m PyInstaller ^
  --onefile --noconsole ^
  --clean ^
  --name "%NAME%" ^
  progress_tracker_extended.py

echo(
echo EXE built at: "%CD%\dist\%NAME%.exe"
pause

@echo off
REM Build Posziona as a Windows .exe using PyInstaller.
REM
REM Prerequisites:
REM   - Python 3 with venv (Python 3.8+)
REM   - pip install -r requirements.txt
REM   - pip install pyinstaller
REM   - pywebview[win64] or pywebview[win32] (for the native backend)
REM   - WebView2 runtime (pre-installed on Windows 10/11)
REM
REM Usage:
REM   build_exe.bat
REM
REM Output: dist\posziona.exe
REM
REM To build with GUI mode (no console window), set console=False
REM in build_exe.spec (CLI flags like --windowed cannot be combined
REM with a .spec file). To build as a single file, the spec already
REM defines a one-file EXE, so just run pyinstaller with the spec.

setlocal
set APP_NAME=posziona
set VERSION=0.1.1

echo === Building Posziona .exe ===

REM Clean previous build
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Install dependencies
echo === Installing dependencies ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

REM Build with PyInstaller using the spec file
echo === Running PyInstaller ===
pyinstaller build_exe.spec --noconfirm

echo.
echo === Done! ===
echo Executable: dist\%APP_NAME%.exe
echo.
echo To run:
echo   dist\%APP_NAME%.exe
echo   dist\%APP_NAME%.exe --mode server
echo   dist\%APP_NAME%.exe --mode client --server-url http://192.168.1.10:5000/
echo   dist\%APP_NAME%.exe --help

endlocal

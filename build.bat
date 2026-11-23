@echo off
title Building JARVIS.exe
echo ============================================
echo   TORVIS (JARVIS) - Native Edition  ^|  EXE builder
echo   BUILD 19 - same config as auto-py-to-exe-config.json
echo   and the GitHub workflow (.github/workflows/build-exe.yml)
echo ============================================
python --version >nul 2>&1 || (echo Python not found. Install Python 3.12 from python.org and tick "Add to PATH". & pause & exit /b 1)
echo Installing what the app needs...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo Building JARVIS.exe (this takes a minute or two)...
python -m PyInstaller --noconfirm --onefile --windowed --name JARVIS --icon icon.ico --add-data "jarvis-hud.html;." --add-data "icon.ico;." --add-data "icon.png;." --add-data "backend.py;." --add-data "jarvis_build14.py;." --add-data "jarvis_build15.py;." --add-data "jarvis_build16.py;." --add-data "jarvis_build17.py;." --add-data "jarvis_build18.py;." --add-data "jarvis_build19.py;." --add-data "requirements.txt;." --collect-all webview --collect-all pystray --collect-all pyttsx3 --hidden-import pyttsx3.drivers.sapi5 --hidden-import speech_recognition --hidden-import pyaudio --hidden-import pystray --hidden-import comtypes --hidden-import PIL --hidden-import cv2 --hidden-import googleapiclient.discovery --hidden-import googleapiclient.http --hidden-import google.oauth2.credentials --hidden-import google_auth_oauthlib.flow --hidden-import pyautogui --hidden-import backend --hidden-import jarvis_build14 --hidden-import jarvis_build15 --hidden-import jarvis_build16 --hidden-import jarvis_build17 --hidden-import jarvis_build18 --hidden-import jarvis_build19 jarvis.py
echo.
echo DONE!  Your app is here:  dist\JARVIS.exe
echo You can move JARVIS.exe anywhere - Desktop, USB, another PC.
pause

@echo off
rem Startet die VidSketch-Oberflaeche (app_gui.py).
rem Liegt im Ordner VidSketch\VidSketch; alle Pfade sind relativ zu dieser Datei.
rem Die Conda-Umgebung "VidSketch" wird unter %USERPROFILE%\miniconda3 erwartet.
rem Anderer Pfad? Einfach VIDSKETCH_PY vor dem Start setzen.

cd /d "%~dp0"

if defined VIDSKETCH_PY (
    set "PY=%VIDSKETCH_PY%"
) else (
    set "PY=%USERPROFILE%\miniconda3\envs\VidSketch\python.exe"
)

if not exist "%PY%" (
    echo Python der Umgebung "VidSketch" wurde nicht gefunden:
    echo   %PY%
    echo Setze VIDSKETCH_PY auf den Pfad zu python.exe oder pruefe die Conda-Installation.
    pause
    exit /b 1
)

"%PY%" app_gui.py
if errorlevel 1 (
    echo.
    echo Die Oberflaeche wurde mit einem Fehler beendet.
    pause
)

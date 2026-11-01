@echo off
rem Carp Landing Net Studio: double-click to open the window.
rem Blender: NET_BLENDER, else ..\bivvy-project\_vendor (read-only), else this project's _vendor (setup_blender.ps1).
cd /d "%~dp0"
python -m studio.cli blender >nul 2>&1
if errorlevel 1 (
  echo Blender not found. Running setup_blender.ps1 to download a portable Blender into _vendor\ ...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_blender.ps1" || goto :fail
)
python -m studio.gui || goto :fail
exit /b 0
:fail
echo.
echo Something went wrong - see the message above.
pause

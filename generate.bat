@echo off
rem Generate a preset without the window, e.g.:  generate.bat net_42_one_piece
rem Add --quick [--state scooping] for a fast single preview. "generate.bat all" builds every preset.
cd /d "%~dp0"
if "%~1"=="" (
  python -m studio.cli list
  echo.
  echo Usage: generate.bat ^<preset^> [--quick [--state deployed^|scooping^|wet^|disassembled]]   or   generate.bat all
  exit /b 1
)
if /i "%~1"=="all" (
  python -m studio.cli all
  exit /b %errorlevel%
)
python -m studio.cli generate %*

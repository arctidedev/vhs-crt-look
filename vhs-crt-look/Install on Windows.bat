@echo off
rem Double-click to install the vhs-crt-look skill for Claude Code (Windows).
rem If Windows shows "Windows protected your PC", click "More info", then "Run anyway".
rem Unattended:  "Install on Windows.bat" --yes   (installs ffmpeg without asking, does not pause)
rem             "Install on Windows.bat" --no-pause   (asks nothing, installs nothing extra, does not pause)
setlocal EnableExtensions
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "DEST=%USERPROFILE%\.claude\skills\vhs-crt-look"
if defined CLAUDE_CONFIG_DIR if exist "%CLAUDE_CONFIG_DIR%\" set "DEST=%CLAUDE_CONFIG_DIR%\skills\vhs-crt-look"

set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3.9 or newer is needed and was not found.
  where winget >nul 2>&1 || goto nopython
  if /i "%~1"=="--no-pause" goto nopython
  echo It can be installed now with:  winget install -e --id Python.Python.3.12 --scope user
  if /i not "%~1"=="--yes" (
    choice /m "Install Python now"
    if errorlevel 2 goto nopython
  )
  winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
  if not defined PY goto nopython
)

if /i not "%HERE%"=="%DEST%" (
  echo Copying the skill to %DEST%
  robocopy "%HERE%" "%DEST%" /E /XD .venv __pycache__ vhslook_preview /NFL /NDL /NJH /NJS /NP >nul
)

%PY% "%DEST%\scripts\vhslook.py" setup %*
set "RC=%ERRORLEVEL%"
goto done

:nopython
echo Install Python from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run this again.
set "RC=1"

:done
if /i "%~1"=="--yes" goto end
if /i "%~1"=="--no-pause" goto end
pause
:end
exit /b %RC%

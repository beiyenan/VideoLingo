@echo off
rem ===================================================================
rem  VideoLingo launcher (portable)
rem
rem  Paths are derived from this script's own location (%~dp0), so the
rem  repository can live anywhere. Copy it next to start.py and double-click.
rem
rem  The port lives in .streamlit\config.toml, not on the command line:
rem  "uv run --port" is rejected by uv, and start.py has no such argument.
rem ===================================================================
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"

rem --- Locate the project root (this file should sit next to start.py) ---
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /D "%ROOT%"

set "URL=http://localhost:8501"
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%ROOT%\.venv\bin\python"

rem --- Find uv: PATH first, then the usual per-user install location ---
set "UV="
for %%U in (uv.exe uv) do (
    if not defined UV (
        for /f "delims=" %%P in ('where %%U 2^>nul') do (
            if not defined UV set "UV=%%P"
        )
    )
)
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%USERPROFILE%\.cargo\bin\uv.exe"   set "UV=%USERPROFILE%\.cargo\bin\uv.exe"

if not exist "%ROOT%\start.py" (
    echo ERROR: start.py was not found in "%ROOT%".
    echo        Keep this launcher in the VideoLingo project folder.
    pause
    exit /b 1
)

if not defined UV (
    echo ERROR: uv was not found.
    echo        Install it from https://docs.astral.sh/uv/ and reopen this window.
    pause
    exit /b 1
)

rem --- Already running? Then just open the page and quit ---
if exist "%PY%" (
    "%PY%" "%ROOT%\open_browser.py" --check "%URL%" >nul 2>&1
    if not errorlevel 1 (
        echo VideoLingo is already running. Opening the web page...
        start "" "%URL%"
        exit /b 0
    )
)

echo ============================================
echo   VideoLingo Launcher
echo   Project: %ROOT%
echo   The web page opens by itself once the server answers.
echo   If it does not open, visit: %URL%
echo   Close this window to stop VideoLingo.
echo ============================================

rem --- Open the browser as soon as the server answers ---
if exist "%ROOT%\open_browser.py" (
    if exist "%PY%" (
        start "" /b "%PY%" "%ROOT%\open_browser.py" "%URL%"
    ) else (
        start "" /b cmd /c ""%ROOT%\open_browser.bat""
    )
) else if exist "%ROOT%\open_browser.bat" (
    start "" /b "%ROOT%\open_browser.bat"
)

rem --- Start the server ---
"%UV%" run "%ROOT%\start.py"

echo.
echo VideoLingo has stopped.
pause
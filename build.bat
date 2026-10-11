@echo off
rem Build dist\Win2AndroidTVRemote.exe (one file, no console window).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller || goto :error
".venv\Scripts\pyinstaller.exe" --noconfirm --onefile --noconsole --name Win2AndroidTVRemote ^
    --collect-submodules zeroconf --collect-submodules androidtvremote2 main.py || goto :error
echo Done: dist\Win2AndroidTVRemote.exe
exit /b 0

:error
echo Build failed.
exit /b 1

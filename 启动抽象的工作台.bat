@echo off
rem Abstract Workbench launcher - double click to start
cd /d "%~dp0"
set PYTHONUTF8=1
rem Prefer the packaged exe; fall back to the project venv.
for %%f in ("dist_app\*\*.exe") do (
  if exist "%%f" (
    start "" "%%f"
    exit /b
  )
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "backend\run_app.py"
  exit /b
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "backend\run_app.py"
  exit /b
)
echo [ERROR] Neither dist_app exe nor .venv python was found.
echo Please keep this .bat next to the dist_app and .venv folders.
pause

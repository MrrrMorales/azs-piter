@echo off
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8080" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
start /min "" python -m http.server 8080
timeout /t 2 /nobreak > nul
start "" "http://localhost:8080"

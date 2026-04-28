@echo off
cd /d D:\PiterAZS
python fetch_per_station_prices.py >> D:\PiterAZS\update_log.txt 2>&1

git diff --quiet station_prices.json
if errorlevel 1 (
    git add station_prices.json >> D:\PiterAZS\update_log.txt 2>&1
    for /f "tokens=*" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'dd.MM.yyyy HH:mm'"') do set DT=%%d
    git commit -m "Автообновление цен %DT% (локально)" >> D:\PiterAZS\update_log.txt 2>&1
    git pull --rebase -X ours >> D:\PiterAZS\update_log.txt 2>&1
    git push >> D:\PiterAZS\update_log.txt 2>&1
    echo [%DT%] Запушено: station_prices.json обновлён >> D:\PiterAZS\update_log.txt
) else (
    echo Изменений нет — пуш не нужен >> D:\PiterAZS\update_log.txt
)

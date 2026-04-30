@echo off
cd /d D:\PiterAZS

set LOG=D:\PiterAZS\update_log.txt
for /f "tokens=*" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'dd.MM.yyyy HH:mm'"') do set DT=%%d

echo. >> %LOG%
echo ======================================== >> %LOG%
echo [%DT%] Запуск полного обновления цен >> %LOG%
echo ======================================== >> %LOG%

:: Шаг 1: средние цены по сетям → prices.json + JSONBin
echo [%DT%] Шаг 1/2: parser.py >> %LOG%
python parser.py >> %LOG% 2>&1
if errorlevel 1 (
    echo [%DT%] ОШИБКА: parser.py завершился с ошибкой >> %LOG%
)

:: Шаг 2: индивидуальные цены + детали АЗС → station_prices.json
echo [%DT%] Шаг 2/2: fetch_per_station_prices.py >> %LOG%
python fetch_per_station_prices.py >> %LOG% 2>&1
if errorlevel 1 (
    echo [%DT%] ОШИБКА: fetch_per_station_prices.py завершился с ошибкой >> %LOG%
)

:: Шаг 3: git push если station_prices.json изменился
git diff --quiet station_prices.json
if errorlevel 1 (
    git add station_prices.json >> %LOG% 2>&1
    git commit -m "Автообновление цен %DT%" >> %LOG% 2>&1
    git pull --rebase -X ours >> %LOG% 2>&1
    git push >> %LOG% 2>&1
    echo [%DT%] Запушено: station_prices.json обновлён >> %LOG%
) else (
    echo [%DT%] station_prices.json не изменился — пуш не нужен >> %LOG%
)

:: prices.json тоже пушим если изменился
git diff --quiet prices.json
if errorlevel 1 (
    git add prices.json >> %LOG% 2>&1
    git commit -m "Автообновление средних цен %DT%" >> %LOG% 2>&1
    git pull --rebase -X ours >> %LOG% 2>&1
    git push >> %LOG% 2>&1
    echo [%DT%] Запушено: prices.json обновлён >> %LOG%
)

echo [%DT%] Готово >> %LOG%

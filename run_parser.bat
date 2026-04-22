@echo off
set JSONBIN_BIN_ID=69e79cb4856a68218959b94f
set JSONBIN_API_KEY=$2a$10$xim0sZ1pskUobfoz7c0iQO7M9aNhCO05lBuDkQcZuK0PMOOMZKwee

echo === Шаг 1: Цены по сети (parser.py) ===
python parser.py

echo.
echo === Шаг 2: Индивидуальные цены по АЗС (fetch_per_station_prices.py) ===
python fetch_per_station_prices.py

pause

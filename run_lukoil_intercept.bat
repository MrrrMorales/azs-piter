@echo off
chcp 65001 >nul
echo ============================================================
echo  Перехват трафика ЛУКОЙЛ с обходом SSL pinning
echo ============================================================
echo.

set PACKAGE=ru.serebryakovas.lukoilmobileapp

REM ---- Проверяем что frida-server запущен ----
frida-ps -U 2>nul | findstr "frida" >nul
if %errorlevel% neq 0 (
    echo [*] Запускаем frida-server...
    start /min adb shell "/data/local/tmp/frida-server &"
    timeout /t 3 >nul
)

REM ---- Скачиваем SSL bypass скрипт если нет ----
if not exist "frida-ssl-bypass.js" (
    echo [*] Скачиваем универсальный SSL pinning bypass...
    curl -L "https://raw.githubusercontent.com/httptoolkit/frida-interception-and-unpinning/main/frida-script.js" -o "frida-ssl-bypass.js"
    if %errorlevel% neq 0 (
        echo [!] Не удалось скачать автоматически.
        echo     Скачай вручную: https://github.com/httptoolkit/frida-interception-and-unpinning
        echo     Сохрани как frida-ssl-bypass.js
        pause & exit /b 1
    )
    echo [OK] Скрипт скачан.
)

echo.
echo [*] Запускаем приложение ЛУКОЙЛ с bypass SSL pinning...
echo     Package: %PACKAGE%
echo.
echo     ДЕЙСТВИЯ В ПРИЛОЖЕНИИ:
echo     1. Войди в аккаунт (или пропусти)
echo     2. Открой карту АЗС
echo     3. Нажми на несколько станций, посмотри цены
echo     4. Закрой приложение
echo.
echo     Весь трафик сохраняется в lukoil_raw.json
echo     Смотри в mitmweb: http://localhost:8081
echo.

frida -U -f %PACKAGE% -l frida-ssl-bypass.js --no-pause

echo.
echo [OK] Сессия завершена. Проверь lukoil_raw.json
pause

@echo off
chcp 65001 >nul
echo ============================================================
echo  Автонастройка Frida + mitmproxy на Android-эмуляторе
echo ============================================================
echo.

REM ---- Проверяем adb ----
where adb >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] adb не найден. Добавь в PATH:
    echo     C:\Users\%USERNAME%\AppData\Local\Android\Sdk\platform-tools
    pause & exit /b 1
)

REM ---- Проверяем, что эмулятор запущен ----
adb devices | findstr "emulator" >nul
if %errorlevel% neq 0 (
    echo [!] Эмулятор не обнаружен. Запусти AVD в Android Studio сначала.
    pause & exit /b 1
)
echo [OK] Эмулятор найден.

REM ---- Получаем root ----
echo [*] Получаем root...
adb root
timeout /t 2 >nul

REM ---- Проверяем архитектуру ----
echo [*] Архитектура эмулятора:
adb shell getprop ro.product.cpu.abi

REM ---- Устанавливаем frida-tools ----
echo.
echo [*] Устанавливаем frida-tools (Python)...
pip install frida-tools objection --quiet
echo [OK] frida-tools установлен.

REM ---- Получаем версию Frida ----
for /f "tokens=*" %%v in ('frida --version') do set FRIDA_VER=%%v
echo [*] Версия Frida: %FRIDA_VER%

REM ---- Скачиваем frida-server ----
set FRIDA_FILE=frida-server-%FRIDA_VER%-android-x86_64.xz
set FRIDA_URL=https://github.com/frida/frida/releases/download/%FRIDA_VER%/%FRIDA_FILE%

if not exist "%FRIDA_FILE%" (
    echo [*] Скачиваем frida-server %FRIDA_VER%...
    curl -L "%FRIDA_URL%" -o "%FRIDA_FILE%"
    if %errorlevel% neq 0 (
        echo [!] Ошибка скачивания. Скачай вручную:
        echo     %FRIDA_URL%
        pause & exit /b 1
    )
) else (
    echo [OK] frida-server уже скачан.
)

REM ---- Распаковываем .xz ----
set FRIDA_BIN=frida-server-%FRIDA_VER%-android-x86_64
if not exist "%FRIDA_BIN%" (
    echo [*] Распаковываем .xz...
    REM Пробуем через Python (всегда доступен)
    python -c "import lzma,shutil; shutil.copyfileobj(lzma.open('%FRIDA_FILE%','rb'),open('%FRIDA_BIN%','wb'))"
    echo [OK] Распаковано.
)

REM ---- Заливаем на эмулятор ----
echo [*] Копируем frida-server на эмулятор...
adb push "%FRIDA_BIN%" /data/local/tmp/frida-server
adb shell chmod 755 /data/local/tmp/frida-server
echo [OK] frida-server установлен в /data/local/tmp/

REM ---- Устанавливаем mitmproxy-сертификат ----
echo.
echo [*] Устанавливаем сертификат mitmproxy в системное хранилище...

REM Качаем сертификат через прокси (mitmproxy должен уже работать на порту 8080)
adb shell settings put global http_proxy 10.0.2.2:8080

REM Скачиваем cert с mitmproxy (через эмулятор)
adb shell "wget -O /sdcard/mitmproxy-ca.pem http://mitm.it/cert/pem" 2>nul
if %errorlevel% neq 0 (
    echo [!] Не удалось скачать сертификат автоматически.
    echo     Убедись что mitmproxy запущен: mitmweb -p 8080
    echo     Потом запусти этот скрипт снова.
    goto :SKIP_CERT
)

REM Получаем hash для имени файла
for /f %%h in ('python -c "import subprocess,sys; r=subprocess.run(['adb','shell','openssl','x509','-inform','PEM','-subject_hash_old','-in','/sdcard/mitmproxy-ca.pem'],capture_output=True,text=True); print(r.stdout.strip().split()[0])"') do set CERT_HASH=%%h
echo [*] Hash сертификата: %CERT_HASH%

adb remount
adb shell "cp /sdcard/mitmproxy-ca.pem /system/etc/security/cacerts/%CERT_HASH%.0"
adb shell "chmod 644 /system/etc/security/cacerts/%CERT_HASH%.0"
echo [OK] Сертификат установлен как %CERT_HASH%.0
adb reboot
echo [*] Эмулятор перезагружается... подожди 30 сек.
timeout /t 30 >nul
adb root

:SKIP_CERT

REM ---- Запускаем frida-server ----
echo.
echo [*] Запускаем frida-server в фоне...
start "frida-server" /min adb shell "/data/local/tmp/frida-server &"
timeout /t 3 >nul

REM ---- Проверяем ----
frida-ps -U | findstr "emulator\|zygote" >nul
if %errorlevel% equ 0 (
    echo [OK] Frida работает!
) else (
    echo [?] Проверь вручную: frida-ps -U
)

echo.
echo ============================================================
echo  Готово! Следующие шаги:
echo.
echo  1. Запусти mitmproxy:
echo     mitmweb -p 8080 -s lukoil_capture.py
echo.
echo  2. Запусти приложение с обходом pinning:
echo     run_lukoil_intercept.bat
echo ============================================================
pause

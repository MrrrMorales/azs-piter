@echo off
:: Запускать от имени Администратора!
:: Регистрирует еженедельное обновление цен АЗС в Windows Task Scheduler

set TASK_NAME=AZS-Piter Weekly Price Update
set SCRIPT=D:\PiterAZS\update_prices.bat
set CMD=cmd.exe /c "%SCRIPT%"

:: Удалить старую задачу если есть
schtasks /delete /tn "%TASK_NAME%" /f 2>nul

:: Создать задачу: каждый понедельник в 09:00
schtasks /create /tn "%TASK_NAME%" /tr "%CMD%" /sc weekly /d MON /st 09:00 /f /rl highest

echo.
if errorlevel 1 (
    echo ОШИБКА: не удалось создать задачу. Запустите от имени Администратора.
) else (
    echo Задача зарегистрирована:
    schtasks /query /tn "%TASK_NAME%" /fo list | findstr /C:"Имя задания" /C:"Следующее" /C:"Task To Run" /C:"Next Run"
    echo.
    echo Цены будут обновляться автоматически каждый понедельник в 09:00.
    echo Лог: D:\PiterAZS\update_log.txt
)
pause

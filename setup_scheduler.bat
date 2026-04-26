@echo off
:: Запускать от имени Администратора!
:: Регистрирует задачу обновления цен ГПН в Task Scheduler

set TASK_NAME=AZS-Piter GPN Price Update
set SCRIPT=D:\PiterAZS\update_gpn_prices.ps1
set PS_CMD=powershell.exe -NonInteractive -ExecutionPolicy Bypass -File "%SCRIPT%"

:: Удалить старую задачу
schtasks /delete /tn "%TASK_NAME%" /f 2>nul

:: Создать задачу с 4 запусками в день
schtasks /create /tn "%TASK_NAME%" /tr "%PS_CMD%" /sc daily /st 07:00 /f
schtasks /create /tn "%TASK_NAME%_11" /tr "%PS_CMD%" /sc daily /st 11:00 /f
schtasks /create /tn "%TASK_NAME%_15" /tr "%PS_CMD%" /sc daily /st 15:00 /f
schtasks /create /tn "%TASK_NAME%_19" /tr "%PS_CMD%" /sc daily /st 19:00 /f

echo.
echo Задачи зарегистрированы:
schtasks /query /tn "%TASK_NAME%" /fo list | findstr "Имя задания\|Следующее"
schtasks /query /tn "%TASK_NAME%_11" /fo list | findstr "Имя задания\|Следующее"
schtasks /query /tn "%TASK_NAME%_15" /fo list | findstr "Имя задания\|Следующее"
schtasks /query /tn "%TASK_NAME%_19" /fo list | findstr "Имя задания\|Следующее"

echo.
echo Готово! Цены ГПН будут обновляться в 07:00, 11:00, 15:00, 19:00
pause

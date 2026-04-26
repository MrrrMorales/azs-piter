# update_gpn_prices.ps1 — Обновление индивидуальных цен ГПН и пуш в репозиторий
# Запускается по расписанию Task Scheduler 4 раза в день

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
$LogFile    = Join-Path $ProjectDir "logs\gpn_update.log"

# Создать папку logs если нет
$logsDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'dd.MM.yyyy HH:mm:ss')  $msg"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

Log "=== Запуск обновления цен ГПН + Татнефть ==="

Set-Location $ProjectDir

# Запуск скрипта
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONUTF8       = '1'
    $output = python fetch_per_station_prices.py 2>&1
    $output | ForEach-Object { Log "  $_" }
} catch {
    Log "ОШИБКА запуска python: $_"
    exit 1
}

# Проверить — обновились ли данные (ищем строку "Готово!")
$success = $output | Where-Object { $_ -match 'Готово!' }
if (-not $success) {
    Log "ПРЕДУПРЕЖДЕНИЕ: скрипт не вернул 'Готово!' — возможна ошибка API"
}

# Проверить количество обновлённых станций
$countLine = $output | Where-Object { $_ -match 'Станций с индивидуальными ценами:' }
if ($countLine) { Log "Результат: $countLine" }

# Git: добавить, закоммитить и запушить если есть изменения
$diff = git -C $ProjectDir diff --name-only station_prices.json
if ($diff) {
    $timestamp = Get-Date -Format 'dd.MM.yyyy HH:mm'
    git -C $ProjectDir add station_prices.json
    git -C $ProjectDir commit -m "Автообновление цен $timestamp (локально)"
    git -C $ProjectDir pull --rebase -X ours
    git -C $ProjectDir push
    Log "Запушено: station_prices.json обновлён"
} else {
    Log "Изменений нет — пуш не нужен"
}

# Ротация лога: оставить последние 1000 строк
$lines = Get-Content $LogFile -Encoding UTF8
if ($lines.Count -gt 1000) {
    $lines[-1000..-1] | Set-Content $LogFile -Encoding UTF8
}

Log "=== Готово ==="

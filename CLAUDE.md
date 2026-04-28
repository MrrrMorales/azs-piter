# АЗС Питер — CLAUDE.md

Карта и агрегатор цен на топливо для АЗС Санкт-Петербурга и Ленинградской области.
Статический сайт (Netlify) + Python-скрипты для сбора данных.

## Структура проекта

```
index.html                — фронтенд: карта Leaflet + sidebar + popup-панель
admin.html                — ручное редактирование цен через JSONBin (с паролем)
parser.py                 — парсер средних цен по брендам (4 источника)
save_stations.py          — скачивает все АЗС из OSM через Overpass API
fetch_per_station_prices.py — индивидуальные цены ГПН через gpnbonus.ru API
enrich_brands.py          — обогащение brand/address через 2GIS API
fix_brands.py             — ручная нормализация брендов в stations.json
prices.json               — кэш средних цен по брендам (результат parser.py)
stations.json             — кэш всех АЗС из OSM (результат save_stations.py)
station_prices.json       — индивидуальные цены АЗС (результат fetch_per_station_prices.py)
config.js                 — API-ключи (не в git, есть config.example.js)
netlify.toml              — no-cache заголовки для JSON-файлов
```

## Команды

```bash
# Обновить список АЗС из OSM (раз в месяц)
python save_stations.py

# Обновить средние цены по брендам
python parser.py

# Обновить индивидуальные цены ГПН
python fetch_per_station_prices.py

# Обогатить бренды через 2GIS (нужен API-ключ)
python enrich_brands.py --key YOUR_2GIS_KEY
python enrich_brands.py --key YOUR_2GIS_KEY --dry-run

# Нормализовать бренды вручную
python fix_brands.py --dry-run
python fix_brands.py

# Локальный сервер (нужен для fetch() — file:// блокируется CORS)
python -m http.server 8080
# или: start-server.bat

# Установка зависимостей
pip install requests beautifulsoup4 lxml
```

## Архитектура

**Поток данных:**
```
OSM (Overpass) → save_stations.py → stations.json
                                         ↓
gsm.ru / benzoportal / fuelprice / benzin-price → parser.py → prices.json → JSONBin
                                         ↓
gpnbonus.ru API → fetch_per_station_prices.py → station_prices.json
                                         ↓
                               index.html (fetch всех трёх)
```

**Приоритет цен в UI (от высшего к низшему):**
1. `station_prices.json` — per-station цены от API бренда (бейдж LIVE)
2. OSM-теги станции
3. `prices.json` — средние по сети (пометка «⚠ по сети»)

## Конфигурация

`config.js` (создать из `config.example.js`):
```js
window.CONFIG = {
  JSONBIN_BIN_ID:  '...',   // ID корзины JSONBin
  JSONBIN_API_KEY: '...',   // мастер-ключ JSONBin
  ADMIN_PASSWORD:  '...',   // пароль для admin.html
}
```

Для `parser.py` те же значения можно задать через env:
```bash
set JSONBIN_BIN_ID=...
set JSONBIN_API_KEY=...
```

## Ключевые решения

- **Нет сервера** — всё статика + локальные скрипты. JSONBin хранит цены в облаке.
- **Бренды нормализуются substring-match** — словари алиасов в `parser.py` и `index.html` должны быть синхронизированы.
- **Газовые станции (АГЗС/LPG) исключены** в `save_stations.py`.
- **Netlify no-cache** на все JSON-файлы — обязательно, иначе пользователи не видят свежие цены.
- **gpnbonus.ru** — неофициальный API мобильного приложения ГПН Бонус. Даёт ~133 станции в регионе.

## Известные ограничения

- Роснефть, ПТК — per-station цены не реализованы (заглушки в `fetch_per_station_prices.py`)
- Лукойл — цены через Яндекс Карты (Playwright): единые по СПб, применяются ко всем Лукойл-станциям OSM.
  Источник: `fetch_lukoil_yandex()` в `fetch_per_station_prices.py`.
  Требует: `pip install playwright && python -m playwright install chromium`.
  Режим headless=False (Яндекс детектирует headless).
- Словари брендов дублируются в 4 файлах — надо держать синхронизированными
- Парсер запускается вручную, нет автоматического расписания

## Knowledge Base

Подробная документация: `D:\AZS.vault` (Obsidian vault)

## Obsidian Knowledge Vault
Хранилище знаний: D:/AZS.vault
### При старте сессии
Прочитай 00-home/index.md и текущие приоритеты.md.
Если задача касается модуля — прочитай заметку из knowledge/.
### При завершении (пользователь: "сохрани сессию")
1. Создай заметку в sessions/ с датой
2. Обнови текущие приоритеты.md
3. Если решение — создай в knowledge/decisions/
4. Если баг — создай в knowledge/debugging/
5. Обнови index.md если новые заметки

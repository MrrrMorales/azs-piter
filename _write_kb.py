import pathlib

TEXT = r"""# АЗС Питер — Knowledge Base

> Карта заправок Санкт-Петербурга и Ленинградской области с актуальными ценами на топливо.
> Проект: `d:\PiterAZS\`

---

## Содержание

1. [Главная и приоритеты](#главная-и-приоритеты)
2. [Архитектура системы](#архитектура-системы)
3. [Технический стек](#технический-стек)
4. [Хранилище данных](#хранилище-данных)
5. [Деплой и инфраструктура](#деплой-и-инфраструктура)
6. [Интеграции](#интеграции)
7. [Решения](#решения)
8. [Отладка](#отладка)
9. [Паттерны кода](#паттерны-кода)
10. [Бизнес и продукт](#бизнес-и-продукт)
11. [Лог сессий](#лог-сессий)
12. [Inbox — необработанные идеи](#inbox--необработанные-идеи)

---

## Главная и приоритеты

### Структура репозитория

```
d:\PiterAZS\
├── index.html        — фронтенд (карта + список)
├── admin.html        — панель управления ценами
├── parser.py         — парсер цен с сайтов сетей
├── save_stations.py  — скачать все АЗС из OSM
├── prices.json       — локальный кэш цен
├── config.js         — ключи JSONBin
└── api.txt           — API-ключ JSONBin (дублирует config.js)
```

### Быстрый старт

1. `py save_stations.py` — обновить список заправок (раз в месяц)
2. `python parser.py` — обновить цены из сайтов сетей
3. Открыть `admin.html` → ввести пароль → сохранить цены в JSONBin
4. `index.html` читает данные автоматически при открытии

### Текущие приоритеты

#### Критично — сделать сейчас

- [ ] **Убрать секреты из кода** — API-ключ JSONBin и пароль админки захардкожены в HTML/JS. Вынести пароль на серверную проверку или сменить на более сложный
- [ ] **Починить парсер** — `prices.json` пустой (`"prices": {}`). Запустить `python parser.py` и проверить что мешает

#### Важно — ближайшие задачи

- [ ] Настроить автозапуск `parser.py` по расписанию (Task Scheduler Windows или cron)
- [ ] Убедиться что `stations.json` залит на GitHub и доступен из `index.html`
- [ ] Проверить работу fallback на Overpass API когда `stations.json` недоступен

#### Идеи

- [ ] Добавить исторический график цен (JSONBin хранит версии)
- [ ] Мобильная адаптация — sidebar перекрывает карту на телефоне
- [ ] Уведомления когда цена упала ниже порога
- [ ] Добавить Татнефть, Shell, Авро в парсер (сейчас только в admin)

---

## Архитектура системы

### Общая схема потоков данных

```
OpenStreetMap (Overpass API)
        │
        ▼
  save_stations.py
        │  (раз в месяц)
        ▼
  stations.json ──────────────────────────────────────┐
                                                       │
  Сайты сетей АЗС                                     │
  (Лукойл, Газпром, Роснефть, ПТК, Neste, Фаэтон)   │
        │                                              │
        ▼                                              │
   parser.py                                          │
        │  (вручную или по расписанию)                 │
        ▼                                              ▼
  prices.json ──────► admin.html ──────► JSONBin API
                       (PUT)
                                              │
                                              │ (GET при загрузке страницы)
                                              ▼
                                         index.html
                                              │
                                              └── + stations.json / Overpass fallback
```

### Компоненты

| Файл | Роль | Когда запускается |
|---|---|---|
| `save_stations.py` | Скачивает все АЗС из OSM, сохраняет в `stations.json` | Вручную, раз в месяц |
| `parser.py` | Парсит цены с сайтов 6 сетей | Вручную или по Task Scheduler |
| `prices.json` | Локальный кэш цен | Результат parser.py |
| `admin.html` | UI для ручного ввода и публикации цен в JSONBin | Вручную |
| `config.js` | Ключи для JSONBin | При открытии страницы |
| `index.html` | Основной фронтенд: карта + список + фильтры | Браузер пользователя |

### Два источника цен (приоритет)

1. **OSM-теги** — если в OpenStreetMap для заправки проставлены теги `fuel:octane_*`, они используются первыми
2. **JSONBin (парсер/admin)** — если OSM-цен нет, ищем по бренду через алиасы

### Два источника станций (fallback)

1. **stations.json** — локальный кэш, быстро (основной путь)
2. **Overpass API** — прямой запрос к OSM, медленно (~30-60 сек), если нет stations.json

---

## Технический стек

### Фронтенд

| Технология | Версия | Назначение |
|---|---|---|
| Leaflet.js | 1.9.4 | Интерактивная карта |
| CartoDB Dark tiles | — | Тёмная тема карты (`dark_all`) |
| Google Fonts | — | Oswald (заголовки), Inter (текст) |
| Vanilla JS | ES2020+ | Вся логика UI без фреймворка |

CDN зависимости (нет package.json, всё через `unpkg.com`):

```html
https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
```

### Бэкенд / скрипты

| Технология | Назначение |
|---|---|
| Python 3 | Парсер цен и загрузчик станций |
| requests | HTTP-запросы к сайтам АЗС |
| BeautifulSoup4 + lxml | Парсинг HTML страниц с ценами |
| urllib (stdlib) | Запросы к Overpass API в `save_stations.py` |

Установка зависимостей:

```bash
pip install requests beautifulsoup4 lxml
```

### Внешние API

| Сервис | Использование |
|---|---|
| JSONBin.io | Хранение и синхронизация цен между admin и фронтом |
| OpenStreetMap Overpass API | Получение координат и тегов всех АЗС |

### Дизайн-система (CSS переменные)

```css
--bg: #0d0f14        /* фон страницы */
--surface: #161921   /* карточки, сайдбар */
--surface2: #1e2330  /* инпуты, внутренние блоки */
--border: #2a2f3e    /* границы */
--accent: #f5a623    /* акцент (оранжевый) */
--text: #eef0f6      /* основной текст */
--muted: #7a8099     /* второстепенный текст */

/* Цвета топлива */
--fuel-92: #3b82f6   /* синий */
--fuel-95: #10b981   /* зелёный */
--fuel-100: #f59e0b  /* жёлтый */
--fuel-dt: #8b5cf6   /* фиолетовый */
```

> Нет сборщика (webpack/vite) — всё работает как статика. Можно хостить на GitHub Pages, Netlify, любом статик-хостинге.

---

## Хранилище данных

### prices.json

Локальный кэш цен, генерируется `parser.py`.

```json
{
  "updated": "21.04.2026 15:29",
  "prices": {
    "лукойл":       { "92": 54.5, "95": 57.8, "100": null, "dt": 62.1 },
    "газпромнефть": { "92": 54.1, "95": 57.5, "100": 67.0, "dt": 61.8 }
  },
  "aliases": {
    "lukoil": "лукойл",
    "газпром": "газпромнефть"
  }
}
```

> Сейчас `"prices": {}` — парсер не смог получить данные.

### stations.json

Список всех АЗС из OpenStreetMap. Генерируется `save_stations.py`, должен быть загружен на GitHub.

```json
[
  {
    "id": 123456789,
    "type": "node",
    "lat": 59.939,
    "lon": 30.316,
    "name": "Лукойл",
    "brand": "Лукойл",
    "address": "Невский проспект 1",
    "opening_hours": "24/7",
    "phone": ""
  }
]
```

> Файл не в репозитории — нужно сгенерировать и залить вручную.

### JSONBin (облачное хранилище)

| Параметр | Значение |
|---|---|
| Bin ID | `69e79cb4856a68218959b94f` |
| API Key | в `config.js` и `api.txt` |
| Чтение | `GET https://api.jsonbin.io/v3/b/{BIN_ID}/latest` |
| Запись | `PUT https://api.jsonbin.io/v3/b/{BIN_ID}` |

JSONBin хранит историю версий — можно восстановить предыдущие цены.

> API-ключ открыт в клиентском JS — любой может прочитать и перезаписать данные.

---

## Деплой и инфраструктура

### Хостинг

Проект — статический сайт без серверной части. Рекомендуется **GitHub Pages**:

1. Создать репозиторий `azs-piter` на GitHub
2. Залить все файлы включая `stations.json`
3. Включить GitHub Pages из ветки `main`
4. Сайт: `https://username.github.io/azs-piter/`

### Обновление данных

**Список станций (раз в месяц):**

```bash
py save_stations.py
git add stations.json && git commit -m "update stations" && git push
```

**Цены — вариант A через парсер:**

```bash
python parser.py
# Открыть admin.html → Сохранить все цены
```

**Цены — вариант B вручную:**

1. Открыть `admin.html`
2. Ввести пароль
3. Ввести актуальные цены → «Сохранить все цены» → уходит в JSONBin

**Автоматизация (Windows Task Scheduler):**

```
Действие: python d:\PiterAZS\parser.py
Расписание: ежедневно в 10:00
```

### Секреты в коде

> Следующие данные открыты в клиентском коде:
> - JSONBin API Key в `config.js`, `index.html`, `admin.html`
> - Пароль админки в `admin.html`

---

## Интеграции

### JSONBin — база данных цен

**Чтение:**

```javascript
const r = await fetch(`https://api.jsonbin.io/v3/b/${BIN_ID}/latest`, {
  headers: { 'X-Master-Key': API_KEY }
});
const data = await r.json();
// data.record → { updated, prices, aliases }
```

**Запись:**

```javascript
const r = await fetch(`https://api.jsonbin.io/v3/b/${BIN_ID}`, {
  method: 'PUT',
  headers: {
    'Content-Type': 'application/json',
    'X-Master-Key': API_KEY
  },
  body: JSON.stringify({ updated, prices, aliases })
});
```

- Бесплатный план: до 10 000 запросов/месяц
- История версий включена

---

### OpenStreetMap / Overpass API

**Запрос (save_stations.py):**

```python
query = """
[out:json][timeout:90];
(
  node["amenity"="fuel"](58.5,27.5,61.5,33.5);
  way["amenity"="fuel"](58.5,27.5,61.5,33.5);
);
out center tags;
"""
url = "https://overpass-api.de/api/interpreter"
```

**Bounding box:** `(58.5, 27.5, 61.5, 33.5)` — СПб и Ленобласть.

**Поля из OSM:**

| Тег | Содержимое |
|---|---|
| `brand` | Бренд (Лукойл, Газпром...) |
| `name` | Название |
| `addr:street`, `addr:housenumber` | Адрес |
| `opening_hours` | Режим работы |
| `phone` / `contact:phone` | Телефон |

**Fallback в index.html** — если `stations.json` не найден, фронт делает прямой запрос к Overpass:

```javascript
async function loadStations() {
  try {
    const r = await fetch('stations.json');
    if (!r.ok) throw new Error('not found');
  } catch (e) {
    return await loadStationsOverpass(); // fallback ~30-60 сек
  }
}
```

---

### Парсер сайтов АЗС

**Поддерживаемые сети:**

| Бренд | URL | Статус |
|---|---|---|
| Лукойл | `https://spb.lukoil.ru/main/fuel/prices` | Реализован |
| Газпром нефть | `https://www.gpnbonus.ru/ceny/` | Реализован |
| Роснефть | `https://www.rosneft.ru/retail/prices/` | Реализован |
| ПТК | `https://ptk.ru/prices/` | Реализован |
| Neste | `https://neste.ru/ceny-na-toplivo/` | Реализован |
| Фаэтон | `https://faeton.ru/prices/` | Реализован |
| Татнефть, Shell, Авро, Трасса, Кинеф, Esso | — | Только ручной ввод |

**Как работает:**

1. GET-запрос с User-Agent Chrome, Accept-Language ru-RU
2. Парсинг HTML через BeautifulSoup + lxml
3. Поиск строк `<tr>` — название топлива и цена в ячейках
4. Пауза 1.5 сек между запросами
5. Сохранение в `prices.json`

**Нормализация цены:**

```python
def parse_price(text):
    text = str(text).replace('\xa0', '').replace(' ', '').replace(',', '.')
    m = re.search(r'\d+\.\d+|\d+', text)
    return float(m.group()) if m else None
```

---

## Решения

### Почему цены в JSONBin, а не на сервере

**Контекст:** проект — статический сайт без бэкенда.

**Альтернативы:**
- Firebase — избыточно, требует Google-проекта
- GitHub Gist API — менее удобный интерфейс
- Локальный `prices.json` — нельзя обновить без `git push`
- JSONBin — минимально, работает из браузера, бесплатно

**Компромиссы:**

| Плюс | Минус |
|---|---|
| Нет сервера — нет расходов | API-ключ открыт в клиентском коде |
| Обновление без деплоя | Любой может перезаписать |
| История версий бесплатно | Зависимость от стороннего сервиса |

При росте проекта → Cloudflare Workers + KV (бесплатно, но с авторизацией).

---

### Почему станции загружаются из кэша stations.json

**Проблема прямого Overpass:** 30-60 сек, может упасть по таймауту, плохой UX.

**Решение:** `stations.json` грузится < 1 сек с CDN. Overpass нужен только раз в месяц. Fallback автоматический — если файл не найден, фронт переключается на Overpass.

---

### Почему парсер запускается вручную

- Проект на ранней стадии, парсеры ломаются при изменении сайтов
- Нужен контроль качества данных перед публикацией

**Автоматизация через GitHub Actions:**

```yaml
name: Update prices
on:
  schedule:
    - cron: '0 7 * * *'  # ежедневно 10:00 МСК
jobs:
  parse:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install requests beautifulsoup4 lxml
      - run: python parser.py
      - env:
          JSONBIN_API_KEY: ${{ secrets.JSONBIN_API_KEY }}
```

---

## Отладка

### Парсер возвращает пустые цены

**Симптом:** `prices.json` содержит `"prices": {}` или парсер выводит `→ Лукойл: {}`.

**Причины:**

1. **Сайт изменил структуру HTML** — самая частая. Перешёл на JS-рендеринг или изменил классы.
2. **Сайт заблокировал User-Agent** — проверить актуальность HEADERS.
3. **Сайт недоступен / timeout** — `safe_get()` молча возвращает `None`.

**Диагностика:**

```python
import requests
from bs4 import BeautifulSoup

r = requests.get('https://spb.lukoil.ru/main/fuel/prices',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
    timeout=15)
print('Status:', r.status_code)
soup = BeautifulSoup(r.text, 'lxml')
rows = soup.select('table tr')
print('Строк в таблицах:', len(rows))
for row in rows[:5]:
    print([c.get_text(strip=True) for c in row.find_all(['td', 'th'])])
```

**Как починить:** открыть сайт → DevTools → найти элемент с ценой → обновить CSS-селектор в `parse_*()`.

---

### stations.json не найден и карта грузит медленно

**Симптом:** карта загружается 30-60 сек, в консоли `stations.json not found`.

**Решение:**

```bash
py save_stations.py
git add stations.json && git commit -m "add stations cache" && git push
```

**При локальной разработке** браузер блокирует `fetch()` по CORS при открытии `file://`. Нужен локальный сервер:

```bash
python -m http.server 8080
# Открыть http://localhost:8080
```

---

## Паттерны кода

### Нормализация бренда через алиасы

**Проблема:** OSM пишет бренд непредсказуемо — `"Лукойл"`, `"LUKOIL"`, `"Lukoil АЗС №42"`.

**Решение — словарь алиасов с проверкой подстроки:**

```python
BRAND_ALIASES = {
    "лукойл": "лукойл", "lukoil": "лукойл",
    "газпром": "газпромнефть", "газпромнефть": "газпромнефть",
    "роснефть": "роснефть", "rosneft": "роснефть",
    "птк": "птк",
    "neste": "neste", "несте": "neste",
    "фаэтон": "фаэтон", "faeton": "фаэтон",
}

def normalize_brand(name: str) -> str | None:
    name = (name or "").lower().strip()
    for key, canonical in BRAND_ALIASES.items():
        if key in name:  # подстрочное вхождение!
            return canonical
    return None
```

**Та же логика на JS:**

```javascript
for (const [alias, canonical] of Object.entries(brandAliases)) {
  if (raw.includes(alias) && brandPrices[canonical])
    return brandPrices[canonical];
}
```

> Словарь хранится в 4 местах: `parser.py`, `prices.json`, `index.html`, `admin.html` — нужно держать синхронизированными.

---

### Приоритет OSM-цен над парсерными

**Иерархия:**

```
1. OSM-теги конкретной заправки (fuel:octane_92 ...)
         ↓ если нет ни одного тега
2. Цены из JSONBin/parser по бренду (усреднённые по сети)
         ↓ если бренд не найден
3. { '92': null, '95': null, '100': null, 'dt': null }
```

**Реализация:**

```javascript
function getPricesForStation(station) {
  const osmPrices = station.prices;
  const hasAny = Object.values(osmPrices).some(v => v !== null && v !== undefined);
  if (hasAny) return osmPrices;  // OSM в приоритете

  const raw = (station.brand || station.name || '').toLowerCase().trim();
  if (brandPrices[raw]) return brandPrices[raw];
  for (const [alias, canonical] of Object.entries(brandAliases)) {
    if (raw.includes(alias) && brandPrices[canonical]) return brandPrices[canonical];
  }
  return { '92': null, '95': null, '100': null, 'dt': null };
}
```

**Почему OSM в приоритете:** OSM-цены специфичны для конкретной точки; парсерные — усреднённые по сети. На практике OSM-цены почти никогда не проставлены.

---

## Бизнес и продукт

### Продукт и аудитория

Веб-карта всех заправок СПб и Ленобласти с ценами. Позволяет найти ближайшую дешёвую заправку.

**Аудитория:** водители в СПб и Ленобласти, особенно мобильные пользователи.

**Ключевые сценарии:**

1. "Где дешевле заправиться?" → сортировка по цене, фильтр по топливу
2. "Где ближайшая заправка?" → карта с маркерами
3. "Сколько стоит ДТ у Лукойла?" → поиск по бренду

**Уникальность:**

- Охватывает всю Ленобласть, не только город
- Тёмный дизайн — удобно ночью в машине
- Бейдж "ДЕШЕВЛЕ ВСЕХ" для самой дешёвой заправки

**Ограничения сейчас:**

- Нет мобильной адаптации (sidebar перекрывает карту)
- Нет геолокации ("рядом со мной")
- Нет истории цен

---

### Поддерживаемые бренды

**С автопарсингом:**

| Бренд | Ключ | Цвет маркера |
|---|---|---|
| Лукойл | `лукойл` | `#e8421a` |
| Газпром нефть | `газпромнефть` | `#0070c0` |
| Роснефть | `роснефть` | `#f5a623` |
| ПТК | `птк` | `#d22` |
| Neste | `neste` | `#006ca0` |
| Фаэтон | `фаэтон` | `#333` |

**Только ручной ввод в admin:** Татнефть, Shell, Авро, Трасса, Кинеф, Esso.

**Виды топлива:**

| Ключ | Отображение | Цвет |
|---|---|---|
| `92` | АИ-92 | `#3b82f6` синий |
| `95` | АИ-95 | `#10b981` зелёный |
| `100` | АИ-100 | `#f59e0b` жёлтый |
| `dt` | ДТ | `#8b5cf6` фиолетовый |

**Фильтрация мусора из OSM:**

```javascript
list = list.filter(s => {
  const hasAddress = s.address && s.address.trim() !== '';
  const hasPrices = Object.values(getPricesForStation(s)).some(v => v !== null);
  return hasAddress || hasPrices;
});
```

---

## Лог сессий

### 2026-04-22 — Первичная документация

**Что обнаружено при анализе проекта:**

- `prices.json` пуст — парсер не работает или не запускался
- `stations.json` отсутствует — нужно запустить `save_stations.py`
- Проект не задеплоен (только локальные файлы в `d:\PiterAZS\`)
- API-ключ JSONBin захардкожен в 4 местах: `config.js`, `api.txt`, `index.html`, `admin.html`
- Пароль администратора открыт в клиентском JS в `admin.html`

**Архитектурные наблюдения:**

- Чистая serverless-архитектура: статика + JSONBin + OSM — хороший выбор для MVP
- Хорошая fallback-логика для загрузки станций (кэш → Overpass)
- Двухуровневый источник цен (OSM → JSONBin) логичен

---

## Inbox — необработанные идеи

### Функционал

- Геолокация — сортировка по расстоянию от пользователя
- График истории цен (JSONBin хранит версии — данные уже есть)
- Мобильная версия — sidebar как bottom sheet на телефоне
- Push-уведомления при падении цены ниже порога
- Сравнение стоимости полного бака (объём × цена)
- Фильтр по брендам в дополнение к фильтру по топливу
- Иконка "24/7" на основе `opening_hours`

### Парсер

- Добавить парсеры для Татнефть, Shell, Авро, Трасса, Кинеф, Esso
- Автоматический push в JSONBin прямо из `parser.py` (без открытия admin.html)
- Не затирать данные если парсер вернул пустой результат
- GitHub Actions для ежедневного обновления

### Технический долг

- Добавить `.gitignore` чтобы `api.txt` не попал в репо
- Сменить или убрать пароль администратора из клиентского JS
- Локальный сервер для разработки (CORS блокирует `file://`)

### Бизнес

- SEO: мета-теги, structured data для поисковиков
- Мониторинг: алерт если данные не обновлялись больше N дней
"""

pathlib.Path('d:/AZSPiter.md').write_text(TEXT, encoding='utf-8')
print(f"OK — {len(TEXT)} chars, {TEXT.count(chr(10))} lines")

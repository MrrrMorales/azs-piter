"""
parser.py — Парсер цен на топливо для АЗС Санкт-Петербурга и Ленобласти
Запуск: python parser.py
Результат загружается в JSONBin (JSONBIN_BIN_ID + JSONBIN_API_KEY из env).

Установка зависимостей:
    pip install requests beautifulsoup4 lxml
"""

import json
import os
import re
import sys
import time
import datetime
import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

JSONBIN_BIN_ID  = os.environ.get('JSONBIN_BIN_ID',  '')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY', '')

PRICE_MIN = 50.0
PRICE_MAX = 160.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def safe_get(url, retries=2, **kwargs):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, timeout=20, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                print(f"  [!] GET {url} -> {e}")
    return None


def parse_price(text):
    """Вытащить число из строки, вернуть None если вне допустимого диапазона."""
    if not text:
        return None
    text = str(text).replace('\xa0', '').replace(' ', '').replace(' ', '').replace(',', '.')
    m = re.search(r'\d{2,3}\.\d{1,2}|\d{2,3}', text)
    if not m:
        return None
    val = float(m.group())
    if PRICE_MIN <= val <= PRICE_MAX:
        return val
    return None


def best_price(cells):
    """Берём максимальную валидную цену из строки таблицы (розница > скидка)."""
    candidates = [parse_price(c) for c in cells[1:]]
    candidates = [v for v in candidates if v is not None]
    return max(candidates) if candidates else None


def classify_fuel(name):
    """Определяем тип топлива по названию строки."""
    n = name.lower().strip()
    if re.search(r'\b100\b', n):
        return '100'
    if re.search(r'\b95\b', n):
        return '95'
    if re.search(r'\b92\b', n) and '95' not in n:
        return '92'
    if re.search(r'дт|дизел|diesel|евродизель', n):
        return 'dt'
    return None


def parse_from_tables(soup, label=''):
    """Универсальный парсер: ищет все таблицы, возвращает {92, 95, 100, dt}."""
    prices = {}
    for row in soup.select('tr'):
        cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
        if len(cells) < 2:
            continue
        fuel = classify_fuel(cells[0])
        if not fuel:
            continue
        val = best_price(cells)
        if val and fuel not in prices:
            prices[fuel] = val
    if prices:
        print(f"  -> {label}: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# ЛУКОЙЛ  https://spb.lukoil.ru/main/fuel/prices
# ─────────────────────────────────────────────────────────────────
def parse_lukoil():
    print("[Лукойл] Запрос...")
    r = safe_get("https://spb.lukoil.ru/main/fuel/prices")
    if not r:
        return None
    return parse_from_tables(BeautifulSoup(r.text, 'lxml'), 'Лукойл')


# ─────────────────────────────────────────────────────────────────
# ГАЗПРОМ НЕФТЬ  https://www.gpnbonus.ru/ceny/
# ─────────────────────────────────────────────────────────────────
def parse_gazprom():
    print("[Газпром] Запрос...")
    r = safe_get("https://www.gpnbonus.ru/ceny/")
    if not r:
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    # Ищем секцию Санкт-Петербург
    spb = None
    for el in soup.find_all(string=re.compile(r'Санкт-Петербург|Петербург', re.I)):
        parent = el.find_parent(['div', 'section', 'tr'])
        if parent:
            spb = parent.find_parent('table') or parent
            break
    return parse_from_tables(spb or soup, 'Газпром')


# ─────────────────────────────────────────────────────────────────
# РОСНЕФТЬ  https://www.rosneft.ru/retail/prices/
# ─────────────────────────────────────────────────────────────────
def parse_rosneft():
    print("[Роснефть] Запрос...")
    r = safe_get("https://www.rosneft.ru/retail/prices/")
    if not r:
        return None
    soup = BeautifulSoup(r.text, 'lxml')
    spb = None
    for el in soup.find_all(string=re.compile(r'Санкт-Петербург|Петербург', re.I)):
        parent = el.find_parent(['tr', 'div', 'li'])
        if parent:
            spb = parent.find_parent('table') or parent
            break
    return parse_from_tables(spb or soup, 'Роснефть')


# ─────────────────────────────────────────────────────────────────
# ПТК  https://ptk.ru/prices/
# ─────────────────────────────────────────────────────────────────
def parse_ptk():
    print("[ПТК] Запрос...")
    r = safe_get("https://ptk.ru/prices/")
    if not r:
        return None
    return parse_from_tables(BeautifulSoup(r.text, 'lxml'), 'ПТК')


# ─────────────────────────────────────────────────────────────────
# NESTE  https://neste.ru/ceny-na-toplivo/
# ─────────────────────────────────────────────────────────────────
def parse_neste():
    print("[Neste] Запрос...")
    r = safe_get("https://neste.ru/ceny-na-toplivo/")
    if not r:
        return None
    return parse_from_tables(BeautifulSoup(r.text, 'lxml'), 'Neste')


# ─────────────────────────────────────────────────────────────────
# ФАЭТОН  https://faeton.ru/prices/
# ─────────────────────────────────────────────────────────────────
def parse_faeton():
    print("[Фаэтон] Запрос...")
    r = safe_get("https://faeton.ru/prices/")
    if not r:
        return None
    return parse_from_tables(BeautifulSoup(r.text, 'lxml'), 'Фаэтон')


# ─────────────────────────────────────────────────────────────────
# СБОРКА
# ─────────────────────────────────────────────────────────────────

PARSERS = {
    'лукойл':       parse_lukoil,
    'газпромнефть': parse_gazprom,
    'роснефть':     parse_rosneft,
    'птк':          parse_ptk,
    'neste':        parse_neste,
    'фаэтон':       parse_faeton,
}

BRAND_ALIASES = {
    'лукойл': 'лукойл', 'lukoil': 'лукойл',
    'газпром': 'газпромнефть', 'gazpromneft': 'газпромнефть', 'газпромнефть': 'газпромнефть',
    'роснефть': 'роснефть', 'rosneft': 'роснефть',
    'птк': 'птк',
    'neste': 'neste', 'несте': 'neste',
    'фаэтон': 'фаэтон', 'faeton': 'фаэтон',
    'татнефть': 'татнефть', 'tatneft': 'татнефть',
    'shell': 'shell',
    'авро': 'авро',
    'трасса': 'трасса',
    'кинеф': 'кинеф',
    'esso': 'esso',
}


def upload_to_jsonbin(output):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        print("[JSONBin] Нет BIN_ID или API_KEY — загрузка пропущена")
        return False
    try:
        r = requests.put(
            f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}",
            json=output,
            headers={
                'Content-Type': 'application/json',
                'X-Master-Key': JSONBIN_API_KEY,
            },
            timeout=15,
        )
        r.raise_for_status()
        print(f"[JSONBin] Загружено успешно -> {r.status_code}")
        return True
    except Exception as e:
        print(f"[JSONBin] Ошибка загрузки: {e}")
        return False


def run():
    print("=" * 50)
    print("Парсер цен на топливо — Питер и Ленобласть")
    print("=" * 50)

    results = {}
    for brand, fn in PARSERS.items():
        prices = fn()
        if prices:
            results[brand] = prices
        time.sleep(1.5)

    output = {
        "updated": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "prices": results,
        "aliases": BRAND_ALIASES,
    }

    # Резервная копия локально
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Загружаем в облако
    upload_to_jsonbin(output)

    print()
    print("=" * 50)
    print("Готово! Сохранено в prices.json")
    print(f"   Брендов с ценами: {len(results)}")
    for b, p in results.items():
        print(f"   {b}: {p}")
    print("=" * 50)


if __name__ == "__main__":
    run()

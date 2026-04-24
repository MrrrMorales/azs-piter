"""
parser.py — Парсер цен на топливо для АЗС Санкт-Петербурга и Ленобласти
Источники (в порядке приоритета):
  0. kirishiavtoservis.ru — официальный сайт (приоритет для сургутнефтегаз)
  1. gsm.ru         — надёжный агрегатор, актуальные данные
  2. benzoportal.ru — резервный агрегатор
  3. fuelprice.ru   — дополнительный источник
  4. benzin-price.ru — последний резерв

Запуск: python parser.py   или   run_parser.bat
Зависимости: pip install requests beautifulsoup4 lxml
"""

import json, os, re, sys, time, datetime
import requests
from bs4 import BeautifulSoup
from brands import ALIASES as BRAND_ALIASES, normalize as _brand_normalize

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

JSONBIN_BIN_ID  = os.environ.get('JSONBIN_BIN_ID',  '')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY', '')

PRICE_MIN = 50.0
PRICE_MAX = 180.0

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

FUEL_MAP = {
    'аи-92': '92', 'аи 92': '92', 'аи92': '92', 'регуляр 92': '92', 'аи92е': '92',
    'аи-95': '95', 'аи 95': '95', 'аи95': '95', 'премиум 95': '95', 'аи95е': '95',
    'аи-98': '100', 'аи 98': '100', 'аи98': '100',
    'аи-100': '100', 'аи 100': '100', 'аи100': '100', 'экто 100': '100', 'pulsar 100': '100',
    'дт': 'dt', 'дизель': 'dt', 'diesel': 'dt', 'евродизель': 'dt', 'дт евро': 'dt',
}


def safe_get(url, retries=2, timeout=25):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries:
                time.sleep(3)
            else:
                print(f'  [!] GET {url} -> {e}')
    return None


def parse_price(text):
    if not text:
        return None
    text = str(text).replace('\xa0', '').replace(' ', '').replace(' ', '').replace(',', '.')
    m = re.search(r'\d{2,3}\.\d{1,2}|\d{2,3}', text)
    if not m:
        return None
    val = float(m.group())
    return val if PRICE_MIN <= val <= PRICE_MAX else None


def classify_fuel(raw):
    n = raw.lower().strip()
    for key, fuel in FUEL_MAP.items():
        if key in n:
            return fuel
    return None


def classify_brand(raw):
    return _brand_normalize(raw)


def merge_results(base, extra):
    """Дополняет base данными из extra, не перезаписывая существующие."""
    for brand, prices in extra.items():
        if brand not in base:
            base[brand] = {}
        for fuel, val in prices.items():
            if fuel not in base[brand] and val:
                base[brand][fuel] = val
    return base


def _parse_tables(soup):
    """Общий парсер HTML-таблиц с ценами топлива. Возвращает {brand: {fuel: price}}."""
    results = {}
    for table in soup.select('table'):
        headers = [th.get_text(strip=True).lower() for th in table.select('th')]
        if not headers:
            continue
        fuel_cols = {i: classify_fuel(h) for i, h in enumerate(headers) if classify_fuel(h)}
        if not fuel_cols:
            continue
        for row in table.select('tr'):
            cells = [td.get_text(strip=True) for td in row.select('td')]
            if not cells:
                continue
            brand = classify_brand(cells[0])
            if not brand:
                continue
            row_prices = results.setdefault(brand, {})
            for col_i, fuel in fuel_cols.items():
                if col_i < len(cells) and fuel not in row_prices:
                    val = parse_price(cells[col_i])
                    if val:
                        row_prices[fuel] = val
    return results


# ─────────────────────────────────────────────────────────────────
# ПАРСЕР 1 — gsm.ru (агрегатор, актуальные данные по регионам)
# ─────────────────────────────────────────────────────────────────
def parse_gsm():
    print('[gsm.ru] Запрос...')
    r = safe_get('https://www.gsm.ru/sankt-peterburg/')
    if not r:
        return {}
    results = _parse_tables(BeautifulSoup(r.text, 'lxml'))
    for b, p in results.items():
        print(f'  -> {b}: {p}')
    return results


# ─────────────────────────────────────────────────────────────────
# ПАРСЕР 2 — benzoportal.ru
# ─────────────────────────────────────────────────────────────────
def parse_benzoportal():
    print('[benzoportal.ru] Запрос...')
    r = safe_get('https://benzoportal.ru/price/?city=2')  # Регион 2 = Санкт-Петербург
    if not r:
        return {}
    results = _parse_tables(BeautifulSoup(r.text, 'lxml'))
    for b, p in results.items():
        print(f'  -> {b}: {p}')
    return results


# ─────────────────────────────────────────────────────────────────
# ПАРСЕР 3 — fuelprice.ru
# ─────────────────────────────────────────────────────────────────
def parse_fuelprice():
    print('[fuelprice.ru] Запрос...')
    r = safe_get('https://fuelprice.ru/t-sankt-peterburg')
    if not r:
        return {}

    soup = BeautifulSoup(r.text, 'lxml')
    results = _parse_tables(soup)

    # Запасной путь — ищем цены в заголовках/тексте если таблиц нет
    if not results:
        for el in soup.find_all(['h2', 'h3', 'strong', 'b']):
            brand = classify_brand(el.get_text(strip=True))
            if not brand:
                continue
            container = el.find_parent(['div', 'section', 'li']) or el
            prices = {}
            for item in container.find_all(string=True):
                fuel = classify_fuel(item)
                val = parse_price(item)
                if fuel and val:
                    prices[fuel] = val
            if prices:
                results[brand] = prices

    for b, p in results.items():
        print(f'  -> {b}: {p}')
    return results


# ─────────────────────────────────────────────────────────────────
# ПАРСЕР 0 — kirishiavtoservis.ru (официальный сайт, приоритет для сургутнефтегаз)
# ─────────────────────────────────────────────────────────────────
def parse_kirishiavtoservis():
    print('[kirishiavtoservis.ru] Запрос...')
    r = safe_get('https://kirishiavtoservis.ru/stations/')
    if not r:
        return {}

    soup = BeautifulSoup(r.text, 'lxml')
    for tag in soup(['script', 'style', 'svg']):
        tag.decompose()

    lines = [l.strip() for l in soup.get_text(separator='\n').split('\n') if l.strip()]

    FUEL_NAMES = {'аи-92': '92', 'аи-95': '95', 'аи-98': '100', 'дт': 'dt'}
    prices = {}
    for i, line in enumerate(lines):
        key = line.lower()
        if key in FUEL_NAMES and FUEL_NAMES[key] not in prices:
            if i + 1 < len(lines):
                val = parse_price(lines[i + 1])
                if val:
                    prices[FUEL_NAMES[key]] = val

    if prices:
        print(f'  -> сургутнефтегаз: {prices}')
        return {'сургутнефтегаз': prices}
    return {}


# ПАРСЕР 4 — benzin-price.ru (резерв)
# ─────────────────────────────────────────────────────────────────
def parse_benzinprice():
    print('[benzin-price.ru] Запрос...')
    r = safe_get('https://www.benzin-price.ru/price.php?region_id=78')
    if not r:
        return {}

    soup = BeautifulSoup(r.text, 'lxml')
    results = {}

    for row in soup.select('tr'):
        cells = [td.get_text(strip=True) for td in row.select('td')]
        if len(cells) < 3:
            continue
        brand = classify_brand(cells[0])
        if not brand:
            continue
        fuels = ['92', '95', '100', 'dt']
        prices = {}
        for i, fuel in enumerate(fuels, start=1):
            if i < len(cells):
                val = parse_price(cells[i])
                if val:
                    prices[fuel] = val
        if prices:
            results[brand] = prices

    for b, p in results.items():
        print(f'  -> {b}: {p}')
    return results


def upload_to_jsonbin(output):
    if not JSONBIN_BIN_ID or not JSONBIN_API_KEY:
        print('[JSONBin] Нет BIN_ID или API_KEY — загрузка пропущена')
        return False
    try:
        r = requests.put(
            f'https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}',
            json=output,
            headers={'Content-Type': 'application/json', 'X-Master-Key': JSONBIN_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        print(f'[JSONBin] Загружено -> {r.status_code}')
        return True
    except Exception as e:
        print(f'[JSONBin] Ошибка: {e}')
        return False


def run():
    print('=' * 55)
    print('Парсер цен на топливо — Питер и Ленобласть')
    print('=' * 55)

    results = {}

    # Пробуем все источники последовательно, объединяем результаты
    for parser_fn in [parse_kirishiavtoservis, parse_gsm, parse_benzoportal, parse_fuelprice, parse_benzinprice]:
        try:
            data = parser_fn()
            if data:
                results = merge_results(results, data)
        except Exception as e:
            print(f'  [!] Ошибка парсера: {e}')

    MIN_BRANDS = 5
    if len(results) < MIN_BRANDS:
        print()
        print(f'[prices.json] Слишком мало брендов ({len(results)}) — старые цены НЕ перезаписываются')
        print('=' * 55)
        return

    # Нормализуем — у каждого бренда должны быть все 4 вида топлива (None если нет данных)
    for brand in results:
        for fuel in ('92', '95', '100', 'dt'):
            results[brand].setdefault(fuel, None)

    output = {
        'updated': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        'prices': results,
        'aliases': BRAND_ALIASES,
    }

    with open('prices.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    upload_to_jsonbin(output)

    print()
    print('=' * 55)
    print('Готово!')
    print(f'   Брендов с ценами: {len(results)}')
    for b, p in results.items():
        print(f'   {b}: {p}')
    print('=' * 55)


if __name__ == '__main__':
    run()

"""
parser.py — Парсер цен на топливо для АЗС Санкт-Петербурга и Ленобласти
Источник: fuelprice.ru (агрегатор, доступен везде)
Запуск: python parser.py   или   run_parser.bat

Зависимости: pip install requests beautifulsoup4 lxml
"""

import json, os, re, sys, time, datetime
import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

JSONBIN_BIN_ID  = os.environ.get('JSONBIN_BIN_ID',  '')
JSONBIN_API_KEY = os.environ.get('JSONBIN_API_KEY', '')

PRICE_MIN = 50.0
PRICE_MAX = 180.0

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

BRAND_ALIASES = {
    'лукойл': 'лукойл', 'lukoil': 'лукойл',
    'газпром': 'газпромнефть', 'gazpromneft': 'газпромнефть', 'газпромнефть': 'газпромнефть',
    'роснефть': 'роснефть', 'rosneft': 'роснефть',
    'птк': 'птк', 'ptk': 'птк',
    'neste': 'neste', 'несте': 'neste',
    'татнефть': 'татнефть', 'tatneft': 'татнефть',
    'shell': 'shell',
    'авро': 'авро',
    'трасса': 'трасса',
    'кинеф': 'кинеф',
    'esso': 'esso',
}

# Маппинг названий с fuelprice.ru → ключи в нашем словаре
BRAND_MAP = {
    'лукойл':       'лукойл',
    'газпромнефть': 'газпромнефть',
    'газпром':      'газпромнефть',
    'роснефть':     'роснефть',
    'птк':          'птк',
    'neste':        'neste',
    'несте':        'neste',
    'татнефть':     'татнефть',
    'shell':        'shell',
    'авро':         'авро',
    'трасса':       'трасса',
    'кинеф':        'кинеф',
    'esso':         'esso',
}

FUEL_MAP = {
    'аи-92': '92', 'аи 92': '92', 'аи92': '92', 'регуляр 92': '92',
    'аи-95': '95', 'аи 95': '95', 'аи95': '95', 'премиум 95': '95',
    'аи-98': '100', 'аи 98': '100', 'аи98': '100',
    'аи-100': '100', 'аи 100': '100', 'аи100': '100',
    'дт': 'dt', 'дизель': 'dt', 'diesel': 'dt', 'евродизель': 'dt',
}


def safe_get(url, retries=2):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, timeout=20)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                print(f'  [!] GET {url} -> {e}')
    return None


def parse_price(text):
    if not text:
        return None
    text = str(text).replace('\xa0', '').replace(' ', '').replace(',', '.')
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
    n = raw.lower().strip()
    for key, brand in BRAND_MAP.items():
        if key in n:
            return brand
    return None


# ─────────────────────────────────────────────────────────────────
# ОСНОВНОЙ ПАРСЕР — fuelprice.ru (агрегатор, работает везде)
# ─────────────────────────────────────────────────────────────────
def parse_fuelprice():
    print('[fuelprice.ru] Запрос...')
    r = safe_get('https://fuelprice.ru/t-sankt-peterburg')
    if not r:
        return {}

    soup = BeautifulSoup(r.text, 'lxml')
    results = {}

    # Ищем все таблицы с ценами по брендам
    for table in soup.select('table'):
        headers = [th.get_text(strip=True).lower() for th in table.select('th')]
        if not headers:
            continue

        # Определяем колонки топлива
        fuel_cols = {}
        for i, h in enumerate(headers):
            fuel = classify_fuel(h)
            if fuel:
                fuel_cols[i] = fuel

        if not fuel_cols:
            continue

        for row in table.select('tr'):
            cells = [td.get_text(strip=True) for td in row.select('td')]
            if not cells:
                continue
            brand = classify_brand(cells[0])
            if not brand:
                continue
            if brand not in results:
                results[brand] = {}
            for col_i, fuel in fuel_cols.items():
                if col_i < len(cells):
                    val = parse_price(cells[col_i])
                    if val and fuel not in results[brand]:
                        results[brand][fuel] = val

    # Запасной вариант: ищем блоки с заголовком бренда и ценами рядом
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
# РЕЗЕРВНЫЙ ПАРСЕР — benzin-price.ru
# ─────────────────────────────────────────────────────────────────
def parse_benzinprice():
    print('[benzin-price.ru] Запрос...')
    # Страница с ценами всех брендов по СПб
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
        # Колонки обычно: бренд, АИ-92, АИ-95, АИ-98, ДТ
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
    print('=' * 50)
    print('Парсер цен на топливо — Питер и Ленобласть')
    print('=' * 50)

    results = parse_fuelprice()

    if not results:
        print('fuelprice.ru не дал результатов, пробуем benzin-price.ru...')
        results = parse_benzinprice()

    output = {
        'updated': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        'prices': results,
        'aliases': BRAND_ALIASES,
    }

    with open('prices.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if results:
        upload_to_jsonbin(output)
    else:
        print('[JSONBin] Нет данных — загрузка пропущена, старые цены сохранены')

    print()
    print('=' * 50)
    print('Готово!')
    print(f'   Брендов с ценами: {len(results)}')
    for b, p in results.items():
        print(f'   {b}: {p}')
    print('=' * 50)


if __name__ == '__main__':
    run()

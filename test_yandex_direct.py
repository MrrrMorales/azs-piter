"""
Тест: получить цены Лукойл напрямую без браузера.
Шаг 1: requests загружает страницу Яндекс Карт → берём CSRF + cookies
Шаг 2: делаем API запрос с этими данными
"""
import requests, re, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from urllib.parse import quote

s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  'Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ru-RU,ru;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})

# Шаг 1: загружаем главную Яндекс Карт
print('Загружаем yandex.ru/maps...')
r = s.get('https://yandex.ru/maps/2/saint-petersburg/', timeout=15)
print(f'  Status: {r.status_code}, cookies: {len(s.cookies)}')

# Ищем CSRF токен
csrf = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', r.text)
if not csrf:
    csrf = re.search(r'csrfToken["\s:=]+([a-f0-9%:_-]{30,})', r.text)

if not csrf:
    print('CSRF не найден — Яндекс требует JS. Нужен Playwright.')
    sys.exit(1)

token = csrf.group(1)
print(f'  CSRF: {token[:50]}')

# Шаг 2: поиск Лукойл с fuelInfo snippet
print('\nЗапрашиваем цены Лукойл...')
params = {
    'text': 'ЛУКОЙЛ АЗС Санкт-Петербург',
    'ajax': '1',
    'lang': 'ru_RU',
    'll': '30.3141,59.9386',
    'z': '12',
    'spn': '0.5,0.3',
    'results': '25',
    'snippets': 'fuel/1.x,businessrating/1.x',
    'csrfToken': token,
    'yandex_gid': '2',
}
s.headers.update({
    'Referer': 'https://yandex.ru/maps/2/saint-petersburg/',
    'X-Requested-With': 'XMLHttpRequest',
    'Accept': 'application/json',
})
r2 = s.get('https://yandex.ru/maps/api/search', params=params, timeout=15)
print(f'  Status: {r2.status_code}')

if r2.status_code != 200:
    print(f'  Ошибка: {r2.text[:200]}')
    sys.exit(1)

data = r2.json()
items = data.get('data', {}).get('items', [])
print(f'  Результатов: {len(items)}')

fuel_count = 0
for item in items:
    fi = item.get('fuelInfo')
    if fi and fi.get('items'):
        fuel_count += 1
        coords = item.get('coordinates', [None, None])
        title = item.get('title', '?')
        addr = item.get('address', '?')
        prices = {p['name']: p['price']['value'] for p in fi['items'] if 'price' in p}
        print(f'\n  {title} | {addr}')
        print(f'  coords: {coords}')
        print(f'  prices: {prices}')

print(f'\nИтого станций с ценами: {fuel_count}/{len(items)}')
if fuel_count == 0:
    print('fuelInfo не найден — Яндекс требует полноценную браузерную сессию.')

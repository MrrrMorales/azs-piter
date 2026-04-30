import requests, json, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Получаем CSRF токен
s = requests.Session()
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0',
    'Accept-Language': 'ru-RU,ru;q=0.9',
})
r = s.get('https://yandex.ru/maps/2/saint-petersburg/', timeout=10)
csrf = re.search(r'"csrfToken":"([^"]+)"', r.text)
if not csrf:
    print('CSRF не найден в странице')
    # попробуем другой способ
    csrf_m = re.search(r'csrfToken["\s:=]+([a-f0-9%:]+)', r.text)
    if csrf_m:
        print('Альтернативный CSRF:', csrf_m.group(1)[:50])
else:
    print('CSRF:', csrf.group(1)[:50])
    token = csrf.group(1)

    # Ищем Лукойл в СПб
    params = {
        'text': 'Лукойл',
        'ajax': '1',
        'lang': 'ru_RU',
        'll': '30.3141,59.9386',
        'z': '12',
        'spn': '0.5,0.3',
        'results': '10',
        'snippets': 'fuel/1.x,businessrating/1.x,subtitle/1.x',
        'csrfToken': token,
        'origin': 'maps-search-form',
        'yandex_gid': '2',  # СПб
    }
    r2 = s.get('https://yandex.ru/maps/api/search', params=params, timeout=15)
    print('Search status:', r2.status_code)

    data = r2.json()
    items = data.get('data', {}).get('items', [])
    print(f'Результатов: {len(items)}')

    for item in items[:5]:
        print(f'\n--- {item.get("title","?")} | {item.get("address","?")} ---')
        snips = item.get('snippets', {})
        print('  Snippets:', list(snips.keys()))
        if 'fuel' in snips:
            print('  Fuel:', json.dumps(snips['fuel'], ensure_ascii=False)[:500])
        # Ищем числа в диапазоне цен топлива (50-80 руб)
        full = json.dumps(item, ensure_ascii=False)
        prices = re.findall(r'[567]\d\.\d+', full)
        if prices:
            print('  Возможные цены:', prices[:5])
        features = item.get('features', [])
        fuel_feat = [f for f in features if f.get('id') == 'fuel']
        if fuel_feat:
            print('  Fuel feature:', json.dumps(fuel_feat[0], ensure_ascii=False)[:300])

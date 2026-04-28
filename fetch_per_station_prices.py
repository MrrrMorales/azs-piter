"""
fetch_per_station_prices.py — Получает индивидуальные цены на топливо для каждой АЗС.

Источники:
  - Газпром нефть (gpnbonus.ru) — ~133 станции в районе СПб, официальный API
  - (расширяемо: Лукойл, Роснефть, etc. при появлении доступных эндпоинтов)

Алгоритм:
  1. Загружает stations.json (наши OSM-станции)
  2. Получает станции бренда с координатами через их API
  3. Сопоставляет бренд-станцию с OSM-станцией по ближайшим координатам (≤200м)
  4. Записывает цены в station_prices.json {osmId -> {92, 95, 100, dt, source, updated}}

Запуск: python fetch_per_station_prices.py
"""

import json, math, sys, time, datetime, os
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Accept-Language': 'ru-RU,ru;q=0.9',
})

OUTPUT_FILE = 'station_prices.json'
# Координатные границы СПб + Ленобласть
LAT_MIN, LAT_MAX = 58.5, 61.5
LON_MIN, LON_MAX = 27.5, 33.5
MATCH_RADIUS_KM = 0.40  # радиус совпадения OSM <-> бренд, км


# ─────────────────────────────────────────────────────────────────
# Геодезия
# ─────────────────────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def find_nearest(osm_stations, lat, lon, max_km=MATCH_RADIUS_KM):
    best, best_d = None, float('inf')
    for s in osm_stations:
        d = haversine_km(lat, lon, s['lat'], s['lon'])
        if d < best_d:
            best_d = d
            best = s
    return (best, best_d) if best and best_d <= max_km else (None, None)


# ─────────────────────────────────────────────────────────────────
# Маппинг fuel type ID / shortTitle → наш ключ
# ─────────────────────────────────────────────────────────────────
def map_fuel_type(product):
    """GPN product dict → '92'|'95'|'100'|'dt'|None"""
    title = (product.get('shortTitle') or '').upper().strip()
    typ   = (product.get('type') or '').lower()

    if typ in ('dizel', 'diesel'):
        return 'dt'
    # Prefer regular grades over premium for the same grade slot
    if title in ('92', 'АИ-92'):
        return '92'
    if title in ('95', 'АИ-95'):       # regular 95
        return '95'
    if title in ('G-95', 'G95'):       # G-Drive 95 premium — store as '95_premium' for separate display
        return '95_premium'
    if title in ('100', 'АИ-100', 'G-100', 'G100', 'ЭКТО 100'):
        return '100'
    if title in ('ДТ', 'DT', 'DIESEL'):
        return 'dt'
    # Fallback: parse number from title
    import re
    m = re.search(r'\b(92|95|98|100)\b', title)
    if m:
        n = m.group(1)
        return '100' if n == '98' else n
    return None


# ─────────────────────────────────────────────────────────────────
# ИСТОЧНИК 1: Газпром нефть (gpnbonus.ru)
# ─────────────────────────────────────────────────────────────────
GPN_BASE = 'https://gpnbonus.ru'
GPN_DELAY = 0.35   # сек между запросами (вежливо к серверу)


def gpn_get_spb_stations():
    """Возвращает все GPN-станции в районе СПб/Ленобласть."""
    print('[GPN] Получаем список станций...')
    try:
        SESSION.headers['Referer'] = GPN_BASE + '/'
        r = SESSION.post(f'{GPN_BASE}/api/stations/list', json={'city': 'spb'}, timeout=20)
        r.raise_for_status()
        all_st = r.json().get('stations', [])
    except Exception as e:
        print(f'  [!] Ошибка получения списка: {e}')
        return []

    spb = []
    for st in all_st:
        try:
            lat = float(st['latitude'])
            lon = float(st['longitude'])
        except (KeyError, ValueError):
            continue
        if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
            spb.append(st)

    print(f'  Найдено {len(spb)} станций ГПН в регионе СПб/Ленобласть')
    return spb


def gpn_get_station_prices(gpn_azs_id):
    """Возвращает цены для конкретной GPN-станции по GPNAZSID."""
    try:
        r = SESSION.post(f'{GPN_BASE}/api/stations/{gpn_azs_id}', json={}, timeout=12)
        r.raise_for_status()
        return r.json().get('data', [])
    except Exception as e:
        print(f'    [!] Цены для {gpn_azs_id}: {e}')
        return []


def parse_gpn_prices(oils_data):
    """
    Из массива oils (GPN API) собирает словарь цен.
    Возвращает {92, 95, 95_premium, 100, dt}.
    """
    prices = {}
    for item in oils_data:
        prod  = item.get('product', {})
        price = item.get('price')
        if not price or not price.get('price'):
            continue
        key = map_fuel_type(prod)
        if key and key not in prices:
            prices[key] = round(float(price['price']), 2)
    return prices


def fetch_gpn(osm_stations):
    """
    Полный цикл: список GPN → цены → сопоставление с OSM.
    Возвращает {osm_id: {92, 95, 100, dt, source, updated}}.
    """
    gpn_stations = gpn_get_spb_stations()
    if not gpn_stations:
        return {}

    # Матчим только по ГПН-станциям OSM — не допускаем ложных совпадений с другими брендами
    gpn_keywords = ('газпром', 'gpn', 'gazprom')
    gpn_osm = [
        s for s in osm_stations
        if any(kw in (s.get('brand') or '').lower() or kw in (s.get('name') or '').lower()
               for kw in gpn_keywords)
    ]
    print(f'[GPN] ГПН-станций в OSM для матчинга: {len(gpn_osm)}')

    results = {}
    matched = 0
    no_match = 0
    updated_ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    print(f'[GPN] Запрашиваем цены ({len(gpn_stations)} станций)...')

    for i, gpn_st in enumerate(gpn_stations, 1):
        gpn_id = gpn_st['GPNAZSID']
        lat    = float(gpn_st['latitude'])
        lon    = float(gpn_st['longitude'])
        addr   = gpn_st.get('address', '')

        oils = gpn_get_station_prices(gpn_id)
        prices = parse_gpn_prices(oils)

        if not prices:
            print(f'  [{i}/{len(gpn_stations)}] {gpn_id} ({addr}) — нет цен')
            time.sleep(GPN_DELAY)
            continue

        # Найти ближайшую ГПН-станцию в OSM
        osm, dist = find_nearest(gpn_osm, lat, lon)
        if osm:
            entry = {
                'source': 'газпромнефть',
                'updated': updated_ts,
                '92':  prices.get('92'),
                '95':  prices.get('95'),
                '100': prices.get('100'),
                'dt':  prices.get('dt'),
            }
            # Добавляем G-95 и G-100 если есть
            if '95_premium' in prices:
                entry['95_premium'] = prices['95_premium']
            results[str(osm['id'])] = entry
            matched += 1
            print(f'  [{i}/{len(gpn_stations)}] ✓ {addr} -> OSM#{osm["id"]} ({dist*1000:.0f}м) | 92={prices.get("92")} 95={prices.get("95")} 100={prices.get("100")} dt={prices.get("dt")}')
        else:
            no_match += 1
            print(f'  [{i}/{len(gpn_stations)}] ? {addr} ({lat:.4f},{lon:.4f}) — OSM не найден')

        time.sleep(GPN_DELAY)

    print(f'[GPN] Готово: совпало {matched}, не нашлось OSM {no_match}')
    return results


# ─────────────────────────────────────────────────────────────────
# ИСТОЧНИК 2: Татнефть (api.gs.tatneft.ru)
# ─────────────────────────────────────────────────────────────────
TATNEFT_API = 'https://api.gs.tatneft.ru'
TATNEFT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Referer': 'https://azs.tatneft.ru/',
    'Origin': 'https://azs.tatneft.ru',
    'Accept-Language': 'ru-RU,ru;q=0.9',
}

# fuel_type_id → наш ключ; для каждого ключа приоритет: первый найденный wins
# Правило: обычная марка приоритетнее Taneco (Taneco — premium, дороже)
TATNEFT_FUEL_PRIORITY = {
    '92':  [36, 29],        # 36=АИ-92, 29=АИ-92 Taneco
    '95':  [34, 74],        # 34=АИ-95, 74=АИ-95 Taneco
    '100': [82],            # 82=АИ-100
    'dt':  [30, 46, 83],    # 30=ДТ, 46=ДТ Taneco, 83=ДТ Арктика Taneco
}


def parse_tatneft_prices(fuel_list):
    """Из fuel-массива Татнефти собирает {92, 95, 100, dt}."""
    by_id = {f['fuel_type_id']: f['price'] for f in fuel_list if f.get('price')}
    prices = {}
    for key, ids in TATNEFT_FUEL_PRIORITY.items():
        for fid in ids:
            if fid in by_id:
                prices[key] = round(float(by_id[fid]), 2)
                break
    return prices


def fetch_tatneft(osm_stations):
    """
    Один запрос → все ~900 станций Татнефти.
    Фильтрует по координатам СПб/Ленобласть, матчит с OSM.
    """
    print('[Татнефть] Получаем список станций...')
    try:
        r = SESSION.get(
            f'{TATNEFT_API}/api/v2/azs/?limit=9999',
            headers=TATNEFT_HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        all_st = r.json().get('data', [])
    except Exception as e:
        print(f'  [!] Ошибка запроса: {e}')
        return {}

    spb_st = [
        s for s in all_st
        if LAT_MIN <= s.get('lat', 0) <= LAT_MAX and LON_MIN <= s.get('lon', 0) <= LON_MAX
    ]
    print(f'  Найдено {len(spb_st)} станций Татнефти в регионе СПб/Ленобласть')

    tatneft_keywords = ('татнефть', 'tatneft')
    tatneft_osm = [
        s for s in osm_stations
        if any(kw in (s.get('brand') or '').lower() or kw in (s.get('name') or '').lower()
               for kw in tatneft_keywords)
    ]
    print(f'[Татнефть] Татнефть-станций в OSM для матчинга: {len(tatneft_osm)}')

    results = {}
    matched = 0
    no_match = 0
    updated_ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    for i, st in enumerate(spb_st, 1):
        lat = st['lat']
        lon = st['lon']
        addr = st.get('address', '')

        prices = parse_tatneft_prices(st.get('fuel', []))
        if not prices:
            print(f'  [{i}/{len(spb_st)}] id={st["id"]} ({addr}) — нет цен')
            continue

        osm, dist = find_nearest(tatneft_osm, lat, lon)
        if osm:
            results[str(osm['id'])] = {
                'source': 'татнефть',
                'updated': updated_ts,
                '92':  prices.get('92'),
                '95':  prices.get('95'),
                '100': prices.get('100'),
                'dt':  prices.get('dt'),
            }
            matched += 1
            print(f'  [{i}/{len(spb_st)}] ✓ id={st["id"]} ({addr}) -> OSM#{osm["id"]} ({dist*1000:.0f}м) | 92={prices.get("92")} 95={prices.get("95")} 100={prices.get("100")} dt={prices.get("dt")}')
        else:
            no_match += 1
            print(f'  [{i}/{len(spb_st)}] ? id={st["id"]} ({addr}) ({lat:.4f},{lon:.4f}) — OSM не найден')

    print(f'[Татнефть] Готово: совпало {matched}, не нашлось OSM {no_match}')
    return results


# ─────────────────────────────────────────────────────────────────
# ИСТОЧНИК 3: Лукойл
#
# Исследование (апрель 2026):
#   ✅ GetSearchObjects?form=gasStation  — все станции с координатами, БЕЗ цен
#   ✅ GetCountryDependentSearchObjectData?form=gasStation&country=RU
#      — битмаска доступных видов топлива для каждой станции (бесплатно)
#   🔒 Мобильный бэкенд: mobile-ap.licard.com / api.licard.com
#      — цены есть, но требует Bearer token из мобильного приложения
#   💰 Коммерческий API: api.omt-consult.ru/v2/stations (benzup.ru) — платный
#
# Текущая реализация: используем бесплатные API для определения ассортимента
# топлива на каждой станции. Цены — средние по сети из prices.json.
# Если LUKOIL_TOKEN появится — раскомментировать блок ниже.
# ─────────────────────────────────────────────────────────────────
LUKOIL_BASE = 'https://auto.lukoil.ru'
# LUKOIL_MOBILE_API = 'https://api.licard.com'  # Bearer token from mobile app
# LUKOIL_TOKEN = os.environ.get('LUKOIL_TOKEN', '')

# FuelId → наш ключ; только основные виды топлива для России
LUKOIL_FUEL_ID_MAP = {
    0: '100', 1: '100',           # АИ 100 ЭКТО / ЕВРО
    3: '92',  4: '92',            # АИ 92 ЭКТО / ЕВРО
    6: '95',  7: '95',  8: '95',  # АИ 95 ЭКТО, ECTO PLUS, ЕВРО
    9: '100', 10: '100',          # АИ 98 (→ 100 в нашей схеме)
    16: 'dt', 17: 'dt', 18: 'dt', 25: 'dt',  # ДИЗЕЛЬ всех видов
}


def lukoil_get_stations():
    """Все станции Лукойл с координатами (без цен)."""
    try:
        r = SESSION.get(f'{LUKOIL_BASE}/api/cartography/GetSearchObjects?form=gasStation', timeout=30)
        r.raise_for_status()
        return r.json().get('GasStations', [])
    except Exception as e:
        print(f'  [!] GetSearchObjects: {e}')
        return []


def lukoil_get_fuel_availability():
    """
    Возвращает {GasStationId: set_of_fuel_keys} для всех станций.
    Использует GetCountryDependentSearchObjectData?country=RU.
    """
    try:
        r = SESSION.get(
            f'{LUKOIL_BASE}/api/cartography/GetCountryDependentSearchObjectData'
            '?form=gasStation&country=RU',
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f'  [!] GetCountryDependentSearchObjectData: {e}')
        return {}

    # Упорядоченный список FuelId-ов, соответствующих битам битмаски (RU)
    fuel_class_order = data.get('FuelClasses', [])
    availability = {}
    for st in data.get('GasStations', []):
        sid = st['GasStationId']
        fuels = set()
        for i, bitmask in enumerate(st.get('FuelClasses', [])):
            base = i * 32
            for bit in range(32):
                if bitmask & (1 << bit):
                    pos = base + bit
                    if pos < len(fuel_class_order):
                        fuel_id = fuel_class_order[pos]
                        key = LUKOIL_FUEL_ID_MAP.get(fuel_id)
                        if key:
                            fuels.add(key)
        availability[sid] = fuels
    return availability


def fetch_lukoil(osm_stations):
    """
    Лукойл: бесплатные API дают координаты + ассортимент топлива на каждой станции.
    Цены — средние по сети из prices.json (нет бесплатного per-station API).

    Итог: {osm_id: {'source':'network', 'fuels':[...], '92':..., ...}}
    UI использует поле 'fuels' чтобы скрыть марки, которых нет на данной АЗС.
    """
    print('[Лукойл] Получаем список станций...')
    all_st = lukoil_get_stations()
    spb_st = [
        s for s in all_st
        if LAT_MIN <= s.get('Latitude', 0) <= LAT_MAX
        and LON_MIN <= s.get('Longitude', 0) <= LON_MAX
    ]
    print(f'  Найдено {len(spb_st)} станций Лукойл в регионе СПб/Ленобласть')

    print('[Лукойл] Получаем ассортимент топлива...')
    availability = lukoil_get_fuel_availability()
    print(f'  Данные о топливе: {len(availability)} станций')

    # Средние цены Лукойл из prices.json
    network_prices = {}
    try:
        with open('prices.json', 'r', encoding='utf-8') as f:
            pd = json.load(f)
        for brand_key, prices in pd.get('prices', {}).items():
            if 'луко' in brand_key.lower():
                network_prices = prices
                break
    except Exception:
        pass

    lukoil_keywords = ('лукойл', 'lukoil')
    lukoil_osm = [
        s for s in osm_stations
        if any(kw in (s.get('brand') or '').lower() or kw in (s.get('name') or '').lower()
               for kw in lukoil_keywords)
    ]
    print(f'[Лукойл] Лукойл-станций в OSM для матчинга: {len(lukoil_osm)}')

    results = {}
    matched = 0
    no_match = 0
    updated_ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')

    for st in spb_st:
        lat = st.get('Latitude', 0)
        lon = st.get('Longitude', 0)
        sid = st['GasStationId']
        addr = st.get('Street', '') or st.get('DisplayName', '')

        fuels_available = availability.get(sid, set())
        if not fuels_available:
            # Нет данных об ассортименте — пропускаем, чтобы не мешать fallback
            continue

        osm, dist = find_nearest(lukoil_osm, lat, lon)
        if not osm:
            no_match += 1
            continue

        fuel_list = sorted(fuels_available, key=lambda k: ['92', '95', '100', 'dt'].index(k) if k in ['92', '95', '100', 'dt'] else 99)
        entry = {
            'source': 'network',  # цены средние по сети, не per-station
            'updated': updated_ts,
            'fuels': fuel_list,   # ассортимент топлива конкретной АЗС
            '92':  network_prices.get('92')  if '92'  in fuels_available else None,
            '95':  network_prices.get('95')  if '95'  in fuels_available else None,
            '100': network_prices.get('100') if '100' in fuels_available else None,
            'dt':  network_prices.get('dt')  if 'dt'  in fuels_available else None,
        }
        results[str(osm['id'])] = entry
        matched += 1
        print(f'  ✓ id={sid} ({addr}) -> OSM#{osm["id"]} ({dist*1000:.0f}м) | {fuel_list}')

    print(f'[Лукойл] Готово: совпало {matched}, не нашлось OSM {no_match}')
    if not network_prices:
        print('  [!] prices.json для Лукойл не найден — цены будут None')
    return results


def fetch_lukoil_yandex(osm_stations):
    """
    Лукойл: реальные цены с Яндекс Карт через Playwright.
    Поскольку Лукойл держит единые цены по СПб, применяем их ко всем
    Лукойл-станциям из OSM.

    Требует: pip install playwright && python -m playwright install chromium
    Требует запуск с GUI (headless=False — Яндекс блокирует headless).
    """
    import asyncio, subprocess, sys

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print('[Лукойл/Яндекс] Playwright не установлен → fallback на fetch_lukoil()')
        return fetch_lukoil(osm_stations)

    print('[Лукойл/Яндекс] Запускаем Playwright для получения цен с Яндекс Карт...')

    async def _run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            ctx = await browser.new_context(locale='ru-RU', viewport={'width': 1366, 'height': 900})
            page = await ctx.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            csrf_token = None
            captured_items = []

            async def on_request(request):
                nonlocal csrf_token
                url = request.url
                if '/maps/api/search' in url and 'csrfToken' in url and not csrf_token:
                    from urllib.parse import urlparse, parse_qs
                    params = parse_qs(urlparse(url).query)
                    token = params.get('csrfToken', [''])[0]
                    if len(token) > 20:
                        csrf_token = token

            async def on_response(response):
                url = response.url
                if '/maps/api/search' in url:
                    try:
                        text = await response.text()
                        if 'fuelInfo' in text and not captured_items:
                            import json as _json
                            d = _json.loads(text)
                            items = d.get('data', {}).get('items', [])
                            captured_items.extend(items)
                            total = d.get('data', {}).get('totalResultCount', 0)
                            fuel_c = sum(1 for it in items if isinstance(it, dict) and it.get('fuelInfo'))
                            print(f'  [Яндекс] {len(items)} из {total}, с ценами: {fuel_c}')
                    except Exception:
                        pass

            page.on('request', on_request)
            page.on('response', on_response)

            try:
                await page.goto('https://yandex.ru/maps/', wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(3)

                try:
                    inp = await page.wait_for_selector(
                        'input[class*="input"], [class*="search"] input, input[type="text"]',
                        timeout=10000
                    )
                    await inp.click()
                    await asyncio.sleep(0.5)
                    await inp.fill('ЛУКОЙЛ АЗС Санкт-Петербург')
                    await asyncio.sleep(0.3)
                    await page.keyboard.press('Enter')
                except Exception:
                    await page.goto('https://yandex.ru/maps/?text=ЛУКОЙЛ%20АЗС%20Санкт-Петербург&type=biz',
                                   wait_until='domcontentloaded', timeout=60000)

                await asyncio.sleep(20)
            except Exception as e:
                print(f'  [!] Playwright ошибка: {e}')
            finally:
                await browser.close()

            return captured_items

    try:
        items = asyncio.run(_run())
    except Exception as e:
        print(f'  [!] asyncio.run ошибка: {e}')
        return fetch_lukoil(osm_stations)

    if not items:
        print('  [!] Яндекс не вернул данных → fallback на fetch_lukoil()')
        return fetch_lukoil(osm_stations)

    # Маппинг имён Яндекса на наши ключи
    YANDEX_FUEL_MAP = {
        'аи 92+': '92', 'аи 92': '92',
        'аи 95':  '95', 'аи-95': '95',
        'аи 95+': '95_premium', 'аи-95+': '95_premium',
        'аи 100': '100', 'аи-100': '100',
        'дт+': 'dt', 'дт': 'dt', 'diesel': 'dt',
    }

    # Извлекаем цены из первой попавшейся станции с fuelInfo (они одинаковые)
    network_prices = {}
    fuel_timestamp = None
    for item in items:
        fi = item.get('fuelInfo') if isinstance(item, dict) else None
        if fi and fi.get('items'):
            fuel_timestamp = fi.get('timestamp')
            for p in fi['items']:
                if 'price' not in p:
                    continue
                key = YANDEX_FUEL_MAP.get(p['name'].lower().strip())
                if key and key not in network_prices:
                    network_prices[key] = round(float(p['price']['value']), 2)
            break

    if not network_prices:
        print('  [!] fuelInfo пуст → fallback')
        return fetch_lukoil(osm_stations)

    if fuel_timestamp:
        import datetime as _dt
        ts_str = _dt.datetime.fromtimestamp(fuel_timestamp).strftime('%d.%m.%Y')
        print(f'  [Яндекс] Цены актуальны на {ts_str}: {network_prices}')

    # Применяем ко всем Лукойл-станциям OSM
    lukoil_keywords = ('лукойл', 'lukoil')
    lukoil_osm = [
        s for s in osm_stations
        if any(kw in (s.get('brand') or '').lower() or kw in (s.get('name') or '').lower()
               for kw in lukoil_keywords)
    ]
    print(f'  [Яндекс] Применяем цены к {len(lukoil_osm)} Лукойл-станциям OSM')

    updated_ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    results = {}
    for osm in lukoil_osm:
        results[str(osm['id'])] = {
            'source': 'яндекс',
            'updated': updated_ts,
            '92':  network_prices.get('92'),
            '95':  network_prices.get('95'),
            '95_premium': network_prices.get('95_premium'),
            '100': network_prices.get('100'),
            'dt':  network_prices.get('dt'),
        }

    print(f'[Лукойл/Яндекс] Готово: {len(results)} станций')
    return results


def fetch_rosneft(osm_stations):
    return {}

def fetch_ptk(osm_stations):
    return {}


# ─────────────────────────────────────────────────────────────────
# ГЛАВНАЯ ФУНКЦИЯ
# ─────────────────────────────────────────────────────────────────
def run():
    print('=' * 60)
    print('  Получение индивидуальных цен АЗС')
    print('=' * 60)

    # Загрузить OSM-станции
    with open('stations.json', 'r', encoding='utf-8') as f:
        osm_stations = json.load(f)
    print(f'Загружено {len(osm_stations)} OSM-станций')

    # Собираем цены из всех источников — каждый раз с нуля,
    # чтобы не накапливались устаревшие или ошибочные матчи
    all_prices = {}

    print()
    for fetcher_fn in [fetch_gpn, fetch_tatneft, fetch_lukoil_yandex, fetch_rosneft, fetch_ptk]:
        try:
            chunk = fetcher_fn(osm_stations)
            # Обновляем: новые данные перезаписывают старые для тех же станций
            all_prices.update(chunk)
            if chunk:
                print(f'  Добавлено/обновлено {len(chunk)} записей')
        except Exception as e:
            print(f'  [!] Ошибка источника {fetcher_fn.__name__}: {e}')

    output = {
        'updated': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
        'stations': all_prices,
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print('=' * 60)
    print(f'Готово! Станций с индивидуальными ценами: {len(all_prices)}')
    print(f'Сохранено в {OUTPUT_FILE}')
    print('=' * 60)


if __name__ == '__main__':
    run()

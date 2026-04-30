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
LON_MIN, LON_MAX = 27.5, 35.5  # 33.5 срезал восток Ленобласти (Тихвин, Бокситогорск)
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


def _lukoil_parse_hours(gs):
    """Парсит StationBusinessHours → читаемая строка или None."""
    if gs.get('TwentyFourHour'):
        return 'Круглосуточно'
    bh = gs.get('StationBusinessHours') or {}
    days_raw = bh.get('Days') or []
    if not days_raw:
        return None

    def fmt_time(t):
        # "08:00:00" → "08:00", "1.00:00:00" → "00:00" (след. полночь = 24:00)
        if not t:
            return '?'
        if t.startswith('1.'):
            return '24:00'
        return t[:5]

    # Если все дни одинаковы — одна строка
    slots = [(fmt_time(d.get('StartTime')), fmt_time(d.get('EndTime'))) for d in days_raw]
    start0, end0 = slots[0]
    if start0 == '00:00' and end0 == '24:00':
        return 'Круглосуточно'
    if all(s == start0 and e == end0 for s, e in slots):
        return f'Ежедневно {start0}–{end0}'

    # Иначе пн-пт / сб-вс
    day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    groups = []
    i = 0
    while i < len(slots):
        j = i + 1
        while j < len(slots) and slots[j] == slots[i]:
            j += 1
        s, e = slots[i]
        if i == j - 1:
            groups.append(f'{day_names[i]}: {s}–{e}')
        else:
            groups.append(f'{day_names[i]}–{day_names[j-1]}: {s}–{e}')
        i = j
    return ', '.join(groups)


def lukoil_get_details(station_ids):
    """
    Батч-запрос GetObjects для списка GasStationId.
    Возвращает {GasStationId: {'address':..., 'phone':..., 'hours':..., 'services':[...]}}.
    20 станций за запрос.
    """
    BATCH = 20
    result = {}
    batches = [station_ids[i:i+BATCH] for i in range(0, len(station_ids), BATCH)]
    for idx, batch in enumerate(batches):
        params = [('ids', f'gasStation{sid}') for sid in batch] + [('lng', 'RU')]
        try:
            r = SESSION.get(f'{LUKOIL_BASE}/api/cartography/GetObjects', params=params, timeout=30)
            r.raise_for_status()
            for item in r.json():
                gs = item.get('GasStation', {})
                sid = gs.get('GasStationId')
                if not sid:
                    continue
                result[sid] = {
                    'address':  gs.get('Address') or gs.get('Street') or None,
                    'phone':    gs.get('Phone') or None,
                    'hours':    _lukoil_parse_hours(gs),
                    'services': [s['Name'] for s in gs.get('Services', []) if s.get('Name')],
                }
        except Exception as e:
            print(f'  [!] GetObjects батч {idx+1}/{len(batches)}: {e}')
        time.sleep(0.3)
    return result


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

    print('[Лукойл] Получаем детальные данные каждой станции (GetObjects)...')
    spb_ids = [s['GasStationId'] for s in spb_st]
    details = lukoil_get_details(spb_ids)
    print(f'  Деталей получено: {len(details)} станций')

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
        det = details.get(sid, {})
        entry = {
            'source': 'network',  # цены средние по сети, не per-station
            'updated': updated_ts,
            'fuels': fuel_list,   # ассортимент топлива конкретной АЗС
            '92':  network_prices.get('92')  if '92'  in fuels_available else None,
            '95':  network_prices.get('95')  if '95'  in fuels_available else None,
            '100': network_prices.get('100') if '100' in fuels_available else None,
            'dt':  network_prices.get('dt')  if 'dt'  in fuels_available else None,
        }
        if det.get('address'):
            entry['address'] = det['address']
        if det.get('phone'):
            entry['phone'] = det['phone']
        if det.get('hours'):
            entry['hours'] = det['hours']
        if det.get('services'):
            entry['services'] = det['services']
        results[str(osm['id'])] = entry
        matched += 1
        print(f'  ✓ id={sid} ({addr}) -> OSM#{osm["id"]} ({dist*1000:.0f}м) | {fuel_list}')

    print(f'[Лукойл] Готово: совпало {matched}, не нашлось OSM {no_match}')
    if not network_prices:
        print('  [!] prices.json для Лукойл не найден — цены будут None')
    return results


def fetch_lukoil_yandex(osm_stations):
    """
    Лукойл: per-station цены с Яндекс Карт через Playwright.
    Собирает все страницы, матчит каждую станцию Яндекса к OSM по координатам.
    Fallback на fetch_lukoil() если Playwright не установлен.
    """
    print('[Лукойл/Яндекс] Запускаем Playwright для получения цен с Яндекс Карт...')
    items = _yandex_playwright_search('ЛУКОЙЛ АЗС Санкт-Петербург')

    if items is None:
        print('[Лукойл/Яндекс] Playwright не установлен → fallback на fetch_lukoil()')
        return fetch_lukoil(osm_stations)
    if not items:
        print('  [!] Яндекс не вернул данных → fallback на fetch_lukoil()')
        return fetch_lukoil(osm_stations)

    per_station = _extract_per_station_prices(items)
    print(f'  [Яндекс] Позиций с ценами и координатами: {len(per_station)}')

    if not per_station:
        print('  [!] Нет per-station данных → fallback на fetch_lukoil()')
        return fetch_lukoil(osm_stations)

    lukoil_keywords = ('лукойл', 'lukoil')
    lukoil_osm = [
        s for s in osm_stations
        if any(kw in (s.get('brand') or '').lower() or kw in (s.get('name') or '').lower()
               for kw in lukoil_keywords)
    ]
    print(f'  [Яндекс] Лукойл-станций в OSM: {len(lukoil_osm)}')

    updated_ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    results = {}
    matched = 0

    for yandex_st in per_station:
        osm, dist = find_nearest(lukoil_osm, yandex_st['lat'], yandex_st['lon'])
        if osm:
            osm_id = str(osm['id'])
            if osm_id not in results:
                p = yandex_st['prices']
                results[osm_id] = {
                    'source': 'яндекс',
                    'updated': updated_ts,
                    '92':         p.get('92'),
                    '95':         p.get('95'),
                    '95_premium': p.get('95_premium'),
                    '100':        p.get('100'),
                    'dt':         p.get('dt'),
                }
                matched += 1
                print(f'  ✓ ({yandex_st["lat"]:.4f},{yandex_st["lon"]:.4f}) -> OSM#{osm["id"]} ({dist*1000:.0f}м) | {p}')

    unmatched = len(lukoil_osm) - matched
    print(f'[Лукойл/Яндекс] Готово: per-station {matched}, без данных {unmatched}, всего {len(results)}')

    # Обогащаем деталями из GetObjects (адрес, телефон, часы, услуги)
    print('[Лукойл/Яндекс] Обогащаем данные из GetObjects...')
    all_lukoil_st = lukoil_get_stations()
    spb_lukoil_st = [
        s for s in all_lukoil_st
        if LAT_MIN <= s.get('Latitude', 0) <= LAT_MAX
        and LON_MIN <= s.get('Longitude', 0) <= LON_MAX
    ]
    if spb_lukoil_st:
        spb_ids = [s['GasStationId'] for s in spb_lukoil_st]
        details = lukoil_get_details(spb_ids)
        osm_by_id = {str(s['id']): s for s in lukoil_osm}
        for osm_id, entry in results.items():
            osm_st = osm_by_id.get(osm_id)
            if not osm_st:
                continue
            best_sid, best_dist = None, float('inf')
            for api_st in spb_lukoil_st:
                d = haversine_km(osm_st.get('lat', 0), osm_st.get('lon', 0),
                                 api_st.get('Latitude', 0), api_st.get('Longitude', 0))
                if d < best_dist:
                    best_dist = d
                    best_sid = api_st['GasStationId']
            if best_sid and best_dist <= MATCH_RADIUS_KM:
                det = details.get(best_sid, {})
                if det.get('address'):
                    entry['address'] = det['address']
                if det.get('phone'):
                    entry['phone'] = det['phone']
                if det.get('hours'):
                    entry['hours'] = det['hours']
                if det.get('services'):
                    entry['services'] = det['services']
        print(f'  GetObjects: детали добавлены для {sum(1 for e in results.values() if "address" in e)} станций')
    return results


# ─────────────────────────────────────────────────────────────────
# ИСТОЧНИК 4: Роснефть
#
# Исследование (апрель 2026):
#   🔒 rosneft-azs.ru/api/v*/stations — API существует, но требует
#      авторизованный токен мобильного приложения (ошибка 516 без него).
#
# Текущая реализация: Playwright + Яндекс Карты, аналогично Лукойлу.
# Роснефть держит единые цены по СПб → применяем ко всем Роснефть-станциям OSM.
# Требует: pip install playwright && python -m playwright install chromium
# Режим headless=False (Яндекс детектирует headless).
# ─────────────────────────────────────────────────────────────────

# Маппинг яндексовых названий топлива → наши ключи (общий для всех Яндекс-источников)
YANDEX_FUEL_MAP = {
    'аи 92':      '92',          'аи 92+':     '92',
    'аи-92':      '92',          'аи-92+':     '92',
    'аи 95':      '95',          'аи-95':      '95',
    'аи 95+':     '95_premium',  'аи-95+':     '95_premium',
    'аи 100':     '100',         'аи-100':     '100',
    'pulsar 92':  '92',          'pulsar 95':  '95',
    'pulsar 95+': '95_premium',  'pulsar 100': '100',
    'дт':         'dt',          'дт+':        'dt',
    'diesel':     'dt',
}


def _yandex_playwright_search(search_text):
    """
    Открывает Яндекс Карты через Playwright, ищет search_text и перехватывает
    ВСЕ страницы /maps/api/search с fuelInfo (прокрутка сайдбара).
    Возвращает список всех items (или [] при ошибке, None если Playwright не установлен).
    """
    import asyncio
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None  # сигнал: Playwright не установлен

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
            captured_items = []
            seen_ids = set()

            async def on_response(response):
                if '/maps/api/search' in response.url:
                    try:
                        text = await response.text()
                        if 'fuelInfo' not in text:
                            return
                        import json as _json
                        d = _json.loads(text)
                        items = d.get('data', {}).get('items', [])
                        total = d.get('data', {}).get('totalResultCount', 0)
                        new_count = 0
                        for it in items:
                            if not isinstance(it, dict):
                                continue
                            iid = it.get('id') or it.get('uri') or it.get('permalink')
                            if iid:
                                if iid not in seen_ids:
                                    seen_ids.add(iid)
                                    captured_items.append(it)
                                    new_count += 1
                            else:
                                captured_items.append(it)
                                new_count += 1
                        fuel_c = sum(1 for it in items if isinstance(it, dict) and it.get('fuelInfo'))
                        if new_count:
                            print(f'  [Яндекс] +{new_count} новых (с ценами: {fuel_c}), всего: {len(captured_items)}/{total}')
                    except Exception:
                        pass

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
                    await inp.fill(search_text)
                    await asyncio.sleep(0.3)
                    await page.keyboard.press('Enter')
                except Exception:
                    from urllib.parse import quote
                    await page.goto(
                        f'https://yandex.ru/maps/?text={quote(search_text)}&type=biz',
                        wait_until='domcontentloaded', timeout=60000
                    )
                await asyncio.sleep(12)  # ждём первую страницу

                # Прокручиваем сайдбар для загрузки всех страниц
                prev_count = 0
                for _ in range(20):
                    await page.evaluate("""() => {
                        const selectors = [
                            '.search-list-view__list',
                            '.card-list-view',
                            '.sidebar-view__panel',
                            '[class*="search-list"]',
                            '[class*="results"]',
                        ];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.scrollHeight > el.clientHeight) {
                                el.scrollTop = el.scrollHeight;
                                return;
                            }
                        }
                        window.scrollTo(0, document.body.scrollHeight);
                    }""")
                    await asyncio.sleep(2)
                    if len(captured_items) == prev_count:
                        break
                    prev_count = len(captured_items)

            except Exception as e:
                print(f'  [!] Playwright ошибка: {e}')
            finally:
                await browser.close()
            return captured_items

    try:
        return asyncio.run(_run())
    except Exception as e:
        print(f'  [!] asyncio.run ошибка: {e}')
        return []


def _extract_network_prices(items):
    """
    Из списка items Яндекс Карт извлекает цены из первой станции с fuelInfo.
    Возвращает (prices_dict, timestamp_str | None).
    """
    for item in items:
        fi = item.get('fuelInfo') if isinstance(item, dict) else None
        if fi and fi.get('items'):
            ts = fi.get('timestamp')
            prices = {}
            for p in fi['items']:
                if 'price' not in p:
                    continue
                key = YANDEX_FUEL_MAP.get(p['name'].lower().strip())
                if key and key not in prices:
                    prices[key] = round(float(p['price']['value']), 2)
            if prices:
                ts_str = None
                if ts:
                    import datetime as _dt
                    ts_str = _dt.datetime.fromtimestamp(ts).strftime('%d.%m.%Y')
                return prices, ts_str
    return {}, None


def _extract_per_station_prices(items):
    """
    Из всех items Яндекс Карт извлекает per-station цены с координатами.
    Поддерживает GeoJSON (coordinates: [lon, lat]) и {lat, lon} форматы.
    Возвращает [{lat, lon, prices}].
    """
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fi = item.get('fuelInfo')
        if not fi or not fi.get('items'):
            continue

        lat, lon = None, None
        geo = item.get('geometry')
        if isinstance(geo, dict):
            coords = geo.get('coordinates')
            if coords and len(coords) >= 2:
                lon, lat = float(coords[0]), float(coords[1])  # GeoJSON: [lon, lat]
        if lat is None:
            pt = item.get('point')
            if isinstance(pt, dict):
                _lat = pt.get('lat') or pt.get('latitude')
                _lon = pt.get('lon') or pt.get('longitude')
                if _lat and _lon:
                    lat, lon = float(_lat), float(_lon)

        if lat is None or lon is None:
            continue

        prices = {}
        for p in fi['items']:
            if 'price' not in p:
                continue
            key = YANDEX_FUEL_MAP.get(p['name'].lower().strip())
            if key and key not in prices:
                prices[key] = round(float(p['price']['value']), 2)

        if prices:
            result.append({'lat': lat, 'lon': lon, 'prices': prices})

    return result


def fetch_rosneft_yandex(osm_stations):
    """
    Роснефть: per-station цены с Яндекс Карт через Playwright.
    Собирает все страницы, матчит каждую станцию Яндекса к OSM по координатам.
    """
    print('[Роснефть/Яндекс] Запускаем Playwright для получения цен с Яндекс Карт...')
    items = _yandex_playwright_search('Роснефть АЗС Санкт-Петербург')

    if items is None:
        print('[Роснефть/Яндекс] Playwright не установлен → пропускаем Роснефть')
        return {}
    if not items:
        print('  [!] Яндекс не вернул данных → пропускаем Роснефть')
        return {}

    per_station = _extract_per_station_prices(items)
    print(f'  [Яндекс] Позиций с ценами и координатами: {len(per_station)}')

    if not per_station:
        print('  [!] Нет per-station данных → пропускаем Роснефть')
        return {}

    rosneft_keywords = ('роснефть', 'rosneft')
    rosneft_osm = [
        s for s in osm_stations
        if any(kw in (s.get('brand') or '').lower() or kw in (s.get('name') or '').lower()
               for kw in rosneft_keywords)
    ]
    print(f'  [Яндекс] Роснефть-станций в OSM: {len(rosneft_osm)}')

    updated_ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    results = {}
    matched = 0

    for yandex_st in per_station:
        osm, dist = find_nearest(rosneft_osm, yandex_st['lat'], yandex_st['lon'])
        if osm:
            osm_id = str(osm['id'])
            if osm_id not in results:
                p = yandex_st['prices']
                results[osm_id] = {
                    'source': 'яндекс',
                    'updated': updated_ts,
                    '92':         p.get('92'),
                    '95':         p.get('95'),
                    '95_premium': p.get('95_premium'),
                    '100':        p.get('100'),
                    'dt':         p.get('dt'),
                }
                matched += 1
                print(f'  ✓ ({yandex_st["lat"]:.4f},{yandex_st["lon"]:.4f}) -> OSM#{osm["id"]} ({dist*1000:.0f}м) | {p}')

    # Fallback для OSM-станций без совпадения: сетевая цена
    unmatched = [s for s in rosneft_osm if str(s['id']) not in results]
    if unmatched:
        network_prices, ts_str = _extract_network_prices(items)
        if network_prices:
            if ts_str:
                print(f'  [Яндекс] Сетевая цена на {ts_str}: {network_prices}')
            for osm in unmatched:
                results[str(osm['id'])] = {
                    'source': 'яндекс',
                    'updated': updated_ts,
                    '92':         network_prices.get('92'),
                    '95':         network_prices.get('95'),
                    '95_premium': network_prices.get('95_premium'),
                    '100':        network_prices.get('100'),
                    'dt':         network_prices.get('dt'),
                }
            print(f'  Fallback (сетевая): {len(unmatched)} станций')

    print(f'[Роснефть/Яндекс] Готово: per-station {matched}, fallback {len(unmatched)}, всего {len(results)}')
    return results


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
    for fetcher_fn in [fetch_gpn, fetch_tatneft, fetch_lukoil_yandex, fetch_rosneft_yandex, fetch_ptk]:
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

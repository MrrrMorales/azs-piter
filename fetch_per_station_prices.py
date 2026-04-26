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
# ЗАГЛУШКИ ДЛЯ БУДУЩИХ ИСТОЧНИКОВ
# ─────────────────────────────────────────────────────────────────
def fetch_lukoil(osm_stations):
    # TODO: добавить как только найдём рабочий endpoint Лукойл
    return {}

def fetch_rosneft(osm_stations):
    # TODO: rosneft.ru endpoints закрыты, нужен другой подход
    return {}

def fetch_ptk(osm_stations):
    # TODO: ptk.ru недоступен
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
    for fetcher_fn in [fetch_gpn, fetch_lukoil, fetch_rosneft, fetch_ptk]:
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

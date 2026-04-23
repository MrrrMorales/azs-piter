"""
enrich_brands.py — Обогащает названия, бренды и адреса АЗС через 2GIS API.

2GIS — самый точный источник данных об организациях в России.
Для каждой АЗС из stations.json ищет ближайший объект в 2GIS в радиусе 100м
и обновляет name, brand, address, phone.

Получить бесплатный API-ключ (10 000 запросов/день):
  https://dev.2gis.com/ → «Создать проект» → тип «Web» → ключ готов

Запуск:
  python enrich_brands.py --key YOUR_2GIS_KEY
  python enrich_brands.py --key YOUR_2GIS_KEY --radius 150 --dry-run
"""

import json
import math
import sys
import time
import argparse
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TWOGIS_SEARCH = 'https://catalog.api.2gis.com/3.0/items'
DELAY = 0.2          # сек между запросами к 2GIS
DEFAULT_RADIUS = 100  # метры — радиус поиска вокруг координат
FUEL_RUBRIC_IDS = {
    '164027653704': True,  # Автозаправки (АЗС)
    '141265769337557': True,  # Заправочные станции
}

# Нормализация известных названий сетей
BRAND_NORMALIZE = {
    'лукойл': 'Лукойл',
    'lukoil': 'Лукойл',
    'газпромнефть': 'Газпромнефть',
    'газпром нефть': 'Газпромнефть',
    'gpn': 'Газпромнефть',
    'роснефть': 'Роснефть',
    'rosneft': 'Роснефть',
    'neste': 'Neste',
    'несте': 'Neste',
    'татнефть': 'Татнефть',
    'tatneft': 'Татнефть',
    'teboil': 'Teboil',
    'тебойл': 'Teboil',
    'shell': 'Shell',
    'птк': 'ПТК',
    'ptk': 'ПТК',
    'петербургская топливная': 'Петербургская топливная компания',
    'пикалёвская топливная': 'Пикалёвская топливная компания',
    'авро': 'Авро',
    'трасса': 'Трасса',
    'кинеф': 'Кинеф',
    'киришиавтосервис': 'Киришиавтосервис',
    'сургутнефтегаз': 'Сургутнефтегаз',
    'esso': 'Esso',
    'nord point': 'Nord Point',
    'линос': 'Линос',
    'linos': 'Линос',
    'aris': 'Aris',
    'китэк': 'КиТЭК',
    'выборгская топливная': 'Выборгская топливная компания',
    'втк': 'ВТК',
    'санга': 'Санга',
    'sanga': 'Санга',
    'фаэтон': 'Фаэтон',
    'фаэтон-аэро': 'Фаэтон',
    'faeton': 'Фаэтон',
    'shelf': 'Shelf',
    'опти': 'Опти',
    'opti': 'Опти',
    'apn': 'APN',
    'bp': 'BP',
    'бп': 'BP',
}


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def normalize_brand(raw_name):
    """Нормализует имя к эталонному написанию."""
    n = raw_name.lower().strip()
    for key, canonical in BRAND_NORMALIZE.items():
        if key in n:
            return canonical
    return None


def search_2gis(lat, lon, radius, api_key):
    """
    Ищет АЗС в радиусе radius метров от lat,lon через 2GIS Catalog API 3.0.
    Возвращает список найденных объектов.
    """
    params = {
        'q': 'АЗС автозаправка',
        'point': f'{lon},{lat}',
        'radius': radius,
        'type': 'branch',
        'key': api_key,
        'lang': 'ru',
        'fields': 'items.name,items.address,items.contact_groups,items.rubrics,items.point',
        'page_size': 10,
    }
    url = TWOGIS_SEARCH + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'AZS-Piter/1.0 (cadillacslava@gmail.com)',
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get('result', {}).get('items', [])
    except Exception as e:
        print(f'    [!] 2GIS error: {e}')
        return []


def is_fuel_station(item):
    """Проверяет, что объект 2GIS — это АЗС."""
    rubrics = item.get('rubrics', [])
    name_lower = item.get('name', '').lower()
    fuel_keywords = ('азс', 'автозаправ', 'заправоч', 'нефть', 'нефт ', 'газпром',
                     'лукойл', 'роснефть', 'neste', 'teboil', 'птк', 'bp ', 'shell')
    if any(kw in name_lower for kw in fuel_keywords):
        return True
    for r in rubrics:
        rid = str(r.get('id', ''))
        rname = r.get('name', '').lower()
        if rid in FUEL_RUBRIC_IDS or 'заправ' in rname or 'азс' in rname:
            return True
    return False


def extract_phone(item):
    """Извлекает первый телефон из contact_groups."""
    for group in item.get('contact_groups', []):
        for contact in group.get('contacts', []):
            if contact.get('type') == 'phone':
                val = contact.get('value', '')
                if val:
                    return val
    return ''


def extract_address(item):
    """Возвращает читаемый адрес из 2GIS."""
    addr = item.get('address', {})
    # Полный адрес в виде строки если есть
    if isinstance(addr, str):
        return addr
    if isinstance(addr, dict):
        full = addr.get('name') or ''
        if full:
            # Убираем ", Россия" или ", Санкт-Петербург, Россия" с конца
            parts = [p.strip() for p in full.split(',')]
            cleaned = [p for p in parts if p.lower() not in
                       ('россия', 'russia', 'санкт-петербург', 'saint petersburg')]
            return ', '.join(cleaned)
    return ''


def best_match(items, station_lat, station_lon):
    """
    Из списка объектов 2GIS выбирает ближайшую АЗС.
    Возвращает (item, distance_m) или (None, None).
    """
    best, best_d = None, float('inf')
    for item in items:
        if not is_fuel_station(item):
            continue
        pt = item.get('point', {})
        try:
            lat2 = float(pt.get('lat', 0) or item.get('geometry', {}).get('centroid', '').split()[1].strip('()'))
            lon2 = float(pt.get('lon', 0) or item.get('geometry', {}).get('centroid', '').split()[0].strip('()'))
        except Exception:
            continue
        if not lat2 or not lon2:
            continue
        d = haversine_m(station_lat, station_lon, lat2, lon2)
        if d < best_d:
            best_d = d
            best = item
    return (best, best_d) if best else (None, None)


def run(api_key, radius, dry_run, force_all, limit):
    print('=' * 60)
    print('  Обогащение брендов АЗС через 2GIS API')
    print('=' * 60)

    with open('stations.json', 'r', encoding='utf-8') as f:
        stations = json.load(f)

    total = len(stations)
    print(f'Загружено {total} станций')
    if force_all:
        to_process = stations
        print('Режим: обновить все станции')
    else:
        # Обновляем только те, где brand пустой или name/brand = "АЗС"
        to_process = [
            s for s in stations
            if not s.get('brand') or s.get('name', '').upper() in ('АЗС', 'AZS')
               or s.get('brand', '').upper() in ('АЗС', 'AZS')
        ]
        print(f'Станций без бренда / с именем «АЗС»: {len(to_process)}')

    if limit:
        to_process = to_process[:limit]
        print(f'Ограничение: первые {limit} станций')

    print()
    updated = 0
    failed = 0
    unchanged = 0

    for i, station in enumerate(to_process, 1):
        lat, lon = station['lat'], station['lon']
        old_name = station.get('name', '')
        old_brand = station.get('brand', '')
        sid = station['id']

        print(f'[{i}/{len(to_process)}] #{sid} «{old_name}» / «{old_brand}»', end=' ... ', flush=True)

        items = search_2gis(lat, lon, radius, api_key)
        match, dist = best_match(items, lat, lon)

        if not match:
            print('не найдено в 2GIS')
            failed += 1
            time.sleep(DELAY)
            continue

        name_2gis = match.get('name', '').strip()
        addr_2gis = extract_address(match)
        phone_2gis = extract_phone(match)
        brand_normalized = normalize_brand(name_2gis) or name_2gis

        changed_fields = []
        if not dry_run:
            if name_2gis and name_2gis != old_name:
                # Для известных сетей используем нормализованное имя
                station['name'] = brand_normalized
                changed_fields.append(f'name: «{old_name}»→«{brand_normalized}»')

            if brand_normalized and brand_normalized != old_brand:
                station['brand'] = brand_normalized
                changed_fields.append(f'brand: «{old_brand}»→«{brand_normalized}»')

            if addr_2gis and not station.get('address'):
                station['address'] = addr_2gis
                changed_fields.append(f'address: «{addr_2gis}»')

            if phone_2gis and not station.get('phone'):
                station['phone'] = phone_2gis
                changed_fields.append(f'phone: {phone_2gis}')

        if changed_fields:
            print(f'✓ {dist:.0f}м | ' + ' | '.join(changed_fields))
            updated += 1
        else:
            print(f'= {dist:.0f}м (без изменений)')
            unchanged += 1

        # Промежуточное сохранение каждые 100 станций
        if not dry_run and i % 100 == 0:
            with open('stations.json', 'w', encoding='utf-8') as f:
                json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))
            print(f'  [Сохранено {i} из {len(to_process)}]')

        time.sleep(DELAY)

    if not dry_run:
        with open('stations.json', 'w', encoding='utf-8') as f:
            json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))

    print()
    print('=' * 60)
    print(f'Готово!')
    print(f'  Обновлено:        {updated}')
    print(f'  Без изменений:    {unchanged}')
    print(f'  Не найдено в 2GIS: {failed}')
    if dry_run:
        print('  (dry-run — stations.json НЕ изменён)')
    else:
        print('  stations.json обновлён')
    print('=' * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Обогащение брендов АЗС через 2GIS API')
    parser.add_argument('--key', required=True, help='API-ключ 2GIS (получить: https://dev.2gis.com)')
    parser.add_argument('--radius', type=int, default=DEFAULT_RADIUS,
                        help=f'Радиус поиска в метрах (по умолчанию {DEFAULT_RADIUS})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Показать изменения без сохранения')
    parser.add_argument('--all', dest='force_all', action='store_true',
                        help='Обновить все станции, не только без бренда')
    parser.add_argument('--limit', type=int, default=0,
                        help='Обработать только первые N станций (для теста)')
    args = parser.parse_args()

    run(
        api_key=args.key,
        radius=args.radius,
        dry_run=args.dry_run,
        force_all=args.force_all,
        limit=args.limit,
    )

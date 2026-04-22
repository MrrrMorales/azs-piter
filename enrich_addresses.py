"""
enrich_addresses.py — Заполняет отсутствующие адреса АЗС через Nominatim reverse geocoding.
Запуск: python enrich_addresses.py

Для станций без адреса делает запрос к OSM Nominatim по координатам (lat/lon).
Соблюдает лимит 1 запрос/сек (требование Nominatim ToS).
"""

import json
import sys
import time
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
HEADERS = {'User-Agent': 'AZS-Piter/1.0 (cadillacslava@gmail.com)'}
DELAY = 1.1  # секунды между запросами


def reverse_geocode(lat, lon):
    params = urllib.parse.urlencode({
        'lat': lat,
        'lon': lon,
        'format': 'json',
        'addressdetails': 1,
        'zoom': 18,
        'accept-language': 'ru',
    })
    url = f'{NOMINATIM_URL}?{params}'
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get('address', {})
    except Exception as e:
        print(f'  [!] Nominatim error lat={lat} lon={lon}: {e}')
        return {}


def format_address(addr, city_ref='Санкт-Петербург'):
    """Форматирует адрес: улица + номер [+ город если не СПб]."""
    road = addr.get('road') or addr.get('pedestrian') or addr.get('path') or ''
    house = addr.get('house_number', '')
    city = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('municipality', '')
    suburb = addr.get('suburb') or addr.get('city_district', '')

    parts = []
    if road:
        parts.append(road + (f', {house}' if house else ''))
    elif suburb:
        parts.append(suburb)

    # Добавляем город только если это не Санкт-Петербург
    if city and city.lower() not in ('санкт-петербург', 'saint petersburg', 'st. petersburg'):
        parts.append(city)

    return ', '.join(parts) if parts else ''


def main():
    print('=' * 55)
    print('  Обогащение адресов АЗС через Nominatim')
    print('=' * 55)

    with open('stations.json', 'r', encoding='utf-8') as f:
        stations = json.load(f)

    total = len(stations)
    missing = [s for s in stations if not s.get('address')]
    print(f'Всего станций: {total}')
    print(f'Без адреса:    {len(missing)}')
    print()

    if not missing:
        print('Все адреса уже заполнены!')
        return

    filled = 0
    failed = 0

    for i, station in enumerate(missing, 1):
        lat, lon = station['lat'], station['lon']
        name = station.get('name', '?')
        print(f'[{i}/{len(missing)}] {name} ({lat:.4f}, {lon:.4f})', end=' ... ', flush=True)

        addr_data = reverse_geocode(lat, lon)
        address = format_address(addr_data)

        if address:
            station['address'] = address
            print(f'OK: {address}')
            filled += 1
        else:
            print('нет данных')
            failed += 1

        # Сохраняем промежуточный результат каждые 50 станций
        if i % 50 == 0:
            with open('stations.json', 'w', encoding='utf-8') as f:
                json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))
            print(f'  [Сохранено {i} из {len(missing)}]')

        time.sleep(DELAY)

    # Финальное сохранение
    with open('stations.json', 'w', encoding='utf-8') as f:
        json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))

    print()
    print('=' * 55)
    print(f'Готово! Заполнено адресов: {filled}')
    print(f'Не удалось получить:       {failed}')
    print(f'stations.json обновлён')
    print('=' * 55)


if __name__ == '__main__':
    main()

"""
fill_addresses.py — Заполняет пустые адреса в stations.json через Nominatim (бесплатно).
Делает reverse geocoding по координатам АЗС без адреса.
Лимит: 1 запрос/сек (требование Nominatim).
Запуск: py fill_addresses.py
"""

import json, time, sys
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/reverse'
HEADERS = {'User-Agent': 'AZSPiter/1.0 cadillacslava@gmail.com'}

def reverse_geocode(lat, lon):
    params = urllib.parse.urlencode({
        'lat': lat, 'lon': lon,
        'format': 'json',
        'addressdetails': 1,
        'zoom': 18,
        'accept-language': 'ru',
    })
    req = urllib.request.Request(f'{NOMINATIM_URL}?{params}', headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        addr = data.get('address', {})
        road = addr.get('road') or addr.get('pedestrian') or addr.get('footway') or ''
        house = addr.get('house_number', '')
        city = (addr.get('city') or addr.get('town') or addr.get('village') or
                addr.get('suburb') or addr.get('county') or '')
        spb = {'санкт-петербург', 'saint petersburg', 'спб'}
        city_part = city if city.lower() not in spb else ''
        parts = []
        if road:
            parts.append(road + (f', {house}' if house else ''))
        elif house:
            parts.append(house)
        if city_part:
            parts.append(city_part)
        return ', '.join(parts)
    except Exception as e:
        print(f'  Ошибка: {e}')
        return ''

with open('stations.json', encoding='utf-8') as f:
    stations = json.load(f)

missing = [s for s in stations if not s.get('address')]
total = len(missing)
print(f'Станций без адреса: {total} из {len(stations)}')
print(f'Примерное время: {total} сек (~{total//60} мин)\n')

updated = 0
for i, s in enumerate(missing, 1):
    lat, lon = s.get('lat'), s.get('lon')
    if not lat or not lon:
        continue
    addr = reverse_geocode(lat, lon)
    if addr:
        s['address'] = addr
        updated += 1
        print(f'[{i}/{total}] {s.get("brand","?")} → {addr}')
    else:
        print(f'[{i}/{total}] {s.get("brand","?")} — адрес не найден')
    time.sleep(1.1)  # Nominatim: max 1 req/sec

with open('stations.json', 'w', encoding='utf-8') as f:
    json.dump(stations, f, ensure_ascii=False, indent=2)

print(f'\nГотово. Обновлено адресов: {updated}/{total}')

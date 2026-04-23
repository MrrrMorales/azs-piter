"""
save_stations.py — Скачивает все АЗС Питера и Ленобласти по границам региона.
Запуск: py save_stations.py
"""

import json, sys
import urllib.request
import urllib.parse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 55)
print("  Скачиваем все АЗС Питера и Ленобласти...")
print("=" * 55)

# Запрос по официальным границам СПб + Ленобласти (исключает Финляндию)
query = """
[out:json][timeout:120];
(
  area["name"="Санкт-Петербург"]["admin_level"="4"]->.spb;
  area["name"="Ленинградская область"]["admin_level"="4"]->.lo;
  node["amenity"="fuel"](area.spb);
  way["amenity"="fuel"](area.spb);
  node["amenity"="fuel"](area.lo);
  way["amenity"="fuel"](area.lo);
);
out center tags;
""".strip()

url = "https://overpass-api.de/api/interpreter"
data = ("data=" + urllib.parse.quote(query)).encode()

req = urllib.request.Request(url, data=data, headers={
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "AZS-Piter/1.0"
})

print("Запрос к OpenStreetMap... (30-90 секунд)")

try:
    with urllib.request.urlopen(req, timeout=150) as resp:
        raw = json.loads(resp.read())
except Exception as e:
    print(f"Ошибка: {e}")
    sys.exit(1)

# Ключевые слова чисто-газовых станций (АГЗС, LPG, метан) — исключаем
GAS_ONLY = {'агзс', 'автогаз', 'газозаправочная', 'lpg', 'метан', 'cng', 'пропан', 'gnv', 'росгаз', 'агнс', 'агнкс'}

def is_gas_only(tags):
    name = (tags.get('name') or tags.get('brand') or '').lower()
    # Исключаем если название явно газовое
    if any(kw in name for kw in GAS_ONLY):
        return True
    # Исключаем если тег fuel:lpg=yes и нет бензиновых тегов
    has_petrol = any(tags.get(f'fuel:octane_{n}') for n in ['92','95','98','100'])
    has_diesel = tags.get('fuel:diesel') or tags.get('fuel:HGV_diesel')
    has_lpg_only = tags.get('fuel:lpg') == 'yes' and not has_petrol and not has_diesel
    return has_lpg_only

def get_fuels(tags):
    fuels = []
    if tags.get('fuel:octane_92') == 'yes': fuels.append('92')
    if tags.get('fuel:octane_95') == 'yes': fuels.append('95')
    if tags.get('fuel:octane_98') == 'yes' or tags.get('fuel:octane_100') == 'yes': fuels.append('100')
    if tags.get('fuel:diesel') == 'yes' or tags.get('fuel:HGV_diesel') == 'yes': fuels.append('dt')
    return fuels

def get_name(tags):
    brand = tags.get('brand') or ''
    name  = tags.get('name')  or ''
    operator = tags.get('operator') or ''
    # Используем name если оно содержит что-то сверх бренда (уникальное название)
    if name and brand and name.lower().strip() != brand.lower().strip():
        return name
    return brand or name or operator or 'АЗС'


def get_address(tags):
    street  = tags.get('addr:street', '')
    house   = tags.get('addr:housenumber', '')
    city    = tags.get('addr:city', '') or tags.get('addr:place', '')
    # addr:city включаем только если это не СПб (чтобы не засорять карточки)
    spb_variants = {'санкт-петербург', 'saint petersburg', 'st. petersburg', 'спб', 'с.-петербург'}
    city_part = city if city.lower() not in spb_variants else ''

    parts = []
    if street:
        parts.append(street + (f', {house}' if house else ''))
    elif house:
        parts.append(house)
    if city_part:
        parts.append(city_part)
    return ', '.join(parts)


seen_ids = set()
stations = []
for el in raw['elements']:
    eid = el['id']
    if eid in seen_ids:
        continue
    seen_ids.add(eid)

    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lon = el.get('lon') or (el.get('center') or {}).get('lon')
    if not lat or not lon:
        continue

    tags = el.get('tags', {})
    if is_gas_only(tags):
        continue

    fuels = get_fuels(tags)
    station = {
        'id':   eid,
        'type': el['type'],
        'lat':  lat,
        'lon':  lon,
        'name':   get_name(tags),
        'brand':  tags.get('brand') or tags.get('operator') or '',
        'address': get_address(tags),
        'opening_hours': tags.get('opening_hours', ''),
        'phone': tags.get('phone') or tags.get('contact:phone') or '',
    }
    if fuels:
        station['fuels'] = fuels
    stations.append(station)

with open('stations.json', 'w', encoding='utf-8') as f:
    json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))

print(f"\nГотово! Сохранено {len(stations)} АЗС в stations.json")

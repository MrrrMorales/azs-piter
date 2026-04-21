"""
save_stations.py — Один раз скачивает все АЗС Питера и Ленобласти
и сохраняет в stations.json.

Запуск: py save_stations.py
Потом закинь stations.json на GitHub в репозиторий azs-piter.
"""

import json
import urllib.request
import urllib.parse

print("=" * 55)
print("  Скачиваем все АЗС Питера и Ленобласти...")
print("=" * 55)

query = """
[out:json][timeout:90];
(
  node["amenity"="fuel"](58.5,27.5,61.5,33.5);
  way["amenity"="fuel"](58.5,27.5,61.5,33.5);
);
out center tags;
""".strip()

url = "https://overpass-api.de/api/interpreter"
data = ("data=" + urllib.parse.quote(query)).encode()

req = urllib.request.Request(url, data=data, headers={
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "AZS-Piter/1.0"
})

print("Запрос к OpenStreetMap... (может занять 30-60 секунд)")

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read())
except Exception as e:
    print(f"Ошибка: {e}")
    exit(1)

def get_name(tags):
    return tags.get("brand") or tags.get("name") or tags.get("operator") or "АЗС"

stations = []
for el in raw["elements"]:
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    if not lat or not lon:
        continue
    tags = el.get("tags", {})
    stations.append({
        "id": el["id"],
        "type": el["type"],
        "lat": lat,
        "lon": lon,
        "name": get_name(tags),
        "brand": tags.get("brand") or tags.get("operator") or "",
        "address": " ".join(filter(None, [
            tags.get("addr:street", ""),
            tags.get("addr:housenumber", "")
        ])).strip(),
        "opening_hours": tags.get("opening_hours", ""),
        "phone": tags.get("phone") or tags.get("contact:phone") or "",
    })

with open("stations.json", "w", encoding="utf-8") as f:
    json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))

print(f"\n✅ Готово! Сохранено {len(stations)} заправок в stations.json")
print(f"   Теперь загрузи stations.json на GitHub в репозиторий azs-piter")

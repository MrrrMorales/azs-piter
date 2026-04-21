"""
parser.py — Парсер цен на топливо для АЗС Санкт-Петербурга и Ленобласти
Запуск: python parser.py
Результат сохраняется в prices.json рядом с этим файлом.

Установка зависимостей (один раз):
    pip install requests beautifulsoup4 lxml
"""

import json
import re
import time
import datetime
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def safe_get(url, **kwargs):
    try:
        r = SESSION.get(url, timeout=15, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  [!] GET {url} → {e}")
        return None


def parse_price(text):
    """Вытащить число из строки вида '56,40 ₽' или '56.4'"""
    if not text:
        return None
    text = str(text).replace('\xa0', '').replace(' ', '').replace(',', '.')
    m = re.search(r'\d+\.\d+|\d+', text)
    return float(m.group()) if m else None


# ─────────────────────────────────────────────────────────────────
# ЛУКОЙЛ
# https://spb.lukoil.ru/main/fuel/prices
# ─────────────────────────────────────────────────────────────────
def parse_lukoil():
    print("[Лукойл] Запрос...")
    url = "https://spb.lukoil.ru/main/fuel/prices"
    r = safe_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    prices = {}
    # Ищем таблицу с ценами
    for row in soup.select("table tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if not cells:
            continue
        name = cells[0].lower()
        val = parse_price(cells[1]) if len(cells) > 1 else None
        if "экто-92" in name or "регуляр-92" in name or ("92" in name and "95" not in name):
            prices["92"] = val
        elif "экто-95" in name or "премиум-95" in name or "95" in name:
            prices["95"] = val
        elif "экто-100" in name or "100" in name:
            prices["100"] = val
        elif "дт" in name or "diesel" in name or "евро" in name:
            prices["dt"] = val
    if prices:
        print(f"  → Лукойл: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# ГАЗПРОМ НЕФТЬ
# https://www.gpnbonus.ru/ceny/
# ─────────────────────────────────────────────────────────────────
def parse_gazprom():
    print("[Газпром] Запрос...")
    url = "https://www.gpnbonus.ru/ceny/"
    r = safe_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    prices = {}
    # Ищем секцию Санкт-Петербург
    spb_section = None
    for el in soup.find_all(string=re.compile(r"Санкт-Петербург|Петербург|Ленинград", re.I)):
        spb_section = el.find_parent(["div", "section", "tr"])
        if spb_section:
            break

    target = spb_section or soup  # если не нашли — берём всю страницу

    for row in target.select("tr") if hasattr(target, 'select') else soup.select("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        name = cells[0].lower()
        val = parse_price(cells[-1])
        if "g-92" in name or "аи-92" in name or ("92" in name and "95" not in name and "100" not in name):
            prices["92"] = val
        elif "g-95" in name or "аи-95" in name or "95" in name:
            prices["95"] = val
        elif "100" in name:
            prices["100"] = val
        elif "дт" in name or "diesel" in name or "g-дт" in name:
            prices["dt"] = val
    if prices:
        print(f"  → Газпром: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# РОСНЕФТЬ
# https://www.rosneft.ru/retail/prices/
# ─────────────────────────────────────────────────────────────────
def parse_rosneft():
    print("[Роснефть] Запрос...")
    url = "https://www.rosneft.ru/retail/prices/"
    r = safe_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    prices = {}

    spb_block = None
    for el in soup.find_all(string=re.compile(r"Санкт-Петербург|Петербург", re.I)):
        parent = el.find_parent(["tr", "div", "li"])
        if parent:
            # попробуем найти соседние строки с ценами
            spb_block = parent.find_parent("table") or parent
            break

    source = spb_block or soup
    for row in source.select("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        name = cells[0].lower()
        val = parse_price(cells[1])
        if re.search(r'\b92\b', name) and "95" not in name:
            prices.setdefault("92", val)
        elif re.search(r'\b95\b', name):
            prices.setdefault("95", val)
        elif re.search(r'\b100\b', name):
            prices.setdefault("100", val)
        elif re.search(r'дт|диз|diesel', name):
            prices.setdefault("dt", val)
    if prices:
        print(f"  → Роснефть: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# ПТКТНК (ПТК — петербургская сеть)
# https://ptk.ru/prices/
# ─────────────────────────────────────────────────────────────────
def parse_ptk():
    print("[ПТК] Запрос...")
    url = "https://ptk.ru/prices/"
    r = safe_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    prices = {}
    for row in soup.select("tr, .price-row"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th", "div"])]
        if len(cells) < 2:
            continue
        name = cells[0].lower()
        val = parse_price(cells[1])
        if "92" in name and "95" not in name:
            prices["92"] = val
        elif "95" in name:
            prices["95"] = val
        elif "100" in name:
            prices["100"] = val
        elif "дт" in name or "дизель" in name:
            prices["dt"] = val
    if prices:
        print(f"  → ПТК: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# NESTE
# https://neste.ru/ceny-na-toplivo/
# ─────────────────────────────────────────────────────────────────
def parse_neste():
    print("[Neste] Запрос...")
    url = "https://neste.ru/ceny-na-toplivo/"
    r = safe_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    prices = {}
    for row in soup.select("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        name = cells[0].lower()
        val = parse_price(cells[-1])
        if "92" in name and "95" not in name:
            prices["92"] = val
        elif "95" in name:
            prices["95"] = val
        elif "100" in name:
            prices["100"] = val
        elif "дт" in name or "diesel" in name or "pro diesel" in name:
            prices["dt"] = val
    if prices:
        print(f"  → Neste: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# ФАЭТОН
# https://faeton.ru/prices/
# ─────────────────────────────────────────────────────────────────
def parse_faeton():
    print("[Фаэтон] Запрос...")
    url = "https://faeton.ru/prices/"
    r = safe_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, "lxml")
    prices = {}
    for row in soup.select("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        name = cells[0].lower()
        val = parse_price(cells[1])
        if "92" in name and "95" not in name:
            prices["92"] = val
        elif "95" in name:
            prices["95"] = val
        elif "100" in name:
            prices["100"] = val
        elif "дт" in name or "дизель" in name:
            prices["dt"] = val
    if prices:
        print(f"  → Фаэтон: {prices}")
    return prices or None


# ─────────────────────────────────────────────────────────────────
# СБОРКА И СОХРАНЕНИЕ
# ─────────────────────────────────────────────────────────────────

PARSERS = {
    "лукойл":   parse_lukoil,
    "газпромнефть": parse_gazprom,
    "роснефть": parse_rosneft,
    "птк":      parse_ptk,
    "neste":    parse_neste,
    "фаэтон":   parse_faeton,
}

# Алиасы: какие строки OSM name/brand → ключ словаря выше
BRAND_ALIASES = {
    "лукойл": "лукойл",
    "lukoil": "лукойл",
    "газпром": "газпромнефть",
    "gazpromneft": "газпромнефть",
    "газпромнефть": "газпромнефть",
    "роснефть": "роснефть",
    "rosneft": "роснефть",
    "птк": "птк",
    "neste": "neste",
    "несте": "neste",
    "фаэтон": "фаэтон",
    "faeton": "фаэтон",
}


def normalize_brand(name: str) -> str | None:
    name = (name or "").lower().strip()
    for key, canonical in BRAND_ALIASES.items():
        if key in name:
            return canonical
    return None


def run():
    print("=" * 50)
    print("Парсер цен на топливо — Питер и Ленобласть")
    print("=" * 50)

    results = {}
    for brand, fn in PARSERS.items():
        prices = fn()
        if prices:
            results[brand] = prices
        time.sleep(1.5)  # пауза между запросами

    output = {
        "updated": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "prices": results,
        "aliases": BRAND_ALIASES,
    }

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 50)
    print(f"✅ Готово! Сохранено в prices.json")
    print(f"   Брендов с ценами: {len(results)}")
    for b, p in results.items():
        print(f"   {b}: {p}")
    print("=" * 50)


if __name__ == "__main__":
    run()

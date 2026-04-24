"""
brands.py — единый реестр брендов АЗС для СПб / Ленобласти.

Импортируется: parser.py, enrich_brands.py
Структура записи: (aliases_list, canonical_key, display_name)
  - canonical_key — нижний регистр, ключ в prices.json и station_prices.json
  - display_name  — красивое написание для UI и stations.json
"""

BRANDS = [
    (['лукойл', 'lukoil'],
        'лукойл', 'Лукойл'),
    (['газпромнефть', 'газпром нефть', 'газпром нефт', 'газпром', 'gpn', 'gazpromneft'],
        'газпромнефть', 'Газпромнефть'),
    (['роснефть', 'rosneft'],
        'роснефть', 'Роснефть'),
    (['птк', 'ptk', 'петербургская топливная', 'пикалёвская топливная'],
        'птк', 'ПТК'),
    (['neste', 'несте'],
        'neste', 'Neste'),
    (['татнефть', 'tatneft'],
        'татнефть', 'Татнефть'),
    (['teboil', 'тебойл'],
        'teboil', 'Teboil'),
    (['shell'],
        'shell', 'Shell'),
    (['авро', 'avro'],
        'авро', 'Авро'),
    (['трасса', 'trassa'],
        'трасса', 'Трасса'),
    (['сургутнефтегаз', 'сургут', 'кинеф', 'kinef', 'киришиавтосервис', 'kirishiavtoservis'],
        'сургутнефтегаз', 'Сургутнефтегаз'),
    (['esso'],
        'esso', 'Esso'),
    (['nord point', 'норд поинт'],
        'nord point', 'Nord Point'),
    (['ойлпласт', 'oilplast'],
        'ойлпласт', 'Ойлпласт'),
    (['nord-line', 'nordline', 'nord line', 'норд-лайн', 'норд лайн'],
        'nord-line', 'Nord-Line'),
    (['линос', 'linos'],
        'линос', 'Линос'),
    (['aris'],
        'aris', 'Aris'),
    (['китэк', 'kitek'],
        'китэк', 'КиТЭК'),
    (['втк', 'выборгская топливная'],
        'втк', 'ВТК'),
    (['санга', 'sanga'],
        'санга', 'Санга'),
    (['фаэтон', 'фаэтон-аэро', 'faeton'],
        'фаэтон', 'Фаэтон'),
    (['shelf'],
        'shelf', 'Shelf'),
    (['опти', 'opti'],
        'опти', 'Опти'),
    (['bp', 'бп'],
        'bp', 'BP'),
    (['apn'],
        'apn', 'APN'),
    (['нева-ойл', 'неваойл'],
        'нева-ойл', 'Нева-ойл'),
    (['топсис'],
        'топсис', 'ТопСис'),
    (['oil-store', 'oil store', 'ойл стор'],
        'oil-store', 'Oil Store'),
]

# alias (lowercase) → canonical key
ALIASES: dict = {}
# canonical key → display name
DISPLAY: dict = {}

for _aliases, _canonical, _display in BRANDS:
    DISPLAY[_canonical] = _display
    for _alias in _aliases:
        ALIASES[_alias] = _canonical


def normalize(raw: str):
    """Привести raw к каноническому ключу (нижний регистр). Возвращает None если бренд неизвестен."""
    if not raw:
        return None
    n = raw.lower().strip()
    if n in ALIASES:
        return ALIASES[n]
    for alias, canonical in ALIASES.items():
        if alias in n:
            return canonical
    return None


def display_name(raw: str):
    """Привести raw к красивому названию бренда. Возвращает None если бренд неизвестен."""
    canonical = normalize(raw)
    return DISPLAY.get(canonical) if canonical else None

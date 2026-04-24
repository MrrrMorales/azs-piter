"""
fix_brands.py — Нормализация брендов и названий нецепных АЗС в stations.json.

Что делает:
  1. Заполняет пустые поля brand по названию станции
  2. Нормализует написание имён (АВРО→Авро, КиришиАвтоСервис→Киришиавтосервис и т.д.)
  3. Заменяет brand='Сургутнефтегаз' → 'Киришиавтосервис' для Киришиавтосервис-станций
  4. Исправляет Газпром-петролеум станции без brand → brand='Газпромнефть'
  5. Удаляет закрытые/несуществующие АЗС (REMOVE_IDS)

Запуск: python fix_brands.py [--dry-run]
"""

import json, sys, argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ── имя (любой регистр) → нормальное написание ──────────────────────────────
NAME_NORMALIZE = {
    'авро':                'Авро',
    'nord point':          'Nord Point',
    'nord point':          'Nord Point',
    'китэк':               'КиТЭК',
    'киришиавтосервис':    'Киришиавтосервис',
    'киришиавтомаркет':    'КиришиАвтоМаркет',
}

# ── brand пустой + name содержит ключ → ставим brand ────────────────────────
BRAND_BY_NAME = {
    'авро':                        'Авро',
    'nord point':                  'Nord Point',
    'aris':                        'Aris',
    'китэк':                       'КиТЭК',
    'линос':                       'Линос',
    'фаэтон':                      'Фаэтон',
    'санга':                       'Санга',
    'shelf':                       'Shelf',
    'опти':                        'Опти',
    'apn':                         'APN',
    'киришиавтосервис':            'Сургутнефтегаз',
    'втк':                         'ВТК',
    'выборгская топливная':        'Выборгская топливная компания',
    'петербургская топливная':     'Петербургская топливная компания',
}

# ── прямая замена brand (независимо от name) ─────────────────────────────────
BRAND_DIRECT_REPLACE = {
    'Киришиавтосервис':    'Сургутнефтегаз',
    'ООО "Киришиавтосервис"': 'Сургутнефтегаз',
    'ООО Киришиавтосервис': 'Сургутнефтегаз',
    'КиришиАвтоСервис':    'Сургутнефтегаз',
    'Кинеф':               'Сургутнефтегаз',
    'ООО "КИНЕФ"':         'Сургутнефтегаз',
    'СургутНефтеГаз':      'Сургутнефтегаз',
    'Сургутнефтегазбанк':  'Сургутнефтегаз',
}

# ── конкретные замены brand ──────────────────────────────────────────────────
# (name_lower_contains, old_brand) → new_brand
BRAND_REPLACE = [
    # Китэк — нормализуем капитализацию
    ('китэк', 'Китэк', 'КиТЭК'),
]

# ── закрытые / несуществующие АЗС — удалить из карты ───────────────────────
# id → причина (строка для лога)
REMOVE_IDS = {
    # ПТК в Любани (Тосненский р-н) — закрыта, Яндекс: «Больше не работает» (2026-04)
    286134744: 'ПТК Любань — закрыта',
}

# ── специальные ID-переопределения ───────────────────────────────────────────
# id → {поле: значение}  (применяются после общих правил)
ID_OVERRIDES = {
    # ООО "Линос" с brand='ООО "Милена"' — это тот же Линос
    537637953: {'brand': 'Линос'},
    # OSM ошибочно помечает эту станцию как ПТК-Сервис АЗС №96,
    # но по факту там Роснефть (Яндекс Карты, 2026-04)
    286134741: {'brand': 'Роснефть', 'name': 'Роснефть'},
    # АЗС Кириши / Oil-store, просп. Энгельса 163с3 — в OSM нет бренда (2026-04)
    4350428000: {'brand': 'Oil-store', 'name': 'Oil-store'},
}


def run(dry_run: bool):
    with open('stations.json', encoding='utf-8') as f:
        stations = json.load(f)

    total_changes = 0
    change_log = []

    # Удаляем закрытые станции
    removed = [s for s in stations if s['id'] in REMOVE_IDS]
    for s in removed:
        reason = REMOVE_IDS[s['id']]
        change_log.append(f'  #{s["id"]} [REMOVE] {reason}  | {s.get("address", "")}')
        total_changes += 1
    if not dry_run:
        stations = [s for s in stations if s['id'] not in REMOVE_IDS]

    for s in stations:
        sid = s['id']
        name  = (s.get('name')  or '').strip()
        brand = (s.get('brand') or '').strip()
        name_l  = name.lower()
        brand_l = brand.lower()

        def set_field(field, new_val, reason):
            nonlocal total_changes
            old_val = s.get(field, '')
            if old_val == new_val:
                return
            change_log.append(f'  #{sid} [{reason}] {field}: {old_val!r} → {new_val!r}  | {s.get("address","")}')
            total_changes += 1
            if not dry_run:
                s[field] = new_val

        # 1a. Прямая замена brand (до всего остального)
        if brand in BRAND_DIRECT_REPLACE:
            set_field('brand', BRAND_DIRECT_REPLACE[brand], 'brand direct replace')
            brand   = BRAND_DIRECT_REPLACE[brand]
            brand_l = brand.lower()

        # 1. ID-переопределения (приоритет)
        if sid in ID_OVERRIDES:
            for field, new_val in ID_OVERRIDES[sid].items():
                set_field(field, new_val, f'ID override')
            continue

        # 2. Нормализация имени
        for key, canonical in NAME_NORMALIZE.items():
            if name_l == key and name != canonical:
                set_field('name', canonical, 'name normalize')
                name   = canonical
                name_l = canonical.lower()
                break

        # 3. Замена brand по точным правилам (name+old_brand)
        for name_key, old_brand, new_brand in BRAND_REPLACE:
            if name_key in name_l and brand == old_brand:
                set_field('brand', new_brand, f'brand replace')
                brand   = new_brand
                brand_l = new_brand.lower()
                break

        # 4. Заполнение пустого brand по имени
        if not brand:
            for key, canonical_brand in BRAND_BY_NAME.items():
                if key in name_l:
                    set_field('brand', canonical_brand, 'brand fill')
                    brand   = canonical_brand
                    brand_l = canonical_brand.lower()
                    break

        # 5. Газпром (чистый petrol) без brand → Газпромнефть
        if name_l == 'газпром' and not brand:
            set_field('brand', 'Газпромнефть', 'газпром→газпромнефть')

    # ── отчёт ────────────────────────────────────────────────────────────────
    print('=' * 60)
    print(f'  fix_brands.py — {"DRY RUN" if dry_run else "ПРИМЕНЯЮ ИЗМЕНЕНИЯ"}')
    print('=' * 60)
    for line in change_log:
        print(line)
    print()
    print(f'Итого изменений: {total_changes}')

    if not dry_run and total_changes > 0:
        with open('stations.json', 'w', encoding='utf-8') as f:
            json.dump(stations, f, ensure_ascii=False, separators=(',', ':'))
        print('stations.json сохранён.')
    elif dry_run:
        print('(dry-run — stations.json НЕ изменён)')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true', help='Показать изменения без сохранения')
    args = p.parse_args()
    run(dry_run=args.dry_run)

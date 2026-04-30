"""
analyze_lukoil_raw.py — анализирует lukoil_raw.json после сессии перехвата.

Запуск: python analyze_lukoil_raw.py

Выводит:
  - Все уникальные хосты и URL
  - Запросы, похожие на цены (price/fuel/azs)
  - Bearer-токен если найден
  - Предлагает лучший эндпоинт для fetch_lukoil_api()
"""

import json
import re
from pathlib import Path

RAW_FILE = Path(__file__).parent / 'lukoil_raw.json'
PRICE_HINTS = re.compile(r'price|fuel|azs|station|цен|топлив|заправ', re.I)


def main():
    if not RAW_FILE.exists():
        print(f'[!] {RAW_FILE} не найден.')
        print('    Сначала запусти mitmweb + run_lukoil_intercept.bat')
        return

    with open(RAW_FILE, encoding='utf-8') as f:
        entries = json.load(f)

    print(f'Всего перехвачено запросов: {len(entries)}\n')

    # Уникальные хосты
    hosts = sorted({re.match(r'https?://([^/]+)', e['url']).group(1)
                    for e in entries if re.match(r'https?://([^/]+)', e['url'])})
    print('=== Уникальные хосты ===')
    for h in hosts:
        print(f'  {h}')

    # Bearer токен
    print('\n=== Bearer токены ===')
    seen_tokens = set()
    for e in entries:
        auth = e.get('req_headers', {}).get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:][:80]
            if token not in seen_tokens:
                seen_tokens.add(token)
                print(f'  URL: {e["url"]}')
                print(f'  Token: {auth[:120]}')
                print()

    if not seen_tokens:
        print('  (не найдено — возможно приложение не требует авторизации)')

    # Запросы с ценами
    print('\n=== Запросы с ценами/топливом ===')
    price_entries = [e for e in entries if PRICE_HINTS.search(e['url'])]
    if not price_entries:
        # Ищем в теле ответа
        price_entries = [
            e for e in entries
            if isinstance(e.get('resp_body'), dict) and
               PRICE_HINTS.search(json.dumps(e['resp_body'], ensure_ascii=False))
        ]

    if price_entries:
        for e in price_entries:
            print(f"\n  [{e['ts']}] {e['method']} {e['url']}")
            print(f"  Status: {e['status']}")
            body = e.get('resp_body')
            if isinstance(body, dict):
                print(f"  Response (first 500 chars):")
                print('  ' + json.dumps(body, ensure_ascii=False)[:500])
    else:
        print('  Не найдено. Попробуй открыть несколько АЗС в приложении.')

    # Все URL списком
    print('\n=== Все URL ===')
    seen_urls = set()
    for e in entries:
        u = e['url']
        if u not in seen_urls:
            seen_urls.add(u)
            print(f"  [{e['method']}] {u}")

    print('\n=== Готово ===')
    print('Посмотри запросы выше и найди эндпоинт с ценами топлива.')
    print('Скопируй URL и заголовки → передай мне → напишу fetch_lukoil_api()')


if __name__ == '__main__':
    main()

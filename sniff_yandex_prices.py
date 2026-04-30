"""
sniff_yandex_prices.py — перехватывает API Яндекс Карт с ценами на топливо.

Запуск: python sniff_yandex_prices.py
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import json
import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT = Path(__file__).parent / 'yandex_traffic.json'

HOSTS = ['yandex.ru', 'yandex.net', 'zapravki.yandex.ru', 'tanker.s3.yandex.net', 'zapravki-static.s3.yandex.net']
PRICE_RE = re.compile(r'price|fuel|azs|gasstation|petrol|цена|топлив|заправ|нефт', re.I)

captured = []


async def main():
    print("Запускаю браузер...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            locale='ru-RU',
            geolocation={'latitude': 59.9386, 'longitude': 30.3141},
            permissions=['geolocation'],
        )
        page = await context.new_page()

        async def on_response(response):
            url = response.url
            if not any(h in url for h in HOSTS):
                return
            # Берём только JSON/text
            ct = response.headers.get('content-type', '')
            if 'json' not in ct and 'text' not in ct and 'javascript' not in ct:
                return
            try:
                body = await response.text()
            except Exception:
                body = ''

            # Пишем всё от yandex


            entry = {
                'url': url,
                'method': response.request.method,
                'status': response.status,
                'req_headers': {k: v for k, v in response.request.headers.items()
                                if k.lower() in ('authorization', 'cookie', 'x-session-id',
                                                  'x-csrf-token', 'origin', 'referer')},
                'body': body[:50000],
            }
            captured.append(entry)
            OUTPUT.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"  [{response.status}] {url[:110]}")
            if PRICE_RE.search(body[:200]):
                print(f"    >>> ЦЕНЫ В ТЕЛЕ: {body[:200]}")

        page.on('response', on_response)

        # Открываем поиск АЗС в СПб
        url = 'https://zapravki.yandex.ru/stations'
        print(f"Открываю: {url}")
        await page.goto(url, timeout=30000)

        print()
        print("=" * 60)
        print("ДЕЙСТВИЯ:")
        print("  1. Дождись загрузки карты с маркерами АЗС")
        print("  2. Нажми на несколько маркеров АЗС — должны появиться цены")
        print("  3. Если видишь список АЗС слева — нажимай на каждую")
        print("  4. Повтори для 5-10 разных станций")
        print("  5. Закрой браузер")
        print("=" * 60)
        print(f"\nТрафик: {OUTPUT}")
        print("Жду...\n")

        await page.wait_for_event('close', timeout=300000)
        await browser.close()

    print(f"\nГотово! Перехвачено {len(captured)} интересных запросов")
    _analyze()


def _analyze():
    if not OUTPUT.exists():
        return
    data = json.loads(OUTPUT.read_text(encoding='utf-8'))
    print("\n=== Запросы с ценами ===")
    for e in data:
        body = e.get('body', '')
        if PRICE_RE.search(body[:300]):
            print(f"\n  [{e['status']}] {e['method']} {e['url'][:100]}")
            print(f"  Тело (первые 400 символов):")
            print(f"  {body[:400]}")


if __name__ == '__main__':
    asyncio.run(main())

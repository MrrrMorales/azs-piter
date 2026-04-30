"""
sniff_lukoil_web.py — перехватывает XHR/fetch запросы на auto.lukoil.ru
и сохраняет все API-вызовы в lukoil_web_traffic.json

Запуск: python sniff_lukoil_web.py
"""

import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT = Path(__file__).parent / 'lukoil_web_traffic.json'
PRICE_HINTS = {'price', 'fuel', 'station', 'azs', 'petroleum', 'цена', 'топлив', 'заправ', 'петрол'}

captured = []


def is_interesting(url: str, body: str) -> bool:
    u = url.lower()
    b = body.lower() if body else ''
    return any(h in u or h in b for h in PRICE_HINTS)


async def main():
    print("Запускаю браузер...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        async def on_response(response):
            url = response.url
            if not ('lukoil' in url or 'licard' in url):
                return
            try:
                ct = response.headers.get('content-type', '')
                if 'json' in ct or 'javascript' in ct:
                    body = await response.text()
                else:
                    body = ''
            except Exception:
                body = ''

            entry = {
                'url': url,
                'method': response.request.method,
                'status': response.status,
                'content_type': response.headers.get('content-type', ''),
                'req_headers': dict(response.request.headers),
                'body_preview': body[:2000] if body else '',
            }
            captured.append(entry)
            OUTPUT.write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding='utf-8')

            flag = '*** ЦЕНЫ ***' if is_interesting(url, body) else ''
            print(f"  [{response.status}] {response.request.method} {url[:100]} {flag}")

        page.on('response', on_response)

        print("Открываю auto.lukoil.ru...")
        await page.goto('https://auto.lukoil.ru/ru/ProductsAndServices/PetrolStations', timeout=30000)

        print("\n" + "="*60)
        print("ДЕЙСТВИЯ:")
        print("  1. Дождись загрузки карты")
        print("  2. Нажми на несколько АЗС в Санкт-Петербурге")
        print("  3. Посмотри цены в popup-окне станции")
        print("  4. Закрой браузер когда наберёшь 5-10 станций")
        print("="*60)
        print(f"\nТрафик пишется в: {OUTPUT}")
        print("Жду пока закроешь браузер...\n")

        await page.wait_for_event('close', timeout=300000)
        await browser.close()

    print(f"\nГотово! Перехвачено {len(captured)} запросов")
    print(f"Запусти: python analyze_lukoil_raw.py")


if __name__ == '__main__':
    asyncio.run(main())

import sys, io, asyncio, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])
        ctx = await browser.new_context(locale='ru-RU')
        page = await ctx.new_page()

        found_fuel = []

        async def on_response(response):
            if '/maps/api/search' not in response.url:
                return
            try:
                text = await response.text()
                if 'fuelInfo' in text:
                    print(f'\n*** fuelInfo НАЙДЕН! ***')
                    print(f'URL: {response.url[:100]}')
                    # Вытащим первый fuelInfo
                    data = json.loads(text)
                    items = data.get('data', {}).get('items', [])
                    for item in items:
                        fi = item.get('fuelInfo')
                        if fi:
                            print(f'Станция: {item.get("title")} | {item.get("address")}')
                            print(f'fuelInfo: {json.dumps(fi, ensure_ascii=False)[:500]}')
                            found_fuel.append(item)
                            break
                else:
                    # Ищем любые цены
                    items = json.loads(text).get('data', {}).get('items', [])
                    if items:
                        print(f'  [{len(items)} items] ключи первого: {list(items[0].keys())[:8]}')
            except:
                pass

        page.on('response', on_response)

        from urllib.parse import quote
        url = f'https://yandex.ru/maps/?text={quote("ЛУКОЙЛ АЗС Санкт-Петербург")}&type=biz'
        print(f'Открываю: {url}')
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(15)

        if not found_fuel:
            print('\nfuelInfo НЕ найден в ответах.')
            print('Яндекс изменил формат API.')

        await browser.close()

asyncio.run(main())

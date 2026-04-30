import requests, re, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

r = requests.get('https://zapravki.yandex.ru/stations',
    headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)

text = r.text
print('Page size:', len(text))

scripts = re.findall(r'src="(https?://[^"]+\.js[^"]*)"', text)
print('\nJS files:')
for s in scripts:
    print(' ', s)

# Search for price-related keywords in page
for kw in ['price', 'fuel_price', 'getPrice', 'station_price', '/api/']:
    idx = text.lower().find(kw.lower())
    if idx >= 0:
        print(f'\n[{kw}] context: {text[max(0,idx-100):idx+300]}')

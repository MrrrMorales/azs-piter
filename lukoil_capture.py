"""
lukoil_capture.py — mitmproxy addon для перехвата API Лукойл/Licard.

Запуск:
    mitmweb -p 8080 -s lukoil_capture.py

Сохраняет все перехваченные запросы/ответы в lukoil_raw.json
для последующего анализа.
"""

import json
import re
import time
from pathlib import Path
from mitmproxy import http

OUTPUT_FILE = Path(__file__).parent / 'lukoil_raw.json'

INTERESTING_HOSTS = [
    'licard.com',
    'licard.ru',
    'lukoil.ru',
    'lukoil.com',
    'mobile-ap',
    'api.licard',
    'lk.lukoil',
    'loyalty.lukoil',
    'serebryakovas',   # dev backend для ru.serebryakovas.lukoilmobileapp
]

PRICE_KEYWORDS = [
    'price', 'fuel', 'station', 'azs', 'petroleum',
    'цена', 'топливо', 'станция', 'азс',
]

captured = []


def _is_interesting(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    if any(h in host for h in INTERESTING_HOSTS):
        return True
    url = flow.request.pretty_url.lower()
    if any(kw in url for kw in PRICE_KEYWORDS):
        return True
    return False


def _try_parse_body(data: bytes) -> object:
    if not data:
        return None
    try:
        return json.loads(data)
    except Exception:
        text = data.decode('utf-8', errors='replace')
        return text if len(text) < 5000 else text[:5000] + '...[truncated]'


def response(flow: http.HTTPFlow):
    if not _is_interesting(flow):
        return

    req = flow.request
    resp = flow.response

    entry = {
        'ts': time.strftime('%H:%M:%S'),
        'method': req.method,
        'url': req.pretty_url,
        'status': resp.status_code,
        'req_headers': dict(req.headers),
        'req_body': _try_parse_body(req.content),
        'resp_headers': dict(resp.headers),
        'resp_body': _try_parse_body(resp.content),
    }

    captured.append(entry)
    _save()

    # Вывод в консоль для быстрого мониторинга
    body_preview = ''
    if isinstance(entry['resp_body'], dict):
        body_preview = str(entry['resp_body'])[:200]
    print(f"\n{'='*60}")
    print(f"[{entry['ts']}] {req.method} {req.pretty_url}")
    print(f"Status: {resp.status_code}")
    if 'Authorization' in req.headers:
        print(f"Auth: {req.headers['Authorization'][:80]}...")
    if body_preview:
        print(f"Body: {body_preview}")
    print('='*60)


def _save():
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(captured, f, ensure_ascii=False, indent=2)
    print(f'[capture] Сохранено {len(captured)} запросов → {OUTPUT_FILE}')

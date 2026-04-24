"""
monitor_azskirishi.py — Мониторинг Telegram-канала @AZSKIRISHI
Отслеживает посты Бориса: цены и статусы станций.
Запуск: python monitor_azskirishi.py
"""

import re
import json
import datetime
import subprocess
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CHANNEL_URL  = 'https://t.me/s/AZSKIRISHI'
STATE_FILE   = os.path.join(SCRIPT_DIR, 'monitor_state.json')
PRICES_FILE  = os.path.join(SCRIPT_DIR, 'prices.json')
STATUS_FILE  = os.path.join(SCRIPT_DIR, 'station_status.json')
LOG_FILE     = os.path.join(SCRIPT_DIR, 'monitor_log.txt')

MAX_LOG_LINES = 500  # обрезаем лог чтобы не рос вечно


# ─────────────────────────────────────────────────────────────
# ЛОГИРОВАНИЕ
# ─────────────────────────────────────────────────────────────
def log(msg):
    ts = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def trim_log():
    if not os.path.exists(LOG_FILE):
        return
    with open(LOG_FILE, encoding='utf-8') as f:
        lines = f.readlines()
    if len(lines) > MAX_LOG_LINES:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.writelines(lines[-MAX_LOG_LINES:])


# ─────────────────────────────────────────────────────────────
# ЗАГРУЗКА КАНАЛА
# ─────────────────────────────────────────────────────────────
def fetch_channel():
    from urllib.request import urlopen, Request
    req = Request(CHANNEL_URL, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    with urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


# ─────────────────────────────────────────────────────────────
# ПАРСИНГ ПОСТОВ
# ─────────────────────────────────────────────────────────────
def get_posts(html):
    """Возвращает список (post_id: int, text: str) для текстовых постов."""
    posts = []
    # Ищем блоки: data-post="AZSKIRISHI/ID" ... tgme_widget_message_text ... </div>
    blocks = re.findall(
        r'data-post="AZSKIRISHI/(\d+)".*?'
        r'tgme_widget_message_text[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    for post_id, raw in blocks:
        text = re.sub(r'<br\s*/?>', '\n', raw)
        text = re.sub('<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 5:
            posts.append((int(post_id), text))
    return posts


# ─────────────────────────────────────────────────────────────
# РАСПОЗНАВАНИЕ ЦЕН
# ─────────────────────────────────────────────────────────────
def parse_prices(text):
    """Ищет цены по карте и наличным. Возвращает (card, cash) или None."""
    t = text.lower()
    # Нужно хотя бы одно из ключевых слов
    if not any(w in t for w in ['картой', 'сбп', 'наличн', 'цена']):
        return None, None

    card = None
    cash = None

    # Цена картой / СБП: "картой или СБП равна 64,5" или "карта: 64.5"
    m = re.search(r'(?:картой|сбп)[^0-9]{0,30}?(\d{2,3}[,.]?\d*)\s*[рр₽]', t)
    if m:
        card = float(m.group(1).replace(',', '.'))

    # Цена наличными: "наличный расчёт равна 60" или "наличными 60"
    m = re.search(r'наличн[^0-9]{0,30}?(\d{2,3}[,.]?\d*)\s*[рр₽]', t)
    if m:
        cash = float(m.group(1).replace(',', '.'))

    return card, cash


# ─────────────────────────────────────────────────────────────
# РАСПОЗНАВАНИЕ СТАТУСА
# ─────────────────────────────────────────────────────────────
CLOSED_WORDS = ['нет электричества', 'не работает', 'закрыт', 'нет интернета',
                'не заправляем', 'отключ', 'нет связи']
OPEN_WORDS   = ['заработал', 'работает', 'открыт', 'возобнов', 'всё хорошо',
                'все хорошо', 'включили', 'появился интернет']

def parse_status(text):
    """Возвращает список {'location': str, 'status': closed|open, 'reason': str}."""
    t = text.lower()

    is_closed = any(w in t for w in CLOSED_WORDS)
    is_open   = any(w in t for w in OPEN_WORDS)

    # Если оба — приоритет у "закрыта"
    if is_closed:
        status = 'closed'
        reason = next((w for w in CLOSED_WORDS if w in t), 'проблема')
    elif is_open:
        status = 'open'
        reason = ''
    else:
        return []

    # Извлекаем локацию (улица, шоссе, номер АЗС)
    location = None

    # "на Уральской", "на Лесном шоссе", "АЗС №3", "Уральская работает/закрыта"
    patterns = [
        r'на\s+([а-яёА-ЯЁ][а-яёА-ЯЁ\s]{2,25}?)(?:\s+(?:нет|не|опять|снова|всё|уже|стало)|[,\.!])',
        r'(азс\s*[№#]\s*\d+)',          # только АЗС с номером (не просто "азс")
        r'([а-яёА-ЯЁ]+(?:\s+[а-яёА-ЯЁ]+)?\s+(?:улица|шоссе|проспект|переулок|набережная|линия))',
        r'^([а-яёА-ЯЁ][а-яёА-ЯЁ\s]{2,20}?)\s+(?:работает|заработал|открыт|закрыт|не работает)',
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            loc = m.group(1).strip().rstrip(',.')
            if len(loc) > 3:  # отсеиваем слишком короткие ("азс", "она")
                location = loc
                break

    if not location:
        return []

    return [{'location': location, 'status': status, 'reason': reason}]


# ─────────────────────────────────────────────────────────────
# JSON HELPERS
# ─────────────────────────────────────────────────────────────
def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────
# GIT
# ─────────────────────────────────────────────────────────────
def git_commit_push(summary):
    os.chdir(SCRIPT_DIR)
    subprocess.run(['git', 'add', 'prices.json', 'station_status.json', 'monitor_state.json'],
                   capture_output=True)
    result = subprocess.run(
        ['git', 'commit', '-m', f'fix: @AZSKIRISHI — {summary}'],
        capture_output=True, text=True, encoding='utf-8'
    )
    if 'nothing to commit' in result.stdout + result.stderr:
        log('Git: нечего коммитить')
        return
    push = subprocess.run(['git', 'push'], capture_output=True, text=True, encoding='utf-8')
    if push.returncode == 0:
        log(f'Git push: OK ({summary})')
    else:
        log(f'Git push: ошибка — {push.stderr.strip()}')


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    os.chdir(SCRIPT_DIR)
    trim_log()
    log('═══ Запуск мониторинга @AZSKIRISHI ═══')

    # Состояние — последний обработанный пост
    state = {'last_post_id': 0}
    if os.path.exists(STATE_FILE):
        try:
            state = load_json(STATE_FILE)
        except Exception:
            pass

    # Загружаем канал
    try:
        html = fetch_channel()
        log('Канал загружен успешно')
    except Exception as e:
        log(f'Ошибка загрузки канала: {e}')
        return

    # Получаем посты
    posts = get_posts(html)
    if not posts:
        log('Текстовых постов не найдено (возможно, только картинки)')
        return

    log(f'Всего текстовых постов на странице: {len(posts)}')

    # Оставляем только новые
    last_id = int(state.get('last_post_id', 0))
    new_posts = [(pid, txt) for pid, txt in posts if pid > last_id]

    if not new_posts:
        log(f'Новых постов нет (последний обработанный ID: {last_id})')
        _finish(state, posts)
        return

    log(f'Новых постов: {len(new_posts)}')

    # Загружаем данные
    prices_data = load_json(PRICES_FILE)
    status_data = load_json(STATUS_FILE)
    prices_changed = False
    status_changed = False
    changes = []

    for pid, text in new_posts:
        log(f'  Пост #{pid}: {text[:120]}')

        # — Цены —
        card, cash = parse_prices(text)
        if card or cash:
            oil = prices_data['prices'].get('oil store', {})
            old_card = oil.get('95')
            old_tiers = oil.get('95_tiers', {})
            new_tiers = {}
            if card:
                new_tiers['card'] = card
            if cash:
                new_tiers['cash'] = cash

            if (card and card != old_card) or new_tiers != old_tiers:
                if card:
                    prices_data['prices']['oil store']['95'] = card
                if new_tiers:
                    prices_data['prices']['oil store']['95_tiers'] = new_tiers
                prices_changed = True
                changes.append(f'цены карта={card} нал={cash}')
                log(f'    → цены обновлены: карта={card}, нал={cash}')

        # — Статус —
        events = parse_status(text)
        for ev in events:
            loc = ev['location']
            if ev['status'] == 'closed':
                status_data['overrides'][loc] = {
                    'status': 'closed',
                    'reason': ev['reason'],
                    'since': datetime.datetime.now().strftime('%d.%m.%Y'),
                    'source': '@AZSKIRISHI'
                }
                changes.append(f'закрыта:{loc}')
                log(f'    → ЗАКРЫТА: {loc} ({ev["reason"]})')
            else:
                if loc in status_data['overrides']:
                    del status_data['overrides'][loc]
                    changes.append(f'открыта:{loc}')
                    log(f'    → ОТКРЫТА: {loc}')
            status_changed = True

    # Сохраняем
    now_str = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    if prices_changed:
        prices_data['updated'] = now_str
        save_json(PRICES_FILE, prices_data)
    if status_changed:
        status_data['updated'] = now_str
        save_json(STATUS_FILE, status_data)

    _finish(state, posts)

    if changes:
        git_commit_push(', '.join(changes))
    else:
        log('Изменений нет — новые посты не содержат цен или статусов')

    log('═══ Готово ═══\n')


def _finish(state, posts):
    """Обновляем last_post_id по всем полученным постам."""
    if posts:
        state['last_post_id'] = max(pid for pid, _ in posts)
    state['last_run'] = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    save_json(STATE_FILE, state)


if __name__ == '__main__':
    main()

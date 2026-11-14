# -*- coding: utf-8 -*-
"""Промокод-радар: Яндекс Путешествия + Островок -> Telegram.
Проверка источников каждые 5 минут, кнопки, мультипользовательность, история."""
import html, json, os, random, re, subprocess, time
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ["TG_TOKEN"]
API = "https://api.telegram.org/bot" + TG_TOKEN
DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DIR, "state.json")

LOOP_SECONDS = 15 * 60   # запуск живёт 15 минут (cron перезапускает каждые 5)
POLL_EVERY = 5 * 60      # проверка источников и рассылка новых кодов — каждые 5 минут
COOLDOWN = 30            # антиспам на кнопке «Обновить»
BACKOFF = 30 * 60        # пауза после ошибки источника
MISS_LIMIT = 3           # сколько проверок код должен пропасть, чтобы стать «старым»
RENOTIFY = 24 * 3600     # не присылать один и тот же код повторно сутки

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SOURCES = {
    "ya": ("🟡 Яндекс Путешествия", [("Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel")]),
    "os": ("🔵 Островок", [("Официальный блог", "https://blog.ostrovok.ru/promokody-ostrovka/"),
                           ("Лисёнок", "https://lisenok-travel.ru/tpost/ostrovok-promokody-na-skidku")]),
}
CODE = r"[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,}"
CODE_RE = re.compile(r"\b(?:" + CODE + r")\b")
STOP = {"ВАЖНО","СКИДКА","СКИДКИ","ПРОМОКОД","ПРОМОКОДЫ","ОСТРОВОК","ЯНДЕКС","ТУРЦИЯ","РОССИЯ",
        "GURU","ГУРУ","RSS","HTML","HTTPS","HTTP","ООО","ИНН","МЕНЮ","ДАТА","СРОК","АКЦИЯ","АКЦИИ",
        "КУПОН","КУПОНЫ","ОТЕЛЬ","ОТЕЛИ","НОЯБРЬ","ДЕКАБРЬ","ЯНВАРЬ","ОТКРЫТЬ","ПОДРОБНЕЕ",
        "ПРОВЕРЕН","ПРОВЕРЕНО","ПЕРВЫЙ","ПОВТОРНЫЙ","ОПИСАНИЕ"}
BAD = re.compile(r"(завершена|завершён|завершен\b|истёк|истек|не действует|expired)", re.I)
CUT = re.compile(r"(истекшие купоны|завершенные промокоды|завершённые промокоды|завершенные купоны)", re.I)

def clean(s):
    return re.sub(r"\s+", " ", s).strip()

def extract_soup(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = soup.get_text("\n")
    m = CUT.search(text)
    if m:
        text = text[:m.start()]
    flat = clean(text)
    found = {}
    def add(code, ctx):
        code = code.strip(" .,:;»)(")
        if code != code.upper() or code in STOP or code in found or BAD.search(ctx):
            return
        found[code] = clean(ctx)[:260]
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) >= 3 and CODE_RE.fullmatch(cells[1].strip()):
            add(cells[1], cells[2] + " · " + cells[0])
    for m in re.finditer(r"\b(" + CODE + r")\s*[—–-]\s*(?i:скидк)[^.]{0,220}\.?", flat):
        add(m.group(1), m.group(0))
    for m in re.finditer(r"(?i:промокод\w*)\s*[:→]?\s*(" + CODE + r")", flat):
        s = max(0, m.start() - 160)
        add(m.group(1), flat[s:m.end() + 160])
    for m in re.finditer(r"Активировать промокод\s*→\s*(" + CODE + r")", flat):
        s = max(0, m.start() - 230)
        add(m.group(1), flat[s:m.end()])
    return found

def fetch(key, st):
    """Ходит по источникам вежливо: ETag/Last-Modified + пауза при ошибках."""
    out = {}
    http = st.setdefault("http", {})
    for name, url in SOURCES[key][1]:
        rec = http.get(url, {})
        if time.time() < rec.get("backoff", 0):
            for c, v in rec.get("codes", {}).items():
                out.setdefault(c, v)
            continue
        headers = dict(HEADERS)
        if rec.get("etag"):
            headers["If-None-Match"] = rec["etag"]
        if rec.get("lm"):
            headers["If-Modified-Since"] = rec["lm"]
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 304:
                codes = rec.get("codes", {})
            else:
                r.raise_for_status()
                codes = {c: {"ctx": ctx, "src": name} for c, ctx in extract_soup(r.text).items()}
                rec["etag"] = r.headers.get("ETag", "")
                rec["lm"] = r.headers.get("Last-Modified", "")
            rec["codes"] = codes
            rec["backoff"] = 0
            for c, v in codes.items():
                out.setdefault(c, v)
        except Exception:
            rec["backoff"] = time.time() + BACKOFF
            for c, v in rec.get("codes", {}).items():
                out.setdefault(c, v)
        http[url] = rec
    return out

def load_state():
    st = {"subs": [], "seen": {}, "old": {}, "cache": {}, "http": {}, "notified": {},
          "offset": 0, "last_poll": 0, "cool": {}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                st.update(json.load(f))
        except Exception:
            pass
    return st

def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        for cmd in (["git", "add", "state.json"], ["git", "commit", "-m", "state"],
                    ["git", "pull", "--rebase", "origin", "main"], ["git", "push"]):
            subprocess.run(cmd, cwd=DIR, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def tg(method, **kw):
    try:
        return requests.post(API + "/" + method, json=kw, timeout=40).json()
    except Exception:
        return {}

MENU = {"inline_keyboard": [
    [{"text": "🟡 Яндекс Путешествия", "callback_data": "ya"},
     {"text": "🔵 Островок", "callback_data": "os"}],
    [{"text": "🕘 Старые коды", "callback_data": "old"},
     {"text": "🔄 Обновить", "callback_data": "refresh"}],
    [{"text": "🔔 Подписаться", "callback_data": "sub"},
     {"text": "🔕 Отписаться", "callback_data": "unsub"}],
]}

def send(chat, text):
    chunks, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > 3500:
            chunks.append(cur)
            cur = block
        else:
            cur = (cur + "\n\n" + block) if cur else block
    if cur:
        chunks.append(cur)
    for i, ch in enumerate(chunks):
        kw = {"chat_id": chat, "text": ch, "parse_mode": "HTML", "disable_web_page_preview": True}
        if i == len(chunks) - 1:
            kw["reply_markup"] = MENU
        tg("sendMessage", **kw)
        time.sleep(0.4)

def fmt_code(code, v):
    ctx = re.sub(r"^" + re.escape(code) + r"\s*[—–:\-]?\s*", "", v["ctx"])
    m = re.search(r"до\s*(\d{2}\.\d{2}\.\d{2,4})", ctx)
    exp = "\n📅 до " + m.group(1) if m else ""
    return "<code>%s</code>\n%s%s" % (html.escape(code), html.escape(ctx[:200]), exp)

def get_codes(key, st, force=False):
    c = st["cache"].get(key, {})
    if force or not c.get("codes"):
        codes = fetch(key, st)
        st["cache"][key] = {"ts": time.time(), "codes": codes}
    return st["cache"].get(key, {}).get("codes", {})

def cmd_list(key, st, chat):
    codes = get_codes(key, st)
    title = SOURCES[key][0]
    if not codes:
        send(chat, title + "\n\nКодов пока не нашёл. Нажми «🔄 Обновить» чуть позже.")
        return
    items = list(codes.items())[:15]
    msg = "%s · актуальные (%d)\n\n" % (title, len(codes))
    msg += "\n\n".join(fmt_code(c, v) for c, v in items)
    if len(codes) > 15:
        msg += "\n\n…и ещё %d." % (len(codes) - 15)
    msg += "\n\n👆 Нажми на код — он скопируется."
    send(chat, msg)

def cmd_old(st, chat):
    old = st.get("old", {})
    if not old:
        send(chat, "🕘 Старых кодов пока нет. Сюда попадают коды, пропавшие из источников.")
        return
    items = sorted(old.items(), key=lambda kv: kv[1].get("gone", ""), reverse=True)[:15]
    msg = "🕘 Старые коды (пропали из источников)\n\n"
    msg += "\n\n".join("<code>%s</code>\n%s\n🕘 пропал %s · %s" % (
        html.escape(c), html.escape(v.get("ctx", "")[:150]), v.get("gone", "?"),
        SOURCES.get(v.get("key", ""), ("?",))[0]) for c, v in items)
    msg += "\n\nНекоторые ещё срабатывают в корзине — можно пробовать."
    send(chat, msg)

def handle(u, st):
    if "callback_query" in u:
        q = u["callback_query"]
        chat = q["message"]["chat"]["id"]
        data = q["data"]
        tg("answerCallbackQuery", callback_query_id=q["id"])
    elif "message" in u and "text" in u["message"]:
        chat = u["message"]["chat"]["id"]
        data = u["message"]["text"].strip().lower()
    else:
        return
    uid = str(chat)
    if data == "/start":
        if chat not in st["subs"]:
            st["subs"].append(chat)
        send(chat, "👋 Привет! Я радар промокодов <b>Яндекс Путешествий</b> и <b>Островка</b>.\n\n"
                   "Жми кнопки ниже — покажу актуальные коды.\n"
                   "🔔 Ты подписан(а): проверяю источники каждые 5 минут и сразу присылаю новые коды.\n\n"
                   "Команды: /yandex /ostrovok /old /stop")
        return
    if data in ("/stop", "unsub"):
        if chat in st["subs"]:
            st["subs"].remove(chat)
        send(chat, "🔕 Рассылка отключена. Кнопки работают всегда.")
        return
    if data == "sub":
        if chat not in st["subs"]:
            st["subs"].append(chat)
        send(chat, "🔔 Подписка включена! Новые коды буду присылать сразу.")
        return
    if data == "/help":
        send(chat, "Кнопки ниже 👇\n/yandex — коды Яндекс Путешествий\n/ostrovok — коды Островка\n"
                   "/old — старые коды\n/stop — отключить рассылку")
        return
    if data == "refresh":
        now = time.time()
        if now - st["cool"].get(uid, 0) < COOLDOWN:
            send(chat, "⏳ Уже обновлял недавно — попробуй через 30 секунд.")
            return
        st["cool"][uid] = now
        get_codes("ya", st, force=True)
        get_codes("os", st, force=True)
        send(chat, "🔄 Обновлено! Жми 🟡 или 🔵.")
        return
    if data in ("ya", "/yandex"):
        cmd_list("ya", st, chat)
        return
    if data in ("os", "/ostrovok"):
        cmd_list("os", st, chat)
        return
    if data in ("old", "/old"):
        cmd_old(st, chat)
        return
    send(chat, "Не понял 🙂 Нажми кнопку ниже.")

def scheduled_check(st):
    found = {}
    for key in SOURCES:
        codes = fetch(key, st)
        st["cache"][key] = {"ts": time.time(), "codes": codes}
        for c, v in codes.items():
            found[c] = dict(v, key=key)
    if not found:
        return
    now = time.time()
    today = time.strftime("%d.%m.%Y", time.gmtime())
    seen = st["seen"]
    notified = st.setdefault("notified", {})
    new = {}
    for c, v in found.items():
        if c not in seen and now - notified.get(c, 0) > RENOTIFY:
            new[c] = v
            notified[c] = now
        seen[c] = dict(v, miss=0)
    for c in list(seen):
        if c not in found:
            seen[c]["miss"] = seen[c].get("miss", 0) + 1
            if seen[c]["miss"] >= MISS_LIMIT:
                st["old"][c] = dict(seen[c], gone=today)
                del seen[c]
    for c in list(notified):
        if now - notified[c] > 2 * RENOTIFY:
            del notified[c]
    if len(st["old"]) > 300:
        for c in sorted(st["old"], key=lambda x: st["old"][x].get("gone", ""))[:len(st["old"]) - 300]:
            del st["old"][c]
    if new and st["subs"]:
        for key in SOURCES:
            part = {c: v for c, v in new.items() if v.get("key") == key}
            if not part:
                continue
            msg = "🔔 Новые коды · %s\n\n" % SOURCES[key][0]
            msg += "\n\n".join(fmt_code(c, v) for c, v in list(part.items())[:15])
            msg += "\n\n👆 Нажми на код — он скопируется."
            for chat in st["subs"]:
                send(chat, msg)

def main():
    st = load_state()
    end = time.time() + LOOP_SECONDS
    last_save = time.time()
    next_poll = st.get("last_poll", 0) + POLL_EVERY
    while time.time() < end:
        try:
            r = requests.get(API + "/getUpdates",
                             params={"offset": st.get("offset", 0), "timeout": 25},
                             timeout=35).json()
            for u in r.get("result", []):
                st["offset"] = u["update_id"] + 1
                try:
                    handle(u, st)
                except Exception:
                    pass
        except Exception:
            time.sleep(5)
        if time.time() >= next_poll:
            try:
                scheduled_check(st)
            except Exception:
                pass
            st["last_poll"] = time.time()
            next_poll = time.time() + POLL_EVERY + random.uniform(-20, 40)
        if time.time() - last_save > 180:
            save_state(st)
            last_save = time.time()
    save_state(st)

if __name__ == "__main__":
    main()
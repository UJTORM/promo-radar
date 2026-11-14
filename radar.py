# -*- coding: utf-8 -*-
"""Промокод-радар: 5 агрегаторов, админ-панель, чистый формат, проверка каждые 5 мин."""
import html, json, os, random, re, subprocess, time
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ["TG_TOKEN"]
ADMIN = int(os.environ.get("TG_ADMIN") or os.environ.get("TG_CHAT") or 0)
API = "https://api.telegram.org/bot" + TG_TOKEN
DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DIR, "state.json")

LOOP_SECONDS = 15 * 60
COOLDOWN = 30
BACKOFF = 30 * 60
MISS_LIMIT = 3
RENOTIFY = 24 * 3600

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SERVICES = {
    "ya": "🟡 ЯНДЕКС ПУТЕШЕСТВИЯ",
    "os": "🔵 ОСТРОВОК",
    "oz": "🟣 OZON TRAVEL",
    "ot": "🟠 ОТЕЛЛО",
    "tp": "🟢 Т-ПУТЕШЕСТВИЯ",
}
BUILTIN = [
    ("ya", "Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel"),
    ("os", "Официальный блог", "https://blog.ostrovok.ru/promokody-ostrovka/"),
    ("os", "Лисёнок", "https://lisenok-travel.ru/tpost/ostrovok-promokody-na-skidku"),
    ("oz", "Lovikod", "https://lovikod.ru/travel/promokody-ozon-travel"),
    ("oz", "7days", "https://7days.ru/promokodi/ozon-travel"),
    ("ot", "Lovikod", "https://lovikod.ru/travel/promokody-otello"),
    ("ot", "7days", "https://7days.ru/promokodi/otello"),
    ("tp", "Lovikod", "https://lovikod.ru/travel/promokody-t-puteshestviya"),
    ("tp", "7days", "https://7days.ru/promokodi/t-puteshestviya"),
]
CODE = r"[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,}"
CODE_RE = re.compile(r"\b(?:" + CODE + r")\b")
STOP = {"ВАЖНО","СКИДКА","СКИДКИ","ПРОМОКОД","ПРОМОКОДЫ","ОСТРОВОК","ЯНДЕКС","ТУРЦИЯ","РОССИЯ",
        "GURU","ГУРУ","RSS","HTML","HTTPS","HTTP","ООО","ИНН","МЕНЮ","ДАТА","СРОК","АКЦИЯ","АКЦИИ",
        "КУПОН","КУПОНЫ","ОТЕЛЬ","ОТЕЛИ","НОЯБРЬ","ДЕКАБРЬ","ЯНВАРЬ","ОТКРЫТЬ","ПОДРОБНЕЕ",
        "ПРОВЕРЕН","ПРОВЕРЕНО","ПЕРВЫЙ","ПОВТОРНЫЙ","ОПИСАНИЕ","OZON","ОТЕЛЛО","TRAVEL"}
BAD = re.compile(r"(завершена|завершён|завершен\b|истёк|истек|не действует|expired)", re.I)
CUT = re.compile(r"(истекшие купоны|завершенные промокоды|завершённые промокоды|завершенные купоны)", re.I)

def clean(s): return re.sub(r"\s+", " ", s).strip()
def num(s): return int(re.sub(r"\s", "", s))
def fmt(n): return f"{n:,}".replace(",", " ")
def msk(t=None): return time.gmtime((t or time.time()) + 3 * 3600)
def msk_str(t, f="%d.%m %H:%M"): return time.strftime(f, msk(t))

def extract_soup(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    for t in soup(["script", "style", "noscript"]): t.decompose()
    text = soup.get_text("\n")
    m = CUT.search(text)
    if m: text = text[:m.start()]
    flat = clean(text); found = {}
    def add(code, ctx):
        code = code.strip(" .,:;»)(")
        if code != code.upper() or code in STOP or code in found or BAD.search(ctx): return
        found[code] = clean(ctx)[:260]
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) >= 3 and CODE_RE.fullmatch(cells[1].strip()):
            add(cells[1], cells[2] + " · " + cells[0])
    for m in re.finditer(r"\b(" + CODE + r")\s*[—–-]\s*(?i:скидк)[^.]{0,220}\.?", flat):
        add(m.group(1), m.group(0))
    for m in re.finditer(r"(?i:промокод\w*)\s*[:→]?\s*(" + CODE + r")", flat):
        s = max(0, m.start() - 160); add(m.group(1), flat[s:m.end() + 160])
    for m in re.finditer(r"Активировать промокод\s*→\s*(" + CODE + r")", flat):
        s = max(0, m.start() - 230); add(m.group(1), flat[s:m.end()])
    return found

def parse_offer(c):
    pct = amt = mn = cap = exp = None
    m = re.search(r"скидк\w*\s*(?:до\s*)?(\d{1,2})\s*%", c, re.I)
    if m: pct = int(m.group(1))
    m = re.search(r"скидк\w*\s*(\d[\d\s]{2,})\s*(?:₽|руб)", c, re.I)
    if m: amt = num(m.group(1))
    m = re.search(r"от\s*(\d[\d\s]{3,})\s*(?:₽|руб)", c, re.I) or re.search(r"от\s*(\d{4,})\b", c)
    if m:
        v = num(m.group(1))
        if v >= 500: mn = v
    m = re.search(r"не более\s*(\d[\d\s]{2,})\s*(?:₽|руб)", c, re.I)
    if m: cap = num(m.group(1))
    m = re.search(r"до\s*(\d{2})\.(\d{2})\.(\d{2,4})", c)
    if m:
        y = int(m.group(3)); y += 2000 if y < 100 else 0
        exp = f"{m.group(1)}.{m.group(2)}.{y}"
    tags = []
    if re.search(r"приложени", c, re.I): tags.append("только в приложении")
    if re.search(r"перв\w+\s*(заказ|бронирован|оплат)|новых пользователей", c, re.I): tags.append("первое бронирование")
    if re.search(r"подборк|со страницы|premium", c, re.I): tags.append("отели из подборки")
    if re.search(r"проживани\w*[^.]{0,40}2027|в течение 2027|2027 года", c, re.I): tags.append("проживание в 2027")
    if re.search(r"санатор|в РФ|по России|территории РФ", c, re.I): tags.append("только РФ")
    if re.search(r"Шардж", c, re.I): tags.append("только Шарджа")
    return pct, amt, mn, cap, exp, tags

def block(code, v):
    pct, amt, mn, cap, exp, tags = parse_offer(v.get("ctx", ""))
    if amt:
        line = f"{fmt(amt)} ₽" + (f" от {fmt(mn)} ₽" if mn else "")
    elif pct:
        line = f"{pct}%" + (f" от {fmt(mn)} ₽" if mn else "") + (f" (макс. {fmt(cap)} ₽)" if cap else "")
    else:
        line = "скидка по условиям акции"
    out = [f"<code>{html.escape(code)}</code>", line,
           f"Действует до {exp}" if exp else "Срок не указан"]
    if tags: out.append("⚠️ " + " · ".join(tags[:2]))
    return "\n".join(out)

def all_sources(st):
    return list(BUILTIN) + [(s["svc"], s["name"], s["url"]) for s in st.get("sources_custom", [])]

def fetch(svc, st):
    out = {}; http = st.setdefault("http", {})
    off = st.get("sources_off", [])
    for s, name, url in all_sources(st):
        if s != svc or url in off: continue
        rec = http.get(url, {})
        if time.time() < rec.get("backoff", 0):
            for c, v in rec.get("codes", {}).items(): out.setdefault(c, v)
            continue
        headers = dict(HEADERS)
        if rec.get("etag"): headers["If-None-Match"] = rec["etag"]
        if rec.get("lm"): headers["If-Modified-Since"] = rec["lm"]
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 304:
                codes = rec.get("codes", {})
            else:
                r.raise_for_status()
                codes = {c: {"ctx": ctx, "src": name} for c, ctx in extract_soup(r.text).items()}
                rec["etag"] = r.headers.get("ETag", ""); rec["lm"] = r.headers.get("Last-Modified", "")
            rec["codes"] = codes; rec["backoff"] = 0; rec["ok_ts"] = time.time(); rec["err"] = ""
            for c, v in codes.items(): out.setdefault(c, v)
        except Exception as e:
            rec["backoff"] = time.time() + BACKOFF; rec["err"] = type(e).__name__
            for c, v in rec.get("codes", {}).items(): out.setdefault(c, v)
        http[url] = rec
    return out

def load_state():
    st = {"subs": [], "seen": {}, "old": {}, "cache": {}, "http": {}, "notified": {}, "digest": {},
          "offset": 0, "last_poll": 0, "cool": {}, "sources_off": [], "sources_custom": [],
          "await_ann": False, "await_src": False,
          "settings": {"interval": 5, "quiet": False, "broadcast": True}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f: st.update(json.load(f))
        except Exception: pass
    return st

def save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(st, f, ensure_ascii=False)
        for cmd in (["git", "add", "state.json"], ["git", "commit", "-m", "state"],
                    ["git", "pull", "--rebase", "origin", "main"], ["git", "push"]):
            subprocess.run(cmd, cwd=DIR, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception: pass

def tg(method, **kw):
    try: return requests.post(API + "/" + method, json=kw, timeout=40).json()
    except Exception: return {}

def menu_for(chat):
    rows = [
        [{"text": "🟡 Яндекс", "callback_data": "ya"}, {"text": "🔵 Островок", "callback_data": "os"}],
        [{"text": "🟣 Ozon", "callback_data": "oz"}, {"text": "🟠 Отелло", "callback_data": "ot"}],
        [{"text": "🟢 Т-Путешествия", "callback_data": "tp"}, {"text": "🕘 Старые", "callback_data": "old"}],
        [{"text": "🔄 Обновить", "callback_data": "refresh"}],
    ]
    if chat == ADMIN: rows.append([{"text": "⚙️ Админ панель", "callback_data": "admin"}])
    return {"inline_keyboard": rows}

def send(chat, text):
    chunks, cur = [], ""
    for b in text.split("\n\n"):
        if len(cur) + len(b) + 2 > 3500: chunks.append(cur); cur = b
        else: cur = (cur + "\n\n" + b) if cur else b
    if cur: chunks.append(cur)
    for i, ch in enumerate(chunks):
        kw = {"chat_id": chat, "text": ch, "parse_mode": "HTML", "disable_web_page_preview": True}
        if i == len(chunks) - 1: kw["reply_markup"] = menu_for(chat)
        tg("sendMessage", **kw); time.sleep(0.4)

def get_codes(svc, st, force=False):
    c = st["cache"].get(svc, {})
    if force or not c.get("codes"):
        st["cache"][svc] = {"ts": time.time(), "codes": fetch(svc, st)}
    return st["cache"].get(svc, {}).get("codes", {})

def cmd_list(svc, st, chat):
    codes = get_codes(svc, st)
    if not codes:
        send(chat, SERVICES[svc] + "\n\nКодов пока не нашёл. Нажми «🔄 Обновить» позже."); return
    items = list(codes.items())[:15]
    msg = f"{SERVICES[svc]} · актуальные ({len(codes)})\n\n" + "\n\n".join(block(c, v) for c, v in items)
    if len(codes) > 15: msg += f"\n\n…и ещё {len(codes) - 15}."
    msg += "\n\n👆 Нажми на код — он скопируется."
    send(chat, msg)

def cmd_old(st, chat):
    old = st.get("old", {})
    if not old:
        send(chat, "🕘 Старых кодов пока нет."); return
    items = sorted(old.items(), key=lambda kv: kv[1].get("gone", ""), reverse=True)[:15]
    msg = "🕘 СТАРЫЕ КОДЫ\n\n" + "\n\n".join(
        block(c, v) + f"\n🕘 пропал {v.get('gone', '?')} · {SERVICES.get(v.get('svc', ''), '')}"
        for c, v in items)
    msg += "\n\nНекоторые ещё срабатывают в корзине."
    send(chat, msg)

def is_quiet(st):
    if not st["settings"].get("quiet"): return False
    h = msk().tm_hour
    return h >= 23 or h < 8

def show_admin(st, chat):
    s = st["settings"]
    msg = ("⚙️ АДМИН-ПАНЕЛЬ\n\n"
           f"⏱ Интервал: {s['interval']} мин\n"
           f"🌙 Тихие часы (23–08 МСК): {'вкл' if s['quiet'] else 'выкл'}\n"
           f"📢 Рассылка: {'вкл' if s['broadcast'] else 'выкл'}\n"
           f"👥 Подписчиков: {len(st['subs'])}")
    kb = {"inline_keyboard": [
        [{"text": f"⏱ Интервал: {s['interval']} мин", "callback_data": "adm_int"},
         {"text": f"🌙 Тихие: {'вкл' if s['quiet'] else 'выкл'}", "callback_data": "adm_quiet"}],
        [{"text": f"📢 Рассылка: {'вкл' if s['broadcast'] else 'выкл'}", "callback_data": "adm_bc"},
         {"text": "🩺 Статус", "callback_data": "adm_status"}],
        [{"text": "📡 Источники", "callback_data": "adm_src"},
         {"text": "👥 Подписчики", "callback_data": "adm_subs"}],
        [{"text": "📣 Объявление всем", "callback_data": "adm_ann"},
         {"text": "➕ Источник", "callback_data": "adm_add"}],
        [{"text": "⬅️ Назад", "callback_data": "adm_back"}],
    ]}
    tg("sendMessage", chat_id=chat, text=msg, reply_markup=kb)

def show_status(st, chat):
    now = time.time(); s = st["settings"]
    lines = ["🩺 СТАТУС РАДАРА",
             f"Последняя проверка: {msk_str(st['last_poll']) if st['last_poll'] else 'ещё не было'} МСК",
             f"Интервал: {s['interval']} мин · Тихие часы: {'вкл' if s['quiet'] else 'выкл'} · Рассылка: {'вкл' if s['broadcast'] else 'выкл'}",
             f"Подписчиков: {len(st['subs'])} · Кодов в базе: {len(st['seen'])} · Старых: {len(st['old'])}",
             "", "Источники:"]
    for svc, name, url in all_sources(st):
        rec = st["http"].get(url, {})
        if url in st.get("sources_off", []):
            lines.append(f"⏸ {name} ({svc}) — выключен")
        elif rec.get("backoff", 0) > now:
            lines.append(f"⚠️ {name} ({svc}) — ошибка {rec.get('err', '')}, пауза до {msk_str(rec['backoff'], '%H:%M')}")
        elif rec.get("ok_ts"):
            lines.append(f"✅ {name} ({svc}) — {int((now - rec['ok_ts']) / 60)} мин назад")
        else:
            lines.append(f"⏳ {name} ({svc}) — ещё не проверялся")
    send(chat, "\n".join(lines))

def show_sources(st, chat):
    rows = []; text = ["📡 ИСТОЧНИКИ (нажми — вкл/выкл):"]
    for i, (svc, name, url) in enumerate(all_sources(st)):
        on = url not in st.get("sources_off", [])
        text.append(f"{'✅' if on else '❌'} {name} · {svc}")
        rows.append([{"text": f"{'✅' if on else '❌'} {name} ({svc})", "callback_data": f"src_{i}"}])
    for i, s in enumerate(st.get("sources_custom", [])):
        rows.append([{"text": f"🗑 удалить: {s['url'][:40]}", "callback_data": f"del_{i}"}])
    rows.append([{"text": "⬅️ Назад", "callback_data": "admin"}])
    tg("sendMessage", chat_id=chat, text="\n".join(text), reply_markup={"inline_keyboard": rows})

def handle(u, st):
    if "callback_query" in u:
        q = u["callback_query"]; chat = q["message"]["chat"]["id"]; data = q["data"]
        tg("answerCallbackQuery", callback_query_id=q["id"])
    elif "message" in u and "text" in u["message"]:
        chat = u["message"]["chat"]["id"]; data = u["message"]["text"].strip()
    else:
        return
    uid = str(chat); low = data.lower()
    admin_cmd = data in ("admin", "adm_int", "adm_quiet", "adm_bc", "adm_status", "adm_src",
                         "adm_subs", "adm_ann", "adm_add", "adm_back", "/admin", "/status") \
                or data.startswith(("src_", "del_"))
    if admin_cmd and chat != ADMIN:
        send(chat, "⛔ Эта команда только для админа."); return
    if chat == ADMIN and st.get("await_ann") and "message" in u:
        st["await_ann"] = False
        for c in st["subs"]: send(c, "📣 ОБЪЯВЛЕНИЕ\n\n" + html.escape(data))
        send(chat, "✅ Объявление разослано."); return
    if chat == ADMIN and st.get("await_src") and "message" in u:
        st["await_src"] = False
        parts = data.split(None, 1)
        if len(parts) == 2 and parts[0] in SERVICES and parts[1].startswith("http"):
            st["sources_custom"].append({"svc": parts[0], "name": "Свой источник", "url": parts[1]})
            send(chat, "✅ Источник добавлен! Проверю в ближайшую проверку.")
        else:
            send(chat, "Формат: код_сервиса ссылка\nНапример: oz https://lovikod.ru/travel/promokody-ozon-travel\nСервисы: ya os oz ot tp")
        return
    if low == "/start":
        if chat not in st["subs"]: st["subs"].append(chat)
        send(chat, "👋 Привет! Я радар промокодов: Яндекс Путешествия, Островок, Ozon Travel, Отелло, Т-Путешествия.\n\n"
                   "Жми кнопки — покажу коды. Новые присылаю сам каждые 5 минут.\n"
                   "Команды: /yandex /ostrovok /ozon /otello /tput /old /stop"
                   + ("\n⚙️ У тебя есть кнопка «Админ панель»." if chat == ADMIN else ""))
        return
    if low in ("/stop", "unsub"):
        if chat in st["subs"]: st["subs"].remove(chat)
        send(chat, "🔕 Рассылка отключена. Кнопки работают всегда."); return
    if low == "sub":
        if chat not in st["subs"]: st["subs"].append(chat)
        send(chat, "🔔 Подписка включена!"); return
    if low == "/help":
        send(chat, "Кнопки ниже 👇\n/yandex /ostrovok /ozon /otello /tput — коды сервисов\n/old — старые коды\n/stop — отключить рассылку"); return
    if low == "refresh":
        now = time.time()
        if now - st["cool"].get(uid, 0) < COOLDOWN:
            send(chat, "⏳ Подожди 30 секунд."); return
        st["cool"][uid] = now
        for svc in SERVICES: get_codes(svc, st, force=True)
        send(chat, "🔄 Обновлено! Жми кнопку сервиса."); return
    if low in ("ya", "/yandex"): cmd_list("ya", st, chat); return
    if low in ("os", "/ostrovok"): cmd_list("os", st, chat); return
    if low in ("oz", "/ozon"): cmd_list("oz", st, chat); return
    if low in ("ot", "/otello"): cmd_list("ot", st, chat); return
    if low in ("tp", "/tput"): cmd_list("tp", st, chat); return
    if low in ("old", "/old"): cmd_old(st, chat); return
    if low in ("admin", "/admin"): show_admin(st, chat); return
    if low in ("adm_status", "/status"): show_status(st, chat); return
    if low == "adm_int":
        opts = [5, 10, 15, 30, 60]
        cur = st["settings"]["interval"]
        st["settings"]["interval"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 5
        show_admin(st, chat); return
    if low == "adm_quiet":
        st["settings"]["quiet"] = not st["settings"]["quiet"]; show_admin(st, chat); return
    if low == "adm_bc":
        st["settings"]["broadcast"] = not st["settings"]["broadcast"]; show_admin(st, chat); return
    if low == "adm_src": show_sources(st, chat); return
    if low == "adm_subs":
        send(chat, "👥 Подписчики (%d):\n%s" % (len(st["subs"]), "\n".join(map(str, st["subs"])) or "пусто")); return
    if low == "adm_ann":
        st["await_ann"] = True; send(chat, "📣 Пришли текст объявления следующим сообщением."); return
    if low == "adm_add":
        st["await_src"] = True
        send(chat, "➕ Пришли источник в формате: сервис ссылка\nСервисы: ya os oz ot tp\nПример: oz https://lovikod.ru/travel/promokody-ozon-travel"); return
    if low == "adm_back":
        send(chat, "⬅️ Главное меню."); return
    if data.startswith("src_"):
        i = int(data[4:]); srcs = all_sources(st)
        if i < len(srcs):
            url = srcs[i][2]; off = st["sources_off"]
            if url in off: off.remove(url)
            else: off.append(url)
        show_sources(st, chat); return
    if data.startswith("del_"):
        i = int(data[4:])
        if i < len(st["sources_custom"]): st["sources_custom"].pop(i)
        show_sources(st, chat); return
    send(chat, "Не понял 🙂 Нажми кнопку ниже.")

def scheduled_check(st):
    now = time.time(); found = {}
    for svc in SERVICES:
        codes = fetch(svc, st)
        st["cache"][svc] = {"ts": now, "codes": codes}
        for c, v in codes.items(): found[c] = dict(v, svc=svc)
    if not found: return
    today = time.strftime("%d.%m.%Y", msk())
    seen = st["seen"]; notified = st.setdefault("notified", {})
    for c, v in found.items():
        if c not in seen and now - notified.get(c, 0) > RENOTIFY:
            st["digest"][c] = v; notified[c] = now
        seen[c] = dict(v, miss=0)
    for c in list(seen):
        if c not in found:
            seen[c]["miss"] = seen[c].get("miss", 0) + 1
            if seen[c]["miss"] >= MISS_LIMIT:
                st["old"][c] = dict(seen[c], gone=today); del seen[c]
    for c in list(notified):
        if now - notified[c] > 2 * RENOTIFY: del notified[c]
    if len(st["old"]) > 300:
        for c in sorted(st["old"], key=lambda x: st["old"][x].get("gone", ""))[:len(st["old"]) - 300]:
            del st["old"][c]
    if st["digest"] and st["subs"] and st["settings"]["broadcast"] and not is_quiet(st):
        for svc in SERVICES:
            part = {c: v for c, v in st["digest"].items() if v.get("svc") == svc}
            if not part: continue
            msg = f"🔔 НОВЫЕ КОДЫ · {SERVICES[svc]}\n\n" + "\n\n".join(block(c, v) for c, v in list(part.items())[:15])
            msg += "\n\n👆 Нажми на код — он скопируется."
            for chat in st["subs"]: send(chat, msg)
        st["digest"] = {}

def main():
    st = load_state()
    end = time.time() + LOOP_SECONDS
    last_save = time.time()
    next_poll = st.get("last_poll", 0) + st["settings"]["interval"] * 60
    while time.time() < end:
        try:
            r = requests.get(API + "/getUpdates", params={"offset": st.get("offset", 0), "timeout": 25}, timeout=35).json()
            for u in r.get("result", []):
                st["offset"] = u["update_id"] + 1
                try: handle(u, st)
                except Exception: pass
        except Exception:
            time.sleep(5)
        if time.time() >= next_poll:
            try: scheduled_check(st)
            except Exception: pass
            st["last_poll"] = time.time()
            next_poll = time.time() + st["settings"]["interval"] * 60 + random.uniform(-20, 40)
        if time.time() - last_save > 180:
            save_state(st); last_save = time.time()
    save_state(st)

if __name__ == "__main__":
    main()
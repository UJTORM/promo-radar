# -*- coding: utf-8 -*-
"""Промокод-радар v7: разделы Отели/Авиа/Маркетплейсы, рейтинг выгоды, полный вывод."""
import html, json, os, random, re, subprocess, time
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ["TG_TOKEN"]
ENV_ADMIN = int(os.environ.get("TG_ADMIN") or os.environ.get("TG_CHAT") or 0)
API = "https://api.telegram.org/bot" + TG_TOKEN
DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DIR, "state.json")
ST = None
LOOP_SECONDS = 15 * 60
COOLDOWN = 30
BACKOFF = 30 * 60
MISS_LIMIT = 3
RENOTIFY = 24 * 3600
CRAWL_TTL = 30 * 60
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
CATS = {"hotel": "🏨 ОТЕЛИ", "avia": "✈️ АВИАБИЛЕТЫ", "market": "🛍 МАРКЕТПЛЕЙСЫ"}
BRANDS = {
 "ya": ("hotel", "🟡 ЯНДЕКС ПУТЕШЕСТВИЯ", [("Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel", "page"), ("7days", "https://7days.ru/promokodi/yandex-travel", "page"), ("Яндекс Журнал", "https://travel.yandex.ru/journal/", "crawl"), ("TG", "https://t.me/s/yandex_travel", "tg")]),
 "os": ("hotel", "🔵 ОСТРОВОК", [("Офиц. блог", "https://blog.ostrovok.ru/promokody-ostrovka/", "page"), ("Блог (офиц.)", "https://blog.ostrovok.ru/", "crawl"), ("Лисёнок", "https://lisenok-travel.ru/tpost/ostrovok-promokody-na-skidku", "page"), ("7days", "https://7days.ru/promokodi/ostrovok", "page"), ("TG", "https://t.me/s/ostrovok", "tg")]),
 "ozt": ("hotel", "🟣 OZON TRAVEL", [("Lovikod", "https://lovikod.ru/travel/promokody-ozon-travel", "page"), ("7days", "https://7days.ru/promokodi/ozon-travel", "page"), ("TG", "https://t.me/s/ozon_travel", "tg")]),
 "ot": ("hotel", "🟠 ОТЕЛЛО", [("Lovikod", "https://lovikod.ru/travel/promokody-otello", "page"), ("7days", "https://7days.ru/promokodi/otello", "page")]),
 "tp": ("hotel", "🟢 Т-ПУТЕШЕСТВИЯ", [("Lovikod", "https://lovikod.ru/travel/promokody-t-puteshestviya", "page"), ("7days", "https://7days.ru/promokodi/t-puteshestviya", "page")]),
 "tv": ("hotel", "🧳 TRAVELATA", [("Lovikod", "https://lovikod.ru/travel/promokody-travelata", "page"), ("7days", "https://7days.ru/promokodi/travelata", "page")]),
 "lv": ("hotel", "🧳 LEVEL.TRAVEL", [("Lovikod", "https://lovikod.ru/travel/promokody-level-travel", "page"), ("7days", "https://7days.ru/promokodi/level-travel", "page")]),
 "tu": ("hotel", "🧳 ТУТУ.РУ", [("Lovikod", "https://lovikod.ru/travel/promokody-tutu", "page"), ("7days", "https://7days.ru/promokodi/tutu", "page")]),
 "pb": ("avia", "🟢 ПОБЕДА", [("7days", "https://7days.ru/promokodi/pobeda", "page"), ("Lovikod", "https://lovikod.ru/travel/promokody-pobeda", "page"), ("TG", "https://t.me/s/pobeda", "tg")]),
 "ut": ("avia", "🔵 UTAIR", [("7days", "https://7days.ru/promokodi/utair", "page"), ("Lovikod", "https://lovikod.ru/travel/promokody-utair", "page"), ("TG", "https://t.me/s/utair", "tg")]),
 "fz": ("avia", "🟠 FLYDUBAI", [("Офиц. сайт", "https://www.flydubai.com/en/", "page"), ("7days", "https://7days.ru/promokodi/flydubai", "page"), ("TG", "https://t.me/s/flydubai", "tg")]),
 "af": ("avia", "🔵 АЭРОФЛОТ", [("Офиц. акции", "https://www.aeroflot.ru/ru-ru/special_offers", "page"), ("7days", "https://7days.ru/promokodi/aeroflot", "page"), ("Lovikod", "https://lovikod.ru/travel/promokody-aeroflot", "page"), ("TG", "https://t.me/s/aeroflot", "tg")]),
 "s7": ("avia", "🟢 S7", [("Офиц. акции", "https://www.s7.ru/ru/offers/", "page"), ("7days", "https://7days.ru/promokodi/s7-airlines", "page"), ("Lovikod", "https://lovikod.ru/travel/promokody-s7", "page"), ("TG", "https://t.me/s/s7airlines", "tg")]),
 "ur": ("avia", "🔴 УРАЛЬСКИЕ АВИАЛИНИИ", [("7days", "https://7days.ru/promokodi/ural-airlines", "page"), ("TG", "https://t.me/s/uralairlines", "tg")]),
 "pg": ("avia", "🟡 PEGASUS", [("Офиц. сайт", "https://www.flypgs.com/en", "page"), ("7days", "https://7days.ru/promokodi/pegasus", "page"), ("TG", "https://t.me/s/flypgs", "tg")]),
 "oz": ("market", "🟣 OZON", [("7days", "https://7days.ru/promokodi/ozon", "page"), ("Lovikod", "https://lovikod.ru/promokody-ozon", "page"), ("TG", "https://t.me/s/ozon", "tg")]),
 "wb": ("market", "🟣 WILDBERRIES", [("7days", "https://7days.ru/promokodi/wildberries", "page"), ("Lovikod", "https://lovikod.ru/promokody-wildberries", "page"), ("TG", "https://t.me/s/wildberries", "tg")]),
 "ym": ("market", "🟡 ЯНДЕКС МАРКЕТ", [("7days", "https://7days.ru/promokodi/yandex-market", "page"), ("Lovikod", "https://lovikod.ru/promokody-yandex-market", "page"), ("TG", "https://t.me/s/yandex_market", "tg")]),
 "mm": ("market", "🟢 МЕГАМАРКЕТ", [("7days", "https://7days.ru/promokodi/megamarket", "page"), ("Lovikod", "https://lovikod.ru/promokody-megamarket", "page"), ("TG", "https://t.me/s/megamarket", "tg")]),
 "ali": ("market", "🟠 ALIEXPRESS", [("7days", "https://7days.ru/promokodi/aliexpress", "page"), ("Lovikod", "https://lovikod.ru/promokody-aliexpress", "page"), ("TG", "https://t.me/s/aliexpress", "tg")]),
}
CODE = r"[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,}"
CODE_RE = re.compile(r"\b(?:" + CODE + r")\b")
STOP = {"ВАЖНО","СКИДКА","СКИДКИ","ПРОМОКОД","ПРОМОКОДЫ","ОСТРОВОК","ЯНДЕКС","ТУРЦИЯ","РОССИЯ","GURU","ГУРУ","RSS","HTML","HTTPS","HTTP","ООО","ИНН","МЕНЮ","ДАТА","СРОК","АКЦИЯ","АКЦИИ","КУПОН","КУПОНЫ","ОТЕЛЬ","ОТЕЛИ","НОЯБРЬ","ДЕКАБРЬ","ЯНВАРЬ","ОТКРЫТЬ","ПОДРОБНЕЕ","ПРОВЕРЕН","ПРОВЕРЕНО","ПЕРВЫЙ","ПОВТОРНЫЙ","ОПИСАНИЕ","OZON","ОТЕЛЛО","TRAVEL","JOURNAL","АЭРОФЛОТ","ПОБЕДА","S7","UTAIR","FLYDUBAI","PEGASUS","OZON","WILDBERRIES","ALIEXPRESS","МЕГАМАРКЕТ","МАРКЕТ"}
BAD = re.compile(r"(завершена|завершён|завершен\b|истёк|истек|не действует|expired)", re.I)
CUT = re.compile(r"(истекшие купоны|завершенные промокоды|завершённые промокоды|завершенные купоны)", re.I)

def clean(s): return re.sub(r"\s+", " ", s).strip()
def num(s): return int(re.sub(r"\s", "", s))
def fmt(n): return f"{n:,}".replace(",", " ")
def msk(t=None): return time.gmtime((t or time.time()) + 3 * 3600)
def msk_str(t, f="%d.%m %H:%M"): return time.strftime(f, msk(t))
def admin_id():
    if ENV_ADMIN: return ENV_ADMIN
    if ST.get("admin"): return ST["admin"]
    if ST["subs"]: ST["admin"] = next(iter(ST["subs"]))
    return ST.get("admin", 0)

def extract_soup(t):
    soup = BeautifulSoup(t, "html.parser")
    for x in soup(["script", "style", "noscript"]): x.decompose()
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
        if len(cells) >= 3 and CODE_RE.fullmatch(cells[1].strip()): add(cells[1], cells[2] + " · " + cells[0])
    for m in re.finditer(r"\b(" + CODE + r")\s*[—–-]\s*(?i:скидк)[^.]{0,220}\.?", flat): add(m.group(1), m.group(0))
    for m in re.finditer(r"(?i:промокод\w*)\s*[:→]?\s*(" + CODE + r")", flat):
        s = max(0, m.start() - 160); add(m.group(1), flat[s:m.end() + 160])
    for m in re.finditer(r"Активировать промокод\s*→\s*(" + CODE + r")", flat):
        s = max(0, m.start() - 230); add(m.group(1), flat[s:m.end()])
    return found

def crawl(url, name):
    r = requests.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
    if "journal" in url:
        links = re.findall(r'href="(/journal/[a-z0-9\-]+/)"', r.text)
        urls = ["https://travel.yandex.ru" + l for l in dict.fromkeys(links)][:6]
    else:
        links = re.findall(r'href="(https?://blog\.ostrovok\.ru/[a-z0-9\-]+/)"', r.text)
        urls = list(dict.fromkeys(links))[:6]
    out = {}
    for u in urls:
        try:
            rr = requests.get(u, headers=HEADERS, timeout=25)
            if rr.status_code != 200: continue
            for c, ctx in extract_soup(rr.text).items(): out.setdefault(c, {"ctx": ctx, "src": name})
        except Exception: continue
    return out

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
    if re.search(r"подборк|со страницы|premium", c, re.I): tags.append("из подборки")
    if re.search(r"проживани\w*[^.]{0,40}2027|в течение 2027|2027 года", c, re.I): tags.append("проживание в 2027")
    if re.search(r"санатор|в РФ|по России|территории РФ", c, re.I): tags.append("только РФ")
    return pct, amt, mn, cap, exp, tags

def value(v, budget):
    p, a, mn, cap, exp, tags = parse_offer(v.get("ctx", ""))
    if mn and budget < mn: return 0
    if a: return a
    if p:
        val = budget * p / 100
        if cap: val = min(val, cap)
        return int(val)
    return 0

def sig(v):
    p, a, mn, cap, exp, tags = parse_offer(v.get("ctx", ""))
    return (p, a, mn, cap, exp, tuple(tags))

def block(code, v, mark=None, budget=None, aliases=()):
    p, a, mn, cap, exp, tags = parse_offer(v.get("ctx", ""))
    if a: line = f"{fmt(a)} ₽" + (f" от {fmt(mn)} ₽" if mn else "")
    elif p: line = f"{p}%" + (f" от {fmt(mn)} ₽" if mn else "") + (f" (макс. {fmt(cap)} ₽)" if cap else "")
    else: line = "скидка по условиям акции"
    out = []
    if mark: out.append(mark)
    out.append(f"<code>{html.escape(code)}</code>")
    out.append(line)
    if p and budget: out.append(f"≈ выгода {fmt(value(v, budget))} ₽ при сумме {fmt(budget)} ₽")
    out.append(f"Действует до {exp}" if exp else "Срок не указан")
    if tags: out.append("⚠️ " + " · ".join(tags[:2]))
    if aliases: out.append("🔁 ещё коды акции: " + " ".join(f"<code>{html.escape(x)}</code>" for x in aliases[:3]))
    return "\n".join(out)

def render_category(cat, entries, st):
    budget = st["settings"]["budgets"][cat]
    scored = [(b, c, v, value(v, budget)) for b, c, v in entries]
    ranked = sorted(scored, key=lambda x: -x[3])
    marks = {}
    for i, (b, c, v, s) in enumerate(ranked[:3]):
        if s > 0: marks[b + ":" + c] = "💰 САМЫЙ ВЫГОДНЫЙ" if i == 0 else "🔥 ВЫГОДНЫЙ"
    by_brand = {}
    for b, c, v, s in scored: by_brand.setdefault(b, []).append((c, v, s))
    brand_best = {b: max(x[2] for x in rows) for b, rows in by_brand.items()}
    parts = []
    for b in sorted(by_brand, key=lambda x: -brand_best[x]):
        groups = {}
        for c, v, s in sorted(by_brand[b], key=lambda x: -x[2]): groups.setdefault(sig(v), []).append((c, v, s))
        blocks = []
        for g in groups.values():
            c, v, s = g[0]
            blocks.append(block(c, v, marks.get(b + ":" + c), budget, [x[0] for x in g[1:]]))
        parts.append(BRANDS[b][1] + "\n\n" + "\n\n".join(blocks))
    return "\n\n".join(parts)

def all_sources(st):
    out = []
    for b, (cat, title, srcs) in BRANDS.items():
        for name, url, kind in srcs: out.append((b, name, url, kind))
    for s in st.get("sources_custom", []): out.append((s["brand"], s["name"], s["url"], "page"))
    return out

def fetch(brand, st):
    out = {}; http = st.setdefault("http", {}); off = st.get("sources_off", []); now = time.time()
    for b, name, url, kind in all_sources(st):
        if b != brand or url in off: continue
        rec = http.get(url, {})
        if now < rec.get("backoff", 0) or (kind == "crawl" and rec.get("codes") and now - rec.get("crawl_ts", 0) < CRAWL_TTL):
            for c, v in rec.get("codes", {}).items(): out.setdefault(c, v)
            continue
        try:
            if kind == "crawl":
                codes = crawl(url, name); rec["crawl_ts"] = now
            else:
                headers = dict(HEADERS)
                if kind == "page":
                    if rec.get("etag"): headers["If-None-Match"] = rec["etag"]
                    if rec.get("lm"): headers["If-Modified-Since"] = rec["lm"]
                r = requests.get(url, headers=headers, timeout=30)
                if r.status_code == 304: codes = rec.get("codes", {})
                else:
                    r.raise_for_status()
                    codes = {c: {"ctx": ctx, "src": name} for c, ctx in extract_soup(r.text).items()}
                    if kind == "page":
                        rec["etag"] = r.headers.get("ETag", ""); rec["lm"] = r.headers.get("Last-Modified", "")
            rec["codes"] = codes; rec["backoff"] = 0; rec["ok_ts"] = now; rec["err"] = ""
            for c, v in codes.items(): out.setdefault(c, v)
        except Exception as e:
            rec["backoff"] = now + BACKOFF; rec["err"] = type(e).__name__
            for c, v in rec.get("codes", {}).items(): out.setdefault(c, v)
        http[url] = rec
    return out

def load_state():
    st = {"subs": {}, "seen": {}, "old": {}, "cache": {}, "http": {}, "notified": {}, "digest": {},
          "offset": 0, "last_poll": 0, "cool": {}, "sources_off": [], "sources_custom": [],
          "await_ann": False, "await_src": False, "admin": 0,
          "settings": {"interval": 5, "quiet": False, "broadcast": True,
                       "budgets": {"hotel": 60000, "avia": 15000, "market": 5000}}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f: st.update(json.load(f))
        except Exception: pass
    if isinstance(st["subs"], list):
        st["subs"] = {c: {"hotel": True, "avia": True, "market": False} for c in st["subs"]}
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

def flags(chat):
    return ST["subs"].setdefault(chat, {"hotel": True, "avia": True, "market": False})

def menu_for(chat):
    f = flags(chat)
    rows = [
        [{"text": "🏨 Отели", "callback_data": "cat_hotel"}, {"text": "✈️ Авиабилеты", "callback_data": "cat_avia"}],
        [{"text": "🛍 Маркетплейсы", "callback_data": "cat_market"}, {"text": "🕘 Старые", "callback_data": "old"}],
        [{"text": f"🔔 Отели: {'вкл' if f['hotel'] else 'выкл'}", "callback_data": "sub_hotel"},
         {"text": f"🔔 Авиа: {'вкл' if f['avia'] else 'выкл'}", "callback_data": "sub_avia"}],
        [{"text": f"🔔 Маркет: {'вкл' if f['market'] else 'выкл'}", "callback_data": "sub_market"},
         {"text": "🔄 Обновить", "callback_data": "refresh"}],
    ]
    if chat == admin_id(): rows.append([{"text": "⚙️ Админ панель", "callback_data": "admin"}])
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

def get_codes(brand, st, force=False):
    c = st["cache"].get(brand, {})
    if force or not c.get("codes"):
        st["cache"][brand] = {"ts": time.time(), "codes": fetch(brand, st)}
    return st["cache"].get(brand, {}).get("codes", {})

def cmd_category(cat, st, chat):
    entries = []
    for b, (c0, title, srcs) in BRANDS.items():
        if c0 != cat: continue
        for c, v in get_codes(b, st).items(): entries.append((b, c, v))
    if not entries:
        send(chat, CATS[cat] + "\n\nКодов пока не нашёл. Нажми «🔄 Обновить» позже."); return
    msg = f"{CATS[cat]} · {len(entries)} кодов\n\n" + render_category(cat, entries, st)
    msg += "\n\n👆 Нажми на код — он скопируется."
    send(chat, msg)

def cmd_old(st, chat):
    old = st.get("old", {})
    if not old: send(chat, "🕘 Старых кодов пока нет."); return
    items = sorted(old.items(), key=lambda kv: kv[1].get("gone", ""), reverse=True)
    msg = "🕘 СТАРЫЕ КОДЫ\n\n" + "\n\n".join(
        block(k.split(":", 1)[1], v) + f"\n🕘 пропал {v.get('gone', '?')} · {BRANDS.get(v.get('brand', ''), ('', '?'))[1]}"
        for k, v in items)
    msg += "\n\nНекоторые ещё срабатывают в корзине."
    send(chat, msg)

def is_quiet(st):
    if not st["settings"].get("quiet"): return False
    h = msk().tm_hour
    return h >= 23 or h < 8

def show_admin(st, chat):
    s = st["settings"]; b = s["budgets"]
    msg = ("⚙️ АДМИН-ПАНЕЛЬ\n\n"
           f"⏱ Интервал: {s['interval']} мин · 🌙 Тихие: {'вкл' if s['quiet'] else 'выкл'} · 📢 Рассылка: {'вкл' if s['broadcast'] else 'выкл'}\n"
           f"💰 Бюджеты: отели {fmt(b['hotel'])} ₽ · авиа {fmt(b['avia'])} ₽ · маркет {fmt(b['market'])} ₽\n"
           f"👥 Подписчиков: {len(st['subs'])} · 🆔 Админ: {admin_id()}")
    kb = {"inline_keyboard": [
        [{"text": f"⏱ {s['interval']} мин", "callback_data": "adm_int"},
         {"text": f"🌙 Тихие: {'вкл' if s['quiet'] else 'выкл'}", "callback_data": "adm_quiet"},
         {"text": f"📢 {'вкл' if s['broadcast'] else 'выкл'}", "callback_data": "adm_bc"}],
        [{"text": f"💰 Отели {fmt(b['hotel'])}", "callback_data": "adm_bud_hotel"},
         {"text": f"💰 Авиа {fmt(b['avia'])}", "callback_data": "adm_bud_avia"},
         {"text": f"💰 Маркет {fmt(b['market'])}", "callback_data": "adm_bud_market"}],
        [{"text": "🩺 Статус", "callback_data": "adm_status"}, {"text": "📡 Источники", "callback_data": "adm_src"}],
        [{"text": "👥 Подписчики", "callback_data": "adm_subs"}, {"text": "📣 Объявление", "callback_data": "adm_ann"}],
        [{"text": "➕ Источник", "callback_data": "adm_add"}, {"text": "⬅️ Назад", "callback_data": "adm_back"}],
    ]}
    tg("sendMessage", chat_id=chat, text=msg, reply_markup=kb)

def show_status(st, chat):
    now = time.time(); s = st["settings"]
    lines = ["🩺 СТАТУС РАДАРА",
             f"Проверка: {msk_str(st['last_poll']) if st['last_poll'] else '—'} МСК · интервал {s['interval']} мин",
             f"Кодов: {len(st['seen'])} · Старых: {len(st['old'])} · Подписчиков: {len(st['subs'])}", ""]
    for cat in CATS:
        lines.append(CATS[cat] + ":")
        for b, name, url, kind in all_sources(st):
            if BRANDS.get(b, ("",))[0] != cat and b in BRANDS: continue
            if b not in BRANDS: continue
            rec = st["http"].get(url, {}); n = len(rec.get("codes", {}))
            if url in st.get("sources_off", []): lines.append(f"⏸ {name} ({b})")
            elif rec.get("backoff", 0) > now: lines.append(f"⚠️ {name} ({b}) {rec.get('err', '')} до {msk_str(rec['backoff'], '%H:%M')}")
            elif rec.get("ok_ts"): lines.append(f"{'✅' if n else '🈳'} {name} ({b}) {n} кодов, {int((now - rec['ok_ts']) / 60)}м")
            else: lines.append(f"⏳ {name} ({b})")
        lines.append("")
    send(chat, "\n".join(lines))

def show_sources(st, chat):
    rows = []; text = ["📡 ИСТОЧНИКИ (нажми — вкл/выкл):"]
    for i, (b, name, url, kind) in enumerate(all_sources(st)):
        on = url not in st.get("sources_off", [])
        rows.append([{"text": f"{'✅' if on else '❌'} {b} · {name}", "callback_data": f"src_{i}"}])
    for i, s in enumerate(st.get("sources_custom", [])):
        rows.append([{"text": f"🗑 {s['url'][:40]}", "callback_data": f"del_{i}"}])
    rows.append([{"text": "⬅️ Назад", "callback_data": "admin"}])
    tg("sendMessage", chat_id=chat, text="\n".join(text), reply_markup={"inline_keyboard": rows})

def handle(u, st):
    if "callback_query" in u:
        q = u["callback_query"]; chat = q["message"]["chat"]["id"]; data = q["data"]
        tg("answerCallbackQuery", callback_query_id=q["id"])
    elif "message" in u and "text" in u["message"]:
        chat = u["message"]["chat"]["id"]; data = u["message"]["text"].strip()
    else: return
    uid = str(chat); low = data.lower()
    admin_cmd = data in ("admin", "adm_int", "adm_quiet", "adm_bc", "adm_status", "adm_src", "adm_subs",
                         "adm_ann", "adm_add", "adm_back", "/admin", "/status") or data.startswith(("src_", "del_", "adm_bud_"))
    if admin_cmd and chat != admin_id(): send(chat, "⛔ Только для админа."); return
    if chat == admin_id() and st.get("await_ann") and "message" in u:
        st["await_ann"] = False
        for c in st["subs"]: send(c, "📣 ОБЪЯВЛЕНИЕ\n\n" + html.escape(data))
        send(chat, "✅ Разослано."); return
    if chat == admin_id() and st.get("await_src") and "message" in u:
        st["await_src"] = False
        parts = data.split(None, 1)
        if len(parts) == 2 and parts[0] in BRANDS and parts[1].startswith("http"):
            st["sources_custom"].append({"brand": parts[0], "name": "Свой источник", "url": parts[1]})
            send(chat, "✅ Источник добавлен!")
        else:
            send(chat, "Формат: бренд ссылка\nБренды: " + " ".join(BRANDS.keys()) + "\nПример: s7 https://www.s7.ru/ru/offers/")
        return
    if low == "/whoami":
        send(chat, f"🆔 Ваш ID: {chat}\nАдмин: {'да ✅' if chat == admin_id() else 'нет'}"); return
    if low == "/start":
        flags(chat)
        if not admin_id(): st["admin"] = chat
        send(chat, "👋 Привет! Радар промокодов: 🏨 отели, ✈️ авиабилеты, 🛍 маркетплейсы.\n"
                   "Жми раздел — покажу все коды, выгодные первыми.\n"
                   "Кнопки 🔔 включают уведомления по разделу.\n"
                   "Команды: /hotel /avia /market /old /stop /whoami"
                   + ("\n⚙️ У тебя кнопка «Админ панель»." if chat == admin_id() else ""))
        return
    if low == "/stop":
        f = flags(chat); f.update({"hotel": False, "avia": False, "market": False})
        send(chat, "🔕 Все уведомления отключены. Кнопки работают."); return
    if low == "/help":
        send(chat, "🏨 /hotel · ✈️ /avia · 🛍 /market\n🕘 /old · 🔕 /stop\nКнопки 🔔 — уведомления по разделам"); return
    if low == "refresh":
        now = time.time()
        if now - st["cool"].get(uid, 0) < COOLDOWN: send(chat, "⏳ Подожди 30 секунд."); return
        st["cool"][uid] = now
        for b in BRANDS: get_codes(b, st, force=True)
        send(chat, "🔄 Обновлено! Жми раздел."); return
    if low in ("cat_hotel", "/hotel"): cmd_category("hotel", st, chat); return
    if low in ("cat_avia", "/avia"): cmd_category("avia", st, chat); return
    if low in ("cat_market", "/market"): cmd_category("market", st, chat); return
    if low in ("old", "/old"): cmd_old(st, chat); return
    if low.startswith("sub_"):
        cat = low[4:]; f = flags(chat); f[cat] = not f[cat]
        send(chat, f"🔔 Уведомления «{CATS[cat]}»: {'вкл ✅' if f[cat] else 'выкл 🔕'}"); return
    if low in ("admin", "/admin"): show_admin(st, chat); return
    if low in ("adm_status", "/status"): show_status(st, chat); return
    if low == "adm_int":
        opts = [5, 10, 15, 30, 60]; cur = st["settings"]["interval"]
        st["settings"]["interval"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 5
        show_admin(st, chat); return
    if low == "adm_quiet": st["settings"]["quiet"] = not st["settings"]["quiet"]; show_admin(st, chat); return
    if low == "adm_bc": st["settings"]["broadcast"] = not st["settings"]["broadcast"]; show_admin(st, chat); return
    if low.startswith("adm_bud_"):
        cat = low[8:]
        opts = {"hotel": [30000, 60000, 100000, 150000], "avia": [5000, 10000, 15000, 30000], "market": [1000, 3000, 5000, 10000]}[cat]
        cur = st["settings"]["budgets"][cat]
        st["settings"]["budgets"][cat] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
        show_admin(st, chat); return
    if low == "adm_src": show_sources(st, chat); return
    if low == "adm_subs":
        cnt = {c: sum(1 for f in st["subs"].values() if f.get(c)) for c in CATS}
        send(chat, "👥 Подписчики (%d):\n%s\nПо разделам: %s" % (
            len(st["subs"]), "\n".join(map(str, st["subs"])) or "пусто",
            " · ".join(f"{CATS[c]} {cnt[c]}" for c in CATS))); return
    if low == "adm_ann": st["await_ann"] = True; send(chat, "📣 Пришли текст объявления."); return
    if low == "adm_add":
        st["await_src"] = True
        send(chat, "➕ Пришли: бренд ссылка\nБренды: " + " ".join(BRANDS.keys()) + "\nПример: s7 https://www.s7.ru/ru/offers/"); return
    if low == "adm_back": send(chat, "⬅️ Главное меню."); return
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
    for b in BRANDS:
        codes = fetch(b, st)
        st["cache"][b] = {"ts": now, "codes": codes}
        for c, v in codes.items(): found[b + ":" + c] = dict(v, brand=b)
    if not found: return
    today = time.strftime("%d.%m.%Y", msk())
    seen = st["seen"]; notified = st.setdefault("notified", {})
    for k, v in found.items():
        if k not in seen and now - notified.get(k, 0) > RENOTIFY:
            st["digest"][k] = v; notified[k] = now
        seen[k] = dict(v, miss=0)
    for k in list(seen):
        if k not in found:
            seen[k]["miss"] = seen[k].get("miss", 0) + 1
            if seen[k]["miss"] >= MISS_LIMIT:
                st["old"][k] = dict(seen[k], gone=today); del seen[k]
    for k in list(notified):
        if now - notified[k] > 2 * RENOTIFY: del notified[k]
    if len(st["old"]) > 500:
        for k in sorted(st["old"], key=lambda x: st["old"][x].get("gone", ""))[:len(st["old"]) - 500]:
            del st["old"][k]
    if st["digest"] and st["subs"] and st["settings"]["broadcast"] and not is_quiet(st):
        for cat in CATS:
            entries = [(v["brand"], k.split(":", 1)[1], v) for k, v in st["digest"].items()
                       if BRANDS.get(v.get("brand", ""), ("",))[0] == cat]
            if not entries: continue
            msg = f"🔔 НОВЫЕ КОДЫ · {CATS[cat]}\n\n" + render_category(cat, entries, st)
            msg += "\n\n👆 Нажми на код — он скопируется."
            for chat, f in st["subs"].items():
                if f.get(cat): send(chat, msg)
        st["digest"] = {}

def main():
    global ST
    ST = load_state(); st = ST
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
        except Exception: time.sleep(5)
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
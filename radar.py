# -*- coding: utf-8 -*-
"""Промокод-радар v10: без deadlock, быстрые ответы."""
import html, json, os, random, re, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ["TG_TOKEN"]
ENV_ADMIN = int(os.environ.get("TG_ADMIN") or os.environ.get("TG_CHAT") or 0)
API = "https://api.telegram.org/bot" + TG_TOKEN
DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DIR, "state.json")
MINIAPP_URL = "https://ujtorm.github.io/promo-radar/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
CATS = {"hotel": "🏨 ОТЕЛИ", "avia": "✈️ АВИАБИЛЕТЫ", "market": "🛍 МАРКЕТПЛЕЙСЫ"}
BRANDS = {
 "ya": ("hotel", "🟡 ЯНДЕКС ПУТЕШЕСТВИЯ", [("Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel"), ("7days", "https://7days.ru/promokodi/yandex-travel")]),
 "os": ("hotel", "🔵 ОСТРОВОК", [("Lovikod", "https://lovikod.ru/travel/promokody-ostrovok"), ("7days", "https://7days.ru/promokodi/ostrovok")]),
 "ozt": ("hotel", "🟣 OZON TRAVEL", [("Lovikod", "https://lovikod.ru/travel/promokody-ozon-travel"), ("7days", "https://7days.ru/promokodi/ozon-travel")]),
 "ot": ("hotel", "🟠 ОТЕЛЛО", [("Lovikod", "https://lovikod.ru/travel/promokody-otello"), ("7days", "https://7days.ru/promokodi/otello")]),
 "tp": ("hotel", "🟢 Т-ПУТЕШЕСТВИЯ", [("Lovikod", "https://lovikod.ru/travel/promokody-t-puteshestviya"), ("7days", "https://7days.ru/promokodi/t-puteshestviya")]),
 "tv": ("hotel", "🧳 TRAVELATA", [("Lovikod", "https://lovikod.ru/travel/promokody-travelata"), ("7days", "https://7days.ru/promokodi/travelata")]),
 "lv": ("hotel", "🧳 LEVEL.TRAVEL", [("Lovikod", "https://lovikod.ru/travel/promokody-level-travel"), ("7days", "https://7days.ru/promokodi/level-travel")]),
 "tu": ("hotel", "🧳 ТУТУ.РУ", [("Lovikod", "https://lovikod.ru/travel/promokody-tutu"), ("7days", "https://7days.ru/promokodi/tutu")]),
 "pb": ("avia", "🟢 ПОБЕДА", [("Lovikod", "https://lovikod.ru/travel/promokody-pobeda"), ("7days", "https://7days.ru/promokodi/pobeda")]),
 "ut": ("avia", "🔵 UTAIR", [("Lovikod", "https://lovikod.ru/travel/promokody-utair"), ("7days", "https://7days.ru/promokodi/utair")]),
 "fz": ("avia", "🟠 FLYDUBAI", [("Lovikod", "https://lovikod.ru/travel/promokody-flydubai"), ("7days", "https://7days.ru/promokodi/flydubai")]),
 "af": ("avia", "🔵 АЭРОФЛОТ", [("Lovikod", "https://lovikod.ru/travel/promokody-aeroflot"), ("7days", "https://7days.ru/promokodi/aeroflot")]),
 "s7": ("avia", "🟢 S7", [("Lovikod", "https://lovikod.ru/travel/promokody-s7"), ("7days", "https://7days.ru/promokodi/s7-airlines")]),
 "ur": ("avia", "🔴 УРАЛЬСКИЕ АВИАЛИНИИ", [("Lovikod", "https://lovikod.ru/travel/promokody-ural-airlines"), ("7days", "https://7days.ru/promokodi/ural-airlines")]),
 "pg": ("avia", "🟡 PEGASUS", [("Lovikod", "https://lovikod.ru/travel/promokody-pegasus"), ("7days", "https://7days.ru/promokodi/pegasus")]),
 "oz": ("market", "🟣 OZON", [("Lovikod", "https://lovikod.ru/promokody-ozon"), ("7days", "https://7days.ru/promokodi/ozon")]),
 "wb": ("market", "🟣 WILDBERRIES", [("Lovikod", "https://lovikod.ru/promokody-wildberries"), ("7days", "https://7days.ru/promokodi/wildberries")]),
 "ym": ("market", "🟡 ЯНДЕКС МАРКЕТ", [("Lovikod", "https://lovikod.ru/promokody-yandex-market"), ("7days", "https://7days.ru/promokodi/yandex-market")]),
 "mm": ("market", "🟢 МЕГАМАРКЕТ", [("Lovikod", "https://lovikod.ru/promokody-megamarket"), ("7days", "https://7days.ru/promokodi/megamarket")]),
 "ali": ("market", "🟠 ALIEXPRESS", [("Lovikod", "https://lovikod.ru/promokody-aliexpress"), ("7days", "https://7days.ru/promokodi/aliexpress")]),
}

CODE = r"[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,}"
CODE_RE = re.compile(r"\b(?:" + CODE + r")\b")
STOP_WORDS = {"ВАЖНО","СКИДКА","СКИДКИ","ПРОМОКОД","ПРОМОКОДЫ","ОСТРОВОК","ЯНДЕКС","ТУРЦИЯ","РОССИЯ","GURU","ГУРУ","RSS","HTML","HTTPS","HTTP","ООО","ИНН","МЕНЮ","ДАТА","СРОК","АКЦИЯ","АКЦИИ","КУПОН","КУПОНЫ","ОТЕЛЬ","ОТЕЛИ","НОЯБРЬ","ДЕКАБРЬ","ЯНВАРЬ","ОТКРЫТЬ","ПОДРОБНЕЕ","ПРОВЕРЕН","ПРОВЕРЕНО","ПЕРВЫЙ","ПОВТОРНЫЙ","ОПИСАНИЕ","OZON","ОТЕЛЛО","TRAVEL","JOURNAL","АЭРОФЛОТ","ПОБЕДА","S7","UTAIR","FLYDUBAI","PEGASUS","WILDBERRIES","ALIEXPRESS","МЕГАМАРКЕТ","МАРКЕТ"}
BAD = re.compile(r"(завершена|завершён|завершен\b|истёк|истек|не действует|expired)", re.I)
CUT = re.compile(r"(истекшие купоны|завершенные промокоды|завершённые промокоды|завершенные купоны)", re.I)

state = None
offset = 0

def clean(s): return re.sub(r"\s+", " ", s).strip()
def num(s): return int(re.sub(r"\s", "", s))
def fmt(n): return f"{n:,}".replace(",", " ")
def msk(t=None): return time.gmtime((t or time.time()) + 3 * 3600)
def msk_str(t, f="%d.%m %H:%M"): return time.strftime(f, msk(t))

def load_state():
    global state, offset
    st = {"subs": {}, "seen": {}, "old": {}, "cache": {}, "http": {}, "notified": {}, "digest": {},
          "last_poll": 0, "sources_off": [], "sources_custom": [],
          "admin": 0,
          "settings": {"interval": 5, "quiet": False, "broadcast": True,
                       "budgets": {"hotel": 60000, "avia": 15000, "market": 5000}}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f: st.update(json.load(f))
        except Exception: pass
    if isinstance(st["subs"], list):
        st["subs"] = {c: {"hotel": True, "avia": True, "market": False} for c in st["subs"]}
    offset = st.get("offset", 0)
    state = st
    return st

def save_state():
    try:
        state["offset"] = offset
        with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(state, f, ensure_ascii=False)
        for cmd in (["git", "add", "state.json"], ["git", "commit", "-m", "state"],
                    ["git", "pull", "--rebase", "origin", "main"], ["git", "push"]):
            subprocess.run(cmd, cwd=DIR, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception: pass

def tg(method, **kw):
    try: return requests.post(API + "/" + method, json=kw, timeout=10).json()
    except Exception: return {}

def admin_id():
    if ENV_ADMIN: return ENV_ADMIN
    if state.get("admin"): return state["admin"]
    if state["subs"]: state["admin"] = next(iter(state["subs"]))
    return state.get("admin", 0)

def flags(chat):
    return state["subs"].setdefault(chat, {"hotel": True, "avia": True, "market": False})

def menu_for(chat):
    f = flags(chat)
    rows = [
        [{"text": "🏨 Отели", "callback_data": "cat_hotel"}, {"text": "✈️ Авиабилеты", "callback_data": "cat_avia"}],
        [{"text": "🛍 Маркетплейсы", "callback_data": "cat_market"}, {"text": "🕘 Старые", "callback_data": "old"}],
        [{"text": f"🔔 Отели: {'вкл' if f['hotel'] else 'выкл'}", "callback_data": "sub_hotel"},
         {"text": f"🔔 Авиа: {'вкл' if f['avia'] else 'выкл'}", "callback_data": "sub_avia"}],
        [{"text": f"🔔 Маркет: {'вкл' if f['market'] else 'выкл'}", "callback_data": "sub_market"},
         {"text": "🔄 Обновить", "callback_data": "refresh"}],
        [{"text": "📱 Мини-апп", "callback_data": "app"}],
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
        tg("sendMessage", **kw); time.sleep(0.15)

def app_keyboard():
    return {"keyboard": [[{"text": "📱 Открыть радар", "web_app": {"url": MINIAPP_URL}}]],
            "resize_keyboard": True, "is_persistent": True}

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

def clean_ctx(code, ctx):
    ctx = re.sub(r"\b" + re.escape(code) + r"\b\s*[—–:→]?\s*", "", ctx, flags=re.I)
    ctx = re.sub(r"промокод\s*[:→]?\s*" + re.escape(code), "", ctx, flags=re.I)
    ctx = re.sub(r"\b" + re.escape(code) + r"\b", "", ctx)
    return re.sub(r"\s+", " ", ctx).strip()

def block(code, v, mark=None, budget=None, aliases=()):
    ctx = clean_ctx(code, v.get("ctx", ""))
    p, a, mn, cap, exp, tags = parse_offer(ctx)
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

def render_category(cat, entries):
    budget = state["settings"]["budgets"][cat]
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

def all_sources():
    out = []
    for b, (cat, title, srcs) in BRANDS.items():
        for name, url in srcs: out.append((b, name, url))
    for s in state.get("sources_custom", []): out.append((s["brand"], s["name"], s["url"]))
    return out

def extract_soup(t):
    soup = BeautifulSoup(t, "html.parser")
    for x in soup(["script", "style", "noscript"]): x.decompose()
    text = soup.get_text("\n")
    m = CUT.search(text)
    if m: text = text[:m.start()]
    flat = clean(text); found = {}
    def add(code, ctx):
        code = code.strip(" .,:;»)(")
        if code != code.upper() or code in STOP_WORDS or code in found or BAD.search(ctx): return
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

def fetch_one(brand, name, url, rec):
    now = time.time(); rec = dict(rec)
    if now < rec.get("backoff", 0): return brand, url, rec, rec.get("codes", {})
    try:
        headers = dict(HEADERS)
        if rec.get("etag"): headers["If-None-Match"] = rec["etag"]
        if rec.get("lm"): headers["If-Modified-Since"] = rec["lm"]
        r = requests.get(url, headers=headers, timeout=(4, 8))
        if r.status_code == 304:
            codes = rec.get("codes", {})
        elif r.status_code in (403, 404, 410, 429):
            rec["backoff"] = now + 6 * 3600; rec["err"] = "HTTP " + str(r.status_code)
            return brand, url, rec, rec.get("codes", {})
        else:
            r.raise_for_status()
            codes = {c: {"ctx": ctx, "src": name} for c, ctx in extract_soup(r.text).items()}
            rec["etag"] = r.headers.get("ETag", ""); rec["lm"] = r.headers.get("Last-Modified", "")
        if codes: rec["empty"] = 0
        else:
            rec["empty"] = rec.get("empty", 0) + 1
            if rec["empty"] >= 3: rec["backoff"] = now + 6 * 3600
        rec["codes"] = codes; rec["ok_ts"] = now; rec["err"] = ""
        return brand, url, rec, codes
    except requests.Timeout:
        rec["backoff"] = now + 2 * 3600; rec["err"] = "timeout"
        return brand, url, rec, rec.get("codes", {})
    except Exception as e:
        rec["backoff"] = now + 2 * 3600; rec["err"] = type(e).__name__
        return brand, url, rec, rec.get("codes", {})

def cycle():
    global state
    t0 = time.time()
    tasks = [(b, n, u) for b, n, u in all_sources() if u not in state["sources_off"]]
    per_brand = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_one, b, n, u, state["http"].get(u, {})): (b, u) for b, n, u in tasks}
        for f in as_completed(futs, timeout=90):
            try: b, url, rec, codes = f.result()
            except Exception: continue
            state["http"][url] = rec
            per_brand.setdefault(b, {})
            for c, v in codes.items(): per_brand[b].setdefault(c, v)
    now = time.time(); found = {}
    for b in BRANDS:
        codes = per_brand.get(b, {})
        state["cache"][b] = {"ts": now, "codes": codes}
        for c, v in codes.items(): found[b + ":" + c] = dict(v, brand=b)
    if not found: return
    today = time.strftime("%d.%m.%Y", msk())
    seen = state["seen"]; notified = state.setdefault("notified", {})
    for k, v in found.items():
        if k not in seen and now - notified.get(k, 0) > 24 * 3600:
            state["digest"][k] = v; notified[k] = now
        seen[k] = dict(v, miss=0)
    for k in list(seen):
        if k not in found:
            seen[k]["miss"] = seen[k].get("miss", 0) + 1
            if seen[k]["miss"] >= 3:
                state["old"][k] = dict(seen[k], gone=today); del seen[k]
    for k in list(notified):
        if now - notified[k] > 2 * 24 * 3600: del notified[k]
    if len(state["old"]) > 500:
        for k in sorted(state["old"], key=lambda x: state["old"][x].get("gone", ""))[:len(state["old"]) - 500]:
            del state["old"][k]
    state["last_poll"] = now
    if state["digest"] and state["subs"] and state["settings"]["broadcast"]:
        s = state["settings"]
        quiet = s.get("quiet") and (msk().tm_hour >= 23 or msk().tm_hour < 8)
        if not quiet:
            for cat in CATS:
                entries = [(v["brand"], k.split(":", 1)[1], v) for k, v in state["digest"].items()
                           if BRANDS.get(v.get("brand", ""), ("",))[0] == cat]
                if not entries: continue
                msg = f"🔔 НОВЫЕ КОДЫ · {CATS[cat]}\n\n" + render_category(cat, entries)
                msg += "\n\n👆 Нажми на код — он скопируется."
                for chat, f in state["subs"].items():
                    if f.get(cat): send(chat, msg)
            state["digest"] = {}
    save_state()
    print(f"[cycle] {len(tasks)} sources, {time.time()-t0:.1f}s", flush=True)

def worker():
    while True:
        try: cycle()
        except Exception as e: print(f"[worker] {e}", flush=True)
        iv = state["settings"]["interval"] * 60
        time.sleep(iv)

def handle_message(u):
    global offset
    if "message" in u and "web_app_data" in u.get("message", {}):
        msg = u["message"]; chat = msg["chat"]["id"]
        try: ops = json.loads(msg["web_app_data"]["data"]).get("ops", [])
        except Exception: return
        is_adm = chat == admin_id(); done = []
        for op in ops:
            t = op.get("t")
            if t == "sub" and op.get("cat") in CATS:
                f = state["subs"].setdefault(chat, {"hotel": True, "avia": True, "market": False})
                f[op["cat"]] = bool(op.get("v")); done.append("подписка " + op["cat"])
            elif not is_adm: continue
            elif t == "set" and op.get("k") in ("interval", "quiet", "broadcast"):
                state["settings"][op["k"]] = op.get("v"); done.append(op["k"])
            elif t == "budget" and op.get("cat") in CATS:
                state["settings"]["budgets"][op["cat"]] = int(op.get("v", 0)); done.append("бюджет")
            elif t == "src_off":
                off, url = state["sources_off"], op.get("url", "")
                if op.get("v") and url not in off: off.append(url)
                if not op.get("v") and url in off: off.remove(url)
                done.append("источник")
            elif t == "src_add" and op.get("brand") in BRANDS and str(op.get("url", "")).startswith("http"):
                state["sources_custom"].append({"brand": op["brand"], "name": "Из приложения", "url": op["url"]}); done.append("источник+")
            elif t == "src_del":
                i = int(op.get("i", -1))
                if 0 <= i < len(state["sources_custom"]): state["sources_custom"].pop(i); done.append("источник−")
            elif t == "ann" and op.get("text"):
                for c in state["subs"]: send(c, "📣 ОБЪЯВЛЕНИЕ\n\n" + html.escape(op["text"][:1500]))
                done.append("объявление")
        save_state()
        send(chat, "✅ Применено: " + (", ".join(done) if done else "нет изменений"))
        tg("sendMessage", chat_id=chat, text="📱 Радар:", reply_markup=app_keyboard())
        return
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
    if chat == admin_id() and state.get("await_ann") and "message" in u:
        state["await_ann"] = False
        for c in state["subs"]: send(c, "📣 ОБЪЯВЛЕНИЕ\n\n" + html.escape(data))
        send(chat, "✅ Разослано."); return
    if chat == admin_id() and state.get("await_src") and "message" in u:
        state["await_src"] = False
        parts = data.split(None, 1)
        if len(parts) == 2 and parts[0] in BRANDS and parts[1].startswith("http"):
            state["sources_custom"].append({"brand": parts[0], "name": "Свой источник", "url": parts[1]})
            send(chat, "✅ Источник добавлен!")
        else:
            send(chat, "Формат: бренд ссылка\nБренды: " + " ".join(BRANDS.keys()))
        return
    if low == "/whoami":
        send(chat, f"🆔 Ваш ID: {chat}\nАдмин: {'да ✅' if chat == admin_id() else 'нет'}"); return
    if low == "/start":
        flags(chat)
        if not admin_id(): state["admin"] = chat
        send(chat, "👋 Привет! Радар промокодов: 🏨 отели, ✈️ авиабилеты, 🛍 маркетплейсы.\n"
                   "Жми раздел — все коды, выгодные первыми. Кнопки 🔔 — уведомления по разделам.\n"
                   "Команды: /hotel /avia /market /old /stop /whoami /app"
                   + ("\n⚙️ У тебя кнопка «Админ панель»." if chat == admin_id() else ""))
        tg("sendMessage", chat_id=chat, text="📱 Открой радар как мини-апп:", reply_markup=app_keyboard())
        return
    if low == "/app":
        tg("sendMessage", chat_id=chat, text="📱 Радар:", reply_markup=app_keyboard()); return
    if low == "app":
        tg("sendMessage", chat_id=chat, text="📱 Открой мини-апп кнопкой под клавиатурой 👇", reply_markup=app_keyboard()); return
    if low == "/stop":
        f = flags(chat); f.update({"hotel": False, "avia": False, "market": False})
        send(chat, "🔕 Все уведомления отключены."); return
    if low == "/help":
        send(chat, "🏨 /hotel · ✈️ /avia · 🛍 /market\n🕘 /old · 🔕 /stop · 📱 /app\nКнопки 🔔 — уведомления по разделам"); return
    if low == "refresh":
        now = time.time()
        if now - state["cool"].get(uid, 0) < 20: send(chat, "⏳ Подожди 20 секунд."); return
        state["cool"][uid] = now
        send(chat, "🔄 Запустил обновление в фоне — свежие данные через ~минуту."); return
    if low in ("cat_hotel", "/hotel"):
        entries = []
        for b, (c0, title, srcs) in BRANDS.items():
            if c0 != cat: continue
            for c, v in state["cache"].get(b, {}).get("codes", {}).items(): entries.append((b, c, v))
        if not entries:
            send(chat, CATS["hotel"] + "\n\n⏳ Данные собираются в фоне (~1 мин). Нажми 🔄 или загляни чуть позже."); return
        msg = f"{CATS['hotel']} · {len(entries)} кодов\n\n" + render_category("hotel", entries)
        msg += "\n\n👆 Нажми на код — он скопируется."
        send(chat, msg); return
    if low in ("cat_avia", "/avia"):
        entries = []
        for b, (c0, title, srcs) in BRANDS.items():
            if c0 != "avia": continue
            for c, v in state["cache"].get(b, {}).get("codes", {}).items(): entries.append((b, c, v))
        if not entries:
            send(chat, CATS["avia"] + "\n\n⏳ Данные собираются в фоне (~1 мин)."); return
        msg = f"{CATS['avia']} · {len(entries)} кодов\n\n" + render_category("avia", entries)
        msg += "\n\n👆 Нажми на код — он скопируется."
        send(chat, msg); return
    if low in ("cat_market", "/market"):
        entries = []
        for b, (c0, title, srcs) in BRANDS.items():
            if c0 != "market": continue
            for c, v in state["cache"].get(b, {}).get("codes", {}).items(): entries.append((b, c, v))
        if not entries:
            send(chat, CATS["market"] + "\n\n⏳ Данные собираются в фоне (~1 мин)."); return
        msg = f"{CATS['market']} · {len(entries)} кодов\n\n" + render_category("market", entries)
        msg += "\n\n👆 Нажми на код — он скопируется."
        send(chat, msg); return
    if low in ("old", "/old"):
        old = state.get("old", {})
        if not old: send(chat, "🕘 Старых кодов пока нет."); return
        items = sorted(old.items(), key=lambda kv: kv[1].get("gone", ""), reverse=True)
        msg = "🕘 СТАРЫЕ КОДЫ\n\n" + "\n\n".join(
            block(k.split(":", 1)[1], v) + f"\n🕘 пропал {v.get('gone', '?')} · {BRANDS.get(v.get('brand', ''), ('', '?'))[1]}"
            for k, v in items)
        msg += "\n\nНекоторые ещё срабатывают в корзине."
        send(chat, msg); return
    if low.startswith("sub_"):
        cat = low[4:]; f = flags(chat); f[cat] = not f[cat]
        send(chat, f"🔔 «{CATS[cat]}»: {'вкл ✅' if f[cat] else 'выкл 🔕'}"); return
    if low in ("admin", "/admin"):
        s = state["settings"]; b = s["budgets"]
        msg = ("⚙️ АДМИН-ПАНЕЛЬ\n\n"
               f"⏱ Интервал: {s['interval']} мин · 🌙 Тихие: {'вкл' if s['quiet'] else 'выкл'} · 📢 Рассылка: {'вкл' if s['broadcast'] else 'выкл'}\n"
               f"💰 Бюджеты: отели {fmt(b['hotel'])} · авиа {fmt(b['avia'])} · маркет {fmt(b['market'])}\n"
               f"👥 Подписчиков: {len(state['subs'])} · 🆔 Админ: {admin_id()}")
        kb = {"inline_keyboard": [
            [{"text": f"⏱ {s['interval']} мин", "callback_data": "adm_int"},
             {"text": f"🌙 {'вкл' if s['quiet'] else 'выкл'}", "callback_data": "adm_quiet"},
             {"text": f"📢 {'вкл' if s['broadcast'] else 'выкл'}", "callback_data": "adm_bc"}],
            [{"text": f"💰 Отели {fmt(b['hotel'])}", "callback_data": "adm_bud_hotel"},
             {"text": f"💰 Авиа {fmt(b['avia'])}", "callback_data": "adm_bud_avia"},
             {"text": f"💰 Маркет {fmt(b['market'])}", "callback_data": "adm_bud_market"}],
            [{"text": "🩺 Статус", "callback_data": "adm_status"}, {"text": "📡 Источники", "callback_data": "adm_src"}],
            [{"text": "👥 Подписчики", "callback_data": "adm_subs"}, {"text": "📣 Объявление", "callback_data": "adm_ann"}],
            [{"text": "➕ Источник", "callback_data": "adm_add"}, {"text": "⬅️ Назад", "callback_data": "adm_back"}],
        ]}
        tg("sendMessage", chat_id=chat, text=msg, reply_markup=kb); return
    if low in ("adm_status", "/status"):
        now = time.time(); s = state["settings"]
        lines = ["🩺 СТАТУС РАДАРА",
                 f"Проверка: {msk_str(state['last_poll']) if state['last_poll'] else '—'} МСК · интервал {s['interval']} мин",
                 f"Кодов: {len(state['seen'])} · Старых: {len(state['old'])} · Подписчиков: {len(state['subs'])}", ""]
        for cat in CATS:
            lines.append(CATS[cat] + ":")
            for b, name, url in all_sources():
                if b not in BRANDS or BRANDS[b][0] != cat: continue
                rec = state["http"].get(url, {}); n = len(rec.get("codes", {}))
                if url in state.get("sources_off", []): lines.append(f"⏸ {name} ({b})")
                elif rec.get("backoff", 0) > now: lines.append(f"⚠️ {name} ({b}) {rec.get('err', '')} до {msk_str(rec['backoff'], '%H:%M')}")
                elif rec.get("ok_ts"): lines.append(f"{'✅' if n else '🈳'} {name} ({b}) {n} кодов, {int((now - rec['ok_ts']) / 60)}м")
                else: lines.append(f"⏳ {name} ({b})")
            lines.append("")
        send(chat, "\n".join(lines)); return
    if low == "adm_int":
        opts = [5, 10, 15, 30, 60]; cur = state["settings"]["interval"]
        state["settings"]["interval"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 5
        save_state(); send(chat, f"⏱ Интервал: {state['settings']['interval']} мин"); return
    if low == "adm_quiet": state["settings"]["quiet"] = not state["settings"]["quiet"]; save_state(); send(chat, f"🌙 Тихие: {'вкл' if state['settings']['quiet'] else 'выкл'}"); return
    if low == "adm_bc": state["settings"]["broadcast"] = not state["settings"]["broadcast"]; save_state(); send(chat, f"📢 Рассылка: {'вкл' if state['settings']['broadcast'] else 'выкл'}"); return
    if low.startswith("adm_bud_"):
        cat = low[8:]
        opts = {"hotel": [30000, 60000, 100000, 150000], "avia": [5000, 10000, 15000, 30000], "market": [1000, 3000, 5000, 10000]}[cat]
        cur = state["settings"]["budgets"][cat]
        state["settings"]["budgets"][cat] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
        save_state(); send(chat, f"💰 Бюджет {cat}: {fmt(state['settings']['budgets'][cat])}"); return
    if low == "adm_src":
        rows = []
        for i, (b, name, url) in enumerate(all_sources()):
            on = url not in state.get("sources_off", [])
            rows.append([{"text": f"{'✅' if on else '❌'} {b} · {name}", "callback_data": f"src_{i}"}])
        for i, s in enumerate(state.get("sources_custom", [])):
            rows.append([{"text": f"🗑 {s['url'][:40]}", "callback_data": f"del_{i}"}])
        rows.append([{"text": "⬅️ Назад", "callback_data": "admin"}])
        tg("sendMessage", chat_id=chat, text="📡 ИСТОЧНИКИ (нажми — вкл/выкл):", reply_markup={"inline_keyboard": rows}); return
    if low == "adm_subs":
        cnt = {c: sum(1 for f in state["subs"].values() if f.get(c)) for c in CATS}
        send(chat, "👥 Подписчики (%d):\n%s\nПо разделам: %s" % (
            len(state["subs"]), "\n".join(map(str, state["subs"])) or "пусто",
            " · ".join(f"{CATS[c]} {cnt[c]}" for c in CATS))); return
    if low == "adm_ann": state["await_ann"] = True; send(chat, "📣 Пришли текст объявления."); return
    if low == "adm_add":
        state["await_src"] = True
        send(chat, "➕ Пришли: бренд ссылка\nБренды: " + " ".join(BRANDS.keys())); return
    if low == "adm_back": send(chat, "⬅️ Главное меню."); return
    if data.startswith("src_"):
        i = int(data[4:]); srcs = all_sources()
        if i < len(srcs):
            url = srcs[i][2]; off = state["sources_off"]
            if url in off: off.remove(url)
            else: off.append(url)
        save_state(); send(chat, "✅ Источник обновлён"); return
    if data.startswith("del_"):
        i = int(data[4:])
        if i < len(state["sources_custom"]): state["sources_custom"].pop(i)
        save_state(); send(chat, "🗑 Источник удалён"); return
    send(chat, "Не понял 🙂 Нажми кнопку ниже.")

def main():
    global state, offset
    load_state()
    th = threading.Thread(target=worker, daemon=True); th.start()
    last_save = time.time()
    while True:
        try:
            r = requests.get(API + "/getUpdates", params={"offset": offset, "timeout": 50}, timeout=60).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                try: handle_message(u)
                except Exception as e: print(f"[handle] {e}", flush=True)
        except Exception as e:
            print(f"[poll] {e}", flush=True); time.sleep(3)
        if time.time() - last_save > 30:
            save_state(); last_save = time.time()

if __name__ == "__main__":
    main()
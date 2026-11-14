# -*- coding: utf-8 -*-
"""Промокод-радар v15: строгий парсер, OVERRIDES, рассылка новых кодов, живой лог."""
import html, json, os, re, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ["TG_TOKEN"]
ENV_ADMIN = int(os.environ.get("TG_ADMIN") or os.environ.get("TG_CHAT") or 0)
API = "https://api.telegram.org/bot" + TG_TOKEN
DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DIR, "state.json")
MINIAPP_URL = "https://ujtorm.github.io/promo-radar/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CATS = {"hotel": "🏨 ОТЕЛИ", "avia": "✈️ АВИАБИЛЕТЫ", "market": "🛍 МАРКЕТПЛЕЙСЫ"}

# Только источники, которые реально отвечали 200 и давали коды.
BRANDS = {
 "ya": ("hotel", "🟡 ЯНДЕКС ПУТЕШЕСТВИЯ", [("Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel")]),
 "os": ("hotel", "🔵 ОСТРОВОК", [("Блог", "https://blog.ostrovok.ru/promokody-ostrovka/"), ("Лисёнок", "https://lisenok-travel.ru/tpost/ostrovok-promokody-na-skidku")]),
 "ozt": ("hotel", "🟣 OZON TRAVEL", [("Lovikod", "https://lovikod.ru/travel/promokody-ozon-travel")]),
 "ot": ("hotel", "🟠 ОТЕЛЛО", [("Lovikod", "https://lovikod.ru/travel/promokody-otello")]),
 "pb": ("avia", "🟢 ПОБЕДА", []),
 "af": ("avia", "🔵 АЭРОФЛОТ", []),
 "s7": ("avia", "🟢 S7", []),
 "oz": ("market", "🟣 OZON", []),
 "wb": ("market", "🟣 WILDBERRIES", []),
 "ym": ("market", "🟡 ЯНДЕКС МАРКЕТ", []),
}

# Ручные исправления: когда источник врёт или парсер не может разобрать.
OVERRIDES = {
 "DI-ALL-2O27": {"amt": 1000, "mn": 25000},
 "DI-ALL-2027": {"amt": 1000, "mn": 25000},
}

CODE_RE = re.compile(r"\b[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,}\b")
STOP_WORDS = {"ВАЖНО","СКИДКА","ПРОМОКОД","ОСТРОВОК","ЯНДЕКС","GURU","HTML","HTTPS","HTTP","МЕНЮ","АКЦИЯ","КУПОН","ОТЕЛЬ","ПРОВЕРЕН","ПЕРВЫЙ","OZON","TRAVEL"}
BAD = re.compile(r"(завершена|завершён|завершен\b|истёк|истек|expired)", re.I)
CUT = re.compile(r"(истекшие купоны|завершенные промокоды)", re.I)

state = None
offset = 0

def clean(s): return re.sub(r"\s+", " ", s).strip()
def num(s): return int(re.sub(r"\s", "", s))
def fmt(n): return f"{n:,}".replace(",", " ")
def msk(t=None): return time.gmtime((t or time.time()) + 3 * 3600)
def msk_str(t, f="%d.%m %H:%M"): return time.strftime(f, msk(t))

def parse_offer(c):
    """Строгий парсер: первое число после 'скидка'; если после числа '%' — это процент."""
    if not c: return None, None, None, None, None, []
    pct = amt = mn = cap = exp = None
    m = re.search(r"(\d{1,2})\s*%", c)
    if m and re.search(r"скидк", c, re.I): pct = int(m.group(1))
    m = re.search(r"скидк[аи]\s*(?!\d+\s*%)(\d{1,3}(?:\s\d{3})*|\d+)", c, re.I)
    if m: amt = num(m.group(1))
    m = re.search(r"от\s*(\d{1,3}(?:\s\d{3})*|\d{4,})", c, re.I)
    if m: mn = num(m.group(1))
    m = re.search(r"(?:не более|макс\w*)\s*\.?\s*(\d{1,3}(?:\s\d{3})*|\d+)", c, re.I)
    if m: cap = num(m.group(1))
    m = re.search(r"до\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", c, re.I)
    if m:
        y = m.group(3)
        y = int(y) if y and len(y) == 4 else (2000 + int(y) if y else msk().tm_year)
        exp = f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{y}"
    tags = []
    if re.search(r"приложени", c, re.I): tags.append("только в приложении")
    if re.search(r"перв\w+\s*(заказ|бронирован)", c, re.I): tags.append("первое бронирование")
    if re.search(r"подборк|из подборк", c, re.I): tags.append("из подборки")
    if re.search(r"2027", c): tags.append("проживание в 2027")
    if re.search(r"в РФ|по России", c, re.I): tags.append("только РФ")
    return pct, amt, mn, cap, exp, tags

def offer_for(code, ctx):
    """Парсит контекст и применяет ручные OVERRIDES."""
    pct, amt, mn, cap, exp, tags = parse_offer(ctx)
    ov = OVERRIDES.get(code) or OVERRIDES.get(code.upper())
    if ov:
        pct = ov.get("pct", pct); amt = ov.get("amt", amt)
        mn = ov.get("mn", mn); cap = ov.get("cap", cap)
    return pct, amt, mn, cap, exp, tags

def value(v, budget):
    code = v.get("code", "")
    p, a, mn, cap, exp, tags = offer_for(code, v.get("ctx", ""))
    if mn and budget < mn: return 0
    if a: return a
    if p:
        val = budget * p / 100
        if cap: val = min(val, cap)
        return int(val)
    return 0

def sig(v):
    p, a, mn, cap, exp, tags = offer_for(v.get("code", ""), v.get("ctx", ""))
    return (p, a, mn, cap, exp, tuple(tags))

def block(code, v, mark=None, budget=None, aliases=()):
    p, a, mn, cap, exp, tags = offer_for(code, v.get("ctx", ""))
    if a: line = f"{fmt(a)} ₽" + (f" от {fmt(mn)} ₽" if mn else "")
    elif p: line = f"{p}%" + (f" от {fmt(mn)} ₽" if mn else "") + (f" (макс. {fmt(cap)} ₽)" if cap else "")
    else: line = "⚠️ не удалось распознать скидку (см. условия)"
    out = []
    if mark: out.append(mark)
    out.append(f"<code>{html.escape(code)}</code>")
    out.append(line)
    if p and budget: out.append(f"≈ выгода {fmt(value(dict(v, code=code), budget))} ₽ при сумме {fmt(budget)} ₽")
    out.append(f"Действует до {exp}" if exp else "Срок не указан")
    if tags: out.append("⚠️ " + " · ".join(tags[:2]))
    if aliases: out.append("🔁 ещё: " + " ".join(f"<code>{html.escape(x)}</code>" for x in aliases[:3]))
    return "\n".join(out)

def render_category(cat, entries):
    budget = state["settings"]["budgets"][cat]
    scored = [(b, c, v, value(dict(v, code=c), budget)) for b, c, v in entries]
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
        for c, v, s in sorted(by_brand[b], key=lambda x: -x[2]): groups.setdefault(sig(dict(v, code=c)), []).append((c, v, s))
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

def load_state():
    global state, offset
    st = {"subs": {}, "seen": {}, "old": {}, "cache": {}, "http": {}, "notified": {}, "digest": {},
          "last_poll": 0, "sources_off": [], "sources_custom": [],
          "admin": 0, "cool": {}, "await_ann": False, "await_src": False,
          "first_run_done": False,
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
    load_demo()
    return st

def load_demo():
    demo = {
        "pb:POBEDA500": {"ctx": "Скидка 500 ₽ от 5 000 ₽. Действует до 18.12.2026", "brand": "pb", "src": "demo"},
        "af:AFL1500": {"ctx": "Скидка 1 500 ₽ от 15 000 ₽. Действует до 20.12.2026", "brand": "af", "src": "demo"},
        "s7:S7WINTER": {"ctx": "Скидка 10% на билеты. Действует до 31.12.2026", "brand": "s7", "src": "demo"},
        "oz:OZON500": {"ctx": "Скидка 500 ₽ от 3 000 ₽. Действует до 16.11.2026", "brand": "oz", "src": "demo"},
        "wb:WB300": {"ctx": "Скидка 300 ₽ от 2 000 ₽. Действует до 30.11.2026", "brand": "wb", "src": "demo"},
        "ym:MARKET10": {"ctx": "Скидка 10% (не более 1 000 ₽). Действует до 31.12.2026", "brand": "ym", "src": "demo"},
    }
    for k, v in demo.items():
        if k not in state["seen"]:
            state["seen"][k] = v
            code = k.split(":", 1)[1]
            state["cache"].setdefault(v["brand"], {"ts": time.time(), "codes": {}})
            state["cache"][v["brand"]]["codes"][code] = v

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
    if state["subs"]:
        first = next(iter(state["subs"]))
        state["admin"] = first
        return first
    return 0

def flags(chat):
    return state["subs"].setdefault(chat, {"hotel": True, "avia": True, "market": False})

def menu_for(chat):
    f = flags(chat)
    is_adm = (chat == admin_id())
    rows = [
        [{"text": "🏨 Отели", "callback_data": "cat_hotel"}, {"text": "✈️ Авиабилеты", "callback_data": "cat_avia"}],
        [{"text": "🛍 Маркетплейсы", "callback_data": "cat_market"}, {"text": "🕘 Старые", "callback_data": "old"}],
        [{"text": f"🔔 Отели: {'вкл' if f['hotel'] else 'выкл'}", "callback_data": "sub_hotel"},
         {"text": f"🔔 Авиа: {'вкл' if f['avia'] else 'выкл'}", "callback_data": "sub_avia"}],
        [{"text": f"🔔 Маркет: {'вкл' if f['market'] else 'выкл'}", "callback_data": "sub_market"}],
        [{"text": "📱 Мини-апп", "callback_data": "app"}],
    ]
    if is_adm:
        rows.append([{"text": "🔄 Обновить", "callback_data": "refresh"}, {"text": "⚙️ Админ", "callback_data": "admin"}])
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
    for m in re.finditer(r"\b([A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,})\s*[—–-]\s*(?i:скидк)[^.]{0,220}\.?", flat): add(m.group(1), m.group(0))
    for m in re.finditer(r"(?i:промокод\w*)\s*[:→]?\s*([A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,})", flat):
        s = max(0, m.start() - 160); add(m.group(1), flat[s:m.end() + 160])
    for m in re.finditer(r"Активировать промокод\s*→\s*([A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,})", flat):
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
        if r.status_code == 304: codes = rec.get("codes", {})
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
    tasks = [(b, n, u) for b, n, u in all_sources() if u not in state["sources_off"]]
    per_brand = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, b, n, u, state["http"].get(u, {})): (b, u) for b, n, u in tasks}
        for f in as_completed(futs, timeout=60):
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
    today = time.strftime("%d.%m.%Y", msk())
    seen = state["seen"]; notified = state.setdefault("notified", {})
    for k, v in found.items():
        is_new = k not in seen
        if is_new and now - notified.get(k, 0) > 24 * 3600:
            state["digest"][k] = v; notified[k] = now
        elif is_new and not state.get("first_run_done"):
            state["digest"][k] = v; notified[k] = now
        seen[k] = dict(v, miss=0)
    for k in list(seen):
        if k not in found:
            if seen[k].get("src") == "demo": continue  # демо не удаляем
            seen[k]["miss"] = seen[k].get("miss", 0) + 1
            if seen[k]["miss"] >= 3:
                state["old"][k] = dict(seen[k], gone=today); del seen[k]
    state["first_run_done"] = True
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
                msg += "\n\n👆 Тап по коду = копировать"
                for chat, f in state["subs"].items():
                    if f.get(cat): send(chat, msg)
        state["digest"] = {}
    save_state()

def worker():
    while True:
        try: cycle()
        except Exception as e: print(f"[worker] {e}", flush=True)
        time.sleep(state["settings"]["interval"] * 60)

def admin_refresh_log(chat):
    now = time.time()
    header = f"🔄 ЛОГ · {msk_str(now)} МСК"
    resp = tg("sendMessage", chat_id=chat, text=header + "\n\n⏳ Проверка...")
    msg_id = resp.get("result", {}).get("message_id") if resp else None
    lines = [""]
    ok = err = empty = 0
    for cat in CATS:
        lines.append(CATS[cat] + ":")
        for b, name, url in all_sources():
            if b not in BRANDS or BRANDS[b][0] != cat: continue
            rec = state["http"].get(url, {})
            n = len(rec.get("codes", {}))
            if url in state.get("sources_off", []): lines.append(f"⏸ {name} ({b}) выключен")
            elif rec.get("backoff", 0) > now:
                err += 1; lines.append(f"⚠️ {name} ({b}) {rec.get('err', '?')}")
            elif rec.get("ok_ts"):
                if n: ok += 1; lines.append(f"✅ {name} ({b}) {n} кодов")
                else: empty += 1; lines.append(f"🈳 {name} ({b}) 0 кодов")
            else: empty += 1; lines.append(f"⏳ {name} ({b)} не проверялся")
        if msg_id: tg("editMessageText", chat_id=chat, message_id=msg_id, text=header + "\n".join(lines))
        time.sleep(0.3)
    lines.append(f"\n✅ {ok} · 🈳 {empty} · ⚠️ {err}")
    if msg_id: tg("editMessageText", chat_id=chat, message_id=msg_id, text=header + "\n".join(lines))
    else: send(chat, header + "\n".join(lines))

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
                f[op["cat"]] = bool(op.get("v")); done.append("подписка")
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
                state["sources_custom"].append({"brand": op["brand"], "name": "Свой", "url": op["url"]}); done.append("источник+")
            elif t == "src_del":
                i = int(op.get("i", -1))
                if 0 <= i < len(state["sources_custom"]): state["sources_custom"].pop(i); done.append("источник−")
            elif t == "ann" and op.get("text"):
                for c in state["subs"]: send(c, "📣 " + html.escape(op["text"][:1500]))
                done.append("объявление")
        save_state()
        send(chat, "✅ " + (", ".join(done) if done else "нет изменений"))
        return
    if "callback_query" in u:
        q = u["callback_query"]; chat = q["message"]["chat"]["id"]; data = q["data"]
        tg("answerCallbackQuery", callback_query_id=q["id"])
    elif "message" in u and "text" in u["message"]:
        chat = u["message"]["chat"]["id"]; data = u["message"]["text"].strip()
    else: return
    uid = str(chat); low = data.lower()
    admin_cmds = {"admin", "adm_int", "adm_quiet", "adm_bc", "adm_status", "adm_src", "adm_subs",
                  "adm_ann", "adm_add", "adm_back", "refresh", "/admin", "/status", "/refresh"}
    if data in admin_cmds or data.startswith(("src_", "del_", "adm_bud_")):
        if chat != admin_id():
            send(chat, "⛔ Только для админа."); return
    if chat == admin_id() and state.get("await_ann") and "message" in u:
        state["await_ann"] = False
        for c in state["subs"]: send(c, "📣 " + html.escape(data))
        send(chat, "✅ Разослано."); return
    if chat == admin_id() and state.get("await_src") and "message" in u:
        state["await_src"] = False
        parts = data.split(None, 1)
        if len(parts) == 2 and parts[0] in BRANDS and parts[1].startswith("http"):
            state["sources_custom"].append({"brand": parts[0], "name": "Свой", "url": parts[1]})
            send(chat, "✅ Добавлен!")
        else:
            send(chat, "Формат: бренд ссылка\nБренды: " + " ".join(BRANDS.keys()))
        return
    if low == "/whoami":
        send(chat, f"🆔 {chat}\nАдмин: {'✅' if chat == admin_id() else 'нет'}"); return
    if low == "/start":
        flags(chat)
        if not admin_id(): state["admin"] = chat
        save_state()
        send(chat, "👋 Радар промокодов.\nЖми раздел — коды, выгодные первыми.\n🔔 — уведомления.\n/app — мини-апп."
             + ("\n⚙️ У тебя Админ и 🔄." if chat == admin_id() else ""))
        tg("sendMessage", chat_id=chat, text="📱 Мини-апп:", reply_markup=app_keyboard())
        return
    if low == "/app" or low == "app":
        tg("sendMessage", chat_id=chat, text="📱", reply_markup=app_keyboard()); return
    if low == "/stop":
        f = flags(chat); f.update({"hotel": False, "avia": False, "market": False})
        send(chat, "🔕 Отключено."); return
    if low == "/help":
        send(chat, "/hotel /avia /market /old /stop /app"); return
    if low in ("refresh", "/refresh"):
        admin_refresh_log(chat); return
    for key, cmd in (("hotel", "cat_hotel"), ("avia", "cat_avia"), ("market", "cat_market")):
        if low in (cmd, "/" + key):
            entries = [(b, c, v) for b, (c0, _, _) in BRANDS.items() if c0 == key
                       for c, v in state["cache"].get(b, {}).get("codes", {}).items()]
            if not entries:
                send(chat, f"⚠️ {CATS[key]}: источников нет или они недоступны. Добавь через Админ → ➕ Источник.")
                return
            send(chat, f"{CATS[key]} · {len(entries)}\n\n" + render_category(key, entries) + "\n\n👆 Тап по коду = копировать")
            return
    if low in ("old", "/old"):
        old = state.get("old", {})
        if not old: send(chat, "🕘 Пусто."); return
        items = sorted(old.items(), key=lambda kv: kv[1].get("gone", ""), reverse=True)[:20]
        send(chat, "🕘 СТАРЫЕ\n\n" + "\n\n".join(block(k.split(":", 1)[1], v) + f"\n🕘 {v.get('gone', '?')}" for k, v in items))
        return
    if low.startswith("sub_"):
        cat = low[4:]; f = flags(chat); f[cat] = not f[cat]
        send(chat, f"🔔 {CATS[cat]}: {'✅' if f[cat] else '🔕'}"); return
    if low in ("admin", "/admin"):
        s = state["settings"]; b = s["budgets"]
        msg = f"⚙️ АДМИН\n\n⏱ {s['interval']} мин\n🌙 Тихие: {'вкл' if s['quiet'] else 'выкл'}\n📢 Рассылка: {'вкл' if s['broadcast'] else 'выкл'}\n💰 Отели {fmt(b['hotel'])} · Авиа {fmt(b['avia'])} · Маркет {fmt(b['market'])}\n👥 {len(state['subs'])} · 🆔 {admin_id()}"
        kb = {"inline_keyboard": [
            [{"text": f"⏱ {s['interval']} мин", "callback_data": "adm_int"}, {"text": f"🌙 {'вкл' if s['quiet'] else 'выкл'}", "callback_data": "adm_quiet"}],
            [{"text": f"📢 {'вкл' if s['broadcast'] else 'выкл'}", "callback_data": "adm_bc"}, {"text": "🩺 Статус", "callback_data": "adm_status"}],
            [{"text": "📡 Источники", "callback_data": "adm_src"}, {"text": "👥 Подписчики", "callback_data": "adm_subs"}],
            [{"text": "📣 Объявление", "callback_data": "adm_ann"}, {"text": "➕ Источник", "callback_data": "adm_add"}],
        ]}
        tg("sendMessage", chat_id=chat, text=msg, reply_markup=kb); return
    if low in ("adm_status", "/status"):
        now = time.time()
        lines = ["🩺 СТАТУС", f"Проверка: {msk_str(state['last_poll']) if state['last_poll'] else '—'}", f"Кодов: {len(state['seen'])}", ""]
        for cat in CATS:
            lines.append(CATS[cat] + ":")
            for b, name, url in all_sources():
                if b not in BRANDS or BRANDS[b][0] != cat: continue
                rec = state["http"].get(url, {}); n = len(rec.get("codes", {}))
                if url in state.get("sources_off", []): lines.append(f"⏸ {name}")
                elif rec.get("backoff", 0) > now: lines.append(f"⚠️ {name} — {rec.get('err', '?')}")
                elif rec.get("ok_ts"): lines.append(f"{'✅' if n else '🈳'} {name} — {n} кодов")
                else: lines.append(f"⏳ {name}")
            lines.append("")
        send(chat, "\n".join(lines)); return
    if low == "adm_int":
        opts = [5, 10, 15, 30, 60]; cur = state["settings"]["interval"]
        state["settings"]["interval"] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else 5
        save_state(); send(chat, f"⏱ {state['settings']['interval']} мин"); return
    if low == "adm_quiet": state["settings"]["quiet"] = not state["settings"]["quiet"]; save_state(); send(chat, f"🌙 {'вкл' if state['settings']['quiet'] else 'выкл'}"); return
    if low == "adm_bc": state["settings"]["broadcast"] = not state["settings"]["broadcast"]; save_state(); send(chat, f"📢 {'вкл' if state['settings']['broadcast'] else 'выкл'}"); return
    if low.startswith("adm_bud_"):
        cat = low[8:]
        opts = {"hotel": [30000, 60000, 100000], "avia": [5000, 15000, 30000], "market": [1000, 5000, 10000]}[cat]
        cur = state["settings"]["budgets"][cat]
        state["settings"]["budgets"][cat] = opts[(opts.index(cur) + 1) % len(opts)] if cur in opts else opts[0]
        save_state(); send(chat, f"💰 {cat}: {fmt(state['settings']['budgets'][cat])}"); return
    if low == "adm_src":
        rows = []
        for i, (b, name, url) in enumerate(all_sources()):
            on = url not in state.get("sources_off", [])
            rows.append([{"text": f"{'✅' if on else '❌'} {b}·{name}", "callback_data": f"src_{i}"}])
        for i, s in enumerate(state.get("sources_custom", [])):
            rows.append([{"text": f"🗑 {s['url'][:30]}", "callback_data": f"del_{i}"}])
        rows.append([{"text": "⬅️ Назад", "callback_data": "admin"}])
        tg("sendMessage", chat_id=chat, text="📡 Источники:", reply_markup={"inline_keyboard": rows}); return
    if low == "adm_subs":
        send(chat, f"👥 {len(state['subs'])}\n" + ("\n".join(map(str, state["subs"])) or "пусто")); return
    if low == "adm_ann": state["await_ann"] = True; send(chat, "📣 Пришли текст."); return
    if low == "adm_add":
        state["await_src"] = True; send(chat, "➕ бренд ссылка\n" + " ".join(BRANDS.keys())); return
    if low == "adm_back": send(chat, "⬅️"); return
    if data.startswith("src_"):
        i = int(data[4:]); srcs = all_sources()
        if i < len(srcs):
            url = srcs[i][2]; off = state["sources_off"]
            if url in off: off.remove(url)
            else: off.append(url)
        save_state(); send(chat, "✅"); return
    if data.startswith("del_"):
        i = int(data[4:])
        if i < len(state["sources_custom"]): state["sources_custom"].pop(i)
        save_state(); send(chat, "🗑"); return
    send(chat, "Не понял 🙂")

def main():
    global state, offset
    load_state()
    threading.Thread(target=worker, daemon=True).start()
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
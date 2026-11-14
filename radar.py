# -*- coding: utf-8 -*-
"""Радар промокодов: Яндекс Путешествия + Островок -> Telegram."""
import html, json, os, re, time
import requests
from bs4 import BeautifulSoup

TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT  = os.environ["TG_CHAT"]
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SOURCES = [
    ("Островок · официальный блог", "https://blog.ostrovok.ru/promokody-ostrovka/"),
    ("Островок · Лисёнок", "https://lisenok-travel.ru/tpost/ostrovok-promokody-na-skidku"),
    ("Яндекс Путешествия · Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel"),
]
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

def extract(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
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

def tg_send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
              "disable_web_page_preview": True}, timeout=30)
    r.raise_for_status()
    time.sleep(1)

def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    seen = state.get("seen", {})
    first_run = not seen
    found, errors = {}, []
    for name, url in SOURCES:
        try:
            for code, ctx in extract(url).items():
                found.setdefault(code, {"source": name, "ctx": ctx})
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}")
    if not found:
        if errors:
            tg_send("⚠️ Радар промокодов: источники недоступны.\n" + "\n".join(errors))
        return
    new = {c: v for c, v in found.items() if c not in seen}
    if first_run:
        items = list(found.items())[:20]
        header = f"✅ Радар запущен! Сейчас активно {len(found)} кодов. Основные:"
    elif new:
        items = list(new.items())
        header = f"🔔 Новые промокоды ({len(new)}):"
    else:
        items, header = [], ""
    if items:
        msg = header
        for code, v in items:
            block = (f"\n\n<b>{html.escape(code)}</b>\n"
                     f"{html.escape(v['ctx'])}\n<i>{html.escape(v['source'])}</i>")
            if len(msg) + len(block) > 3500:
                tg_send(msg)
                msg = ""
            msg += block
        msg += "\n\nПроверяй скидку в корзине перед оплатой 😉"
        tg_send(msg)
    for c, v in found.items():
        seen[c] = v
    state["seen"] = seen
    state["last_check"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
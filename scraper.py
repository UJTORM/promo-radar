# -*- coding: utf-8 -*-
"""Сборщик промокодов. Без Telegram. Пишет state.json, который читает сайт."""
import json, os, re, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(DIR, "state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SOURCES = [
 ("ya", "Lovikod", "https://lovikod.ru/travel/promokody-yandex-travel"),
 ("os", "Блог Островка", "https://blog.ostrovok.ru/promokody-ostrovka/"),
 ("os", "Лисёнок", "https://lisenok-travel.ru/tpost/ostrovok-promokody-na-skidku"),
 ("ozt", "Lovikod", "https://lovikod.ru/travel/promokody-ozon-travel"),
 ("ot", "Lovikod", "https://lovikod.ru/travel/promokody-otello"),
]
CODE_RE = re.compile(r"\b[A-ZА-ЯЁ][A-ZА-ЯЁ0-9\-]{3,}\b")
STOP = {"ВАЖНО","СКИДКА","ПРОМОКОД","ОСТРОВОК","ЯНДЕКС","GURU","HTML","HTTPS","HTTP","МЕНЮ","АКЦИЯ","КУПОН","ОТЕЛЬ","ПРОВЕРЕН","ПЕРВЫЙ","OZON","TRAVEL"}
BAD = re.compile(r"(завершена|завершён|завершен\b|истёк|истек|expired)", re.I)
CUT = re.compile(r"(истекшие купоны|завершенные промокоды)", re.I)

def clean(s): return re.sub(r"\s+", " ", s).strip()

def extract(text):
    soup = BeautifulSoup(text, "html.parser")
    for x in soup(["script", "style", "noscript"]): x.decompose()
    t = soup.get_text("\n")
    m = CUT.search(t)
    if m: t = t[:m.start()]
    flat = clean(t); found = {}
    def add(code, ctx):
        code = code.strip(" .,:;»)(")
        if code != code.upper() or code in STOP or code in found or BAD.search(ctx): return
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
    if now < rec.get("backoff", 0): return url, rec, rec.get("codes", {})
    try:
        h = dict(HEADERS)
        if rec.get("etag"): h["If-None-Match"] = rec["etag"]
        r = requests.get(url, headers=h, timeout=(4, 8))
        if r.status_code == 304: codes = rec.get("codes", {})
        elif r.status_code in (403, 404, 410, 429):
            rec["backoff"] = now + 6 * 3600; rec["err"] = "HTTP " + str(r.status_code)
            return url, rec, rec.get("codes", {})
        else:
            r.raise_for_status()
            codes = {c: {"ctx": ctx, "src": name, "brand": brand} for c, ctx in extract(r.text).items()}
            rec["etag"] = r.headers.get("ETag", "")
        rec["codes"] = codes; rec["ok_ts"] = now; rec["err"] = ""
        return url, rec, codes
    except Exception as e:
        rec["backoff"] = now + 2 * 3600; rec["err"] = type(e).__name__
        return url, rec, rec.get("codes", {})

def main():
    t0 = time.time()
    st = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f: st = json.load(f)
        except Exception: pass
    st.setdefault("seen", {}); st.setdefault("old", {}); st.setdefault("http", {}); st.setdefault("log", [])
    per = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(fetch_one, b, n, u, st["http"].get(u, {})) for b, n, u in SOURCES]
        for f in as_completed(futs, timeout=60):
            try: url, rec, codes = f.result()
            except Exception: continue
            st["http"][url] = rec
            for c, v in codes.items(): per[c] = v
    now = time.time(); today = time.strftime("%d.%m.%Y", time.gmtime(now + 3 * 3600))
    for c, v in per.items():
        st["seen"][c] = dict(v, miss=0)
    for c in list(st["seen"]):
        if c not in per and st["seen"][c].get("src") != "demo":
            st["seen"][c]["miss"] = st["seen"][c].get("miss", 0) + 1
            if st["seen"][c]["miss"] >= 3:
                st["old"][c] = dict(st["seen"][c], gone=today); del st["seen"][c]
    errs = [f"{u.split('//')[-1][:20]}:{r.get('err')}" for u, r in st["http"].items() if r.get("err")]
    st["log"] = (st["log"] + [{
        "ts": time.strftime("%d.%m %H:%M", time.gmtime(now + 3 * 3600)),
        "dur": round(time.time() - t0, 1),
        "total": len(per),
        "errs": errs,
    }])[-30:]
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(st, f, ensure_ascii=False)
    subprocess.run(["git", "add", "state.json"], cwd=DIR)
    subprocess.run(["git", "commit", "-m", f"state: {len(per)} codes"], cwd=DIR)
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=DIR)
    subprocess.run(["git", "push"], cwd=DIR)
    print(f"[scraper] {len(per)} codes, {time.time()-t0:.1f}s, errs={errs}", flush=True)

if __name__ == "__main__":
    main()
import os, re, json, sqlite3, difflib
from common import strip_accents, MIN_ATTENDANCE

DB_PATH = os.environ.get("DB_PATH", "data/events.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY, name TEXT, province TEXT, venue TEXT,
  start_date TEXT, end_date TEXT, time_text TEXT, attendance INTEGER,
  fireworks INTEGER DEFAULT 0, concert INTEGER DEFAULT 0,
  urls TEXT, alerted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS seen(url TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS health(name TEXT PRIMARY KEY, fails INTEGER);
CREATE TABLE IF NOT EXISTS tries(url TEXT PRIMARY KEY, n INTEGER DEFAULT 0);
"""


def conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def seen(c, url):
    return c.execute("SELECT 1 FROM seen WHERE url=?", (url,)).fetchone() is not None


def mark_seen(c, url):
    c.execute("INSERT OR IGNORE INTO seen(url) VALUES(?)", (url,))
    c.commit()


def bump_try(c, url):
    """Đếm số lần đã thử một bài (khi chưa đọc được nội dung). Trả về số lần."""
    c.execute("INSERT INTO tries(url,n) VALUES(?,1) ON CONFLICT(url) DO UPDATE SET n=n+1", (url,))
    c.commit()
    return c.execute("SELECT n FROM tries WHERE url=?", (url,)).fetchone()["n"]


def get_meta(c, k):
    r = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r["v"] if r else None


def set_meta(c, k, v):
    c.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
    c.commit()


def record_health(c, name, ok):
    """Ghi nhận nguồn chạy tốt/lỗi. Trả về số lần lỗi liên tiếp."""
    r = c.execute("SELECT fails FROM health WHERE name=?", (name,)).fetchone()
    fails = 0 if ok else (r["fails"] if r else 0) + 1
    c.execute("INSERT INTO health(name,fails) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET fails=excluded.fails",
              (name, fails))
    c.commit()
    return fails


def _same(a, b):
    """Hai tên có phải cùng một sự kiện không (so sánh không dấu, bỏ dấu câu)."""
    na, nb = strip_accents(a), strip_accents(b)
    if difflib.SequenceMatcher(None, na, nb).ratio() >= 0.6:
        return True
    ta, tb = re.findall(r"\w+", na), re.findall(r"\w+", nb)
    if len(set(ta) & set(tb)) / max(1, min(len(set(ta)), len(set(tb)))) >= 0.7:
        return True
    # có chung một cụm từ liên tiếp >= 3 từ (vd: "ok om bok")
    m = difflib.SequenceMatcher(None, ta, tb).find_longest_match(0, len(ta), 0, len(tb))
    return m.size >= 3


def upsert_event(c, ev, url):
    """Thêm sự kiện mới, hoặc gộp vào sự kiện đã có (cùng tỉnh, ngày lệch <=1, tên giống nhau).
    Trả về (id, is_new)."""
    rows = c.execute(
        "SELECT * FROM events WHERE province=? AND start_date BETWEEN date(?, '-1 day') AND date(?, '+1 day')",
        (ev["province"], ev["start_date"], ev["start_date"])).fetchall()
    for r in rows:
        if _same(r["name"], ev["name"]):
            urls = json.loads(r["urls"])
            if url not in urls:
                urls.append(url)
            att = max(r["attendance"] or 0, ev["attendance"] or 0) or None
            c.execute(
                "UPDATE events SET urls=?, attendance=?, fireworks=?, concert=?, "
                "venue=COALESCE(venue,?), end_date=COALESCE(end_date,?), time_text=COALESCE(time_text,?) WHERE id=?",
                (json.dumps(urls), att, int(bool(r["fireworks"] or ev["fireworks"])),
                 int(bool(r["concert"] or ev["concert"])), ev["venue"], ev["end_date"], ev["time_text"], r["id"]))
            c.commit()
            return r["id"], False
    cur = c.execute(
        "INSERT INTO events(name,province,venue,start_date,end_date,time_text,attendance,fireworks,concert,urls) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (ev["name"], ev["province"], ev["venue"], ev["start_date"], ev["end_date"], ev["time_text"],
         ev["attendance"], int(ev["fireworks"]), int(ev["concert"]), json.dumps([url])))
    c.commit()
    return cur.lastrowid, True


def get_event(c, event_id):
    return dict(c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())


def set_alerted(c, event_id):
    c.execute("UPDATE events SET alerted=1 WHERE id=?", (event_id,))
    c.commit()


def upcoming(c, d_from, d_to):
    """Sự kiện có khoảng ngày giao với [d_from, d_to] (định dạng YYYY-MM-DD)."""
    rows = c.execute(
        "SELECT * FROM events WHERE COALESCE(end_date,start_date) >= ? AND start_date <= ? "
        "AND COALESCE(attendance,0) >= ? ORDER BY start_date, name", (d_from, d_to, MIN_ATTENDANCE)).fetchall()
    return [dict(r) for r in rows]

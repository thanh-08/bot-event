import json, re, time, urllib.parse
import feedparser, requests, yaml
from bs4 import BeautifulSoup
from common import PROVINCES

UA = {"User-Agent": "Mozilla/5.0 (compatible; EventBot/1.0)"}
GN_MAX_PER_RUN = 30      # số link Google News giải mã tối đa mỗi lần chạy (tránh bị Google chặn 429)
_gn = {"n": 0, "blocked": False}
ERRORS = []          # mẫu lỗi khi đọc bài/giải mã link (để in ra chẩn đoán)


def _note(kind, msg):
    msg = f"{kind}: {' '.join(str(msg).split())[:140]}"
    if msg not in ERRORS and len(ERRORS) < 6:
        ERRORS.append(msg)


def load_sources():
    with open("sources.yaml", encoding="utf-8") as f:
        sources = yaml.safe_load(f)["sources"]
    for p in PROVINCES:
        q = urllib.parse.quote(f"lễ hội OR sự kiện OR pháo hoa OR đại nhạc hội OR concert OR liveshow OR đêm nhạc {p} when:14d")
        sources.append({
            "name": f"Google News - {p}",
            "url": f"https://news.google.com/rss/search?q={q}&hl=vi&gl=VN&ceid=VN:vi",
            "province": p,
        })
    return sources


def _text(html):
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


# Dạng link bài báo của các báo địa phương: ...-a132968.html | ...-post874811.html | /chuyen-muc/202610/ten-bai-ab12cd3/
ARTICLE_RE = re.compile(r"(-a\d{4,}\.html|-post\d{4,}\.html|/\d{6}/[^/]+/?$)")


def fetch_html_source(src):
    """Báo không có RSS: đọc trang chủ/chuyên mục, lấy các link trông giống link bài báo (cùng tên miền)."""
    r = requests.get(src["url"], headers=UA, timeout=20)
    r.raise_for_status()
    host = urllib.parse.urlparse(src["url"]).netloc.replace("www.", "")
    pat = re.compile(src["article_re"]) if src.get("article_re") else ARTICLE_RE
    items, seen = [], set()
    for a in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
        url = urllib.parse.urljoin(src["url"], a["href"]).split("#")[0]
        if url in seen or urllib.parse.urlparse(url).netloc.replace("www.", "") != host or not pat.search(url):
            continue
        title = " ".join((a.get("title") or a.get_text(" ", strip=True)).split())
        if len(title) < 20:                  # link ảnh/nút "xem thêm" -> bỏ
            continue
        seen.add(url)
        items.append({"source": src["name"], "title": title, "url": url, "summary": "",
                      "hint_province": src.get("province")})
    return items


def fetch_source(src):
    if src.get("type") == "html":
        return fetch_html_source(src)
    r = requests.get(src["url"], headers=UA, timeout=20)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    items = []
    for e in feed.entries:
        items.append({
            "source": src["name"],
            "title": _text(e.get("title", "")),
            "url": urllib.parse.urljoin(src["url"], e.get("link", "")),
            "summary": _text(e.get("summary", "")),
            "hint_province": src.get("province"),
        })
    return items


_GN_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"}


def _gn_params(b64):
    """Lấy chữ ký + mốc thời gian từ trang bài Google News (cần cho bước giải mã)."""
    last = "không tìm thấy thẻ chứa chữ ký"
    for path in ("articles", "rss/articles"):
        r = requests.get(f"https://news.google.com/{path}/{b64}", headers=_GN_HEADERS, timeout=15)
        r.raise_for_status()
        el = BeautifulSoup(r.text, "html.parser").select_one("c-wiz > div[jscontroller]")
        if el is not None and el.get("data-n-a-sg") and el.get("data-n-a-ts"):
            return el["data-n-a-sg"], el["data-n-a-ts"]
    raise RuntimeError(last)


def set_gn_blocked():
    _gn["blocked"] = True


def gn_blocked():
    return _gn["blocked"]


def gn_available():
    """Còn được phép giải mã link Google News trong lần chạy này không."""
    return not _gn["blocked"] and _gn["n"] < GN_MAX_PER_RUN


def _resolve_google_news(url):
    """Link Google News chỉ là trang chuyển hướng; giải mã để lấy link bài gốc. Lỗi thì trả None.
    (Tự viết thay cho thư viện googlenewsdecoder vì thư viện đó hỏng khi selectolax >= 1.0.)"""
    _gn["n"] += 1
    try:
        parts = urllib.parse.urlparse(url).path.split("/")
        if len(parts) < 2 or parts[-2] not in ("articles", "read"):
            _note("giải mã Google News", "link không đúng dạng /articles/<mã>")
            return None
        b64 = parts[-1]
        sig, ts = _gn_params(b64)
        inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
                 f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{b64}",{ts},"{sig}"]')
        payload = json.dumps([[["Fbv4je", inner]]])
        r = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                          headers={**_GN_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                          data="f.req=" + urllib.parse.quote(payload), timeout=15)
        r.raise_for_status()
        parsed = json.loads(r.text.split("\n\n")[1])[:-2]
        real = json.loads(parsed[0][2])[1]
        if real and real.startswith("http"):
            time.sleep(2)           # giãn cách để Google không chặn
            return real
        _note("giải mã Google News", "kết quả không phải link")
    except Exception as e:
        if "429" in str(e):
            _gn["blocked"] = True   # Google đang chặn: dừng giải mã đến hết lần chạy này
        _note("giải mã Google News", repr(e))
    return None


def fetch_article(url):
    """Trả về (link_thật, nội_dung_bài). Lỗi thì nội dung rỗng."""
    if not url:
        return url, ""
    real = url
    if "news.google.com" in url:
        real = _resolve_google_news(url)
        if not real:
            return url, ""
    try:
        r = requests.get(real, headers=UA, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        body = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))[:4000]
        return real, body
    except Exception as e:
        _note("đọc bài " + real.split("/")[2] if "//" in real else "đọc bài", e)
        return real, ""

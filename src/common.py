import os, re, unicodedata
from datetime import datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))
BIG_ATTENDANCE = 10000


def now_vn():
    return datetime.now(VN_TZ)


def load_env(path=".env"):
    """Đọc file .env (nếu có) vào biến môi trường. Biến đã có sẵn thì giữ nguyên."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def strip_accents(s):
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


# 8 tỉnh/thành theo đề bài + tên các địa phương cũ đã sáp nhập (từ 1/7/2025)
PROVINCES = {
    "TP. Hồ Chí Minh": ["tp.hcm", "tphcm", "tp hcm", "thành phố hồ chí minh", "sài gòn",
                        "bình dương", "thủ dầu một", "bà rịa", "vũng tàu", "côn đảo"],
    "Đồng Nai": ["biên hòa", "bình phước", "đồng xoài"],
    "Tây Ninh": ["long an", "tân an", "núi bà đen"],
    "An Giang": ["kiên giang", "phú quốc", "rạch giá", "hà tiên", "châu đốc", "long xuyên"],
    "Đồng Tháp": ["tiền giang", "mỹ tho", "cao lãnh", "sa đéc"],
    "Vĩnh Long": ["bến tre", "trà vinh"],
    "Cần Thơ": ["sóc trăng", "hậu giang", "ninh kiều"],
    "Cà Mau": ["bạc liêu", "đất mũi"],
}

EVENT_KEYWORDS = [
    "lễ hội", "vía bà", "ok om bok", "chôl chnăm thmây", "cúng đình", "khai mạc", "bế mạc",
    "pháo hoa", "countdown", "đại nhạc hội", "đêm nhạc", "concert", "festival", "hội chợ",
    "triển lãm", "giải chạy", "marathon", "lễ kỷ niệm", "đua ghe", "ngày hội", "hội nghị",
    "nghỉ lễ", "kỳ nghỉ", "dịp lễ", "tết", "giải đấu",
]


def _count(norm_text, terms):
    n = 0
    for t in terms:
        pat = r"(?<![a-z0-9])" + re.escape(strip_accents(t)) + r"(?![a-z0-9])"
        n += len(re.findall(pat, norm_text))
    return n


def has_event_kw(text):
    return _count(strip_accents(text), EVENT_KEYWORDS) > 0


def find_province(text):
    """Trả về tên tỉnh (trong 8 tỉnh) xuất hiện nhiều nhất trong text, hoặc None."""
    norm = strip_accents(text)
    best, best_n = None, 0
    for name, aliases in PROVINCES.items():
        n = _count(norm, [name] + aliases)
        if n > best_n:
            best, best_n = name, n
    return best


def is_big(ev):
    return (ev.get("attendance") or 0) >= BIG_ATTENDANCE or bool(ev.get("fireworks")) or bool(ev.get("concert"))


def priority(ev):
    if is_big(ev):
        return "CAO"
    if (ev.get("attendance") or 0) >= 3000 or "le hoi" in strip_accents(ev.get("name", "")):
        return "TB"
    return "THẤP"


_DATE_HINT = [r"\d{1,2}\s*/\s*\d{1,2}", r"ngay\s+\d{1,2}", r"thang\s+\d{1,2}", r"\d{1,2}\s*(?:-|den)\s*\d{1,2}\s*/"]


def has_date_hint(text):
    """Bài có dấu hiệu nêu ngày cụ thể không (vd: 17/10, ngày 5, tháng 11). Không có thì AI cũng không trích được ngày."""
    norm = strip_accents(text)
    return any(re.search(pat, norm) for pat in _DATE_HINT)

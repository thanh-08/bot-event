import os, re, unicodedata
from datetime import date, datetime, timezone, timedelta

VN_TZ = timezone(timedelta(hours=7))
BIG_ATTENDANCE = 10000
# Bản tin, lệnh tra cứu và Excel chỉ hiển thị sự kiện lớn (xem is_visible). Đặt 0 để hiển thị tất cả sự kiện.
# Sự kiện bị ẩn vẫn được lưu trong cơ sở dữ liệu.
MIN_ATTENDANCE = 10000


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
    "nghỉ lễ", "kỳ nghỉ", "dịp lễ", "tết", "giải đấu", "đông đúc", "tấp nập", "nhạc hội", 
    "cúng đình", "hội", 
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


# ---------------------------------------------------------------- mức ưu tiên đối với mạng lưới
# Điểm = quy mô + địa điểm. CAO nếu quy mô lớn (is_big) hoặc điểm >= PRIORITY_HIGH; TB nếu điểm >= PRIORITY_MID.
# Có thể thêm/bớt địa điểm trọng điểm và lễ hội lớn ở hai danh sách dưới đây (không cần sửa code khác).
PRIORITY_HIGH = 5
PRIORITY_MID = 3

# Địa điểm trọng điểm của mạng: (từ khóa, điểm 1-3). Lấy địa điểm có điểm cao nhất tìm thấy trong tên/địa điểm sự kiện.
HOTSPOTS = [
    # đầu mối giao thông
    ("sân bay", 3), ("tân sơn nhất", 3), ("sân bay long thành", 3), ("cảng", 2), ("bến xe", 1),
    # khu du lịch, điểm tập trung đông khách
    ("núi bà đen", 3), ("núi sam", 3), ("phú quốc", 3), ("vinwonders", 3), ("landmark 81", 3),
    ("nguyễn huệ", 3), ("phố đi bộ", 2), ("bến ninh kiều", 3), ("ninh kiều", 2), ("chợ nổi", 2),
    ("đầm sen", 2), ("suối tiên", 2), ("thảo cầm viên", 2), ("bến bạch đằng", 2), ("cần giờ", 2),
    ("vũng tàu", 2), ("côn đảo", 2), ("đất mũi", 2), ("châu đốc", 2), ("rạch giá", 1),
    ("khu du lịch", 2), ("khu di tích", 2), ("sân vận động", 2), ("trung tâm hội chợ", 2), ("secc", 3),
    ("nhà thi đấu", 1), ("quảng trường", 1), ("công viên", 1),
]

# Lễ hội truyền thống/tín ngưỡng thường rất đông người dù báo không nêu con số.
BIG_FESTIVALS = ["nguyễn trung trực", "bà chúa xứ", "vía bà", "ok om bok", "nghinh ông", "chôl chnăm thmây",
                 "chol chnam thmay", "sene dolta", "bà đen", "đua ghe ngo", "cúng đình", "kỳ yên"]

# Đô thị lớn, mật độ người dùng cao: cộng thêm điểm.
DENSE_PROVINCES = {"TP. Hồ Chí Minh": 1}

PRIORITY_NAMES = {"CAO": "Cao", "TB": "Trung bình", "THẤP": "Thấp"}


def is_visible(ev):
    """Sự kiện có được hiển thị không: từ MIN_ATTENDANCE người, hoặc có pháo hoa, hoặc đại nhạc hội,
    hoặc là lễ hội truyền thống lớn (BIG_FESTIVALS) dù báo không nêu số người."""
    if MIN_ATTENDANCE <= 0:
        return True
    if (ev.get("attendance") or 0) >= MIN_ATTENDANCE or ev.get("fireworks") or ev.get("concert"):
        return True
    return bool(_count(strip_accents(f"{ev.get('name') or ''} {ev.get('venue') or ''}"), BIG_FESTIVALS))


def is_big(ev):
    return (ev.get("attendance") or 0) >= BIG_ATTENDANCE or bool(ev.get("fireworks")) or bool(ev.get("concert"))


def priority_info(ev):
    """Trả về (nhãn 'CAO'|'TB'|'THẤP', điểm, [các lý do]) theo quy mô và địa điểm."""
    text = strip_accents(f"{ev.get('name') or ''} {ev.get('venue') or ''}")
    pts, why = 0, []

    att = ev.get("attendance") or 0
    if att >= 20000:
        pts += 4
    elif att >= BIG_ATTENDANCE:
        pts += 3
    elif att >= 5000:
        pts += 2
    elif att >= 1000:
        pts += 1
    if att >= 1000:
        why.append(f"quy mô ~{att:,} người".replace(",", "."))
    if ev.get("fireworks"):
        pts += 2
        why.append("có bắn pháo hoa")
    if ev.get("concert"):
        pts += 2
        why.append("đại nhạc hội/đêm nhạc lớn")

    try:
        days = (date.fromisoformat(ev["end_date"]) - date.fromisoformat(ev["start_date"])).days + 1
    except (KeyError, TypeError, ValueError):
        days = 1
    if days >= 3:
        pts += 1
        why.append(f"kéo dài {days} ngày")

    fest = [t for t in BIG_FESTIVALS if _count(text, [t])]
    if fest:
        pts += 3
        why.append("lễ hội truyền thống lớn")
    elif _count(text, ["lễ hội"]):
        pts += 1
    if _count(text, ["quốc tế", "quốc gia", "countdown", "marathon", "giải chạy", "festival", "liên hoan"]):
        pts += 1

    spots = [(p, k) for k, p in HOTSPOTS if _count(text, [k])]
    if spots:
        p, k = max(spots)
        pts += p
        why.append(f"địa điểm trọng điểm: {k}")
    dense = DENSE_PROVINCES.get(ev.get("province"), 0)
    if dense:
        pts += dense
        why.append(f"đô thị lớn ({ev['province']})")

    if is_big(ev) or pts >= PRIORITY_HIGH:
        label = "CAO"
    elif pts >= PRIORITY_MID:
        label = "TB"
    else:
        label = "THẤP"
    return label, pts, why


def priority(ev):
    return priority_info(ev)[0]


_DATE_HINT = [r"\d{1,2}\s*/\s*\d{1,2}", r"ngay\s+\d{1,2}", r"thang\s+\d{1,2}", r"\d{1,2}\s*(?:-|den)\s*\d{1,2}\s*/"]


def has_date_hint(text):
    """Bài có dấu hiệu nêu ngày cụ thể không (vd: 17/10, ngày 5, tháng 11). Không có thì AI cũng không trích được ngày."""
    norm = strip_accents(text)
    return any(re.search(pat, norm) for pat in _DATE_HINT)

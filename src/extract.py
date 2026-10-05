import os, re, json, time
from datetime import date, timedelta
import requests
from common import PROVINCES, strip_accents

MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")

PROMPT = """Hôm nay là {today}. Đọc bài báo dưới đây và trích xuất thông tin MỘT sự kiện/lễ hội chính.
Chỉ trả về một đối tượng JSON, không viết thêm gì khác, gồm các khóa:
- is_event: true nếu bài nói về sự kiện/lễ hội sắp diễn ra hoặc đang diễn ra; false nếu đã kết thúc, chỉ là tin tổng kết, hoặc không có sự kiện cụ thể
- name: tên sự kiện (ngắn gọn)
- province: một trong {provinces}, hoặc null nếu sự kiện diễn ra ngoài 8 tỉnh/thành này (ví dụ Hà Nội, Đà Nẵng, Lai Châu). Hãy suy luận từ địa danh (ví dụ Cần Giờ, Thủ Đức thuộc TP. Hồ Chí Minh; Phú Quốc thuộc An Giang). Lưu ý: Sóc Trăng, Hậu Giang thuộc Cần Thơ; Bình Dương, Bà Rịa - Vũng Tàu thuộc TP. Hồ Chí Minh; Long An thuộc Tây Ninh; Bến Tre, Trà Vinh thuộc Vĩnh Long; Tiền Giang thuộc Đồng Tháp; Kiên Giang thuộc An Giang; Bạc Liêu thuộc Cà Mau; Bình Phước thuộc Đồng Nai
- venue: địa điểm cụ thể (xã/phường, khu vực, tên địa điểm) hoặc null
- start_date: YYYY-MM-DD (dương lịch) hoặc null (nếu bài không nêu rõ ngày thì để null, KHÔNG đoán)
- end_date: YYYY-MM-DD (dương lịch) hoặc null
- lunar_start: CHỈ điền khi bài nêu ngày diễn ra theo ÂM LỊCH mà KHÔNG kèm ngày dương lịch tương ứng; dạng "D/M" (ví dụ "27/8" là 27 tháng 8 âm lịch), nếu không thì null. Khi đó để start_date = null, KHÔNG tự đổi sang dương lịch
- lunar_end: tương tự lunar_start cho ngày kết thúc (hoặc null)
- time_text: giờ bắt đầu dạng chữ (ví dụ "19:00") hoặc null
- attendance: số người dự kiến (số nguyên) hoặc null (KHÔNG đoán). Nếu bài chỉ dùng cách nói ước lượng thì quy đổi theo mức thấp nhất của cách nói đó: "hàng trăm nghìn" = 100000, "hàng chục nghìn/ngàn" = 20000, "hàng vạn" = 10000, "hàng nghìn/ngàn" = 2000. "Biển người", "đông người", "đông đảo" mà không có con số thì để null
- fireworks: true nếu có bắn pháo hoa
- concert: true nếu là concert/liveshow/đại nhạc hội của nghệ sĩ nổi tiếng, hoặc diễn ra ở sân vận động, quảng trường hay khu đô thị lớn

Tiêu đề: {title}
Nội dung: {text}"""


_last_call = [0.0]


def _parse_json(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else None


class QuotaExceeded(Exception):
    """Mọi mô hình Gemini đều hết hạn mức miễn phí hoặc không dùng được."""


class _ModelOut(Exception):
    """Một mô hình cụ thể không dùng được (404 hoặc hết hạn mức)."""


_dead = set()   # các mô hình đã hết hạn mức/không tồn tại trong lần chạy này


def _models():
    raw = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite,gemini-3.8-flash"
    return [m.strip() for m in raw.split(",") if m.strip()]


def _gemini_model(prompt, key, model):
    """Gọi một mô hình Gemini. Lỗi tạm thời (5xx) thì chờ rồi thử lại; hết hạn mức/404 thì báo _ModelOut."""
    wait = 7 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    waits_5xx = [6, 15, 30]
    tried_429 = False
    attempt = 0
    while True:
        r = requests.post(url, headers={"x-goog-api-key": key, "content-type": "application/json"},
                          json=body, timeout=60)
        _last_call[0] = time.time()
        if r.status_code == 200:
            return _parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        if r.status_code == 404:
            raise _ModelOut("không tồn tại hoặc đã ngừng")
        if r.status_code == 429:
            if "PerDay" in r.text or tried_429:      # hết hạn mức ngày, hoặc đã chờ mà vẫn bị chặn
                raise _ModelOut("hết hạn mức miễn phí")
            tried_429 = True
            print(f"  [Gemini] {model}: vượt giới hạn tốc độ (429), chờ 40s rồi thử lại 1 lần...")
            time.sleep(40)
            continue
        if r.status_code in (500, 502, 503, 504) and attempt < len(waits_5xx):
            print(f"  [Gemini] {model}: máy chủ báo {r.status_code} (quá tải tạm thời), chờ {waits_5xx[attempt]}s rồi thử lại...")
            time.sleep(waits_5xx[attempt])
            attempt += 1
            continue
        raise RuntimeError(f"Gemini lỗi {r.status_code}: {' '.join(r.text.split())[:200]}")


def _call_gemini(prompt, key):
    """Thử lần lượt các mô hình trong GEMINI_MODEL (cách nhau dấu phẩy) cho đến khi có mô hình dùng được."""
    notes = []
    for model in _models():
        if model in _dead:
            continue
        try:
            return _gemini_model(prompt, key, model)
        except _ModelOut as e:
            _dead.add(model)
            notes.append(f"{model} {e}")
            print(f"  [Gemini] mô hình {model} {e} -> chuyển mô hình khác")
    raise QuotaExceeded("; ".join(notes) or "không còn mô hình Gemini nào khả dụng")


def _call_claude(prompt, key):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"LLM lỗi {r.status_code}: {r.text[:150]}")
    return _parse_json(r.json()["content"][0]["text"])


def _call_llm(prompt):
    """Ưu tiên Gemini (miễn phí) nếu có GEMINI_API_KEY, sau đó Claude; không có khóa nào thì trả None."""
    if os.environ.get("GEMINI_API_KEY"):
        return _call_gemini(prompt, os.environ["GEMINI_API_KEY"])
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _call_claude(prompt, os.environ["ANTHROPIC_API_KEY"])
    return None


def _iso(v):
    try:
        return date.fromisoformat(str(v)).isoformat() if v else None
    except ValueError:
        return None


def _lunar_to_solar(txt, today):
    """"27/8" (âm lịch) -> ngày dương lịch gần nhất từ (hôm nay - 30 ngày) trở đi. Lỗi thì None."""
    m = re.match(r"\s*(\d{1,2})\s*/\s*(\d{1,2})", str(txt or ""))
    if not m:
        return None
    from lunardate import LunarDate
    day, month = int(m[1]), int(m[2])
    for year in (today.year, today.year + 1):
        try:
            ld = LunarDate(year, month, day)
            d = ld.to_solar_date() if hasattr(ld, "to_solar_date") else ld.toSolarDate()
        except Exception:
            continue
        if d >= today - timedelta(days=30):
            return d.isoformat()
    return None


def _clean(d, province, title, today=None):
    att = d.get("attendance")
    if isinstance(att, str):                       # AI đôi khi trả "30.000" / "30,000 người" dạng chữ
        nums = re.sub(r"[.,\s](?=\d{3}\b)", "", att)
        m = re.search(r"\d+", nums)
        att = int(m[0]) if m else None
    try:
        att = int(att) if att else None
    except (ValueError, TypeError):
        att = None
    # AI nói sự kiện nằm ngoài 8 tỉnh (hoặc không rõ tỉnh) -> loại, không đoán theo nguồn tin
    prov = d.get("province") if d.get("province") in PROVINCES else None
    start, end = _iso(d.get("start_date")), _iso(d.get("end_date"))
    if not start and today and d.get("lunar_start"):          # bài chỉ nêu ngày âm lịch -> tự đổi sang dương lịch
        start = _lunar_to_solar(d.get("lunar_start"), today)
        end = end or _lunar_to_solar(d.get("lunar_end"), today)
    return {
        "is_event": bool(d.get("is_event")) and prov is not None,
        "name": (d.get("name") or title)[:200],
        "province": prov,
        "venue": d.get("venue") or None,
        "start_date": start,
        "end_date": end,
        "time_text": d.get("time_text") or None,
        "attendance": att,
        "fireworks": bool(d.get("fireworks")),
        "concert": bool(d.get("concert")),
    }


# ---------- Bộ trích xuất dự phòng (không dùng AI) ----------
def _mk(year, month, day, today):
    try:
        if year:
            return date(year, month, day).isoformat()
        d = date(today.year, month, day)
        if d < today - timedelta(days=30):
            d = date(today.year + 1, month, day)
        return d.isoformat()
    except ValueError:
        return None


def heuristic(title, text, province, today):
    norm = strip_accents(f"{title}. {text}")
    start = end = None
    m = re.search(r"(\d{1,2})\s*(?:-|–|den|va)\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}))?", norm)
    if m:
        d1, d2, mo, yr = int(m[1]), int(m[2]), int(m[3]), int(m[4] or 0)
        start, end = _mk(yr, mo, d1, today), _mk(yr, mo, d2, today)
    else:
        m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}))?", norm)
        if m:
            start = _mk(int(m[3] or 0), int(m[2]), int(m[1]), today)
    att = None
    m = re.search(r"(\d+(?:[.,]\d+)*)\s*(nghin|ngan)?\s*(nguoi|luot khach|khan gia|du khach)", norm)
    if m:
        try:
            if m[2]:
                att = int(float(m[1].replace(",", ".")) * 1000)
            else:
                att = int(re.sub(r"[.,]", "", m[1]))
        except ValueError:
            att = None
    return {
        "is_event": True, "name": title[:200], "province": province, "venue": None,
        "start_date": start, "end_date": end, "time_text": None, "attendance": att,
        "fireworks": "phao hoa" in norm, "concert": "dai nhac hoi" in norm or "concert" in norm,
    }


_mode_printed = [False]


def ai_mode():
    if os.environ.get("GEMINI_API_KEY"):
        return "Gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "Claude"
    return None


def extract(title, text, province, today):
    """Có khóa AI: dùng AI; nếu AI lỗi trả về None (để thử lại sau, KHÔNG dùng quy tắc đơn giản vì kém chính xác).
    Không có khóa AI: dùng bộ trích xuất đơn giản."""
    mode = ai_mode()
    if not _mode_printed[0]:
        _mode_printed[0] = True
        print(f"  >> Chế độ trích xuất: {mode + ' (AI)' if mode else 'quy tắc đơn giản (KHÔNG dùng AI)'}")
    if not mode:
        return heuristic(title, text, province, today)
    try:
        d = _call_llm(PROMPT.format(today=today.isoformat(), provinces=", ".join(PROVINCES),
                                    title=title, text=text[:3500]))
    except QuotaExceeded:
        raise
    except Exception as e:
        print("  [LLM] " + " ".join(str(e).split())[:220])
        return None
    if not d:
        print("  [LLM] AI không trả về JSON hợp lệ cho bài này")
        return None
    print(f"  [AI-{mode}] {str(d.get('name') or title)[:70]}")
    return _clean(d, province, title, today)

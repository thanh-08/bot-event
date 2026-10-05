import os, json
from datetime import date
import requests
from common import priority_info

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def tg(method, **params):
    """Gọi Telegram Bot API. Không để lộ token trong thông báo lỗi."""
    token = os.environ["TELEGRAM_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram {method} lỗi {r.status_code}: {r.text[:200]}")
    return r.json()


def chat_ids():
    raw = os.environ.get("TELEGRAM_CHAT_IDS") or os.environ.get("TELEGRAM_CHAT_ID") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def send(chat_id, text):
    """Gửi tin, tự chia nhỏ nếu dài hơn giới hạn của Telegram (4096 ký tự)."""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > 3800:
            parts.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    parts.append(cur)
    for p in parts:
        tg("sendMessage", chat_id=chat_id, text=p, disable_web_page_preview=True)


def send_document(chat_id, path, caption=""):
    """Gửi một file (vd: Excel) qua Telegram. Không để lộ token trong thông báo lỗi."""
    token = os.environ["TELEGRAM_TOKEN"]
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                          data={"chat_id": chat_id, "caption": caption[:1000]},
                          files={"document": (os.path.basename(path), f)}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Telegram sendDocument lỗi {r.status_code}: {r.text[:200]}")


def broadcast(text):
    for cid in chat_ids():
        try:
            send(cid, text)
        except Exception as e:
            print(f"Gửi tới {cid} lỗi: {e}")


def fmt_date(ev):
    s = date.fromisoformat(ev["start_date"])
    e = date.fromisoformat(ev["end_date"]) if ev.get("end_date") and ev["end_date"] != ev["start_date"] else None
    if not e:
        return f"{s.day:02d}/{s.month:02d}"
    if s.month == e.month:
        return f"{s.day:02d}–{e.day:02d}/{s.month:02d}"
    return f"{s.day:02d}/{s.month:02d}–{e.day:02d}/{e.month:02d}"


def format_event(ev):
    label, _, why = priority_info(ev)
    lines = [f"[{label}] {fmt_date(ev)} · {ev['province']}", ev["name"]]
    if ev.get("time_text"):
        lines.append(f"Giờ: {ev['time_text']}")
    if ev.get("venue"):
        lines.append(f"Địa điểm: {ev['venue']}")
    scale = []
    if ev.get("attendance"):
        scale.append(f"~{ev['attendance']:,} người".replace(",", "."))
    else:
        scale.append("chưa rõ số lượng người")
    if ev.get("fireworks"):
        scale.append("có bắn pháo hoa")
    if ev.get("concert"):
        scale.append("có đại nhạc hội")
    lines.append("Quy mô: " + " · ".join(scale))
    if why and label != "THẤP":
        lines.append("Ưu tiên mạng: " + "; ".join(why))
    urls = json.loads(ev["urls"]) if isinstance(ev.get("urls"), str) else (ev.get("urls") or [])
    if urls:
        lines.append(f"Nguồn: {urls[0]}")
    return "\n".join(lines)


def format_list(title, events):
    if not events:
        return f"{title}\nKhông có sự kiện nào."
    return f"{title}: {len(events)} sự kiện\n\n" + "\n\n".join(format_event(e) for e in events)


def format_digest(events, now):
    from common import is_big
    big = sum(1 for e in events if is_big(e))
    head = (f"BẢN TIN SỰ KIỆN MIỀN NAM — {now:%H:%M} {WEEKDAYS[now.weekday()]} {now:%d/%m/%Y}\n"
            f"7 ngày tới: {len(events)} sự kiện ({big} quy mô lớn)")
    if not events:
        return head + "\n\nChưa ghi nhận sự kiện nào."
    return head + "\n\n" + "\n\n".join(format_event(e) for e in events) + \
        "\n\nGõ /tuannay để xem đầy đủ, /tinh <tên tỉnh> để lọc."


def format_alert(ev):
    return "CẢNH BÁO SỰ KIỆN QUY MÔ LỚN\n\n" + format_event(ev)

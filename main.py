"""Bot tin lễ hội, sự kiện miền Nam.

Cách chạy:
  python main.py check    kiểm tra các nguồn RSS có hoạt động không
  python main.py test     gửi 1 tin nhắn thử để kiểm tra token/chat_id
  python main.py run      thu thập + cảnh báo + trả lời lệnh + gửi bản tin 07:00 (mặc định)
  python main.py reply <chat_id> /excel [...]   tạo Excel và gửi cho chat_id (Worker gọi)
  python main.py digest   gửi bản tin ngay lập tức
  python main.py export week [YYYY-MM-DD]   xuất Excel 7 ngày kể từ ngày đó (mặc định hôm nay)
  python main.py export month [YYYY-MM]     xuất Excel cả tháng (không ghi tháng: 30 ngày tới)
"""
import os, sys, json, traceback
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from common import (MIN_ATTENDANCE, load_env, now_vn, has_event_kw, has_date_hint, find_province, is_big, strip_accents, PROVINCES)  # noqa: E402
import collectors, extract, db, notify, report  # noqa: E402

MAX_EXAMINE_PER_RUN = 80      # giới hạn số bài mở ra đọc mỗi lần chạy (để chạy nhanh)
MAX_LLM_PER_RUN = 40          # giới hạn số bài gọi AI mỗi lần chạy (để chi phí gần 0)
GN_COOLDOWN_HOURS = 3        # nghỉ giải mã Google News bao lâu sau khi bị chặn 429
FAIL_ALERT_AT = 3             # báo khi một nguồn lỗi liên tiếp 3 lần

HELP = ("Lệnh hỗ trợ:\n/homnay - sự kiện hôm nay\n/tuannay - 7 ngày tới\n"
        "/tinh <tên tỉnh> - lọc theo tỉnh (vd: /tinh Cần Thơ)\n/sukien <từ khóa> - tìm sự kiện (vd: /sukien pháo hoa)\n"
        "/excel - file Excel 7 ngày tới\n/excel thang - file Excel 30 ngày tới (hoặc /excel thang 2026-11 cho cả tháng 11/2026)")


# ---------------------------------------------------------------- thu thập
def _done(c, it, final_url):
    """Đánh dấu bài đã xử lý xong (cả link gốc lẫn link đã giải mã)."""
    db.mark_seen(c, it["url"])
    if final_url:
        db.mark_seen(c, final_url)


def collect(c):
    today = now_vn().date()
    st = {"moi": 0, "tu_khoa": 0, "ai": 0, "khong_tinh": 0, "khong_phai_sk": 0, "khong_ngay": 0, "ngoai_khoang": 0, "ai_loi": 0, "co_noi_dung": 0, "cho_lai": 0, "gn_hoan": 0, "trung_bai": 0}
    new_events = 0

    # Nếu lần chạy trước bị Google chặn (429) thì nghỉ một thời gian, không gọi lại (gọi dồn chỉ làm lệnh chặn kéo dài)
    until = db.get_meta(c, "gn_block_until")
    if until and now_vn().isoformat() < until:
        collectors.set_gn_blocked()
        print(f"[Google News] đang tạm nghỉ giải mã đến {until[:16]} (bị Google giới hạn tốc độ ở lần chạy trước)")

    # Giai đoạn 1: đọc tất cả nguồn, gom các bài ứng viên (chưa tốn AI)
    cands, in_run = [], set()
    for src in collectors.load_sources():
        try:
            items = collectors.fetch_source(src)
            if not items:
                raise RuntimeError("không có bài nào trong nguồn")
            db.record_health(c, src["name"], True)
        except Exception as e:
            fails = db.record_health(c, src["name"], False)
            print(f"[LỖI] {src['name']}: {e}")
            if fails == FAIL_ALERT_AT:
                notify.broadcast(f"CẢNH BÁO: nguồn \"{src['name']}\" lỗi {fails} lần liên tiếp.\nLỗi: {str(e)[:150]}")
            continue
        print(f"[OK] {src['name']}: {len(items)} bài")
        for it in items:
            url = it["url"]
            if not url or url in in_run or db.seen(c, url):
                continue
            in_run.add(url)
            st["moi"] += 1
            text = f"{it['title']}. {it['summary']}"
            if not has_event_kw(text):
                db.mark_seen(c, url)
                continue
            st["tu_khoa"] += 1
            cands.append((it, find_province(text)))

    # Giai đoạn 2: ưu tiên bài có link trực tiếp (đọc được nội dung) và có tên tỉnh ngay trong tiêu đề/tóm tắt
    def _rank(x):
        it, prov = x
        return (1 if "news.google.com" in it["url"] else 0, 0 if prov else (1 if it.get("hint_province") else 2))
    cands.sort(key=_rank)
    ai_errors = 0
    examined = 0
    for it, _ in cands:
        if st["ai"] >= MAX_LLM_PER_RUN or examined >= MAX_EXAMINE_PER_RUN:
            break
        if "news.google.com" in it["url"] and not collectors.gn_available():
            st["gn_hoan"] += 1             # Google đang chặn/đã hết lượt giải mã: giữ nguyên, thử lại lần sau (không tính số lần thử)
            continue
        examined += 1
        final_url, body = collectors.fetch_article(it["url"])
        if final_url != it["url"] and db.seen(c, final_url):     # cùng bài đã xử lý qua nguồn khác
            db.mark_seen(c, it["url"])
            st["trung_bai"] += 1
            continue
        full = f"{it['title']}. {it['summary']}\n{body}"
        province = find_province(full) or it.get("hint_province")
        st["co_noi_dung"] += 1 if body else 0
        if not province:
            st["khong_tinh"] += 1
            _done(c, it, final_url)
            continue
        if not has_date_hint(full):
            if body:                          # đã đọc cả bài mà không có ngày nào -> bỏ hẳn
                st["khong_ngay"] += 1
                _done(c, it, final_url)
            else:                             # chưa đọc được nội dung: thử lại ở các lần chạy sau (tối đa 3 lần)
                st["cho_lai"] += 1
                if not collectors.gn_blocked() and db.bump_try(c, it["url"]) >= 3:
                    _done(c, it, final_url)
            continue
        try:
            ev = extract.extract(it["title"], full, province, today)
        except extract.QuotaExceeded as e:
            print(f"Hết hạn mức AI miễn phí ({e}). Bot sẽ thử lại ở lần chạy sau, các bài chưa xử lý được giữ lại.")
            break
        if ev is None:                      # AI lỗi: không đánh dấu đã xem để thử lại lần sau
            ai_errors += 1
            if ai_errors >= 3:
                print("AI lỗi liên tiếp 3 lần -> dừng xử lý lần này.")
                if db.get_meta(c, "last_ai_alert") != today.isoformat():
                    notify.broadcast("CẢNH BÁO: bộ trích xuất AI đang lỗi (xem log GitHub Actions). Bot sẽ thử lại lần chạy sau.")
                    db.set_meta(c, "last_ai_alert", today.isoformat())
                break
            continue
        ai_errors = 0
        st["ai"] += 1
        _done(c, it, final_url)
        if not ev["is_event"]:
            st["khong_phai_sk"] += 1
            print(f"  [bỏ: ngoài 8 tỉnh / đã kết thúc / không phải sự kiện] {it['title'][:80]}")
            continue
        if not ev["start_date"]:
            st["khong_ngay"] += 1
            print(f"  [bỏ: không rõ ngày] {it['title'][:80]}")
            continue
        if not (today - timedelta(days=1)).isoformat() <= ev["start_date"] <= (today + timedelta(days=180)).isoformat():
            st["ngoai_khoang"] += 1
            print(f"  [bỏ: ngày {ev['start_date']} ngoài khoảng] {it['title'][:80]}")
            continue
        event_id, is_new = db.upsert_event(c, ev, final_url)
        new_events += is_new
        row = db.get_event(c, event_id)
        if is_big(row) and (row.get("attendance") or 0) >= MIN_ATTENDANCE and not row["alerted"]:
            notify.broadcast(notify.format_alert(row))
            db.set_alerted(c, event_id)

    if collectors.gn_blocked() and not (until and now_vn().isoformat() < until):
        db.set_meta(c, "gn_block_until", (now_vn() + timedelta(hours=GN_COOLDOWN_HOURS)).isoformat())
        print(f"[Google News] bị chặn 429 -> nghỉ giải mã {GN_COOLDOWN_HOURS} giờ")
    print("---- Tổng kết lần chạy ----")
    print(f"Bài mới chưa xem: {st['moi']} | có từ khóa sự kiện: {st['tu_khoa']} | đã mở ra đọc: {examined} | còn chờ lần sau: {max(0, len(cands) - examined)}")
    print(f"Đọc được nội dung bài: {st['co_noi_dung']}/{examined} | chưa đọc được, sẽ thử lại: {st['cho_lai']} | trùng bài đã xử lý: {st['trung_bai']} | hoãn (Google giới hạn tốc độ): {st['gn_hoan']}")
    print(f"Gửi cho AI: {st['ai']} | không xác định được tỉnh: {st['khong_tinh']} | không có ngày: {st['khong_ngay']} | "
          f"không phải sự kiện sắp tới/ngoài 8 tỉnh: {st['khong_phai_sk']} | ngày ngoài khoảng: {st['ngoai_khoang']}")
    if collectors.ERRORS:
        print("Mẫu lỗi khi đọc bài (để chẩn đoán):")
        for e in collectors.ERRORS:
            print("  -", e)
    print(f"Sự kiện mới lưu: {new_events}")


# ---------------------------------------------------------------- bản tin
def send_digest(c):
    now = now_vn()
    d = now.date()
    evs = db.upcoming(c, d.isoformat(), (d + timedelta(days=7)).isoformat())
    notify.broadcast(notify.format_digest(evs, now))


def maybe_digest(c):
    now = now_vn()
    today = now.date().isoformat()
    if now.hour >= 7 and db.get_meta(c, "last_digest") != today:
        send_digest(c)
        db.set_meta(c, "last_digest", today)


# ---------------------------------------------------------------- lệnh bot
def answer(c, text):
    cmd, _, arg = text.partition(" ")
    cmd, arg = strip_accents(cmd.split("@")[0]), arg.strip()   # chấp nhận cả "/tỉnh" (gõ có dấu)
    today = now_vn().date()
    iso = today.isoformat()
    in_days = lambda n: (today + timedelta(days=n)).isoformat()

    if cmd == "/homnay":
        return notify.format_list("Sự kiện hôm nay", db.upcoming(c, iso, iso))
    if cmd == "/tuannay":
        return notify.format_list("Sự kiện 7 ngày tới", db.upcoming(c, iso, in_days(6)))
    if cmd == "/tinh":
        if not arg:
            return "Cú pháp: /tinh <tên tỉnh>, ví dụ: /tinh Cần Thơ"
        p = find_province(arg)
        if not p:
            return "Chưa nhận ra tỉnh này. Hỗ trợ: " + ", ".join(PROVINCES)
        evs = [e for e in db.upcoming(c, iso, in_days(60)) if e["province"] == p]
        return notify.format_list(f"Sự kiện tại {p} (60 ngày tới)", evs)
    if cmd == "/sukien":
        if not arg:
            return "Cú pháp: /sukien <từ khóa>, ví dụ: /sukien pháo hoa"
        k = strip_accents(arg)
        evs = [e for e in db.upcoming(c, iso, in_days(180))
               if k in strip_accents(f"{e['name']} {e['venue'] or ''} {e['province']}")]
        return notify.format_list(f"Kết quả cho \"{arg}\"", evs)
    return HELP


def send_excel(c, chat_id, text):
    """/excel [tuan|thang] [ngày hoặc tháng]: tạo file Excel và gửi vào cuộc trò chuyện."""
    import tempfile
    parts = [strip_accents(x) for x in text.split()[1:]]
    kind = "month" if parts and parts[0] in ("thang", "month") else "week"
    arg = parts[1] if len(parts) > 1 else (parts[0] if parts and parts[0] not in ("tuan", "week", "thang", "month") else "")
    try:
        path = os.path.join(tempfile.mkdtemp(), f"su_kien_{'thang' if kind == 'month' else 'tuan'}.xlsx")
        path, n = report.build(kind, arg, out_path=path, c=c)
    except ValueError as e:
        notify.send(chat_id, f"Không tạo được file: {e}")
        return
    notify.send_document(chat_id, path, f"Danh sách sự kiện ({n} sự kiện). Mở bằng Excel.")


def export_json(c):
    """Xuất data/events.json cho Cloudflare Worker (trả lời lệnh tức thời, không cần chạy Actions)."""
    from common import PROVINCES
    d = now_vn().date()
    rows = db.upcoming(c, (d - timedelta(days=1)).isoformat(), (d + timedelta(days=365)).isoformat())
    evs = [{"start": r["start_date"], "end": r["end_date"] or r["start_date"], "province": r["province"],
            "search": strip_accents(f"{r['name']} {r['venue'] or ''} {r['province']}"),
            "text": notify.format_event(r)} for r in rows]
    with open("data/events.json", "w", encoding="utf-8") as f:
        json.dump({"updated": now_vn().isoformat(), "provinces": PROVINCES, "events": evs}, f, ensure_ascii=False)
    print(f"Đã xuất data/events.json ({len(evs)} sự kiện)")


def handle_commands(c):
    if os.environ.get("USE_WEBHOOK"):      # lệnh đã do Cloudflare Worker trả lời; getUpdates sẽ báo lỗi 409 nếu webhook đang bật
        return
    offset = int(db.get_meta(c, "tg_offset") or 0)
    data = notify.tg("getUpdates", offset=offset, timeout=0)
    for u in data.get("result", []):
        db.set_meta(c, "tg_offset", str(u["update_id"] + 1))
        msg = u.get("message") or {}
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        try:
            if strip_accents(text.split()[0].split("@")[0]) == "/excel":
                send_excel(c, msg["chat"]["id"], text)
            else:
                notify.send(msg["chat"]["id"], answer(c, text))
        except Exception as e:
            print(f"Lỗi trả lời lệnh {text!r}: {e}")


# ---------------------------------------------------------------- điểm vào
def check_sources():
    for src in collectors.load_sources():
        try:
            n = len(collectors.fetch_source(src))
            print(f"OK    {src['name']}: {n} bài")
        except Exception as e:
            print(f"LỖI   {src['name']}: {e}")


def main():
    load_env()
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "check":
        return check_sources()
    if mode == "test":
        notify.broadcast("Bot sự kiện miền Nam đã kết nối thành công. Gõ /help để xem lệnh.")
        return
    if mode == "export":
        args = sys.argv[2:]
        kind = args[0] if args else "week"
        try:
            path, n = report.build(kind, args[1] if len(args) > 1 else None)
        except ValueError as e:
            sys.exit(f"Lỗi: {e}")
        print(f"Đã xuất {n} sự kiện ra file: {path}")
        return
    c = db.conn()
    if mode == "reply":                    # python main.py reply <chat_id> /excel thang ... (do Worker gọi qua workflow_dispatch)
        send_excel(c, sys.argv[2], " ".join(sys.argv[3:]))
        return
    errors = 0
    steps = {"run": [collect, export_json, handle_commands, maybe_digest], "digest": [send_digest]}[mode]
    for step in steps:
        try:
            step(c)
        except Exception:
            errors += 1
            traceback.print_exc()
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

"""Chẩn đoán: cho biết bao nhiêu bài vượt qua từng bước lọc (không gọi AI, không gửi tin).
Chạy: python debug_filter.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from common import load_env, has_event_kw, find_province
import collectors

load_env()
tong = co_tu_khoa = co_tinh = 0
mau = []
for src in collectors.load_sources():
    try:
        items = collectors.fetch_source(src)
    except Exception as e:
        print("LỖI", src["name"], e)
        continue
    for it in items:
        tong += 1
        text = f"{it['title']}. {it['summary']}"
        if not has_event_kw(text):
            continue
        co_tu_khoa += 1
        if find_province(text) or it.get("hint_province"):
            co_tinh += 1
            if len(mau) < 15:
                mau.append(f"[{src['name']}] {it['title']}")
print(f"Tổng số bài: {tong}")
print(f"Có từ khóa sự kiện: {co_tu_khoa}")
print(f"Có từ khóa + xác định được tỉnh (hoặc nguồn Google News theo tỉnh): {co_tinh}")
print("\nMột số bài sẽ được đưa cho AI:")
for m in mau:
    print(" -", m)

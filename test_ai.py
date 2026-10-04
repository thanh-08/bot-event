"""Kiểm tra nhanh AI có hoạt động không. Chạy: python test_ai.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from datetime import date
from common import load_env
import extract

load_env()
mode = extract.ai_mode()
print("Khóa AI được nhận:", mode if mode else "KHÔNG CÓ (kiểm tra file .env)")
bai = ("Lễ hội Ok Om Bok 2026 tại Cần Thơ",
       "Lễ hội diễn ra từ chiều 17 đến 18/10 tại công viên Maspero, phường Ninh Kiều, "
       "dự kiến thu hút khoảng 20.000 người, có bắn pháo hoa vào tối 17/10.")
print("Đang gọi AI...")
d = extract._call_llm(extract.PROMPT.format(today=date.today().isoformat(),
        provinces=", ".join(extract.PROVINCES), title=bai[0], text=bai[1])) if mode else None
if d:
    print("THÀNH CÔNG - AI đã trả về:")
    for k, v in d.items():
        print(f"  {k}: {v}")
else:
    print("AI chưa hoạt động (không có khóa hoặc không trả về kết quả).")

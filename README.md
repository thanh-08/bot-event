# Bot tin lễ hội, sự kiện miền Nam

Bot tự động thu thập tin lễ hội/sự kiện tại 8 tỉnh miền Nam (TP.HCM, Đồng Nai, Tây Ninh, An Giang,
Đồng Tháp, Vĩnh Long, Cần Thơ, Cà Mau), lọc trùng, trích xuất thông tin chuẩn và gửi qua **Telegram**:
bản tin 07:00 hằng ngày (7 ngày tới) và cảnh báo ngay khi có sự kiện lớn (≥10.000 người, pháo hoa, đại nhạc hội).

## Luồng hoạt động

RSS (báo điện tử + báo địa phương + 8 truy vấn Google News) → lọc từ khóa + tỉnh → trích xuất (AI hoặc quy tắc) →
khử trùng + lưu SQLite → bản tin 07:00 / cảnh báo / lệnh Telegram. Chạy bằng GitHub Actions mỗi 30 phút.

## Vì sao chọn Telegram

Miễn phí, tạo bot trong vài phút qua BotFather, tài liệu đầy đủ, không cần đăng ký doanh nghiệp.
Zalo OA cần đăng ký OA và có thể phát sinh phí ZNS; WhatsApp cần tài khoản Meta Business và mẫu tin được duyệt.
Gửi cho nhiều người: thêm nhiều chat_id, phân tách bằng dấu phẩy.

## Cài đặt (khoảng 30 phút)

1. **Tạo bot**: trong Telegram chat với `@BotFather` → `/newbot` → lưu lại *token*.
2. **Lấy chat_id**: mở bot vừa tạo, bấm Start, gửi 1 tin bất kỳ; mở trình duyệt tới
   `https://api.telegram.org/bot<TOKEN>/getUpdates` và đọc số `"chat":{"id": ...}`.
3. **(Tuỳ chọn) khóa AI**: lấy `GEMINI_API_KEY` (miễn phí) tại aistudio.google.com/apikey, hoặc `ANTHROPIC_API_KEY` ở console.anthropic.com. Bỏ trống thì bot dùng bộ trích xuất đơn giản.
4. **Chạy thử trên máy**:
   ```bash
   python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env                                 # rồi điền token, chat_id
   python main.py test      # nhận tin nhắn thử trên điện thoại
   python main.py check     # xem nguồn nào hoạt động
   python main.py run       # thu thập + trả lời lệnh
   python main.py digest    # gửi bản tin ngay
   ```
5. **Chạy tự động trên GitHub**: đẩy code lên repo → Settings → Secrets and variables → Actions →
   thêm `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_IDS`, và `GEMINI_API_KEY` hoặc `ANTHROPIC_API_KEY` (nếu dùng AI). Vào tab Actions, chạy tay
   workflow *event-bot* một lần để kiểm tra.

## Bảo mật

Token và khóa API chỉ nằm trong `.env` (đã nằm trong `.gitignore`) hoặc GitHub Secrets, không có trong mã nguồn.

## Thêm nguồn

Sửa `sources.yaml` (thêm một dòng `{name, url}`), rồi chạy `python main.py check`.

## Giới hạn đã biết

- GitHub Actions không chạy liên tục nên lệnh `/homnay`, `/tinh`... được trả lời trong lần chạy kế tiếp (tối đa ~30 phút).
  Muốn phản hồi tức thì, chạy `python main.py run` lặp lại trên VPS miễn phí.
- Bản tin 07:00 có thể trễ vài phút đến vài chục phút do lịch của GitHub Actions.
- Khi không có khóa AI, bộ trích xuất đơn giản chỉ bắt được ngày dạng `dd/mm`, nên độ chính xác thấp hơn.

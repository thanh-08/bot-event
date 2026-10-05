# Bot tin lễ hội, sự kiện miền Nam

Bot tự động thu thập tin lễ hội/sự kiện tại 8 tỉnh/thành miền Nam (TP. Hồ Chí Minh, Đồng Nai, Tây Ninh, An Giang,
Đồng Tháp, Vĩnh Long, Cần Thơ, Cà Mau), lọc trùng, trích xuất thông tin chuẩn và gửi qua **Telegram**:
bản tin 07:00 mỗi ngày (7 ngày tới), cảnh báo riêng khi có sự kiện lớn, lệnh tra cứu.

## Tính năng

| Yêu cầu | Cách bot đáp ứng |
|---|---|
| Thu thập từ ≥5 nguồn công khai | 18 nguồn trong `sources.yaml` (RSS và quét trang chủ) + 8 truy vấn Google News theo tỉnh |
| Lọc đúng địa bàn, loại tin trùng | Lọc từ khóa + tên tỉnh (gồm các tỉnh cũ đã sáp nhập); bảng `seen` chặn bài trùng link; sự kiện cùng tỉnh, cùng ngày, tên giống nhau được gộp thành một |
| Trích xuất thông tin chuẩn | AI (Gemini) lấy: tên, tỉnh, địa điểm, ngày giờ bắt đầu/kết thúc, quy mô, pháo hoa, đại nhạc hội, link nguồn. Ngày âm lịch được đổi sang dương lịch |
| Bản tin 07:00 | Sự kiện trong 7 ngày tới, sắp theo ngày. Gửi ở lượt chạy đầu tiên sau 07:00 giờ Việt Nam, mỗi ngày một lần (thường đến lúc 07:03 đến 07:05) |
| Cảnh báo sự kiện lớn | Gửi ngay khi gặp sự kiện từ 10.000 người, hoặc có pháo hoa/đại nhạc hội; mỗi sự kiện chỉ báo một lần |
| Lệnh tra cứu | `/homnay`, `/tuannay`, `/tinh <tỉnh>`, `/sukien <từ khóa>` |
| (Cộng điểm) AI trích xuất | Gemini (có gói miễn phí) |
| (Cộng điểm) Mức ưu tiên đối với mạng lưới | Mỗi sự kiện được gắn CAO / TB / THẤP theo quy mô và địa điểm, kèm lý do (xem mục *Mức ưu tiên đối với mạng lưới*) |
| (Cộng điểm) Xuất Excel theo tuần/tháng | `python main.py export week|month` hoặc lệnh `/excel` trên Telegram (xem mục *Xuất Excel*) |

## Luồng hoạt động

```
Nguồn tin (báo, Google News) -> thu thập -> lọc từ khóa + tỉnh -> AI trích xuất -> khử trùng + lưu SQLite
                                                                                      |
             Điện thoại <- Telegram <- bản tin 07:00 / cảnh báo / lệnh <--------------+
```

Bot chạy tự động trên **GitHub Actions** nên không phụ thuộc máy cá nhân.

## Vì sao chọn Telegram

Miễn phí, tạo bot trong vài phút qua BotFather, có tài liệu đầy đủ, không cần đăng ký doanh nghiệp.
Zalo OA cần đăng ký tài khoản OA và có thể phát sinh phí gửi tin; WhatsApp cần tài khoản Meta Business và mẫu tin được duyệt.
Gửi cho nhiều người: điền nhiều chat_id, cách nhau bằng dấu phẩy.

## Nguồn dữ liệu

Đang dùng (đã kiểm tra, lấy được bài): VnExpress, Tuổi Trẻ, Thanh Niên, Báo Tin tức, Báo Tây Ninh (RSS),
SGGP, Báo Đồng Nai, Báo An Giang, Báo Đồng Tháp, Báo Vĩnh Long, Báo Cần Thơ, Báo Cà Mau, và Google News theo từng tỉnh.

Đã thử nhưng không dùng được: cổng thông tin UBND các tỉnh, trang Sở VH-TT-DL, VietnamPlus, VOV, Ticketbox, VinWonders,
Klook, Trip.com. Các trang này không trả về danh sách bài khi bot đọc (nhiều khả năng dùng JavaScript hoặc chặn truy cập
tự động), nên đã bỏ khỏi `sources.yaml`. Thêm hoặc bớt nguồn bằng cách sửa file này rồi chạy `python main.py check`.

## Cài đặt trên máy (khoảng 30 phút)

Yêu cầu: Python 3.9 trở lên.

1. **Tạo bot**: trong Telegram chat với `@BotFather`, gõ `/newbot`, lưu lại *token*.
2. **Lấy chat_id**: mở bot vừa tạo, bấm Start, gửi một tin bất kỳ; mở trình duyệt tới
   `https://api.telegram.org/bot<TOKEN>/getUpdates` và đọc số trong `"chat":{"id": ...}`.
3. **Khóa AI (tùy chọn)**: lấy `GEMINI_API_KEY` miễn phí tại aistudio.google.com/apikey. Bỏ trống thì bot dùng bộ trích xuất đơn giản (kém chính xác hơn).
4. **Chạy thử**:
   ```
   python -m venv venv
   venv\Scripts\activate            (Mac/Linux: source venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env           (rồi điền token, chat_id, khóa AI vào .env)
   python main.py test              nhận tin nhắn thử trên điện thoại
   python main.py check             kiểm tra nguồn nào hoạt động
   python main.py run               thu thập + cảnh báo + trả lời lệnh
   python main.py digest            gửi bản tin ngay
   ```

## Chạy tự động trên GitHub Actions

1. Tạo repo **Public** trên GitHub rồi tải toàn bộ mã lên (không tải `.env` và thư mục `venv`).
2. Vào *Settings → Secrets and variables → Actions*, thêm 3 secret: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_IDS`, `GEMINI_API_KEY`.
3. Vào *Settings → Actions → General → Workflow permissions*, chọn **Read and write permissions**.
4. Vào tab *Actions*, chọn *event-bot* rồi bấm *Run workflow* để chạy thử.

Workflow (`.github/workflows/bot.yml`) chạy `python main.py run` (theo lịch, bấm tay hoặc do dịch vụ ngoài gọi). Mỗi lượt đọc nguồn, gửi cảnh báo, trả lời các lệnh đang chờ,
gửi bản tin nếu đã quá 07:00, rồi lưu cơ sở dữ liệu về repo (vì máy chạy của GitHub bị xóa sau mỗi lượt).

### Lịch chạy kép để bản tin đúng giờ

GitHub chỉ cam kết lịch chạy theo kiểu "cố gắng hết sức": lượt chạy có thể bị trễ hoặc bỏ khi hệ thống bận, nhất là với repo mới
(trong thực tế dự án này từng chỉ chạy khoảng 3 giờ một lần dù đặt lịch 30 phút). Vì vậy bot dùng hai nguồn kích hoạt cùng lúc:

1. **Lịch của GitHub** (`schedule` trong `bot.yml`): đặt ở các phút lẻ (17 và 47 mỗi giờ) để tránh giờ cao điểm, cộng hai lượt dự phòng lúc 07:03 và 07:33 giờ Việt Nam.
2. **Dịch vụ hẹn giờ bên ngoài (cron-job.org)**: cứ 30 phút gọi API `workflow_dispatch` của GitHub một lần để bot chạy đúng giờ, kể cả lúc 07:00.

Cách thiết lập kích hoạt ngoài:

- Tạo *fine-grained personal access token* trên GitHub, chỉ chọn repo của bot và chỉ cấp quyền **Actions: Read and write**, đặt ngày hết hạn.
- Trên cron-job.org tạo job gọi `POST https://api.github.com/repos/<người dùng>/<tên repo>/actions/workflows/bot.yml/dispatches`
  với nội dung `{"ref":"main"}`, lịch 30 phút một lần, các header `Authorization: Bearer <token>`,
  `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.
  Kết quả đúng là HTTP 204.
- Token chỉ nằm trong cấu hình của job, không nằm trong mã nguồn hay repo. Khi token hết hạn, tạo token mới và cập nhật header `Authorization`.

Nếu dịch vụ bên ngoài hoặc token gặp sự cố, bot tự quay về lịch của GitHub, nghĩa là vẫn chạy nhưng có thể chậm. Workflow đặt
`concurrency` nên các lượt chạy xếp hàng tuần tự và bản tin vẫn chỉ gửi một lần mỗi ngày (ngày gửi gần nhất được lưu trong cơ sở dữ liệu).
Mỗi lượt chạy thu thập tin trước rồi mới gửi bản tin, nên bản tin 07:00 thường đến sau 3 đến 5 phút.

## Trả lời lệnh tức thời (Cloudflare Worker)

GitHub Actions chỉ chạy theo lượt nên lệnh phải chờ lượt kế tiếp. Để bot trả lời trong ~1 giây, Telegram được cấu hình
gọi thẳng (webhook) tới một Cloudflare Worker miễn phí (100.000 yêu cầu/ngày). Worker đọc `data/events.json`
(Actions cập nhật sau mỗi lượt thu thập) nên không cần máy chủ chạy liên tục. Việc thu thập, cảnh báo và bản tin 07:00 vẫn do Actions làm.
Riêng `/excel` cần tạo file nên Worker báo "đang tạo" rồi gọi Actions gửi file sau khoảng 1 phút.

Thiết lập (khoảng 10 phút):

1. Tạo tài khoản miễn phí tại cloudflare.com. Sửa `worker/wrangler.toml`: thay `<người-dùng>/<repo>` bằng repo của bạn.
2. Trong thư mục `worker/`, chạy `npx wrangler login`, rồi đặt từng secret bằng `npx wrangler secret put <TÊN>`:
   `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_IDS` (giống GitHub Secrets), `WEBHOOK_SECRET` (chuỗi ngẫu nhiên tự đặt, tối đa 256 ký tự gồm chữ, số, `_`, `-`),
   `GITHUB_TOKEN` (fine-grained token, chỉ repo này, quyền **Actions: Read and write**; có thể dùng lại token của cron-job.org).
3. `npx wrangler deploy`, lấy địa chỉ dạng `https://event-bot.<tên>.workers.dev`.
4. Đăng ký webhook (một lần; thay 3 giá trị):
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://event-bot.<tên>.workers.dev&secret_token=<WEBHOOK_SECRET>"`
5. Chạy tay workflow *event-bot* một lần để sinh `data/events.json`, rồi nhắn `/tuannay` thử.

Lưu ý: khi webhook đang bật, `getUpdates` bị Telegram từ chối (lỗi 409), nên workflow đã đặt `USE_WEBHOOK=1` để bỏ bước đọc lệnh.
Muốn quay về cách cũ: gọi `.../deleteWebhook` và xóa dòng `USE_WEBHOOK` trong `bot.yml`.
Dữ liệu lệnh tra cứu mới đến mức lượt thu thập gần nhất (tối đa ~30 phút), kèm bộ nhớ đệm GitHub khoảng 5 phút.

## Lệnh trên bot

| Lệnh | Ý nghĩa |
|---|---|
| `/homnay` | Sự kiện đang diễn ra hôm nay |
| `/tuannay` | Sự kiện trong 7 ngày tới |
| `/tinh <tên tỉnh>` | Sự kiện của một tỉnh trong 60 ngày tới, ví dụ `/tinh Cần Thơ` (gõ có dấu hay không dấu đều được) |
| `/sukien <từ khóa>` | Tìm theo từ khóa, ví dụ `/sukien pháo hoa` |
| `/excel` | Gửi file Excel các sự kiện 7 ngày tới |
| `/excel thang` | File Excel 30 ngày tới; `/excel thang 2026-11` cho cả tháng 11/2026 |

Khi dùng Cloudflare Worker, lệnh được trả lời gần như tức thì (riêng `/excel` mất khoảng 1 phút). Nếu không dùng Worker, lệnh được trả lời ở lượt Actions kế tiếp.

## Mức ưu tiên đối với mạng lưới

Mỗi sự kiện được gắn **CAO / TB (trung bình) / THẤP** theo quy mô và địa điểm, kèm dòng "Ưu tiên mạng" nêu lý do.

- Điểm theo quy mô: số người (từ 1.000, 5.000, 10.000, 20.000), có pháo hoa, có đại nhạc hội, kéo dài từ 3 ngày,
  lễ hội truyền thống lớn (Vía Bà, Ok Om Bok, Nghinh Ông, lễ hội Nguyễn Trung Trực…).
- Điểm theo địa điểm: sân bay/cảng, khu du lịch đông khách, sân vận động, quảng trường, phố đi bộ… và TP. Hồ Chí Minh.
- CAO: sự kiện từ 10.000 người, có pháo hoa hoặc đại nhạc hội, hoặc tổng điểm từ 5. TB: từ 3 đến 4 điểm. THẤP: còn lại.

Đây là quy tắc tự đặt. Muốn chỉnh danh sách địa điểm trọng điểm hoặc ngưỡng điểm, sửa `HOTSPOTS`, `BIG_FESTIVALS`,
`PRIORITY_HIGH`, `PRIORITY_MID` trong `src/common.py`.

## Xuất Excel theo tuần/tháng

```bash
python main.py export week              # 7 ngày tới, file nằm trong thư mục exports/
python main.py export week 2026-10-12   # 7 ngày kể từ ngày chỉ định
python main.py export month             # 30 ngày tới
python main.py export month 2026-11     # cả tháng 11/2026
```

File có 2 sheet: *Danh sách sự kiện* (lọc được, tô màu theo mức ưu tiên, có link bài gốc) và *Tổng hợp* (số sự kiện
theo tỉnh và mức ưu tiên, kèm cách xếp mức ưu tiên). Lệnh `/excel` trên Telegram làm điều tương tự và gửi file vào
cuộc trò chuyện.

## Cấu hình

| Cần chỉnh | Ở đâu |
|---|---|
| Nguồn tin | `sources.yaml` (`type: html` cho báo không có RSS) |
| Từ khóa lọc sự kiện, tên tỉnh và địa danh, ngưỡng sự kiện lớn, địa điểm trọng điểm và ngưỡng ưu tiên | `src/common.py` |
| Mô hình AI | biến `GEMINI_MODEL` (danh sách cách nhau dấu phẩy; mặc định `gemini-3.5-flash-lite,gemini-3.8-flash`) |
| Số bài xử lý mỗi lượt | `MAX_EXAMINE_PER_RUN`, `MAX_LLM_PER_RUN` trong `main.py` |

## Cơ sở dữ liệu

SQLite, lưu ở `data/events.db`, gồm các bảng: `events` (sự kiện đã trích xuất, kèm danh sách link nguồn và cờ đã cảnh báo),
`seen` (các bài đã xử lý), `meta` (ngày gửi bản tin gần nhất, mốc tin nhắn Telegram đã đọc), `health` (số lần lỗi liên tiếp của từng nguồn).
Trên GitHub Actions, file này được commit về repo sau mỗi lượt để giữ trạng thái giữa các lần chạy.

## Xử lý lỗi và bảo mật

- Mỗi nguồn được đọc trong khối bắt lỗi riêng; nguồn lỗi 3 lần liên tiếp thì bot nhắn cảnh báo qua Telegram.
- Khi AI hết hạn mức hoặc quá tải, bot dừng gọi AI ở lượt đó và giữ lại các bài chưa xử lý cho lượt sau.
- Token và khóa API chỉ nằm trong `.env` (đã có trong `.gitignore`) hoặc GitHub Secrets, không có trong mã nguồn; thông báo lỗi không in token.
- Token dùng cho cron-job.org chỉ có quyền Actions trên đúng một repo và có ngày hết hạn; khi ngừng dùng thì xóa job và thu hồi token.

## Giới hạn đã biết

- Nếu không dùng Cloudflare Worker, lệnh trên GitHub Actions trả lời trễ tối đa khoảng 30 phút. Bản tin 07:00 thường đến lúc 07:03 đến 07:05; nếu kích hoạt ngoài gặp sự cố thì có thể trễ nhiều hơn (xem phần lịch chạy kép).
- Chưa lấy được dữ liệu từ cổng UBND, Sở VH-TT-DL và các trang bán vé (xem phần nguồn dữ liệu).
- Gói AI miễn phí có hạn mức nhất định; khi hết hạn mức, các bài còn lại được xử lý ở các lượt sau.
- Một số bài không nêu ngày cụ thể nên bị bỏ qua; chưa mở rộng ra các tỉnh miền Nam ngoài 8 tỉnh/thành trên.
- Dữ liệu lấy từ báo chí công khai và có thể chưa đầy đủ; hãy kiểm tra lại qua link nguồn.

## Cấu trúc thư mục

```
main.py                 điểm vào: run, check, test, digest, export, reply
worker/                 Cloudflare Worker trả lời lệnh tức thời
src/common.py           tỉnh, từ khóa, mức ưu tiên
src/collectors.py       đọc RSS / quét trang / Google News
src/extract.py          trích xuất bằng AI (có dự phòng quy tắc đơn giản)
src/db.py               SQLite, khử trùng
src/notify.py           gửi tin và file Telegram, định dạng bản tin
src/report.py           xuất Excel theo tuần/tháng
sources.yaml            danh sách nguồn
data/events.db          cơ sở dữ liệu
.github/workflows/      lịch chạy GitHub Actions
```

// Cloudflare Worker: nhận webhook Telegram và trả lời lệnh tức thời từ data/events.json (do GitHub Actions cập nhật).
// /excel cần tạo file nên Worker báo "đang tạo" rồi gọi GitHub Actions (workflow_dispatch) làm tiếp.

const HELP =
  "Lệnh hỗ trợ:\n/homnay - sự kiện hôm nay\n/tuannay - 7 ngày tới\n" +
  "/tinh <tên tỉnh> - lọc theo tỉnh (vd: /tinh Cần Thơ)\n/sukien <từ khóa> - tìm sự kiện (vd: /sukien pháo hoa)\n" +
  "/excel - file Excel 7 ngày tới\n/excel thang - file Excel 30 ngày tới (hoặc /excel thang 2026-11 cho cả tháng 11/2026)";

const strip = (s) =>
  (s || "").replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const esc = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function vnDate(plusDays = 0) {
  return new Date(Date.now() + 7 * 3600e3 + plusDays * 86400e3).toISOString().slice(0, 10);
}

function upcoming(events, from, to) {
  return events.filter((e) => (e.end || e.start) >= from && e.start <= to);
}

function findProvince(text, provinces) {
  const norm = strip(text);
  let best = null, bestN = 0;
  for (const [name, aliases] of Object.entries(provinces)) {
    let n = 0;
    for (const t of [name, ...aliases]) {
      const m = norm.match(new RegExp("(?<![a-z0-9])" + esc(strip(t)) + "(?![a-z0-9])", "g"));
      n += m ? m.length : 0;
    }
    if (n > bestN) { best = name; bestN = n; }
  }
  return best;
}

function formatList(title, evs) {
  if (!evs.length) return `${title}\nKhông có sự kiện nào.`;
  return `${title}: ${evs.length} sự kiện\n\n` + evs.map((e) => e.text).join("\n\n");
}

async function loadData(env) {
  const r = await fetch(env.EVENTS_URL, { cf: { cacheTtl: 60, cacheEverything: true } });
  if (!r.ok) throw new Error(`Không tải được events.json (${r.status})`);
  return r.json();
}

async function tg(env, method, params) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!r.ok) console.log(`Telegram ${method} lỗi ${r.status}`);   // không in token
}

async function send(env, chatId, text) {
  const parts = []; let cur = "";
  for (const block of text.split("\n\n")) {
    if (cur && cur.length + block.length + 2 > 3800) { parts.push(cur); cur = block; }
    else cur = cur ? `${cur}\n\n${block}` : block;
  }
  parts.push(cur);
  for (const p of parts) await tg(env, "sendMessage", { chat_id: chatId, text: p, disable_web_page_preview: true });
}

async function answer(env, text) {
  const [first, ...rest] = text.split(/\s+/);
  const cmd = strip(first.split("@")[0]);
  const arg = rest.join(" ").trim();
  if (!["/homnay", "/tuannay", "/tinh", "/sukien"].includes(cmd)) return HELP;

  const data = await loadData(env);
  const today = vnDate(), inDays = (n) => vnDate(n);
  if (cmd === "/homnay") return formatList("Sự kiện hôm nay", upcoming(data.events, today, today));
  if (cmd === "/tuannay") return formatList("Sự kiện 7 ngày tới", upcoming(data.events, today, inDays(6)));
  if (cmd === "/tinh") {
    if (!arg) return "Cú pháp: /tinh <tên tỉnh>, ví dụ: /tinh Cần Thơ";
    const p = findProvince(arg, data.provinces);
    if (!p) return "Chưa nhận ra tỉnh này. Hỗ trợ: " + Object.keys(data.provinces).join(", ");
    return formatList(`Sự kiện tại ${p} (60 ngày tới)`, upcoming(data.events, today, inDays(60)).filter((e) => e.province === p));
  }
  if (!arg) return "Cú pháp: /sukien <từ khóa>, ví dụ: /sukien pháo hoa";
  const k = strip(arg);
  return formatList(`Kết quả cho "${arg}"`, upcoming(data.events, today, inDays(180)).filter((e) => e.search.includes(k)));
}

async function dispatchExcel(env, chatId, text) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/bot.yml/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "event-bot-worker",
    },
    body: JSON.stringify({ ref: "main", inputs: { chat_id: String(chatId), text } }),
  });
  return r.status === 204;
}

// Giới hạn /excel: mỗi chat 1 lần / 60 giây (lưu trong bộ nhớ của Worker, chỉ mang tính hạn chế lạm dụng)
const lastExcel = new Map();

async function handle(env, msg) {
  const chatId = msg.chat.id;
  const text = (msg.text || "").trim();
  try {
    if (strip(text.split(/\s+/)[0].split("@")[0]) === "/excel") {
      const now = Date.now();
      if (now - (lastExcel.get(chatId) || 0) < 60000) {
        await send(env, chatId, "Bạn vừa yêu cầu file Excel, vui lòng đợi khoảng 1 phút rồi thử lại.");
        return;
      }
      lastExcel.set(chatId, now);
      if (lastExcel.size > 500) lastExcel.clear();
      await send(env, chatId, "Đang tạo file Excel, khoảng 1 phút sẽ gửi vào đây...");
      if (!(await dispatchExcel(env, chatId, text))) await send(env, chatId, "Không tạo được file Excel lúc này, thử lại sau ít phút.");
      return;
    }
    await send(env, chatId, await answer(env, text));
  } catch (e) {
    console.log("Lỗi trả lời lệnh:", e.message);
    await send(env, chatId, "Bot gặp lỗi khi tra cứu, thử lại sau ít phút.");
  }
}

export default {
  async fetch(req, env, ctx) {
    if (req.method !== "POST") return new Response("event-bot worker");
    if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) return new Response("forbidden", { status: 403 });
    const msg = (await req.json()).message;
    if (msg && (msg.text || "").trim().startsWith("/")) ctx.waitUntil(handle(env, msg));
    return new Response("ok");
  },
};

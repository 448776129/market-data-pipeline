/**
 * 行情K线动态接口（Cloudflare Worker）
 *
 * 免费托管在 Cloudflare Workers（无需服务器），数据直接读取本仓库
 * （448776129/market-data-pipeline）由 GitHub Actions 生成的 CSV 文件，
 * 在边缘节点上解析并转成 JSON 返回。
 *
 * 部署：见 api/README.md
 *
 * 路由：
 *   GET /kline?symbol=AAPL                          → AAPL 全量日线（默认）
 *   GET /kline?symbol=AAPL&interval=1d&start=2024-01-01&end=2024-12-31
 *   GET /kline?symbol=0700.HK&interval=1h&limit=100
 *   GET /kline?symbol=600519.SS&interval=1d
 *
 * 参数：
 *   symbol   必填。股票代码，如 AAPL / 0700.HK / 600519.SS
 *   interval 可选，默认 1d。枚举：1d(日线) 1m(1分钟) 1h(1小时)
 *   start    可选。起始日期 YYYY-MM-DD（含），按索引列过滤
 *   end      可选。结束日期 YYYY-MM-DD（含）
 *   limit    可选。最多返回行数，默认返回全部
 *   format   可选。json（默认）| csv（返回原始CSV文本）
 */

// 数据仓库信息（与 git remote 一致）
const REPO_OWNER = "448776129";
const REPO_NAME = "market-data-pipeline";
const REPO_BRANCH = "master";

// interval -> data 子目录映射
const INTERVAL_DIR = {
  "1d": "kline",
  "1m": "kline_1m",
  "1h": "kline_1h",
};

// 从代码后缀推断区域；裸代码默认美股
function inferRegion(symbol) {
  const s = symbol.toUpperCase();
  if (s.endsWith(".HK")) return "hk";
  if (s.endsWith(".KS")) return "kr";
  if (s.endsWith(".SS") || s.endsWith(".SZ")) return "cn";
  return "us";
}

// 解析 CSV 文本为对象数组（首行表头）
function parseCSV(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  if (lines.length === 0) return [];
  const header = splitLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = splitLine(lines[i]);
    if (cells.length === 0) continue;
    const obj = {};
    for (let j = 0; j < header.length; j++) {
      obj[header[j]] = cells[j] !== undefined ? cells[j] : "";
    }
    rows.push(obj);
  }
  return rows;
}

// 简易 CSV 行切分（处理带引号字段）
function splitLine(line) {
  const out = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

// 统一响应头（允许跨域调用）
function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "public, max-age=60",
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders() },
  });
}

function error(msg, status = 400) {
  return json({ error: msg }, status);
}

// 数值/日期过滤预备：返回比较用的时间戳（Date 或 Datetime 索引列）
function tsOf(value) {
  if (value === undefined || value === null || value === "") return null;
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d.getTime();
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    // 仅支持 /kline 路由
    if (path !== "/kline" && path !== "/") {
      return error("Not found. Use /kline", 404);
    }

    const params = url.searchParams;
    const symbol = (params.get("symbol") || "").trim().toUpperCase();
    if (!symbol) {
      return json({
        usage: {
          endpoint: "/kline",
          params: {
            symbol: "股票代码（必填）",
            interval: "1d|1m|1h，默认 1d",
            start: "起始日期 YYYY-MM-DD",
            end: "结束日期 YYYY-MM-DD",
            limit: "最多返回行数（默认返回最新 N 条）",
            order: "asc|desc，默认 asc；desc 时最新在前",
            format: "json|csv，默认 json",
          },
          example:
            "https://<your-worker>.workers.dev/kline?symbol=AAPL&interval=1d&start=2024-01-01&end=2024-12-31",
        },
      });
    }

    const interval = (params.get("interval") || "1d").toLowerCase();
    if (!INTERVAL_DIR[interval]) {
      return error(`Invalid interval: ${interval}. Allowed: ${Object.keys(INTERVAL_DIR).join(", ")}`);
    }

    const region = (params.get("region") || inferRegion(symbol)).toLowerCase();
    const limit = parseInt(params.get("limit") || "0", 10);
    const format = (params.get("format") || "json").toLowerCase();

    const startTs = tsOf(params.get("start"));
    const endTs = tsOf(params.get("end"));

    // 从 GitHub 拉取对应 CSV
    const csvUrl = `https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${REPO_BRANCH}/data/${region}/${INTERVAL_DIR[interval]}/${symbol}.csv`;

    let resp;
    try {
      resp = await fetch(csvUrl);
    } catch (e) {
      return error(`Failed to fetch upstream: ${e.message}`, 502);
    }

    if (!resp.ok) {
      if (resp.status === 404) {
        return error(`No data for ${symbol} (${interval}). File not found: data/${region}/${INTERVAL_DIR[interval]}/${symbol}.csv`, 404);
      }
      return error(`Upstream error: ${resp.status}`, 502);
    }

    const text = await resp.text();

    if (format === "csv") {
      return new Response(text, {
        status: 200,
        headers: { "Content-Type": "text/csv; charset=utf-8", ...corsHeaders() },
      });
    }

    let rows = parseCSV(text);

    // 索引列：日线用 Date，分钟线用 Datetime
    const indexCol = interval === "1d" ? "Date" : "Datetime";

    if (startTs !== null || endTs !== null) {
      rows = rows.filter((r) => {
        const t = tsOf(r[indexCol]);
        if (t === null) return true; // 无法解析的行保留
        if (startTs !== null && t < startTs) return false;
        if (endTs !== null && t > endTs) return false;
        return true;
      });
    }

    // 排序：默认按时间升序（与 CSV 一致）；order=desc 时最新在前
    const order = (params.get("order") || "asc").toLowerCase();
    if (order === "desc") {
      rows.reverse();
    }

    // limit：默认返回最新 N 条（自动取时间上最近的数据）
    if (limit > 0) {
      if (order === "desc") {
        rows = rows.slice(0, limit);
      } else {
        rows = rows.slice(-limit);
      }
    }

    return json({ symbol, region, interval, count: rows.length, order, data: rows });
  },
};
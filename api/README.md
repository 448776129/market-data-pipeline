# 行情K线动态接口（Cloudflare Worker）

免费、无需服务器。数据直接读取本仓库 `data/` 下的 CSV，在 Cloudflare 边缘节点解析并转成 JSON 返回。

> 已部署：**https://market-data-api.wangfugui.workers.dev**

## 调用示例

你的量化系统直接请求：

```bash
# 最新 5 条日K（limit 默认返回最新数据）
curl "https://market-data-api.wangfugui.workers.dev/kline?symbol=AAPL&limit=5"

# AAPL 一年日K（2024-01-01 ~ 2024-12-31）
curl "https://market-data-api.wangfugui.workers.dev/kline?symbol=AAPL&interval=1d&start=2024-01-01&end=2024-12-31"

# 最新 100 条，倒序（最新在前）
curl "https://market-data-api.wangfugui.workers.dev/kline?symbol=0700.HK&interval=1h&limit=100&order=desc"

# A股 600519.SS 日线
curl "https://market-data-api.wangfugui.workers.dev/kline?symbol=600519.SS&interval=1d"

# 韩股 005930.KS 15分钟K线
curl "https://market-data-api.wangfugui.workers.dev/kline?symbol=005930.KS&interval=15m"

# 原始CSV（format=csv）
curl "https://market-data-api.wangfugui.workers.dev/kline?symbol=AAPL&format=csv"
```

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `symbol` | 是 | 股票代码，如 `AAPL` / `0700.HK` / `600519.SS` / `005930.KS` |
| `interval` | 否 | `1d`(日线,默认) / `1m` / `15m` / `1h` |
| `start` | 否 | 起始日期 `YYYY-MM-DD` |
| `end` | 否 | 结束日期 `YYYY-MM-DD` |
| `limit` | 否 | 最多返回行数；**默认返回最新 N 条** |
| `order` | 否 | `asc`(默认,时间升序) / `desc`(最新在前) |
| `format` | 否 | `json`(默认) / `csv` |

> **`limit` 行为**：默认返回时间上最晚的 N 条（最新数据）。配合 `order=desc` 时最新日期排在最前。若省略 `limit`，则返回日期范围内的全部数据。

## 返回格式（JSON）

```json
{
  "symbol": "AAPL",
  "region": "us",
  "interval": "1d",
  "count": 5,
  "order": "asc",
  "data": [
    { "Date": "2024-08-09", "Open": "210.10", "High": "216.50", "Low": "209.86", "Close": "216.24", "Adj Close": "216.24", "Volume": "72447800" }
  ]
}
```

## 区域自动识别

代码后缀自动判断市场，无需传 `region`：
- 裸代码（如 `AAPL`）→ US
- `.HK` → 港股
- `.SS` / `.SZ` → A股
- `.KS` → 韩股

## 配额

Cloudflare Workers 免费计划：**10 万次请求/天**，对量化系统个人使用完全够用。

## 部署（约 2 分钟）

1. 注册 [Cloudflare](https://dash.cloudflare.com) 账号（免费）。
2. 安装 [Wrangler CLI](https://developers.cloudflare.com/workers/wrangler/)：
   ```bash
   npm install -g wrangler
   ```
3. 登录并部署：
   ```bash
   cd api
   npm install
   wrangler login        # 浏览器授权
   wrangler deploy       # 输出 https://market-data-api.<你的子域>.workers.dev
   ```
4. 后续更新代码后重新部署：
   ```bash
   cd api
   wrangler deploy
   ```

> **重要**：接口通过 GitHub 公开仓库读取数据，请确保 [market-data-pipeline](https://github.com/448776129/market-data-pipeline) 仓库为 **Public**（否则 404）。数据由你已经配置好的 GitHub Actions 自动更新，接口无需改动。

## 本地开发

```bash
cd api
npm install
wrangler dev          # 本地 http://localhost:8787
```
# ParkWise — Redis 智慧停車場管理系統

## 專案動機

實體停車場會持續發生車輛進出。當多台車同時進場時，系統必須避免重複分配同一車位；離場後，又要立即釋放車位，供下一台車使用。ParkWise 以網頁模擬上述流程，展示 Redis 在即時狀態管理與多人競爭資源時的用途。

## 專題目標

- 建立包含 A 區 12 格、B 區 8 格的 20 格停車場。
- 支援輸入模擬車牌、自動分配車位、判斷滿位及防止同車牌重複入場。
- 支援車輛離場、車位回收、模擬停車費計算。
- 透過 Redis Streams 保留進出場事件，並使用 Pub/Sub 更新網頁狀態。
- 透過壓力測試與資料一致性檢查驗證系統功能。

## 系統架構

瀏覽器 → Flask REST API → Redis Lua Script → Redis Sorted Set / Hash / Streams；Redis Pub/Sub → Flask SSE → 瀏覽器即時更新。Docker Compose 用於在本機啟動 Redis 服務；雲端可改用獨立 Redis 服務。

## Redis 進階功能

| 功能 | 實際用途 |
|---|---|
| Lua Script | 原子性檢查車牌、分配車位、記錄入場及離場 |
| Sorted Set | 保存空車位、使用 `ZPOPMIN` 分配車位，離場時 `ZADD` 歸還 |
| Streams | 用 `XADD` 保留進出場事件 |
| Pub/Sub | 使用 `PUBLISH` 通知網頁狀態異動 |
| Pipeline / Transactions | 以 Transaction 重設模擬資料，Pipeline 批次取得儀表板資料 |

## 實際測試成果

測試指令：`python load_test.py --users 50 --workers 50 --turnover 5 --reset`

依據本專題本機實測的終端機輸出：

| 指標 | 實測結果 |
|---|---|
| 模擬車牌 | 50 個不同車牌 |
| 並行工作執行緒 | 最多 50 個 |
| 初始車位 | 20 格 |
| 成功入場 | 20 台 |
| 滿位拒絕 | 30 台 |
| 後續離場 | 5 台 |
| 新車重新入場 | 5 台 |
| 最終在場車輛 | 20 台 |
| 累計入場／離場 | 25 次／5 次 |
| Redis Stream 事件 | 30 筆 |
| 模擬營收 | NT$150 |
| 一致性驗證 | PASS |

上述結果為本機一次實測紀錄，部署到雲端後仍應重新驗證；50 個執行緒不代表所有車輛在完全相同時間點到達。

## 專案限制

本專題使用模擬車牌與計費規則，尚未整合車牌辨識、感應設備、正式金流與使用者身分驗證；因此定位為課堂展示，不是實際商用停車場平台。

## 部署與參考文件

- 啟動方式及 Redis Keys：`README.md`
- GitHub / Render / 雲端 Redis 部署：`DEPLOY_GUIDE_TW.md`
- Redis 官方文件：https://redis.io/docs/latest/
- Flask 官方文件：https://flask.palletsprojects.com/

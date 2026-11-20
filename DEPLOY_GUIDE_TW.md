# ParkWise 雲端部署教學（GitHub + Render + Redis）

本教學說明如何將 ParkWise 的 Flask 網站與 Redis 資料庫部署到雲端，取得可供課堂展示的公開 URL。

## 1. ParkWise 專案結構

解壓縮後開啟 `ParkWise/`，至少可以看到：
- `app.py`：Flask 後端 + Redis Lua Script / Streams / Pub/Sub
- `wsgi.py`：Render/Gunicorn 啟動入口
- `render.yaml`：Render 配置範例
- `requirements.txt`：Python 套件（含 gunicorn）
- `templates/`：HTML 頁面
- `static/`：CSS/JavaScript
- `docker-compose.yml`：Windows 本機 Redis 容器（雲端不使用）
- `load_test.py`、`verify_redis.py`：測試、驗證
- `.env.example`：本機設定範例（不要上傳真正 `.env`）
- `README.md`：功能介紹與本機啟動說明

## 2. 上傳 GitHub

1. 開啟 https://github.com/new ，建立 `ParkWise` repository。
2. 解壓縮 ZIP，**進入最裡面的 `ParkWise` 資料夾**，選取 `app.py`、`wsgi.py`、`static/`、`templates/` 等所有內容上傳到 GitHub repository 根目錄。
3. 在 GitHub 首頁要直接看見 `app.py`、`requirements.txt`、`wsgi.py`、`render.yaml`；如果只能看到另一層 `ParkWise` 資料夾，代表放錯層級。
4. 不要上傳 `.env`、`.venv/`、`__pycache__/`、真實車牌資料或密碼。

## 3. 準備雲端 Redis

使用你選擇的 Redis 服務供應商，取得允許 Render 伺服器存取的完整 Redis 連線 URL，例如：

    rediss://default:<PASSWORD>@<HOST>:<PORT>

上面只是格式範例，**不是可用連線字串**；請依服務商實際提供的內容設定。若服務要求 TLS，請使用 `rediss://`。不要把連線字串貼到 GitHub 或提交給不相關的人。

## 4. 在 Render 部署 Flask

1. 至 https://dashboard.render.com/ 登入。
2. 建立 New → Web Service，連接你的 GitHub `ParkWise` repository。
3. 依服務商介面選擇 Python runtime 和可用的 instance plan。
4. Build Command：`pip install -r requirements.txt`
5. Start Command：

    gunicorn --workers 1 --threads 16 --worker-class gthread --timeout 120 --bind 0.0.0.0:$PORT wsgi:app

6. Environment 設定（都不要放 GitHub）：
   - `REDIS_URL`：雲端 Redis 的完整連線 URL。
   - `ADMIN_TOKEN`：自行設定的高強度管理員密碼。
7. 執行 Deploy；如果有錯誤，查看 Render → Logs。
8. 當畫面顯示 Live、並取得公開 `https://...onrender.com` 網址時，才代表部署完成。

注意：Render 服務的 `localhost` 不是你 Windows 電腦，因此不能把本機 `redis://127.0.0.1:6380/0` 當成雲端 Redis URL。若你的部署平台不支援該方案，請以平台當下規則為準。

## 5. 驗收

1. 打開公開網址首頁，應該看見 20 格車位。
2. 打開 `/api/status`，應該返回 JSON。
3. 使用**模擬車牌**測試入場與離場、車位釋放。
4. 同時開兩個瀏覽器，確認資料更新。
5. 使用管理員密碼重設展示資料。

## 6. 安全提醒

本系統為教學 Demo，入場和離場 API 未實作使用者登入或速率限制；公開網址任何人都可能送出測試操作。請只放模擬車牌、假資料，不要放真實車牌或個資，也不要當成正式商用停車場管理服務。

## 7. Windows 本機測試（可選）

在解壓縮後的 `ParkWise` 資料夾：

```powershell
docker compose up -d
docker compose exec redis redis-cli ping
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe app.py
```

請在 `.env` 修改 `ADMIN_TOKEN`。本機網站： http://127.0.0.1:5001 。

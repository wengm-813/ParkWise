"""50 vehicles compete for 20 slots; demonstrate exit + reuse.

Example:
    python load_test.py --users 50 --workers 50 --turnover 5 --reset
"""
import argparse
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))


def main():
    p = argparse.ArgumentParser(description='ParkWise concurrency and turnover demo')
    p.add_argument('--users', type=int, default=50)
    p.add_argument('--workers', type=int, default=50)
    p.add_argument('--turnover', type=int, default=5,
                   help='成功入場者離場幾台，再補相同數量的車')
    p.add_argument('--reset', action='store_true', help='測試前使用 .env 管理員密碼重設資料')
    p.add_argument('--url', default='http://127.0.0.1:5001')
    args = p.parse_args()
    if args.users < 1 or args.workers < 1 or args.turnover < 0:
        p.error('users、workers 必須大於 0；turnover 不可小於 0')
    base = args.url.rstrip('/')

    def send(path, data):
        try:
            res = requests.post(base + path, json=data, timeout=25)
            return res.json()
        except (requests.RequestException, ValueError) as exc:
            return {'ok': False, 'code': 'NETWORK_ERROR', 'message': str(exc)}

    if args.reset:
        token = os.getenv('ADMIN_TOKEN', '')
        if not token or token == 'CHANGE_THIS_TO_YOUR_OWN_SECRET':
            p.error('請先修改 .env 中的 ADMIN_TOKEN，再使用 --reset')
        try:
            res = requests.post(base + '/api/admin/reset', headers={'X-Admin-Token': token}, timeout=10)
            res.raise_for_status()
            print('管理員重設成功：20 格空車位')
        except requests.RequestException as exc:
            p.error(f'重設失敗：{exc}')

    print(f'第一階段：{args.users} 位不同車牌、最多 {args.workers} 個並行工作執行緒，競爭 20 格車位')
    def one_enter(index):
        plate = f'TEST-{index:04d}'
        return plate, send('/api/enter', {'plate': plate, 'zone': 'AUTO'})

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(one_enter, i) for i in range(1, args.users + 1)]
        for future in as_completed(futures):
            results.append(future.result())
    counts = Counter(result.get('code', '?') for _, result in results)
    for code, count in sorted(counts.items()):
        print(f'  {code}: {count}')
    successful = sorted(plate for plate, resp in results if resp.get('code') == 'ENTERED')
    try:
        state = requests.get(base + '/api/status', timeout=10).json()
        print(f'  當前已停 {state["occupied"]} / {state["capacity"]} 格，空位 {state["free"]} 格')
    except (requests.RequestException, ValueError, KeyError) as exc:
        print(f'  無法讀取統計：{exc}')

    n = min(args.turnover, len(successful))
    if n:
        print(f'第二階段：讓 {n} 台車離場，再讓 {n} 台新車進場（示範車位循環使用）')
        for plate in successful[:n]:
            result = send('/api/exit', {'plate': plate})
            print(f'  出場 {plate}: {result.get("code", "?")}，費用 NT$ {result.get("fee", "?")}')
        for j in range(n):
            plate = f'NEW-{j+1:04d}'
            result = send('/api/enter', {'plate': plate, 'zone': 'AUTO'})
            print(f'  新車 {plate}: {result.get("code", "?")}，車位 {result.get("spot", "-")}')
        state = requests.get(base + '/api/status', timeout=10).json()
        print(f'  最終已停 {state["occupied"]} / {state["capacity"]}；累計入場 {state["metrics"]["total_entries"]}、離場 {state["metrics"]["total_exits"]}；營收 NT$ {state["metrics"]["total_revenue"]}')
    print('注意：測試結果需以實際輸出為準。若未重設、資料已存在或請求逾時，數字可能不同。')


if __name__ == '__main__':
    main()

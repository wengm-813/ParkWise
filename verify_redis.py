"""Read Redis values and check capacity/vehicle invariants for ParkWise."""
import os
from pathlib import Path

import redis
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))
r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://127.0.0.1:6380/0'), decode_responses=True)


def main():
    try:
        with r.pipeline() as pipe:
            pipe.zcard('parkwise:free:A')
            pipe.zcard('parkwise:free:B')
            pipe.hlen('parkwise:occupied')
            pipe.hlen('parkwise:plate_spot')
            pipe.hlen('parkwise:entry_time')
            pipe.xlen('parkwise:events')
            pipe.hgetall('parkwise:metrics')
            free_a, free_b, occupied, plates, timestamps, events, metrics = pipe.execute()
    except redis.RedisError as exc:
        raise SystemExit(f'無法連線 Redis: {exc}') from exc
    print('=== ParkWise Redis 驗證 ===')
    print(f'A 區空位: {free_a} / 12')
    print(f'B 區空位: {free_b} / 8')
    print(f'在場車輛: {occupied}')
    print(f'不同車牌: {plates}')
    print(f'入場時間欄位: {timestamps}')
    print(f'Stream 事件數: {events}')
    print(f'計數器: {metrics}')
    consistent = (free_a + free_b + occupied == 20 and occupied == plates == timestamps)
    print('資料結構一致性: ' + ('PASS ✅' if consistent else 'FAIL ❌'))
    if not consistent:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

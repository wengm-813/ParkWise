"""ParkWise 智慧停車場：Flask + Redis Lua / Sorted Set / Streams / Pub/Sub.

本專案為單一停車場、單一 Redis 執行個體的教學示範。
"""
from __future__ import annotations

import hmac
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import redis
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

load_dotenv(Path(__file__).with_name('.env'))

app = Flask(__name__)
r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://127.0.0.1:6380/0'), decode_responses=True)
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', '')
HOURLY_FEE = 30
ZONES = {'A': 12, 'B': 8}
PREFIX = 'parkwise:'
FREE_A = PREFIX + 'free:A'
FREE_B = PREFIX + 'free:B'
OCCUPIED = PREFIX + 'occupied'   # Hash: spot ID => plate
PLATE_SPOT = PREFIX + 'plate_spot'  # Hash: plate => spot ID
ENTRY_TIME = PREFIX + 'entry_time' # Hash: plate => UNIX timestamp
EVENTS = PREFIX + 'events'       # Redis Stream
CHANNEL = PREFIX + 'updates'     # Pub/Sub channel
METRICS = PREFIX + 'metrics'     # Hash counters
INITIALIZED = PREFIX + 'initialized'
RESET_KEYS = [FREE_A, FREE_B, OCCUPIED, PLATE_SPOT, ENTRY_TIME, EVENTS, METRICS, INITIALIZED]
LUA_KEYS = [FREE_A, FREE_B, OCCUPIED, PLATE_SPOT, ENTRY_TIME, EVENTS, CHANNEL, METRICS]

# Each entry attempt runs atomically, including slot allocation, metadata updates,
# Stream event and Pub/Sub notification. The physical slot is selected from ZSET.
ENTER_LUA = r''' 
local plate = ARGV[1]
local preferred = ARGV[2]
local now = ARGV[3]
if redis.call('HEXISTS', KEYS[4], plate) == 1 then
    redis.call('HINCRBY', KEYS[8], 'duplicate_denied', 1)
    return {'DUPLICATE', ''}
end
local selected = nil
local zone = nil
if preferred == 'A' or preferred == 'AUTO' then
    local p = redis.call('ZPOPMIN', KEYS[1])
    if #p > 0 then selected = p[1]; zone = 'A' end
end
if not selected and (preferred == 'B' or preferred == 'AUTO') then
    local p = redis.call('ZPOPMIN', KEYS[2])
    if #p > 0 then selected = p[1]; zone = 'B' end
end
if not selected then
    redis.call('HINCRBY', KEYS[8], 'full_denied', 1)
    return {'FULL', ''}
end
redis.call('HSET', KEYS[3], selected, plate)
redis.call('HSET', KEYS[4], plate, selected)
redis.call('HSET', KEYS[5], plate, now)
redis.call('HINCRBY', KEYS[8], 'total_entries', 1)
redis.call('XADD', KEYS[6], 'MAXLEN', '~', 5000, '*',
    'kind', 'entry', 'plate', plate, 'spot', selected,
    'zone', zone, 'timestamp', now, 'fee', '0')
redis.call('PUBLISH', KEYS[7], 'entry')
return {'ENTERED', selected, zone}
'''

# Exit atomically frees the spot, calculates parking fee and logs event.
EXIT_LUA = r'''
local plate = ARGV[1]
local now = tonumber(ARGV[2])
local rate = tonumber(ARGV[3])
local spot = redis.call('HGET', KEYS[4], plate)
if not spot then return {'NOT_FOUND', '', '0', '0'} end
local entered = tonumber(redis.call('HGET', KEYS[5], plate) or ARGV[2])
local seconds = math.max(0, now - entered)
local hours = math.max(1, math.ceil(seconds / 3600))
local fee = hours * rate
local zone = string.sub(spot, 1, 1)
local rank = tonumber(string.sub(spot, 3))
redis.call('HDEL', KEYS[3], spot)
redis.call('HDEL', KEYS[4], plate)
redis.call('HDEL', KEYS[5], plate)
if zone == 'A' then
    redis.call('ZADD', KEYS[1], rank, spot)
else
    redis.call('ZADD', KEYS[2], rank, spot)
end
redis.call('HINCRBY', KEYS[8], 'total_exits', 1)
redis.call('HINCRBY', KEYS[8], 'total_revenue', fee)
redis.call('XADD', KEYS[6], 'MAXLEN', '~', 5000, '*',
    'kind', 'exit', 'plate', plate, 'spot', spot,
    'zone', zone, 'timestamp', ARGV[2],
    'fee', tostring(fee), 'duration_seconds', tostring(seconds))
redis.call('PUBLISH', KEYS[7], 'exit')
return {'EXITED', spot, tostring(seconds), tostring(fee)}
'''

enter_script = r.register_script(ENTER_LUA)
exit_script = r.register_script(EXIT_LUA)


def reset_demo() -> None:
    """Safely reset demo data with a Redis MULTI/EXEC transaction."""
    with r.pipeline(transaction=True) as pipe:
        pipe.delete(*RESET_KEYS)
        pipe.zadd(FREE_A, {f'A-{i:02d}': i for i in range(1, ZONES['A'] + 1)})
        pipe.zadd(FREE_B, {f'B-{i:02d}': i for i in range(1, ZONES['B'] + 1)})
        pipe.hset(METRICS, mapping={
            'total_entries': 0, 'total_exits': 0,
            'total_revenue': 0, 'full_denied': 0, 'duplicate_denied': 0,
        })
        pipe.set(INITIALIZED, '1')
        pipe.publish(CHANNEL, 'reset')
        pipe.execute()


def ensure_initialized() -> None:
    if not r.exists(INITIALIZED):
        reset_demo()


def valid_plate(plate: str) -> bool:
    # General demo format, not a Taiwan plate-format validation.
    return bool(re.fullmatch(r'[A-Z0-9][A-Z0-9-]{1,11}', plate))


def status_snapshot() -> dict:
    with r.pipeline(transaction=False) as pipe:
        pipe.hgetall(OCCUPIED)
        pipe.hgetall(ENTRY_TIME)
        pipe.zcard(FREE_A)
        pipe.zcard(FREE_B)
        pipe.hgetall(METRICS)
        pipe.xrevrange(EVENTS, count=12)
        occupied, entry_times, free_a, free_b, raw_metrics, raw_events = pipe.execute()

    spots = []
    for zone, count in ZONES.items():
        for i in range(1, count + 1):
            sid = f'{zone}-{i:02d}'
            plate = occupied.get(sid)
            spots.append({
                'id': sid, 'zone': zone, 'occupied': bool(plate),
                'plate': plate or '',
                'entry_time': int(entry_times[plate]) if plate and plate in entry_times else None,
            })
    events = []
    for stream_id, fields in raw_events:
        ts = int(fields.get('timestamp', 0))
        events.append({
            'id': stream_id, 'kind': fields.get('kind', ''),
            'plate': fields.get('plate', ''), 'spot': fields.get('spot', ''),
            'fee': int(fields.get('fee', '0')),
            'time': datetime.fromtimestamp(ts).strftime('%H:%M:%S'),
        })
    metrics = {k: int(v) for k, v in raw_metrics.items()}
    total = sum(ZONES.values())
    free = free_a + free_b
    return {
        'capacity': total, 'occupied': total - free, 'free': free,
        'zones': {
            'A': {'capacity': ZONES['A'], 'free': free_a, 'occupied': ZONES['A'] - free_a},
            'B': {'capacity': ZONES['B'], 'free': free_b, 'occupied': ZONES['B'] - free_b},
        },
        'hourly_fee': HOURLY_FEE,
        'spots': spots, 'metrics': metrics, 'events': events,
        'server_time': int(time.time()),
    }


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/admin')
def admin():
    return render_template('admin.html')


@app.get('/api/status')
def api_status():
    return jsonify(status_snapshot())


@app.post('/api/enter')
def api_enter():
    payload = request.get_json(silent=True) or {}
    plate = str(payload.get('plate', '')).strip().upper()
    zone = str(payload.get('zone', 'AUTO')).strip().upper()
    if not valid_plate(plate):
        return jsonify(ok=False, code='INVALID_PLATE', message='車牌須為 2～12 位英數字或連字號'), 400
    if zone not in ('AUTO', 'A', 'B'):
        return jsonify(ok=False, code='INVALID_ZONE', message='請選擇自動、A 區或 B 區'), 400
    result = enter_script(keys=LUA_KEYS, args=[plate, zone, str(int(time.time()))])
    code = result[0]
    if code == 'DUPLICATE':
        return jsonify(ok=False, code=code, message='此車牌已在場內，不能重複入場'), 409
    if code == 'FULL':
        return jsonify(ok=False, code=code, message='指定區域已無空位，請稍後再試'), 409
    return jsonify(ok=True, code=code, plate=plate, spot=result[1], zone=result[2], message=f'入場成功，車位 {result[1]}')


@app.post('/api/exit')
def api_exit():
    payload = request.get_json(silent=True) or {}
    plate = str(payload.get('plate', '')).strip().upper()
    if not valid_plate(plate):
        return jsonify(ok=False, code='INVALID_PLATE', message='請輸入有效的車牌'), 400
    result = exit_script(keys=LUA_KEYS, args=[plate, str(int(time.time())), HOURLY_FEE])
    if result[0] == 'NOT_FOUND':
        return jsonify(ok=False, code='NOT_FOUND', message='此車牌目前不在場內'), 404
    return jsonify(ok=True, code=result[0], plate=plate, spot=result[1],
                   duration_seconds=int(result[2]), fee=int(result[3]),
                   message=f'出場成功，停車費 NT$ {result[3]}')


@app.post('/api/admin/reset')
def api_reset():
    if not ADMIN_TOKEN:
        return jsonify(ok=False, message='尚未設定 ADMIN_TOKEN，請先設定 .env'), 503
    provided = request.headers.get('X-Admin-Token', '')
    if not hmac.compare_digest(provided, ADMIN_TOKEN):
        return jsonify(ok=False, message='管理員密碼錯誤'), 403
    reset_demo()
    return jsonify(ok=True, message='停車場資料已重設：A 區 12 格、B 區 8 格')


@app.get('/api/live')
def api_live():
    """Bridge Redis Pub/Sub into browser EventSource (Server-Sent Events)."""
    def generate():
        with r.pubsub(ignore_subscribe_messages=True) as pubsub:
            pubsub.subscribe(CHANNEL)
            yield 'retry: 2000\n\n'
            while True:
                message = pubsub.get_message(timeout=15.0)
                if message is None:
                    yield ': heartbeat\n\n'
                else:
                    data = json.dumps({'event': message['data']}, ensure_ascii=False)
                    yield f'data: {data}\n\n'
    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


if __name__ == '__main__':
    try:
        r.ping()
        ensure_initialized()
    except redis.RedisError as exc:
        raise SystemExit(f'無法連線到 Redis，請確認 Docker 容器已啟動。詳細資訊：{exc}') from exc
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5001')), debug=False, threaded=True)

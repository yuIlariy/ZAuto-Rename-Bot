# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Special Thanks To @ReshamOwner
# Update Channel @Digital_Botz & @OthersBees
"""
Apache License 2.0
Copyright (c) 2025 @Digital_Botz
"""

from aiohttp import web
from datetime import datetime, timezone, timedelta
import time
import psutil
import shutil
import os
import json
import hmac
import hashlib
import asyncio
from urllib.parse import parse_qsl
from config import Config
from plugins import __version__
from helper.utils import humanbytes
from helper.database import digital_botz

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)

DigitalAutoRenameBot = web.RouteTableDef()

# --- NETWORK SPEED TRACKER GLOBALS (UNCHANGED) ---
last_net_io = psutil.net_io_counters()
last_time = time.time()
last_up_speed = 0.0
last_dl_speed = 0.0

# --- DB QUERY TTL CACHE (Reduces MongoDB load on rapid stream ticks) ---
_db_cache = {
    "timestamp": 0.0,
    "ttl": 15.0,
    "real_total_users": 0,
    "real_total_premium_users": 0,
    "raw_total_renames": 0,
    "net_stats": {"sent": 0, "recv": 0}
}

# --- PERSISTENT 7-DAY & 24-HOUR ANALYTICS ROLLUP BUFFER & CACHE ---
_rollup_buffer = {
    "daily": {},   # { "YYYY-MM-DD": {"renames": int, "bytes": int, "peak": int} }
    "hourly": {}   # { "YYYY-MM-DDTHH": {"renames": int, "bytes": int, "peak": int} }
}

_analytics_cache = {
    "7d": {"timestamp": 0.0, "ttl": 15.0, "data": None},
    "24h": {"timestamp": 0.0, "ttl": 15.0, "data": None}
}

# --- SHARED SSE BROADCASTER STATE ---
_sse_subscribers = set()
_latest_raw_bundle = None

# --- GLOBAL BROADCAST JOB STATE ---
_broadcast_state = {
    "running": False,
    "total": 0,
    "sent": 0,
    "failed": 0,
    "cancel_requested": False
}


def _utc_keys(now_dt=None):
    dt = now_dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%dT%H")


def record_rename_event(size_bytes: int):
    """Buffers a completed rename into in-memory hourly/daily rollup counters."""
    try:
        day_key, hour_key = _utc_keys()
        safe_bytes = max(0, int(size_bytes or 0))

        d_entry = _rollup_buffer["daily"].setdefault(day_key, {"renames": 0, "bytes": 0, "peak": 0})
        d_entry["renames"] += 1
        d_entry["bytes"] += safe_bytes

        h_entry = _rollup_buffer["hourly"].setdefault(hour_key, {"renames": 0, "bytes": 0, "peak": 0})
        h_entry["renames"] += 1
        h_entry["bytes"] += safe_bytes
    except Exception:
        pass


# ⚠️ INVISIBLE HOOK: Intercept successful uploads without modifying file_rename.py
if not hasattr(digital_botz, "_limit_is_hooked"):
    original_update_limit = digital_botz.update_daily_limit

    async def hooked_update_limit(user_id, size):
        await digital_botz.increment_total_renames()  # Saves to DB exactly once
        record_rename_event(size)
        return await original_update_limit(user_id, size)  # Pass back to DB normally

    digital_botz.update_daily_limit = hooked_update_limit
    digital_botz._limit_is_hooked = True


# ==========================================
# --- TELEGRAM MINI APP AUTH VERIFICATION ---
# ==========================================
def _get_admin_ids():
    raw = getattr(Config, "ADMIN", [])
    if isinstance(raw, int):
        return {raw}
    if isinstance(raw, (list, tuple, set)):
        return {int(x) for x in raw if str(x).isdigit()}
    if isinstance(raw, str):
        return {int(x) for x in raw.replace(",", " ").split() if x.isdigit()}
    return set()


def verify_telegram_user(init_data: str):
    """Validates Telegram WebApp initData via HMAC-SHA256 and returns the Telegram user dict if authentic."""
    bot_token = getattr(Config, "BOT_TOKEN", "")
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        # Reject expired initData older than 24 hours
        auth_date = int(parsed.get("auth_date", 0))
        if auth_date <= 0 or (time.time() - auth_date) > 86400:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_raw = parsed.get("user")
        if not user_raw:
            return None

        return json.loads(user_raw)
    except Exception:
        return None


def verify_telegram_webapp(init_data: str):
    """Validates Telegram WebApp initData and checks Config.ADMIN."""
    user_obj = verify_telegram_user(init_data)
    if not user_obj:
        return None
    user_id = int(user_obj.get("id", 0))
    if user_id not in _get_admin_ids():
        return None
    return user_obj


def _extract_viewer_from_request(request):
    """Extracts (user_id, is_admin, user_obj) from Authorization header or initData query param."""
    init_data = ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("tma "):
        init_data = auth_header[4:].strip()
    elif request.query.get("initData"):
        init_data = request.query.get("initData", "").strip()

    user_obj = verify_telegram_user(init_data)
    if not user_obj or "id" not in user_obj:
        return None, False, None
    uid = int(user_obj["id"])
    return uid, (uid in _get_admin_ids()), user_obj


def _extract_admin_from_request(request):
    _, is_admin, user_obj = _extract_viewer_from_request(request)
    return user_obj if is_admin else None


def mask_filename(filename: str) -> str:
    """Masks sensitive filenames for public viewers while preserving the file extension."""
    if not filename or not isinstance(filename, str):
        return "••••••••.bin"
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].strip()
        if ext and len(ext) <= 8 and "/" not in ext and "\\" not in ext and " " not in ext:
            return f"••••••••.{ext}"
    return "••••••••"


def format_short_number(num):
    """Formats numbers to 1k, 1.8k, 2.39k formats."""
    if num < 1000:
        return str(num)
    for unit in ['k', 'M', 'B']:
        num /= 1000.0
        if num < 1000:
            formatted = f"{num:.2f}".rstrip('0').rstrip('.')
            return f"{formatted}{unit}"
    return str(num)


def extract_extension(filename: str) -> str:
    """Extracts a brief uppercase file extension (e.g. MKV, MP4, ZIP)."""
    if not filename or not isinstance(filename, str) or "." not in filename:
        return ""
    ext = filename.rsplit(".", 1)[-1].strip().upper()
    if not ext or len(ext) > 8 or "/" in ext or "\\" in ext or " " in ext:
        return ""
    return ext


def parse_human_bytes(size_str):
    """Parses human-readable byte strings (e.g., '12.50 MB/s') back to float bytes."""
    if not size_str or not isinstance(size_str, str):
        return 0.0
    clean = size_str.replace("/s", "").strip()
    parts = clean.split()
    if len(parts) != 2:
        return 0.0
    try:
        val = float(parts[0])
    except ValueError:
        return 0.0
    unit = parts[1].upper()
    multipliers = {
        "B": 1,
        "KB": 1024, "KIB": 1024,
        "MB": 1024 ** 2, "MIB": 1024 ** 2,
        "GB": 1024 ** 3, "GIB": 1024 ** 3,
        "TB": 1024 ** 4, "TIB": 1024 ** 4,
    }
    return val * multipliers.get(unit, 1)


def format_eta(current_str, total_str, speed_str):
    """Calculates human-readable ETA from formatted progress strings."""
    speed_bps = parse_human_bytes(speed_str)
    if speed_bps <= 0:
        return "Calculating..."
    current_b = parse_human_bytes(current_str)
    total_b = parse_human_bytes(total_str)
    remaining_b = max(0.0, total_b - current_b)
    if remaining_b <= 0:
        return "Finishing..."
    rem_sec = int(remaining_b / speed_bps)
    if rem_sec < 60:
        return f"{rem_sec}s"
    mins, secs = divmod(rem_sec, 60)
    if mins < 60:
        return f"{mins}m {secs:02d}s"
    hrs, mins = divmod(mins, 60)
    return f"{hrs}h {mins:02d}m"


def _sample_active_tasks_count() -> int:
    """Reads live active pipeline task count safely."""
    try:
        from plugins import file_rename
        active_progress = getattr(file_rename, "active_progress", {})
        manager = getattr(file_rename, "manager", None)
        count = len(active_progress)
        if count == 0 and manager:
            for dl_list in getattr(manager, "active_downloads", {}).values():
                count += len(dl_list)
            for ul_list in getattr(manager, "staging_pool", {}).values():
                count += len(ul_list)
        return int(count)
    except Exception:
        return 0


async def flush_analytics_rollups():
    """Flushes buffered hourly and daily analytics rollups to MongoDB."""
    if not hasattr(digital_botz, "db") or digital_botz.db is None:
        return

    now_dt = datetime.now(timezone.utc)
    daily_col = digital_botz.db["analytics_daily"]
    hourly_col = digital_botz.db["analytics_hourly"]

    # Snapshot & swap buffers atomically
    daily_snapshot = _rollup_buffer["daily"]
    hourly_snapshot = _rollup_buffer["hourly"]
    _rollup_buffer["daily"] = {}
    _rollup_buffer["hourly"] = {}

    for day_key, vals in daily_snapshot.items():
        if vals["renames"] == 0 and vals["bytes"] == 0 and vals["peak"] == 0:
            continue
        try:
            await daily_col.update_one(
                {"_id": day_key},
                {
                    "$inc": {
                        "renames_count": vals["renames"],
                        "bytes_transferred": vals["bytes"]
                    },
                    "$max": {
                        "peak_active_tasks": vals["peak"]
                    },
                    "$set": {
                        "date": day_key,
                        "updated_at": now_dt
                    }
                },
                upsert=True
            )
            doc = await daily_col.find_one({"_id": day_key})
            if doc:
                gb_val = round(float(doc.get("bytes_transferred", 0)) / (1024 ** 3), 3)
                await daily_col.update_one({"_id": day_key}, {"$set": {"gb_transferred": gb_val}})
        except Exception:
            cur = _rollup_buffer["daily"].setdefault(day_key, {"renames": 0, "bytes": 0, "peak": 0})
            cur["renames"] += vals["renames"]
            cur["bytes"] += vals["bytes"]
            cur["peak"] = max(cur["peak"], vals["peak"])

    for hour_key, vals in hourly_snapshot.items():
        if vals["renames"] == 0 and vals["bytes"] == 0 and vals["peak"] == 0:
            continue
        try:
            await hourly_col.update_one(
                {"_id": hour_key},
                {
                    "$inc": {
                        "renames_count": vals["renames"],
                        "bytes_transferred": vals["bytes"]
                    },
                    "$max": {
                        "peak_active_tasks": vals["peak"]
                    },
                    "$set": {
                        "hour": hour_key,
                        "updated_at": now_dt
                    }
                },
                upsert=True
            )
            doc = await hourly_col.find_one({"_id": hour_key})
            if doc:
                gb_val = round(float(doc.get("bytes_transferred", 0)) / (1024 ** 3), 3)
                await hourly_col.update_one({"_id": hour_key}, {"$set": {"gb_transferred": gb_val}})
        except Exception:
            cur = _rollup_buffer["hourly"].setdefault(hour_key, {"renames": 0, "bytes": 0, "peak": 0})
            cur["renames"] += vals["renames"]
            cur["bytes"] += vals["bytes"]
            cur["peak"] = max(cur["peak"], vals["peak"])


async def _analytics_rollup_loop():
    """Lightweight background task sampling peak tasks every 5s and flushing MongoDB rollups every 30s."""
    last_flush = time.time()
    last_prune = 0.0

    while True:
        try:
            await asyncio.sleep(5.0)
            active_now = _sample_active_tasks_count()
            day_key, hour_key = _utc_keys()

            d_entry = _rollup_buffer["daily"].setdefault(day_key, {"renames": 0, "bytes": 0, "peak": 0})
            if active_now > d_entry["peak"]:
                d_entry["peak"] = active_now

            h_entry = _rollup_buffer["hourly"].setdefault(hour_key, {"renames": 0, "bytes": 0, "peak": 0})
            if active_now > h_entry["peak"]:
                h_entry["peak"] = active_now

            now = time.time()
            if now - last_flush >= 30.0:
                await flush_analytics_rollups()
                last_flush = now
                _analytics_cache["7d"]["timestamp"] = 0.0
                _analytics_cache["24h"]["timestamp"] = 0.0

            # Prune hourly documents older than 8 days once per hour
            if now - last_prune >= 3600.0 and hasattr(digital_botz, "db") and digital_botz.db is not None:
                try:
                    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H")
                    await digital_botz.db["analytics_hourly"].delete_many({"_id": {"$lt": cutoff}})
                except Exception:
                    pass
                last_prune = now

        except asyncio.CancelledError:
            await flush_analytics_rollups()
            break
        except Exception:
            await asyncio.sleep(5.0)


async def get_7d_analytics():
    """Returns 7-day daily rollup series (renames_count, gb_transferred, peak_active_tasks) with 15s cache."""
    cache_slot = _analytics_cache["7d"]
    now_ts = time.time()
    if cache_slot["data"] is not None and (now_ts - cache_slot["timestamp"]) < cache_slot["ttl"]:
        return cache_slot["data"]

    now_dt = datetime.now(timezone.utc)
    day_keys = [(now_dt - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
    docs_by_day = {}

    if hasattr(digital_botz, "db") and digital_botz.db is not None:
        try:
            cursor = digital_botz.db["analytics_daily"].find({"_id": {"$in": day_keys}})
            async for doc in cursor:
                docs_by_day[doc["_id"]] = doc
        except Exception:
            pass

    days_list = []
    total_renames_7d = 0
    total_bytes_7d = 0
    peak_tasks_7d = 0

    for idx, d_key in enumerate(day_keys):
        db_doc = docs_by_day.get(d_key, {})
        pending = _rollup_buffer["daily"].get(d_key, {"renames": 0, "bytes": 0, "peak": 0})

        renames_count = int(db_doc.get("renames_count", 0)) + int(pending.get("renames", 0))
        bytes_transferred = int(db_doc.get("bytes_transferred", 0)) + int(pending.get("bytes", 0))
        gb_transferred = round(bytes_transferred / (1024 ** 3), 2)
        peak_active_tasks = max(int(db_doc.get("peak_active_tasks", 0)), int(pending.get("peak", 0)))

        dt_obj = datetime.strptime(d_key, "%Y-%m-%d")
        short_label = "Today" if idx == 6 else dt_obj.strftime("%b %d")

        total_renames_7d += renames_count
        total_bytes_7d += bytes_transferred
        if peak_active_tasks > peak_tasks_7d:
            peak_tasks_7d = peak_active_tasks

        days_list.append({
            "date": d_key,
            "label": short_label,
            "renames_count": renames_count,
            "gb_transferred": gb_transferred,
            "bytes_transferred": bytes_transferred,
            "peak_active_tasks": peak_active_tasks
        })

    result = {
        "range": "7d",
        "days": days_list,
        "summary": {
            "total_renames": total_renames_7d,
            "total_renames_short": format_short_number(total_renames_7d),
            "total_gb": round(total_bytes_7d / (1024 ** 3), 2),
            "peak_active_tasks": peak_tasks_7d
        }
    }

    cache_slot["data"] = result
    cache_slot["timestamp"] = now_ts
    return result


async def get_24h_analytics():
    """Returns 24-hour hourly rollup series in the same schema as get_7d_analytics for seamless chart toggling."""
    cache_slot = _analytics_cache["24h"]
    now_ts = time.time()
    if cache_slot["data"] is not None and (now_ts - cache_slot["timestamp"]) < cache_slot["ttl"]:
        return cache_slot["data"]

    now_dt = datetime.now(timezone.utc)
    hour_slots = [(now_dt - timedelta(hours=offset)) for offset in range(23, -1, -1)]
    hour_keys = [dt.strftime("%Y-%m-%dT%H") for dt in hour_slots]
    docs_by_hour = {}

    if hasattr(digital_botz, "db") and digital_botz.db is not None:
        try:
            cursor = digital_botz.db["analytics_hourly"].find({"_id": {"$in": hour_keys}})
            async for doc in cursor:
                docs_by_hour[doc["_id"]] = doc
        except Exception:
            pass

    buckets = []
    total_renames_24h = 0
    total_bytes_24h = 0
    peak_tasks_24h = 0

    for idx, dt_obj in enumerate(hour_slots):
        h_key = dt_obj.strftime("%Y-%m-%dT%H")
        db_doc = docs_by_hour.get(h_key, {})
        pending = _rollup_buffer["hourly"].get(h_key, {"renames": 0, "bytes": 0, "peak": 0})

        renames_count = int(db_doc.get("renames_count", 0)) + int(pending.get("renames", 0))
        bytes_transferred = int(db_doc.get("bytes_transferred", 0)) + int(pending.get("bytes", 0))
        gb_transferred = round(bytes_transferred / (1024 ** 3), 2)
        peak_active_tasks = max(int(db_doc.get("peak_active_tasks", 0)), int(pending.get("peak", 0)))

        hour_label = dt_obj.strftime("%H:00")
        display_date = f"{dt_obj.strftime('%Y-%m-%d')} {hour_label} UTC"

        total_renames_24h += renames_count
        total_bytes_24h += bytes_transferred
        if peak_active_tasks > peak_tasks_24h:
            peak_tasks_24h = peak_active_tasks

        buckets.append({
            "date": display_date,
            "hour": hour_label,
            "label": "Now" if idx == 23 else hour_label,
            "renames_count": renames_count,
            "gb_transferred": gb_transferred,
            "bytes_transferred": bytes_transferred,
            "peak_active_tasks": peak_active_tasks
        })

    result = {
        "range": "24h",
        "days": buckets,
        "summary": {
            "total_renames": total_renames_24h,
            "total_renames_short": format_short_number(total_renames_24h),
            "total_gb": round(total_bytes_24h / (1024 ** 3), 2),
            "peak_active_tasks": peak_tasks_24h
        }
    }

    cache_slot["data"] = result
    cache_slot["timestamp"] = now_ts
    return result


async def get_cached_db_metrics():
    """Fetches DB metrics concurrently with a 15-second TTL cache."""
    now = time.time()
    if now - _db_cache["timestamp"] >= _db_cache["ttl"] or _db_cache["timestamp"] == 0.0:
        results = await asyncio.gather(
            digital_botz.total_users_count(),
            digital_botz.total_premium_users_count(),
            digital_botz.get_total_renames(),
            digital_botz.get_network_stats(),
            return_exceptions=True
        )
        if not isinstance(results[0], Exception) and results[0] is not None:
            _db_cache["real_total_users"] = results[0]
        if not isinstance(results[1], Exception) and results[1] is not None:
            _db_cache["real_total_premium_users"] = results[1]
        if not isinstance(results[2], Exception) and results[2] is not None:
            _db_cache["raw_total_renames"] = results[2]
        if not isinstance(results[3], Exception) and isinstance(results[3], dict):
            _db_cache["net_stats"] = results[3]
        _db_cache["timestamp"] = now

    return (
        _db_cache["real_total_users"],
        _db_cache["real_total_premium_users"],
        _db_cache["raw_total_renames"],
        _db_cache["net_stats"]
    )


def _build_worker_lookup():
    """Maps id(worker_client) -> readable worker label."""
    workers = getattr(Config, "WORKER_CLIENTS", [])
    lookup = {}
    for idx, w in enumerate(workers):
        w_name = getattr(w, "name", None)
        if not w_name:
            me = getattr(w, "me", None)
            w_name = f"@{me.username}" if getattr(me, "username", None) else getattr(me, "first_name", f"Worker-{idx + 1}")
        lookup[id(w)] = f"#{idx + 1} {w_name}"
    return lookup


async def get_status(is_admin: bool = False):
    """Fetches and formats system, fleet, and bot statistics."""
    global last_net_io, last_time, last_up_speed, last_dl_speed

    try:
        from plugins import file_rename
        worker_loads = getattr(file_rename, "worker_loads", {})
        manager = getattr(file_rename, "manager", None)
        active_progress = getattr(file_rename, "active_progress", {})
        queue_paused = bool(getattr(file_rename, "queue_paused", False))
        maintenance_message = str(getattr(file_rename, "maintenance_message", "") or "")
    except ImportError:
        worker_loads = {}
        manager = None
        active_progress = {}
        queue_paused = False
        maintenance_message = ""

    # Fetch cached DB values concurrently
    real_total_users, real_total_premium_users, raw_total_renames, net_stats = await get_cached_db_metrics()

    # Apply Magic Boost for public viewers; show exact DB counts to Admins
    if is_admin:
        total_users = real_total_users
        total_premium_users = real_total_premium_users
    else:
        total_users = real_total_users + 1009
        total_premium_users = real_total_premium_users + 64

    # --- UPTIME CALCULATIONS ---
    now = time.time()
    bot_sec = max(0, now - Config.BOT_UPTIME)
    b_days, b_rem = divmod(bot_sec, 86400)
    b_hrs, b_rem = divmod(b_rem, 3600)
    b_mins, b_secs = divmod(b_rem, 60)
    bot_uptime = f"{int(b_days)}d {int(b_hrs)}h {int(b_mins)}m" if b_days > 0 else f"{int(b_hrs):02d}h {int(b_mins):02d}m {int(b_secs):02d}s"

    sys_sec = max(0, now - psutil.boot_time())
    s_days, s_rem = divmod(sys_sec, 86400)
    s_hrs, s_rem = divmod(s_rem, 3600)
    s_mins, s_secs = divmod(s_rem, 60)
    system_uptime = f"{int(s_days)}d {int(s_hrs)}h {int(s_mins)}m" if s_days > 0 else f"{int(s_hrs):02d}h {int(s_mins):02d}m {int(s_secs):02d}s"

    total, used, free = shutil.disk_usage(".")

    # --- OVERALL BANDWIDTH SPEED TRACKER (UNCHANGED) ---
    current_net_io = psutil.net_io_counters()
    current_time = time.time()
    time_delta = current_time - last_time
    if time_delta >= 1.0:
        last_up_speed = max(0.0, (current_net_io.bytes_sent - last_net_io.bytes_sent) / time_delta)
        last_dl_speed = max(0.0, (current_net_io.bytes_recv - last_net_io.bytes_recv) / time_delta)
        last_net_io = current_net_io
        last_time = current_time

    formatted_total_renames = format_short_number(raw_total_renames)
    data_sent = humanbytes(net_stats.get('sent', 0))
    data_recv = humanbytes(net_stats.get('recv', 0))

    # --- AGGREGATE ACTIVE SPEED PER WORKER ID ---
    worker_speeds = {}
    for prog in list(active_progress.values()):
        wid = prog.get("worker_id")
        if wid is not None:
            bps = prog.get("speed_bps")
            if bps is None:
                bps = parse_human_bytes(prog.get("speed", "0 B/s"))
            worker_speeds[wid] = worker_speeds.get(wid, 0.0) + float(bps)

    # --- FLEET NODE & ACTIVE TASKS MONITORING ---
    workers = getattr(Config, "WORKER_CLIENTS", [])
    total_workers = len(workers)
    healthy_workers = 0
    active_workers = 0
    worker_nodes = []

    for idx, w in enumerate(workers):
        is_disabled = bool(getattr(w, "is_disabled", False))
        unhealthy_until = float(getattr(w, "unhealthy_until", 0) or 0)
        is_healthy = bool(getattr(w, "is_healthy", True)) and not is_disabled

        # Auto-reflect recovery once cooldown expires
        if not is_disabled and not is_healthy and unhealthy_until > 0 and now >= unhealthy_until:
            w.is_healthy = True
            w.unhealthy_until = 0
            is_healthy = True
            unhealthy_until = 0

        cooldown_sec = max(0, int(unhealthy_until - now)) if (not is_healthy and not is_disabled) else 0
        is_connected = bool(getattr(w, "is_connected", True))
        load = int(worker_loads.get(w, 0))

        if is_healthy:
            healthy_workers += 1
        if load > 0:
            active_workers += 1

        w_name = getattr(w, "name", None)
        if not w_name:
            me = getattr(w, "me", None)
            w_name = f"@{me.username}" if getattr(me, "username", None) else getattr(me, "first_name", f"Worker-{idx + 1}")

        node_bps = worker_speeds.get(id(w), 0.0)
        node_speed_str = f"{humanbytes(node_bps)}/s" if node_bps > 0 else "0 B/s"

        status_text = "Disabled" if is_disabled else ("Rate-Limited" if not is_healthy else ("Busy" if load > 0 else "Idle"))

        node_info = {
            "id": idx + 1,
            "worker_id": str(id(w)),
            "name": str(w_name),
            "healthy": is_healthy,
            "disabled": is_disabled,
            "connected": is_connected,
            "load": load,
            "cooldown_sec": cooldown_sec,
            "speed": node_speed_str,
            "speed_bps": round(node_bps, 2),
            "status": status_text,
            "floodwait_count": int(getattr(w, "floodwait_count", 0) or 0),
            "floodwait_total_sec": int(getattr(w, "floodwait_total_sec", 0) or 0)
        }
        if is_admin:
            node_info["floodwait_history"] = list(getattr(w, "floodwait_history", []) or [])[-10:]

        worker_nodes.append(node_info)

    free_workers = max(0, healthy_workers - active_workers)

    # Count active tasks & active user batches
    current_active_tasks = len(active_progress)
    if current_active_tasks == 0 and manager:
        for dl_list in getattr(manager, 'active_downloads', {}).values():
            current_active_tasks += len(dl_list)
        for ul_list in getattr(manager, 'staging_pool', {}).values():
            current_active_tasks += len(ul_list)

    active_batches = len(getattr(manager, 'batch_state', {})) if manager else 0

    up_speed_str = f"{humanbytes(last_up_speed)}/s" if last_up_speed > 0 else "0 B/s"
    dl_speed_str = f"{humanbytes(last_dl_speed)}/s" if last_dl_speed > 0 else "0 B/s"

    payload = {
        "bot_status": "Paused (Draining)" if queue_paused else "Operational",
        "queue_paused": queue_paused,
        "maintenance_message": maintenance_message if is_admin else "",
        "bot_version": __version__,
        "total_users": total_users,
        "premium_users": total_premium_users,
        "real_total_users": real_total_users if is_admin else None,
        "real_premium_users": real_total_premium_users if is_admin else None,
        "is_admin": is_admin,
        "bot_uptime": bot_uptime,
        "system_uptime": system_uptime,
        "cpu_usage": round(psutil.cpu_percent(), 1),
        "ram_usage": round(psutil.virtual_memory().percent, 1),
        "disk_usage": round(psutil.disk_usage('.').percent, 1),
        "total_disk": humanbytes(total),
        "used_disk": humanbytes(used),
        "free_disk": humanbytes(free),
        "data_sent": data_sent,
        "data_recv": data_recv,
        "up_speed": up_speed_str,
        "dl_speed": dl_speed_str,
        "up_speed_bps": round(last_up_speed, 2),
        "dl_speed_bps": round(last_dl_speed, 2),
        "total_renames": formatted_total_renames,
        "total_workers": total_workers,
        "healthy_workers": healthy_workers,
        "active_workers": active_workers,
        "free_workers": free_workers,
        "worker_nodes": worker_nodes,
        "active_tasks": current_active_tasks,
        "active_batches": active_batches,
        "timestamp": int(time.time()),
        "github_link": "https://github.com/DigitalBotz/Digital-Auto-Rename-Bot",
        "telegram_link": "https://t.me/OtherBs"
    }
    if is_admin:
        payload["broadcast"] = dict(_broadcast_state)
    return payload


def get_queue_data(viewer_uid=None, is_admin: bool = False):
    """Collects active downloads, active uploads, and queued pending tasks with viewer-aware privacy masking."""
    try:
        from plugins.file_rename import active_progress, manager
    except ImportError:
        return {"success": False, "error": "Cannot load required modules", "downloading": [], "uploading": [], "pending": []}

    try:
        worker_lookup = _build_worker_lookup()
        downloading = []
        uploading = []
        pending = []

        for tid, prog in list(active_progress.items()):
            raw_fname = (prog.get("filename") or "Unknown_File").strip()
            owner_id = prog.get("user_id")
            is_owner = (viewer_uid is not None and owner_id is not None and int(owner_id) == int(viewer_uid))
            can_see_name = is_admin or is_owner

            item = {
                "task_id": tid,
                "filename": raw_fname if can_see_name else mask_filename(raw_fname),
                "is_masked": not can_see_name,
                "is_owner": is_owner,
                "extension": extract_extension(raw_fname),
                "status": prog.get("status", "Downloading"),
                "percentage": prog.get("percentage", 0),
                "current": prog.get("current", "0 B"),
                "total": prog.get("total", "0 B"),
                "speed": prog.get("speed", "0 B/s"),
                "worker_name": worker_lookup.get(prog.get("worker_id"), "Primary Bot"),
                "eta": format_eta(
                    prog.get("current", "0 B"),
                    prog.get("total", "0 B"),
                    prog.get("speed", "0 B/s")
                )
            }
            if is_admin and owner_id is not None:
                item["user_id"] = owner_id

            if item["status"] == "Downloading":
                downloading.append(item)
            else:
                uploading.append(item)

        if manager and hasattr(manager, 'user_tasks'):
            for uid_key, u_tasks in list(manager.user_tasks.items()):
                for item in list(u_tasks):
                    msg = item.get('msg')
                    tid_str = str(item.get('task_id', ''))
                    if msg and getattr(msg, 'media', None):
                        rkn_file = getattr(msg, msg.media.value, None)
                        raw_fname = (getattr(rkn_file, 'file_name', None) or "Unknown_File").strip()
                        fsize = humanbytes(getattr(rkn_file, 'file_size', 0)) if getattr(rkn_file, 'file_size', 0) else ""
                        owner_id = getattr(getattr(msg, 'from_user', None), 'id', uid_key)
                        is_owner = (viewer_uid is not None and owner_id is not None and int(owner_id) == int(viewer_uid))
                        can_see_name = is_admin or is_owner

                        p_item = {
                            "task_id": tid_str,
                            "filename": raw_fname if can_see_name else mask_filename(raw_fname),
                            "is_masked": not can_see_name,
                            "is_owner": is_owner,
                            "extension": extract_extension(raw_fname),
                            "size": fsize,
                            "status": "Pending"
                        }
                        if is_admin and owner_id is not None:
                            p_item["user_id"] = owner_id
                        pending.append(p_item)

        return {
            "success": True,
            "downloading": downloading,
            "uploading": uploading,
            "pending": pending
        }
    except Exception as e:
        return {"success": False, "error": str(e), "downloading": [], "uploading": [], "pending": []}


def _personalize_bundle(raw_bundle: dict, viewer_uid=None, is_admin: bool = False) -> dict:
    """Produces a viewer-tailored copy of the shared telemetry snapshot without recomputing psutil/DB."""
    status_copy = dict(raw_bundle["status"])
    if not is_admin:
        status_copy["total_users"] = raw_bundle["real_total_users"] + 1009
        status_copy["premium_users"] = raw_bundle["real_total_premium_users"] + 64
        status_copy["real_total_users"] = None
        status_copy["real_premium_users"] = None
        status_copy["is_admin"] = False
        status_copy["maintenance_message"] = ""
        status_copy.pop("broadcast", None)
        status_copy["worker_nodes"] = [
            {k: v for k, v in n.items() if k != "floodwait_history"}
            for n in status_copy.get("worker_nodes", [])
        ]

    def _mask_list(raw_list):
        out = []
        for entry in raw_list:
            owner_id = entry.get("user_id")
            is_owner = (viewer_uid is not None and owner_id is not None and int(owner_id) == int(viewer_uid))
            can_see = is_admin or is_owner
            raw_name = entry.get("_raw_filename") or entry.get("filename", "Unknown_File")
            c = {k: v for k, v in entry.items() if k != "_raw_filename"}
            c["filename"] = raw_name if can_see else mask_filename(raw_name)
            c["is_masked"] = not can_see
            c["is_owner"] = is_owner
            if not is_admin:
                c.pop("user_id", None)
            out.append(c)
        return out

    q_raw = raw_bundle["queue"]
    queue_copy = {
        "success": q_raw.get("success", True),
        "downloading": _mask_list(q_raw.get("downloading", [])),
        "uploading": _mask_list(q_raw.get("uploading", [])),
        "pending": _mask_list(q_raw.get("pending", []))
    }

    return {
        "status": status_copy,
        "queue": queue_copy,
        "analytics_7d": raw_bundle["analytics_7d"],
        "analytics_24h": raw_bundle["analytics_24h"]
    }


async def _collect_raw_bundle() -> dict:
    """Collects raw unmasked status, queue, 7d & 24h analytics once per tick for the shared broadcaster."""
    status_admin = await get_status(is_admin=True)
    queue_admin = get_queue_data(viewer_uid=None, is_admin=True)
    for bucket in ("downloading", "uploading", "pending"):
        for item in queue_admin.get(bucket, []):
            item["_raw_filename"] = item.get("filename", "Unknown_File")

    a7d = await get_7d_analytics()
    a24h = await get_24h_analytics()

    return {
        "real_total_users": status_admin.get("real_total_users", 0),
        "real_total_premium_users": status_admin.get("real_premium_users", 0),
        "status": status_admin,
        "queue": queue_admin,
        "analytics_7d": a7d,
        "analytics_24h": a24h
    }


async def _sse_broadcaster_loop():
    """Single shared background loop computing telemetry once and fanning out to all SSE subscribers."""
    global _latest_raw_bundle
    while True:
        try:
            bundle = await _collect_raw_bundle()
            _latest_raw_bundle = bundle
            if _sse_subscribers:
                for q in list(_sse_subscribers):
                    if q.full():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        q.put_nowait(bundle)
                    except asyncio.QueueFull:
                        pass
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(1.0)


@DigitalAutoRenameBot.get("/", allow_head=True)
async def root_route_handler(request):
    status_data = await get_status(is_admin=False)

    try:
        with open('templates/welcome.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        return web.Response(text="API is Operational. (templates/welcome.html is missing)", content_type='text/plain')

    for key, value in status_data.items():
        if not isinstance(value, (list, dict)) and value is not None:
            html_content = html_content.replace(f'{{{{{key}}}}}', str(value))

    return web.Response(text=html_content, content_type='text/html')


@DigitalAutoRenameBot.get("/api/status")
async def api_status_handler(request):
    _, is_admin, _ = _extract_viewer_from_request(request)
    status_data = await get_status(is_admin=is_admin)
    return web.json_response(status_data)


@DigitalAutoRenameBot.get("/api/queue")
async def api_queue_handler(request):
    viewer_uid, is_admin, _ = _extract_viewer_from_request(request)
    return web.json_response(get_queue_data(viewer_uid=viewer_uid, is_admin=is_admin))


@DigitalAutoRenameBot.get("/api/user/plan")
async def api_user_plan_handler(request):
    """Returns personal plan type, daily usage, remaining quota, and expiry for authenticated Mini App users."""
    viewer_uid, is_admin, user_obj = _extract_viewer_from_request(request)
    if viewer_uid is None:
        return web.json_response({"authenticated": False})

    plan = await digital_botz.get_user_plan_stats(viewer_uid)
    plan["authenticated"] = True
    plan["is_admin"] = is_admin
    plan["first_name"] = (user_obj or {}).get("first_name", "User")
    return web.json_response(plan)


@DigitalAutoRenameBot.get("/api/analytics/7d")
async def api_analytics_7d_handler(request):
    analytics_data = await get_7d_analytics()
    return web.json_response(analytics_data)


@DigitalAutoRenameBot.get("/api/analytics/24h")
async def api_analytics_24h_handler(request):
    analytics_data = await get_24h_analytics()
    return web.json_response(analytics_data)


@DigitalAutoRenameBot.post("/api/admin/verify")
async def api_admin_verify_handler(request):
    """Verifies Telegram Mini App initData and unlocks admin UI if user is in Config.ADMIN."""
    admin_user = _extract_admin_from_request(request)
    if not admin_user:
        return web.json_response({"authorized": False}, status=403)
    return web.json_response({
        "authorized": True,
        "user": {
            "id": admin_user.get("id"),
            "first_name": admin_user.get("first_name", "Admin"),
            "username": admin_user.get("username", "")
        }
    })


@DigitalAutoRenameBot.get("/api/admin/user")
async def api_admin_user_lookup_handler(request):
    """Looks up a bot user by numeric ID or @username for the Admin Console."""
    if not _extract_admin_from_request(request):
        return web.json_response({"success": False, "error": "Unauthorized Telegram session"}, status=403)

    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"success": False, "error": "Enter a User ID or @username"}, status=400)

    doc = await digital_botz.find_user_by_query(q)
    if not doc:
        return web.json_response({"success": False, "error": "User not found in database"}, status=404)

    uid = int(doc["_id"])
    plan = await digital_botz.get_user_plan_stats(uid)
    ban = doc.get("ban_status") or {}

    try:
        from plugins.file_rename import active_progress, manager
        active_cnt = sum(1 for p in active_progress.values() if p.get("user_id") == uid)
        queued_cnt = len(manager.user_tasks.get(uid, [])) + len(manager.staging_pool.get(uid, []))
    except Exception:
        active_cnt = 0
        queued_cnt = 0

    return web.json_response({
        "success": True,
        "user": {
            "user_id": uid,
            "first_name": doc.get("first_name") or "Unknown",
            "username": doc.get("username") or "",
            "is_banned": bool(ban.get("is_banned", False)),
            "ban_reason": ban.get("ban_reason", ""),
            "active_tasks": active_cnt,
            "queued_tasks": queued_cnt,
            "plan": plan
        }
    })


async def _run_broadcast_job(text: str):
    _broadcast_state.update({
        "running": True,
        "total": 0,
        "sent": 0,
        "failed": 0,
        "cancel_requested": False
    })

    try:
        from plugins import file_rename
        bot = getattr(file_rename, "active_bot_client", None)
        if not bot or not hasattr(digital_botz, "db") or digital_botz.db is None:
            return

        user_ids = [doc["_id"] async for doc in digital_botz.db["user"].find({}, {"_id": 1})]
        _broadcast_state["total"] = len(user_ids)

        for uid in user_ids:
            if _broadcast_state["cancel_requested"]:
                break
            try:
                await bot.send_message(int(uid), text)
                _broadcast_state["sent"] += 1
            except Exception as e:
                wait_sec = getattr(e, "value", None)
                if wait_sec:
                    await asyncio.sleep(int(wait_sec))
                    try:
                        await bot.send_message(int(uid), text)
                        _broadcast_state["sent"] += 1
                    except Exception:
                        _broadcast_state["failed"] += 1
                else:
                    _broadcast_state["failed"] += 1
            await asyncio.sleep(0.06)
    finally:
        _broadcast_state["running"] = False


@DigitalAutoRenameBot.post("/api/admin/action")
async def api_admin_action_handler(request):
    """Executes authenticated Telegram Mini App admin commands."""
    admin_user = _extract_admin_from_request(request)
    if not admin_user:
        return web.json_response({"success": False, "error": "Unauthorized Telegram session"}, status=403)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Invalid JSON payload"}, status=400)

    action = body.get("action")

    if action == "purge_queue":
        try:
            from helper.database import Task
            from plugins.file_rename import active_progress, manager

            running_ids = set(active_progress.keys())
            if manager and hasattr(manager, "staging_pool"):
                for staged_list in manager.staging_pool.values():
                    for item in staged_list:
                        running_ids.add(str(item.get("task_id")))

            purged_pending = 0
            if manager and hasattr(manager, "user_tasks"):
                for uid, u_tasks in list(manager.user_tasks.items()):
                    lock = await manager.get_lock(uid)
                    async with lock:
                        kept = []
                        for item in u_tasks:
                            tid_str = str(item.get("task_id"))
                            if tid_str in running_ids:
                                kept.append(item)
                            else:
                                purged_pending += 1
                                if uid in manager.batch_state:
                                    manager.batch_state[uid]["total_files"] = max(
                                        manager.batch_state[uid]["processed"],
                                        manager.batch_state[uid]["total_files"] - 1
                                    )
                        manager.user_tasks[uid] = kept

            all_tasks = await Task.find_all().to_list()
            deleted_db = 0
            for t in all_tasks:
                if str(t.id) not in running_ids:
                    await t.delete()
                    deleted_db += 1

            total_purged = max(deleted_db, purged_pending)
            return web.json_response({
                "success": True,
                "message": f"Purged {total_purged} stuck/pending task(s) without touching active transfers."
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "heal_workers":
        try:
            from plugins.file_rename import manager
            workers = getattr(Config, "WORKER_CLIENTS", [])
            healed = 0
            reconnected = 0

            for w in workers:
                if getattr(w, "is_disabled", False):
                    continue
                if not getattr(w, "is_healthy", True) or getattr(w, "unhealthy_until", 0) > 0:
                    healed += 1
                w.is_healthy = True
                w.unhealthy_until = 0
                if not getattr(w, "is_connected", True):
                    try:
                        await w.connect()
                        reconnected += 1
                    except Exception:
                        pass

            if manager and hasattr(manager, "silent_users"):
                manager.silent_users.clear()

            return web.json_response({
                "success": True,
                "message": f"Healed {healed} node(s) & reconnected {reconnected} session(s)."
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "worker_control":
        try:
            workers = getattr(Config, "WORKER_CLIENTS", [])
            worker_id = str(body.get("worker_id", "")).strip()
            op = str(body.get("op", "")).strip()
            target = next((w for w in workers if str(id(w)) == worker_id), None)
            if target is None:
                return web.json_response({"success": False, "error": "Worker node not found"}, status=404)

            if op == "heal":
                target.is_disabled = False
                target.is_healthy = True
                target.unhealthy_until = 0
                return web.json_response({"success": True, "message": "Worker node healed and restored."})
            elif op == "disable":
                target.is_disabled = True
                target.is_healthy = False
                return web.json_response({"success": True, "message": "Worker node disabled from rotation."})
            elif op == "enable":
                target.is_disabled = False
                target.is_healthy = True
                target.unhealthy_until = 0
                return web.json_response({"success": True, "message": "Worker node enabled."})
            return web.json_response({"success": False, "error": "Invalid worker operation"}, status=400)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "toggle_pause":
        try:
            from plugins import file_rename
            file_rename.queue_paused = not bool(getattr(file_rename, "queue_paused", False))
            state_label = "PAUSED (draining active batches)" if file_rename.queue_paused else "RESUMED (accepting batches)"
            return web.json_response({
                "success": True,
                "queue_paused": file_rename.queue_paused,
                "message": f"Batch intake is now {state_label}."
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "set_maintenance_message":
        try:
            from plugins import file_rename
            file_rename.maintenance_message = str(body.get("message", "") or "").strip()
            return web.json_response({
                "success": True,
                "message": "Maintenance notice saved."
            })
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "cancel_task":
        try:
            from plugins import file_rename
            task_id = str(body.get("task_id", "")).strip()
            if hasattr(file_rename, "cancel_single_task"):
                ok, msg = await file_rename.cancel_single_task(task_id, getattr(file_rename, "active_bot_client", None))
                return web.json_response({"success": ok, "message": msg, "error": None if ok else msg}, status=200 if ok else 404)
            return web.json_response({"success": False, "error": "Task cancellation unavailable"}, status=500)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "user_manage":
        try:
            from plugins import file_rename
            target_uid = int(body.get("user_id", 0))
            op = str(body.get("op", "")).strip()
            if not target_uid:
                return web.json_response({"success": False, "error": "Invalid user_id"}, status=400)

            if op == "grant_premium":
                days = int(body.get("days", 30))
                await digital_botz.add_premium(target_uid, days)
                _db_cache["timestamp"] = 0.0
                label = "Lifetime" if days == 0 else f"{days}d"
                return web.json_response({"success": True, "message": f"Granted {label} Premium to {target_uid}."})
            elif op == "revoke_premium":
                await digital_botz.remove_premium(target_uid)
                _db_cache["timestamp"] = 0.0
                return web.json_response({"success": True, "message": f"Revoked Premium from {target_uid}."})
            elif op == "ban":
                reason = str(body.get("reason", "Banned by Admin")).strip() or "Banned by Admin"
                await digital_botz.ban_user(target_uid, 0, reason)
                cleared = 0
                if hasattr(file_rename, "cancel_user_tasks"):
                    cleared = await file_rename.cancel_user_tasks(target_uid, getattr(file_rename, "active_bot_client", None))
                return web.json_response({"success": True, "message": f"Banned {target_uid} & cleared {cleared} task(s)."})
            elif op == "unban":
                await digital_botz.remove_ban(target_uid)
                return web.json_response({"success": True, "message": f"Unbanned {target_uid}."})
            elif op == "clear_tasks":
                cleared = 0
                if hasattr(file_rename, "cancel_user_tasks"):
                    cleared = await file_rename.cancel_user_tasks(target_uid, getattr(file_rename, "active_bot_client", None))
                else:
                    await digital_botz.clear_user_tasks(target_uid)
                return web.json_response({"success": True, "message": f"Cleared {cleared} task(s) for user {target_uid}."})

            return web.json_response({"success": False, "error": "Unknown user operation"}, status=400)
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=500)

    elif action == "broadcast_start":
        if _broadcast_state["running"]:
            return web.json_response({"success": False, "error": "A broadcast is already running."}, status=409)
        msg = str(body.get("message", "")).strip()
        if not msg:
            return web.json_response({"success": False, "error": "Broadcast message cannot be empty."}, status=400)
        asyncio.create_task(_run_broadcast_job(msg))
        return web.json_response({"success": True, "message": "Broadcast started in background."})

    elif action == "broadcast_cancel":
        _broadcast_state["cancel_requested"] = True
        return web.json_response({"success": True, "message": "Broadcast cancellation requested."})

    return web.json_response({"success": False, "error": "Unknown admin action"}, status=400)


@DigitalAutoRenameBot.get("/api/stream")
async def api_stream_handler(request):
    """Unified Server-Sent Events (SSE) endpoint backed by a single shared broadcaster."""
    viewer_uid, is_admin, _ = _extract_viewer_from_request(request)

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )
    await response.prepare(request)

    q = asyncio.Queue(maxsize=2)
    _sse_subscribers.add(q)

    try:
        initial_raw = _latest_raw_bundle or await _collect_raw_bundle()
        initial_payload = _personalize_bundle(initial_raw, viewer_uid=viewer_uid, is_admin=is_admin)
        await response.write(f"data: {json.dumps(initial_payload)}\n\n".encode("utf-8"))
        await response.drain()

        while True:
            try:
                raw_bundle = await asyncio.wait_for(q.get(), timeout=15.0)
                payload = _personalize_bundle(raw_bundle, viewer_uid=viewer_uid, is_admin=is_admin)
                await response.write(f"data: {json.dumps(payload)}\n\n".encode("utf-8"))
                await response.drain()
            except asyncio.TimeoutError:
                await response.write(b": keepalive\n\n")
                await response.drain()
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception:
        pass
    finally:
        _sse_subscribers.discard(q)

    return response


async def _on_startup_analytics(app):
    app["analytics_rollup_task"] = asyncio.create_task(_analytics_rollup_loop())
    app["sse_broadcaster_task"] = asyncio.create_task(_sse_broadcaster_loop())


async def _on_cleanup_analytics(app):
    for key in ("sse_broadcaster_task", "analytics_rollup_task"):
        task = app.get(key)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    await flush_analytics_rollups()


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(DigitalAutoRenameBot)
    web_app.on_startup.append(_on_startup_analytics)
    web_app.on_cleanup.append(_on_cleanup_analytics)
    return web_app

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
import time
import psutil
import shutil
import os
import json
import asyncio
from config import Config
from plugins import __version__
from helper.utils import humanbytes
from helper.database import digital_botz

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)

DigitalAutoRenameBot = web.RouteTableDef()

# --- NETWORK SPEED TRACKER GLOBALS ---
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

# ⚠️ INVISIBLE HOOK: Intercept successful uploads without modifying file_rename.py
if not hasattr(digital_botz, "_limit_is_hooked"):
    original_update_limit = digital_botz.update_daily_limit

    async def hooked_update_limit(user_id, size):
        await digital_botz.increment_total_renames()  # Saves to DB exactly once
        return await original_update_limit(user_id, size)  # Pass back to DB normally

    digital_botz.update_daily_limit = hooked_update_limit
    digital_botz._limit_is_hooked = True


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


async def get_status():
    """Fetches and formats system, fleet, and bot statistics."""
    global last_net_io, last_time, last_up_speed, last_dl_speed

    try:
        from plugins.file_rename import worker_loads, manager, active_progress
    except ImportError:
        worker_loads = {}
        manager = None
        active_progress = {}

    # Fetch cached DB values concurrently
    real_total_users, real_total_premium_users, raw_total_renames, net_stats = await get_cached_db_metrics()

    # Apply Magic Boost
    total_users = real_total_users + 1009
    total_premium_users = real_total_premium_users + 64

    # --- UPTIME CALCULATIONS ---
    bot_sec = max(0, time.time() - Config.BOT_UPTIME)
    b_days, b_rem = divmod(bot_sec, 86400)
    b_hrs, b_rem = divmod(b_rem, 3600)
    b_mins, b_secs = divmod(b_rem, 60)
    bot_uptime = f"{int(b_days)}d {int(b_hrs)}h {int(b_mins)}m" if b_days > 0 else f"{int(b_hrs):02d}h {int(b_mins):02d}m {int(b_secs):02d}s"

    sys_sec = max(0, time.time() - psutil.boot_time())
    s_days, s_rem = divmod(sys_sec, 86400)
    s_hrs, s_rem = divmod(s_rem, 3600)
    s_mins, s_secs = divmod(s_rem, 60)
    system_uptime = f"{int(s_days)}d {int(s_hrs)}h {int(s_mins)}m" if s_days > 0 else f"{int(s_hrs):02d}h {int(s_mins):02d}m {int(s_secs):02d}s"

    total, used, free = shutil.disk_usage(".")

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

    # --- FLEET NODE & ACTIVE TASKS MONITORING ---
    workers = getattr(Config, "WORKER_CLIENTS", [])
    total_workers = len(workers)
    healthy_workers = 0
    active_workers = 0
    worker_nodes = []

    for idx, w in enumerate(workers):
        is_healthy = bool(getattr(w, "is_healthy", True))
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

        worker_nodes.append({
            "id": idx + 1,
            "name": str(w_name),
            "healthy": is_healthy,
            "connected": is_connected,
            "load": load,
            "status": "Rate-Limited" if not is_healthy else ("Busy" if load > 0 else "Idle")
        })

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

    return {
        "bot_status": "Operational",
        "bot_version": __version__,
        "total_users": total_users,
        "premium_users": total_premium_users,
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


def get_queue_data():
    """Collects active downloads, active uploads, and queued pending tasks."""
    try:
        from plugins.file_rename import active_progress, manager
    except ImportError:
        return {"success": False, "error": "Cannot load required modules", "downloading": [], "uploading": [], "pending": []}

    try:
        downloading = []
        uploading = []
        pending = []

        for tid, prog in list(active_progress.items()):
            item = dict(prog)
            item["task_id"] = tid
            item["eta"] = format_eta(
                item.get("current", "0 B"),
                item.get("total", "0 B"),
                item.get("speed", "0 B/s")
            )
            if item.get("status") == "Downloading":
                downloading.append(item)
            else:
                uploading.append(item)

        if manager and hasattr(manager, 'user_tasks'):
            for u_tasks in list(manager.user_tasks.values()):
                for item in list(u_tasks):
                    msg = item.get('msg')
                    if msg and getattr(msg, 'media', None):
                        rkn_file = getattr(msg, msg.media.value, None)
                        fname = getattr(rkn_file, 'file_name', None) or "Unknown_File"
                        fsize = humanbytes(getattr(rkn_file, 'file_size', 0)) if getattr(rkn_file, 'file_size', 0) else ""
                        pending.append({
                            "filename": fname,
                            "size": fsize,
                            "status": "Pending"
                        })

        return {
            "success": True,
            "downloading": downloading,
            "uploading": uploading,
            "pending": pending
        }
    except Exception as e:
        return {"success": False, "error": str(e), "downloading": [], "uploading": [], "pending": []}


@DigitalAutoRenameBot.get("/", allow_head=True)
async def root_route_handler(request):
    status_data = await get_status()

    try:
        with open('templates/welcome.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        return web.Response(text="API is Operational. (templates/welcome.html is missing)", content_type='text/plain')

    for key, value in status_data.items():
        if not isinstance(value, (list, dict)):
            html_content = html_content.replace(f'{{{{{key}}}}}', str(value))

    return web.Response(text=html_content, content_type='text/html')


@DigitalAutoRenameBot.get("/api/status")
async def api_status_handler(request):
    status_data = await get_status()
    return web.json_response(status_data)


@DigitalAutoRenameBot.get("/api/queue")
async def api_queue_handler(request):
    return web.json_response(get_queue_data())


@DigitalAutoRenameBot.get("/api/stream")
async def api_stream_handler(request):
    """Unified Server-Sent Events (SSE) endpoint pushing live status & queue telemetry."""
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

    try:
        while True:
            status_data = await get_status()
            queue_data = get_queue_data()
            payload = {
                "status": status_data,
                "queue": queue_data
            }
            chunk = f"data: {json.dumps(payload)}\n\n".encode("utf-8")
            await response.write(chunk)
            await response.drain()
            await asyncio.sleep(1.0)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception:
        pass

    return response


async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(DigitalAutoRenameBot)
    return web_app

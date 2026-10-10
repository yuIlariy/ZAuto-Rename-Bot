# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Special Thanks To @ReshamOwner
# Update Channel @Digital_Botz & @DigitalBotz_Support
"""
Apache License 2.0
Copyright (c) 2025 @Digital_Botz
"""

from aiohttp import web
import time
import psutil
import shutil
import os
from collections import deque
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
last_up_speed = 0
last_dl_speed = 0

# --- 24-HOUR ROLLING RENAME TRACKER ---
recent_renames = deque()

# ⚠️ INVISIBLE HOOK: Intercept successful uploads without modifying file_rename.py
original_update_limit = digital_botz.update_daily_limit

async def hooked_update_limit(user_id, size):
    recent_renames.append(time.time()) # Log the timestamp of the successful rename
    return await original_update_limit(user_id, size) # Pass it back to the database normally

# Override the database method in memory
digital_botz.update_daily_limit = hooked_update_limit

async def get_status():
    """Fetches and formats system and bot statistics."""
    global last_net_io, last_time, last_up_speed, last_dl_speed, recent_renames
    
    # Safely import directly from the advanced QueueManager in the Auto Renamer
    try:
        from plugins.file_rename import worker_loads, manager
    except ImportError:
        worker_loads = {}
        manager = None
    
    # 📜 Fetch real values from database
    real_total_users = await digital_botz.total_users_count()
    real_total_premium_users = await digital_botz.total_premium_users_count()
    
    # 🪄 Apply Magic Boost (Matching your Auto-Renamer Telegram bot stats)
    total_users = real_total_users + 1009
    total_premium_users = real_total_premium_users + 64
    
    # --- UPTIME CALCULATIONS ---
    # Bot Uptime
    bot_sec = time.time() - Config.BOT_UPTIME
    b_days, b_rem = divmod(bot_sec, 86400)
    b_hrs, b_rem = divmod(b_rem, 3600)
    b_mins, b_secs = divmod(b_rem, 60)
    bot_uptime = f"{int(b_days)}d {int(b_hrs)}h {int(b_mins)}m" if b_days > 0 else f"{int(b_hrs):02d}h{int(b_mins):02d}m{int(b_secs):02d}s"

    # VPS System Uptime
    sys_sec = time.time() - psutil.boot_time()
    s_days, s_rem = divmod(sys_sec, 86400)
    s_hrs, s_rem = divmod(s_rem, 3600)
    s_mins, s_secs = divmod(s_rem, 60)
    system_uptime = f"{int(s_days)}d {int(s_hrs)}h {int(s_mins)}m" if s_days > 0 else f"{int(s_hrs):02d}h{int(s_mins):02d}m{int(s_secs):02d}s"

    total, used, free = shutil.disk_usage(".")
    
    current_net_io = psutil.net_io_counters()
    current_time = time.time()
    
    # --- LIVE SPEEDS (Updates every 1 second) ---
    time_delta = current_time - last_time
    if time_delta >= 1.0: 
        last_up_speed = (current_net_io.bytes_sent - last_net_io.bytes_sent) / time_delta
        last_dl_speed = (current_net_io.bytes_recv - last_net_io.bytes_recv) / time_delta
        last_net_io = current_net_io
        last_time = current_time

    # --- 24-HOUR ROLLING WINDOW CALCULATION ---
    # Continuously clean up timestamps older than exactly 86,400 seconds (24 hours)
    while recent_renames and current_time - recent_renames[0] > 86400:
        recent_renames.popleft()
    
    renames_24h = len(recent_renames)

    # Restore Lifetime Database Bandwidth
    net_stats = await digital_botz.get_network_stats()
    data_sent = humanbytes(net_stats.get('sent', 0))
    data_recv = humanbytes(net_stats.get('recv', 0))

    # --- FLEET NODE & ACTIVE TASKS MONITORING ---
    total_workers = len(getattr(Config, "WORKER_CLIENTS", []))
    active_workers = sum(1 for load in worker_loads.values() if load > 0)
    free_workers = max(0, total_workers - active_workers)
    
    # Safely extract processing count from the Advanced QueueManager
    current_active_tasks = 0
    if manager:
        for dl_list in getattr(manager, 'active_downloads', {}).values():
            current_active_tasks += len(dl_list)
        for ul_list in getattr(manager, 'staging_pool', {}).values():
            current_active_tasks += len(ul_list)
    
    # Safely format speed strings
    up_speed_str = f"{humanbytes(last_up_speed)}/s" if last_up_speed > 0 else "0 B/s"
    dl_speed_str = f"{humanbytes(last_dl_speed)}/s" if last_dl_speed > 0 else "0 B/s"
    
    return {
        "bot_status": "Operational",
        "bot_version": __version__,
        "total_users": total_users,
        "premium_users": total_premium_users,
        "bot_uptime": bot_uptime,
        "system_uptime": system_uptime,
        "cpu_usage": psutil.cpu_percent(),
        "ram_usage": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent,
        "total_disk": humanbytes(total),
        "used_disk": humanbytes(used),
        "free_disk": humanbytes(free),
        "data_sent": data_sent,
        "data_recv": data_recv,
        "up_speed": up_speed_str,
        "dl_speed": dl_speed_str,
        "renames_24h": renames_24h,
        "total_workers": total_workers,
        "active_workers": active_workers,
        "free_workers": free_workers,
        "active_tasks": current_active_tasks,
        "timestamp": int(time.time()),
        "github_link": "https://github.com/DigitalBotz/Digital-Auto-Rename-Bot",
        "telegram_link": "https://t.me/OtherBs"
    }

@DigitalAutoRenameBot.get("/", allow_head=True)
async def root_route_handler(request):
    status_data = await get_status()
    
    try:
        with open('templates/welcome.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        return web.Response(text="API is Operational. (templates/welcome.html is missing)", content_type='text/plain')
    
    for key, value in status_data.items():
        html_content = html_content.replace(f'{{{{{key}}}}}', str(value))
    
    return web.Response(text=html_content, content_type='text/html')

@DigitalAutoRenameBot.get("/api/status")
async def api_status_handler(request):
    status_data = await get_status()
    return web.json_response(status_data)

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(DigitalAutoRenameBot)
    return web_app

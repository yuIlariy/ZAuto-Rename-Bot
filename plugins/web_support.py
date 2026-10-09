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
from config import Config
from plugins import __version__
from helper.utils import humanbytes
from helper.database import digital_botz

# Safely import tracking dictionaries for fleet and active processing
try:
    from plugins.file_rename import active_tasks, worker_loads
except ImportError:
    active_tasks = {}
    worker_loads = {}

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)

DigitalAutoRenameBot = web.RouteTableDef()

# --- NETWORK SPEED TRACKER GLOBALS ---
last_net_io = psutil.net_io_counters()
last_time = time.time()
last_up_speed = 0
last_dl_speed = 0

# Static 1-Minute Tracker Globals
last_minute_time = time.time()
last_minute_sent = last_net_io.bytes_sent
last_minute_recv = last_net_io.bytes_recv
avg_up_speed = 0
avg_dl_speed = 0

async def get_status():
    """Fetches and formats system and bot statistics."""
    global last_net_io, last_time, last_up_speed, last_dl_speed
    global last_minute_time, last_minute_sent, last_minute_recv, avg_up_speed, avg_dl_speed
    
    # 📜 Fetch real values from database
    real_total_users = await digital_botz.total_users_count()
    real_total_premium_users = await digital_botz.total_premium_users_count()
    
    # 🪄 Apply Magic Boost (Matching your Auto-Renamer Telegram bot stats)
    total_users = real_total_users + 1009
    total_premium_users = real_total_premium_users + 64
    
    currentTime = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - Config.BOT_UPTIME))    
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

    # --- 1-MINUTE AVERAGE SPEEDS (Updates exactly once every 60 seconds) ---
    minute_delta = current_time - last_minute_time
    if minute_delta >= 60.0:
        avg_up_speed = (current_net_io.bytes_sent - last_minute_sent) / minute_delta
        avg_dl_speed = (current_net_io.bytes_recv - last_minute_recv) / minute_delta
        last_minute_time = current_time
        last_minute_sent = current_net_io.bytes_sent
        last_minute_recv = current_net_io.bytes_recv

    # Combine Up and Down for the Average
    avg_total_speed = avg_up_speed + avg_dl_speed

    # Restore Lifetime Database Bandwidth
    net_stats = await digital_botz.get_network_stats()
    data_sent = humanbytes(net_stats.get('sent', 0))
    data_recv = humanbytes(net_stats.get('recv', 0))

    # --- FLEET NODE & ACTIVE TASKS MONITORING ---
    total_workers = len(getattr(Config, "WORKER_CLIENTS", []))
    active_workers = sum(1 for load in worker_loads.values() if load > 0)
    free_workers = max(0, total_workers - active_workers)
    current_active_tasks = len(active_tasks)
    
    # Safely format speed strings (handles 0 bytes properly)
    up_speed_str = f"{humanbytes(last_up_speed)}/s" if last_up_speed > 0 else "0 B/s"
    dl_speed_str = f"{humanbytes(last_dl_speed)}/s" if last_dl_speed > 0 else "0 B/s"
    avg_speed_str = f"{humanbytes(avg_total_speed)}/s" if avg_total_speed > 0 else "0 B/s"
    
    return {
        "bot_status": "Operational",
        "bot_version": __version__,
        "total_users": total_users,
        "premium_users": total_premium_users,
        "bot_uptime": currentTime,
        "system_uptime": currentTime,
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
        "avg_speed": avg_speed_str,
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

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

# Ensure templates directory exists
os.makedirs('templates', exist_ok=True)

DigitalAutoRenameBot = web.RouteTableDef()

async def get_status():
    """Fetches and formats system and bot statistics."""
    # 📜 Fetch real values from database
    real_total_users = await digital_botz.total_users_count()
    real_total_premium_users = await digital_botz.total_premium_users_count()
    
    # 🪄 Apply Magic Boost (Matching your Auto-Renamer Telegram bot stats)
    total_users = real_total_users + 1009
    total_premium_users = real_total_premium_users + 64
    
    currentTime = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - Config.BOT_UPTIME))    
    total, used, free = shutil.disk_usage(".")
    
    # Using persistent DB network stats instead of volatile system psutil counters
    net_stats = await digital_botz.get_network_stats()
    sent = humanbytes(net_stats.get('sent', 0))
    recv = humanbytes(net_stats.get('recv', 0))
    
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
        "data_sent": sent,
        "data_recv": recv,
        "system_sent": sent,
        "system_recv": recv,
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
    
    # Dynamically inject all context variables into the HTML template
    for key, value in status_data.items():
        html_content = html_content.replace(f'{{{{{key}}}}}', str(value))
    
    return web.Response(text=html_content, content_type='text/html')

# NEW ROUTE: Provides real-time JSON data for the website to fetch every second
@DigitalAutoRenameBot.get("/api/status")
async def api_status_handler(request):
    status_data = await get_status()
    return web.json_response(status_data)

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(DigitalAutoRenameBot)
    return web_app

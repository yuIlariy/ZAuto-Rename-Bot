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

# extra imports
import random, asyncio, datetime, pytz, time, psutil, shutil

# pyrogram imports
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, CallbackQuery

# bots imports
from helper.database import digital_botz
from config import Config, rkn
from helper.utils import humanbytes
from plugins import __version__ as _bot_version_, __developer__, __database__, __library__, __language__, __programer__

# NOTE: 'upload_doc' import removed as it is no longer needed

# --- Helper Function for Uptime ---
def get_uptime(start_time):
    now = time.time()
    diff = int(now - start_time)
    days, remainder = divmod(diff, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_str = ""
    if days > 0:
        uptime_str += f"{days}d "
    if hours > 0 or days > 0:
        uptime_str += f"{hours}h "
    uptime_str += f"{minutes}m {seconds}s"
    return uptime_str.strip()
# ----------------------------------


@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    start_button = [[        
        InlineKeyboardButton('Uᴩᴅᴀ𝚃ᴇꜱ', url='https://t.me/OtherBs'),
        InlineKeyboardButton('Sᴜᴩᴩᴏʀ𝚃', url='https://t.me/DigitalBotz_Support')
        ],[
        InlineKeyboardButton('Aʙᴏυᴛ', callback_data='about'),
        InlineKeyboardButton('Hᴇʟᴩ', callback_data='help')       
         ]]
        
    
    user = message.from_user
    await digital_botz.add_user(client, message) 
    if Config.RKN_PIC:
        await message.reply_photo(Config.RKN_PIC, caption=rkn.START_TXT.format(user.mention), reply_markup=InlineKeyboardMarkup(start_button))    
    else:
        await message.reply_text(text=rkn.START_TXT.format(user.mention), reply_markup=InlineKeyboardMarkup(start_button), disable_web_page_preview=True)

@Client.on_callback_query()
async def cb_handler(client, query: CallbackQuery):
    data = query.data 
    if data == "start":
        start_button = [[        
        InlineKeyboardButton('Uᴩᴅᴀ𝚃ᴇꜱ', url='https://t.me/OtherBs'),
        InlineKeyboardButton('Sᴜᴩᴩᴏʀ𝚃', url='https://t.me/DigitalBotz_Support')
        ],[
        InlineKeyboardButton('Aʙᴏυᴛ', callback_data='about'),
        InlineKeyboardButton('Hᴇʟᴩ', callback_data='help')       
         ]]
            
        
        await query.message.edit_text(
            text=rkn.START_TXT.format(query.from_user.mention),
            disable_web_page_preview=True,
            reply_markup = InlineKeyboardMarkup(start_button))
        
    elif data == "help":
        await query.message.edit_text(
            text=rkn.HELP_TXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                #⚠️ don't change source code & source link ⚠️ #
                InlineKeyboardButton("ᴛʜᴜᴍʙɴᴀɪʟ", callback_data = "thumbnail"),
                InlineKeyboardButton("ᴄᴀᴘᴛɪᴏɴ", callback_data = "caption")
                ],[          
                
                InlineKeyboardButton("ᴀʙᴏᴜᴛ", callback_data = "about"),
                InlineKeyboardButton("Bᴀᴄᴋ", callback_data = "start")
                
                  ]]))         
        
    elif data == "about":
        about_button = [[
         #⚠️ don't change source code & source link ⚠️ #
        InlineKeyboardButton("𝚂ᴏᴜʀᴄᴇ", callback_data = "source_code"), #Whoever is deploying this repo is given a warning ⚠️ not to remove this repo link #first & last warning ⚠️
        InlineKeyboardButton("ʙᴏᴛ sᴛᴀᴛᴜs", callback_data = "bot_status")
        ],[
        InlineKeyboardButton("ʟɪᴠᴇ sᴛᴀᴛᴜs", callback_data = "live_status")           
        ]]
        
        about_button[-1].append(InlineKeyboardButton("Bᴀᴄᴋ", callback_data = "start"))
            
        await query.message.edit_text(
            text=rkn.ABOUT_TXT.format(client.mention, __developer__, __programer__, __library__, __language__, __database__, _bot_version_),
            disable_web_page_preview = True,
            reply_markup=InlineKeyboardMarkup(about_button))    
        
    

    elif data == "thumbnail":
        await query.message.edit_text(
            text=rkn.THUMBNAIL,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
             InlineKeyboardButton(" Bᴀᴄᴋ", callback_data = "help")]])) 
      
    elif data == "caption":
        await query.message.edit_text(
            text=rkn.CAPTION,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
             InlineKeyboardButton(" Bᴀᴄᴋ", callback_data = "help")]])) 
      
        
    elif data == "bot_status":
        real_total_users = await digital_botz.total_users_count()
        #💥 Magic Boost 
        total_users = real_total_users + 1009
        
        # Fixed: Use the new Premium Count function
        total_premium_users = await digital_botz.total_premium_users_count()
        
        # Fixed: Use custom get_uptime function
        uptime = get_uptime(client.uptime)
        
        # --- FIXED: Fetch Persistent Stats ---
        db_stats = await digital_botz.get_network_stats()
        db_sent = db_stats.get('sent', 0)
        db_recv = db_stats.get('recv', 0)
        
        sent = humanbytes(db_sent + psutil.net_io_counters().bytes_sent)
        recv = humanbytes(db_recv + psutil.net_io_counters().bytes_recv)
        # -------------------------------------

        await query.message.edit_text(
            text=rkn.BOT_STATUS.format(uptime, total_users, total_premium_users, sent, recv),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
             InlineKeyboardButton(" Bᴀᴄᴋ", callback_data = "about")]])) 
      
    elif data == "live_status":
        # Fixed: Use custom get_uptime function
        currentTime = get_uptime(client.uptime)
        
        total, used, free = shutil.disk_usage(".")
        total = humanbytes(total)
        used = humanbytes(used)
        free = humanbytes(free)
        
        # --- FIXED: Fetch Persistent Stats ---
        db_stats = await digital_botz.get_network_stats()
        db_sent = db_stats.get('sent', 0)
        db_recv = db_stats.get('recv', 0)
        
        sent = humanbytes(db_sent + psutil.net_io_counters().bytes_sent)
        recv = humanbytes(db_recv + psutil.net_io_counters().bytes_recv)
        # -------------------------------------

        cpu_usage = psutil.cpu_percent()
        ram_usage = psutil.virtual_memory().percent
        disk_usage = psutil.disk_usage('/').percent
        await query.message.edit_text(
            text=rkn.LIVE_STATUS.format(currentTime, cpu_usage, ram_usage, total, used, disk_usage, free, sent, recv),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
             InlineKeyboardButton(" Bᴀᴄᴋ", callback_data = "about")]])) 
      
    elif data == "source_code":
        await query.message.edit_text(
            text=rkn.DEV_TXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                #⚠️ don't change source code & source link ⚠️ #
           #Whoever is deploying this repo is given a warning ⚠️ not to remove this repo link #first & last warning ⚠️   
                InlineKeyboardButton("💞 Sᴏᴜʀᴄᴇ Cᴏᴅᴇ 💞", url="https://github.com/DigitalBotz/Digital-Auto-Rename-Bot")
            ],[
                InlineKeyboardButton("🔒 Cʟᴏꜱᴇ", callback_data = "close"),
                InlineKeyboardButton("◀️ Bᴀᴄᴋ", callback_data = "start")
                 ]])          
        )
            
    elif data == "close":
        try:
            await query.message.delete()
            await query.message.reply_to_message.delete()
            await query.message.continue_propagation()
        except:
            await query.message.delete()
            await query.message.continue_propagation()

# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Update Channel @Digital_Botz & @DigitalBotz_Support

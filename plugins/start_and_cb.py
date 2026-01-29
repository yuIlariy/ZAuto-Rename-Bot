import random, asyncio, datetime, pytz, time, psutil, shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, CallbackQuery
from helper.database import digital_botz
from config import Config, rkn
from helper.utils import humanbytes
from plugins import __version__ as _bot_version_, __developer__, __database__, __library__, __language__, __programer__

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

upgrade_button = InlineKeyboardMarkup([[        
        InlineKeyboardButton('buy premium ✓', user_id=int(6318135266)),
         ],[
        InlineKeyboardButton("Bᴀᴄᴋ", callback_data = "start")
]])

upgrade_trial_button = InlineKeyboardMarkup([[        
        InlineKeyboardButton('buy premium ✓', user_id=int(6318135266)),
         ],[
        InlineKeyboardButton("ᴛʀɪᴀʟ - 𝟷𝟸 ʜᴏᴜʀs ✓", callback_data = "give_trial"),
        InlineKeyboardButton("Bᴀᴄᴋ", callback_data = "start")
]])

@Client.on_message(filters.private & filters.command("start"))
async def start(client, message):
    start_button = [[        
        InlineKeyboardButton('Uᴩᴅᴀ𝚇ᴇꜱ', url='https://t.me/OtherBs'),
        InlineKeyboardButton('Sᴜᴩᴩᴏʀ𝚃', url='https://t.me/DigitalBotz_Support')
    ],[
        InlineKeyboardButton('Aʙᴏᴛ', callback_data='about'),
        InlineKeyboardButton('Hᴇʟᴩ', callback_data='help')
    ]]

    user = message.from_user
    await digital_botz.add_user(client, message) 
    if client.premium:
        start_button.append([InlineKeyboardButton('💸 ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ 💸', callback_data='upgrade')])

    if Config.RKN_PIC:
        await message.reply_photo(Config.RKN_PIC, caption=rkn.START_TXT.format(user.mention), reply_markup=InlineKeyboardMarkup(start_button))    
    else:
        await message.reply_text(text=rkn.START_TXT.format(user.mention), reply_markup=InlineKeyboardMarkup(start_button), disable_web_page_preview=True)

@Client.on_callback_query()
async def cb_handler(client, query: CallbackQuery):
    data = query.data
    if data == "start":
        start_button = [[        
            InlineKeyboardButton('Uᴩᴅᴀ𝚇ᴇꜱ', url='https://t.me/OtherBs'),
            InlineKeyboardButton('Sᴜᴩᴩᴏʀ𝚃', url='https://t.me/DigitalBotz_Support')
        ],[
            InlineKeyboardButton('Aʙᴏᴛ', callback_data='about'),
            InlineKeyboardButton('Hᴇʟᴩ', callback_data='help')       
        ]]
        
        if client.premium:
            start_button.append([InlineKeyboardButton('💸 ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ 💸', callback_data='upgrade')])

        await query.message.edit_text(
            text=rkn.START_TXT.format(query.from_user.mention),
            disable_web_page_preview=True,
            reply_markup = InlineKeyboardMarkup(start_button))

    elif data == "help":
        await query.message.edit_text(
            text=rkn.HELP_TXT,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("ᴛʜᴜᴍʙɴᴀɪʟ", callback_data="thumbnail"),
                InlineKeyboardButton("ᴄᴀᴘᴛɪᴏɴ", callback_data="caption")
            ],[          
                InlineKeyboardButton("ᴀʙᴏᴜᴛ", callback_data="about"),
                InlineKeyboardButton("Bᴀᴄᴋ", callback_data="start")
            ]]))         
        
    elif data == "about":
        about_button = [[
            InlineKeyboardButton("𝚂ᴏᴜʀᴄᴇ", callback_data="source_code"),
            InlineKeyboardButton("ʙᴏᴛ sᴛᴀᴛᴜs", callback_data="bot_status")
        ],[
            InlineKeyboardButton("ʟɪᴠᴇ sᴛᴀᴛᴜs", callback_data="live_status")
        ]]
        
        if client.premium:
            about_button[-1].append(InlineKeyboardButton("ᴜᴘɢʀᴀᴅᴇ", callback_data="upgrade"))
            about_button.append([InlineKeyboardButton("Bᴀᴄᴋ", callback_data="start")])
        else:
            about_button[-1].append(InlineKeyboardButton("Bᴀᴄᴋ", callback_data="start"))
        await query.message.edit_text(
            text=rkn.ABOUT_TXT.format(client.mention, __developer__, __programer__, __library__, __language__, __database__, _bot_version_),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(about_button))    

    elif data == "upgrade":
        if not client.premium:
            return await query.message.delete()

        user = query.from_user
        upgrade_msg = rkn.UPGRADE_PLAN.format(user.mention) if client.uploadlimit else rkn.UPGRADE_PREMIUM.format(user.mention)
        free_trial_status = await digital_botz.get_free_trial_status(query.from_user.id)

        if not await digital_botz.has_premium_access(query.from_user.id):
            if not free_trial_status:
                await query.message.edit_text(text=upgrade_msg, disable_web_page_preview=True, reply_markup=upgrade_trial_button)
            else:
                await query.message.edit_text(text=upgrade_msg, disable_web_page_preview=True, reply_markup=upgrade_button)
        else:
            await query.message.edit_text(text=upgrade_msg, disable_web_page_preview=True, reply_markup=upgrade_button)

    elif data == "give_trial":
        if not client.premium:
            return await query.message.delete()

        await query.message.delete()
        free_trial_status = await digital_botz.get_free_trial_status(query.from_user.id)
        if not free_trial_status:
            await digital_botz.give_free_trail(query.from_user.id)
            new_text = "**ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴛʀɪᴀʟ ʜᴀs ʙᴇᴇɴ ᴀᴅᴅᴇᴅ ғᴏʀ 𝟷𝟸 ʜᴏᴜʀs...**"
        else:
            new_text = "**🤣 ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ᴜsᴇᴅ ғʀᴇᴇ...**"
        await client.send_message(query.from_user.id, text=new_text)

    elif data == "thumbnail":
        await query.message.edit_text(text=rkn.THUMBNAIL, disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Bᴀᴄᴋ", callback_data="help")]]))

    elif data == "caption":
        await query.message.edit_text(text=rkn.CAPTION, disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Bᴀᴄᴋ", callback_data="help")]]))

    elif data == "bot_status":
        real_total_users = await digital_botz.total_users_count()
        total_users = real_total_users + 1009
        
        total_premium_users = await digital_botz.total_premium_users_count()
        uptime = get_uptime(client.uptime)
        
        db_stats = await digital_botz.get_bot_stats()
        db_sent = db_stats.get('total_sent', 0)
        db_recv = db_stats.get('total_recv', 0)
        
        sent = humanbytes(db_sent + psutil.net_io_counters().bytes_sent)
        recv = humanbytes(db_recv + psutil.net_io_counters().bytes_recv)
        
        await query.message.edit_text(
            text=rkn.BOT_STATUS.format(uptime, total_users, total_premium_users, sent, recv),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[
             InlineKeyboardButton(" Bᴀᴄᴋ", callback_data = "about")]])) 
      
    elif data == "live_status":
        currentTime = get_uptime(client.uptime)
        
        total, used, free = shutil.disk_usage(".")
        total = humanbytes(total)
        used = humanbytes(used)
        free = humanbytes(free)
        
        db_stats = await digital_botz.get_bot_stats()
        db_sent = db_stats.get('total_sent', 0)
        db_recv = db_stats.get('total_recv', 0)
        
        sent = humanbytes(db_sent + psutil.net_io_counters().bytes_sent)
        recv = humanbytes(db_recv + psutil.net_io_counters().bytes_recv)
        
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

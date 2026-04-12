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

# pyrogram imports
from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.file_id import FileId
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply

# hachoir imports
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image

# bots imports
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix, remove_path
from helper.database import digital_botz
from config import Config
from plugins.auto_rename import EnhancedAutoRenamer

# extra imports
from asyncio import sleep
import os, time, asyncio
import re

UPLOAD_TEXT = """Uploading Started...."""
DOWNLOAD_TEXT = """Download Started..."""

app = Client("4gb_FileRenameBot", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=Config.STRING_SESSION)

renamer = EnhancedAutoRenamer()

# ==========================================
# --- QUEUE MANAGER CLASS ---
# ==========================================
class QueueManager:
    """Manages user tasks, upload queues, and worker states to prevent memory leaks."""
    def __init__(self):
        self.user_tasks = {}    # user_id -> list of messages to download
        self.upload_queues = {} # user_id -> asyncio.Queue for ready uploads
        self.workers = {}       # user_id -> dict of running async tasks

    def add_task(self, user_id, message):
        """Adds a message to the user's download queue."""
        if user_id not in self.user_tasks:
            self.user_tasks[user_id] = []
        self.user_tasks[user_id].append(message)
        return len(self.user_tasks[user_id])

    def has_worker(self, user_id):
        """Checks if there are active background workers for this user."""
        return user_id in self.workers

    def init_upload_queue(self, user_id):
        """Initializes an asyncio Queue for the user's uploads."""
        if user_id not in self.upload_queues:
            self.upload_queues[user_id] = asyncio.Queue()
        return self.upload_queues[user_id]

    def register_workers(self, user_id, dl_task, ul_task):
        """Registers the active asyncio tasks for tracking."""
        self.workers[user_id] = {'dl': dl_task, 'ul': ul_task}

    def cleanup(self, user_id):
        """Safely removes all traces of a user from memory once their queue is empty."""
        if user_id in self.workers:
            del self.workers[user_id]
        if user_id in self.upload_queues:
            del self.upload_queues[user_id]
        if user_id in self.user_tasks:
            del self.user_tasks[user_id]

# Initialize the manager
manager = QueueManager()
# ==========================================

@Client.on_message(filters.private & (filters.audio | filters.document | filters.video))
async def rename_start(client, message):
    user_id = message.from_user.id
    rkn_file = getattr(message, message.media.value)
    
    # --- PREMIUM & LIMIT CHECKS ---
    is_premium = await digital_botz.check_premium(user_id)
    
    # 1. Check File Size (Max 2GB for Free Users)
    if not is_premium and rkn_file.file_size > 2000 * 1024 * 1024:
        btn = [[InlineKeyboardButton("💎 Vɪᴇᴡ Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ", callback_data="premium_plans")]]
        return await message.reply_text(
            "⚠️ **Fɪʟᴇ Tᴏᴏ Lᴀʀɢᴇ!**\n\n"
            "Free users can only rename files up to **2GB**.\n"
            "Upgrade to Premium to upload files up to **4GB+** via Session!",
            reply_markup=InlineKeyboardMarkup(btn)
        )

    # 2. Check Daily Limit (6GB for Free Users)
    if not is_premium:
        can_upload = await digital_botz.check_daily_limit(user_id, rkn_file.file_size)
        if not can_upload:
            btn = [[InlineKeyboardButton("💎 Gᴇᴛ Pʀᴇᴍɪᴜᴍ", callback_data="premium_plans")]]
            return await message.reply_text(
                "🚫 **Dᴀɪʟʏ Lɪᴍɪᴛ Exᴄᴇᴇᴅᴇᴅ!**\n\n"
                "You have used your **6GB free daily limit**.\n"
                "Come back tomorrow or upgrade to Premium for unlimited renaming!",
                reply_markup=InlineKeyboardMarkup(btn)
            )
    # ------------------------------

    # 1. Add Message to Queue Manager
    pos = manager.add_task(user_id, message)
    
    # 2. Check if Workers are already running
    if manager.has_worker(user_id):
        await message.reply_text(f"✅ **Added to Queue!**\nPosition: {pos}", quote=True)
        return

    # 3. Initialize Upload Queue and Start Workers
    manager.init_upload_queue(user_id)
        
    dl_task = asyncio.create_task(download_worker(client, user_id))
    ul_task = asyncio.create_task(upload_worker(client, user_id))
    
    manager.register_workers(user_id, dl_task, ul_task)

async def download_worker(client, user_id):
    try:
        while user_id in manager.user_tasks and manager.user_tasks[user_id]:
            # Sort Queue by Season/Episode if applicable
            def get_sort_key(msg):
                try:
                    file_val = getattr(msg, msg.media.value)
                    info = renamer.extract_all_info(file_val.file_name or "")
                    s = int(info['season'].upper().replace("S", "")) if info.get('season') else 0
                    e = int(info['episode'].upper().replace("E", "")) if info.get('episode') else 0
                    return (s, e)
                except: return (999, 999)

            manager.user_tasks[user_id].sort(key=get_sort_key)
            message = manager.user_tasks[user_id].pop(0)
            
            try:
                rkn_file = getattr(message, message.media.value)
                filename = rkn_file.file_name or "unknown_file"
                filesize = humanbytes(rkn_file.file_size)
                
                # Send Status
                rkn_processing = await message.reply_text("**🔄 Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ Sᴛᴀʀᴛᴇᴅ...**\n⏳ **Pʀᴏᴄᴇꜱꜱɪɴɢ...**")

                # Rename Logic
                info = renamer.extract_all_info(filename)
                user_data = await digital_botz.get_user_data(user_id)
                format_template = user_data.get('format_template', "{filename}")
                new_filename = renamer.apply_format_template(info, format_template)
                
                if not new_filename.endswith(f".{info['extension']}"):
                    new_filename += f".{info['extension']}"
                
                if not os.path.isdir("Renames"): os.makedirs("Renames", exist_ok=True)
                file_path = f"Renames/{new_filename}"

                # Download Process
                await rkn_processing.edit(f"📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ:**\n`{new_filename}`")
                dl_path = await client.download_media(
                    message=message, 
                    file_name=file_path, 
                    progress=progress_for_pyrogram, 
                    progress_args=(DOWNLOAD_TEXT, rkn_processing, time.time())
                )

                # Metadata & Thumbnail Setup
                duration = 0
                try:
                    parser = createParser(file_path)
                    metadata = extractMetadata(parser)
                    if metadata and metadata.has("duration"):
                        duration = metadata.get('duration').seconds
                    if parser: parser.close()
                except: pass
                
                ph_path = None
                c_caption = user_data.get('caption', None)
                c_thumb = user_data.get('file_id', None)
                caption = c_caption.format(filename=new_filename, filesize=filesize, duration=convert(duration)) if c_caption else f"**{new_filename}**"
                
                if c_thumb:
                    ph_path = await client.download_media(c_thumb)
                elif getattr(rkn_file, 'thumbs', None):
                    ph_path = await client.download_media(rkn_file.thumbs[0].file_id)

                # Determine Upload Type
                upload_type = "document"
                if message.media == MessageMediaType.VIDEO: upload_type = "video"
                elif message.media == MessageMediaType.AUDIO: upload_type = "audio"

                await rkn_processing.edit("⏳ **Rᴇᴀᴅy ᴛᴏ Uᴩʟᴏᴀᴅ...**")
                
                upload_data = {
                    'message': message, 'file_path': file_path, 'ph_path': ph_path,
                    'caption': caption, 'duration': duration, 'rkn_processing': rkn_processing,
                    'upload_type': upload_type, 'file_size': rkn_file.file_size, 'user_id': user_id
                }
                
                # Push to Upload Queue
                await manager.upload_queues[user_id].put(upload_data)
                
            except Exception as e:
                print(f"Download Error: {e}")

            await asyncio.sleep(1)
    finally:
        # Sentinel to signal upload worker to finish
        if user_id in manager.upload_queues:
            await manager.upload_queues[user_id].put(None)

async def upload_worker(client, user_id):
    try:
        while True:
            # Safely get data from the queue manager
            if user_id not in manager.upload_queues:
                break
                
            data = await manager.upload_queues[user_id].get()
            if data is None: break
                
            # Use Session Client for files > 2GB (for Premium/Admin)
            uploader = app if (Config.STRING_SESSION and data['file_size'] > 2000 * 1024 * 1024) else client
            
            try:
                await data['rkn_processing'].edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                filw, error = await upload_files(
                    uploader, 
                    Config.LOG_CHANNEL if uploader == app else data['user_id'], 
                    data['upload_type'], data['file_path'], data['ph_path'], 
                    data['caption'], data['duration'], data['rkn_processing']
                )

                if not error:
                    # Update database with file size for daily limit tracking
                    is_premium = await digital_botz.check_premium(user_id)
                    if not is_premium:
                        await digital_botz.update_daily_limit(user_id, data['file_size'])
                    
                    if uploader == app:
                        await client.copy_message(user_id, filw.chat.id, filw.id)
                    
                    await data['rkn_processing'].edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟy!**")
                    await asyncio.sleep(2)
                    await data['rkn_processing'].delete()

            except Exception as e:
                print(f"Upload task failed: {e}")

            finally:
                await remove_path(data['ph_path'], data['file_path'])
            
    finally:
        # Cleanly wipe the user from memory once all tasks are done
        manager.cleanup(user_id)

async def upload_files(bot, sender_id, upload_type, file_path, ph_path, caption, duration, rkn_processing):
    try:
        if upload_type == "document":
            filw = await bot.send_document(sender_id, document=file_path, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        elif upload_type == "video":
            filw = await bot.send_video(sender_id, video=file_path, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        elif upload_type == "audio":
            filw = await bot.send_audio(sender_id, audio=file_path, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        return filw, None
    except Exception as e:
        return None, str(e)

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
from helper.database import digital_botz, Task 
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
# --- LEAST BUSY WORKER LOAD BALANCER ---
# ==========================================
worker_loads = {}

def get_least_busy_worker(main_client):
    """Finds the worker currently handling the fewest queues."""
    workers = getattr(Config, "WORKER_CLIENTS", [])
    if not workers:
        return main_client
    
    for w in workers:
        if w not in worker_loads:
            worker_loads[w] = 0
            
    # Return the worker with the minimum active tasks
    least_busy = min(workers, key=lambda w: worker_loads.get(w, 0))
    return least_busy
# ==========================================

# ==========================================
# --- QUEUE MANAGER CLASS ---
# ==========================================
class QueueManager:
    """Manages user tasks, upload queues, and worker states in memory while syncing with DB"""
    def __init__(self):
        self.user_tasks = {}    
        self.upload_queues = {} 
        self.workers = {}       

    def add_task(self, user_id, message, task_id):
        """Adds a message and its DB task ID to the user's queue"""
        if user_id not in self.user_tasks:
            self.user_tasks[user_id] = []
        self.user_tasks[user_id].append({'msg': message, 'task_id': task_id})
        return len(self.user_tasks[user_id])

    def has_worker(self, user_id):
        return user_id in self.workers

    def init_upload_queue(self, user_id):
        if user_id not in self.upload_queues:
            self.upload_queues[user_id] = asyncio.Queue()
        return self.upload_queues[user_id]

    def register_workers(self, user_id, dl_task, ul_task):
        self.workers[user_id] = {'dl': dl_task, 'ul': ul_task}

    def cleanup(self, user_id):
        if user_id in self.workers:
            del self.workers[user_id]
        if user_id in self.upload_queues:
            del self.upload_queues[user_id]
        if user_id in self.user_tasks:
            del self.user_tasks[user_id]

manager = QueueManager()

# ==========================================
# --- REBOOT RESUME FUNCTION ---
# ==========================================
async def resume_all_tasks(client):
    """Called on startup to find and restart tasks interrupted by a crash/reboot"""
    print("🔄 Checking for incomplete tasks to resume...")
    try:
        tasks = await Task.find_all().to_list()
        count = 0
        for task in tasks:
            try:
                # Fetch original message
                msg = await client.get_messages(task.user_id, task.message_id)
                # Delete old task from DB so it doesn't duplicate when rename_start runs
                await task.delete() 
                
                if msg and not msg.empty:
                    try:
                        await msg.reply_text("🔄 **Rᴇꜱᴜᴍɪɴɢ Iɴᴄᴏᴍᴩʟᴇᴛᴇ Tᴀꜱᴋ...**", quote=True)
                    except: pass
                    
                    # Re-trigger the rename flow as if the user just sent it
                    await rename_start(client, msg)
                    count += 1
            except Exception as e:
                print(f"Failed to resume task {task.id}: {e}")
                
        if count > 0:
            print(f"✅ Resumed {count} tasks successfully.")
        else:
            print("✅ No pending tasks to resume.")
    except Exception as e:
        print(f"Error in resume_all_tasks: {e}")

# ==========================================

@Client.on_message(filters.private & (filters.audio | filters.document | filters.video))
async def rename_start(client, message):
    user_id = message.from_user.id
    rkn_file = getattr(message, message.media.value)
    
    # --- PREMIUM & LIMIT CHECKS ---
    is_premium = await digital_botz.check_premium(user_id)
    
    if not is_premium and rkn_file.file_size > 2000 * 1024 * 1024:
        btn = [[InlineKeyboardButton("💎 Vɪᴇᴡ Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ", callback_data="premium_plans")]]
        return await message.reply_text("⚠️ **Fɪʟᴇ Tᴏᴏ Lᴀʀɢᴇ!**\n\nFree users can only rename files up to **2GB**.\nUpgrade to Premium to upload files up to **4GB+**!", reply_markup=InlineKeyboardMarkup(btn))

    if not is_premium:
        can_upload = await digital_botz.check_daily_limit(user_id, rkn_file.file_size)
        if not can_upload:
            btn = [[InlineKeyboardButton("💎 Gᴇᴛ Pʀᴇᴍɪᴜᴍ", callback_data="premium_plans")]]
            return await message.reply_text("🚫 **Dᴀɪʟʏ Lɪᴍɪᴛ Exᴄᴇᴇᴅᴇᴅ!**\n\nYou have used your **6GB free daily limit**.", reply_markup=InlineKeyboardMarkup(btn))
    # ------------------------------

    # Add Task to MongoDB Backup
    task_id = await digital_botz.add_task(user_id, message.id)

    # Add Message to Queue Manager
    pos = manager.add_task(user_id, message, task_id)
    
    # If workers are already running for this user, just let the queue handle it!
    if manager.has_worker(user_id):
        await message.reply_text(f"✅ **Added to Queue!**\nPosition: {pos}", quote=True)
        return

    # --- ASSIGN FLEET WORKER FOR THIS USER'S QUEUE ---
    manager.init_upload_queue(user_id)
    assigned_worker = get_least_busy_worker(client)
    if assigned_worker != client:
        worker_loads[assigned_worker] = worker_loads.get(assigned_worker, 0) + 1

    # Start Workers using the Assigned Fleet Bot
    dl_task = asyncio.create_task(download_worker(client, assigned_worker, user_id))
    ul_task = asyncio.create_task(upload_worker(client, assigned_worker, user_id))
    manager.register_workers(user_id, dl_task, ul_task)

async def download_worker(main_client, worker_client, user_id):
    try:
        while user_id in manager.user_tasks and manager.user_tasks[user_id]:
            # Sort Queue by Season/Episode to maintain perfect order!
            def get_sort_key(item):
                try:
                    file_val = getattr(item['msg'], item['msg'].media.value)
                    info = renamer.extract_all_info(file_val.file_name or "")
                    s = int(info['season'].upper().replace("S", "")) if info.get('season') else 0
                    e = int(info['episode'].upper().replace("E", "")) if info.get('episode') else 0
                    return (s, e)
                except: return (999, 999)

            manager.user_tasks[user_id].sort(key=get_sort_key)
            item = manager.user_tasks[user_id].pop(0)
            message = item['msg']
            task_id = item['task_id']
            
            await digital_botz.update_task_status(task_id, "processing")
            
            try:
                rkn_file = getattr(message, message.media.value)
                filename = rkn_file.file_name or "unknown_file"
                filesize = humanbytes(rkn_file.file_size)
                
                rkn_processing = await message.reply_text("**🔄 Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ Sᴛᴀʀᴛᴇᴅ...**\n⏳ **Pʀᴏᴄᴇꜱꜱɪɴɢ...**")

                info = renamer.extract_all_info(filename)
                user_data = await digital_botz.get_user_data(user_id)
                format_template = user_data.get('format_template', "{filename}")
                new_filename = renamer.apply_format_template(info, format_template)
                
                if not new_filename.endswith(f".{info['extension']}"):
                    new_filename += f".{info['extension']}"
                
                if not os.path.isdir("Renames"): os.makedirs("Renames", exist_ok=True)
                file_path = f"Renames/{new_filename}"

                await rkn_processing.edit(f"📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ:**\n`{new_filename}`")
                
                # --- LOG CHANNEL BRIDGE FOR QUEUE ---
                log_msg = None
                if worker_client != main_client:
                    try:
                        log_msg = await message.copy(Config.LOG_CHANNEL)
                        target_msg = await worker_client.get_messages(Config.LOG_CHANNEL, log_msg.id)
                    except Exception as e:
                        await digital_botz.delete_task(task_id)
                        await rkn_processing.edit(f"⚠️ **Fleet Error:** Main bot must be Admin in LOG_CHANNEL.\n{e}")
                        continue
                else:
                    target_msg = message

                try:
                    dl_path = await worker_client.download_media(
                        message=target_msg, 
                        file_name=file_path, 
                        progress=progress_for_pyrogram, 
                        progress_args=(DOWNLOAD_TEXT, rkn_processing, time.time())
                    )
                except Exception as e:
                    print(f"Download Error: {e}")
                    await digital_botz.delete_task(task_id)
                    await rkn_processing.edit(f"**Download Error:** {e}")
                    continue
                finally:
                    if log_msg:
                        try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg.id)
                        except: pass

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
                    ph_path = await main_client.download_media(c_thumb)
                elif getattr(rkn_file, 'thumbs', None):
                    ph_path = await main_client.download_media(rkn_file.thumbs[0].file_id)

                upload_type = "document"
                if message.media == MessageMediaType.VIDEO: upload_type = "video"
                elif message.media == MessageMediaType.AUDIO: upload_type = "audio"

                await rkn_processing.edit("⏳ **Rᴇᴀᴅy ᴛᴏ Uᴩʟᴏᴀᴅ...**")
                
                upload_data = {
                    'message': message, 'file_path': file_path, 'ph_path': ph_path,
                    'caption': caption, 'duration': duration, 'rkn_processing': rkn_processing,
                    'upload_type': upload_type, 'file_size': rkn_file.file_size, 'user_id': user_id,
                    'task_id': task_id
                }
                
                await manager.upload_queues[user_id].put(upload_data)
                
            except Exception as e:
                print(f"Queue Error: {e}")
                await digital_botz.delete_task(task_id)
                
            await asyncio.sleep(1)
    finally:
        if user_id in manager.upload_queues:
            await manager.upload_queues[user_id].put(None)

async def upload_worker(main_client, worker_client, user_id):
    try:
        while True:
            if user_id not in manager.upload_queues:
                break
                
            data = await manager.upload_queues[user_id].get()
            if data is None: break
                
            uploader = app if (Config.STRING_SESSION and data['file_size'] > 2000 * 1024 * 1024) else worker_client
            is_main_bot = (uploader == main_client)
            
            try:
                await data['rkn_processing'].edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                
                if not is_main_bot:
                    filw, error = await upload_files(
                        uploader, 
                        Config.LOG_CHANNEL, 
                        data['upload_type'], data['file_path'], data['ph_path'], 
                        data['caption'], data['duration'], data['rkn_processing']
                    )
                    if not error and filw:
                        await asyncio.sleep(2)
                        await main_client.copy_message(user_id, Config.LOG_CHANNEL, filw.id)
                        try: await main_client.delete_messages(Config.LOG_CHANNEL, filw.id)
                        except: pass
                else:
                    filw, error = await upload_files(
                        uploader, 
                        data['user_id'], 
                        data['upload_type'], data['file_path'], data['ph_path'], 
                        data['caption'], data['duration'], data['rkn_processing']
                    )

                if not error:
                    # Active Leaderboard Tracking
                    await digital_botz.update_daily_limit(user_id, data['file_size'])
                    
                    await digital_botz.delete_task(data['task_id'])
                    await data['rkn_processing'].edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟy!**")
                    await asyncio.sleep(2)
                    await data['rkn_processing'].delete()
                else:
                    await digital_botz.delete_task(data['task_id'])
                    await data['rkn_processing'].edit(f"**Eʀʀᴏʀ:** {error}")

            except Exception as e:
                print(f"Upload task failed: {e}")
                await digital_botz.delete_task(data['task_id'])

            finally:
                await remove_path(data['ph_path'], data['file_path'])
            
    finally:
        manager.cleanup(user_id)
        # Queue complete! Release the worker for the next user.
        if worker_client != main_client:
            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)

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

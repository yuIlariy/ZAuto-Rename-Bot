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
import os, time, asyncio, re, shutil

UPLOAD_TEXT = """Uploading Started...."""
DOWNLOAD_TEXT = """Download Started..."""

app = Client("4gb_FileRenameBot", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=Config.STRING_SESSION)

renamer = EnhancedAutoRenamer()

# ==========================================
# --- GLOBAL PREMIUM UPLOAD LOCK ---
# Prevents FILE_PART_INVALID by making 2GB+ files politely take turns on the string session
upload_lock = asyncio.Lock()
# ==========================================

# ==========================================
# --- SEQUENCE SORTER ---
# ==========================================
def get_sort_key(item):
    """Extracts Season and Episode to maintain strict sequential order."""
    try:
        file_val = getattr(item['msg'], item['msg'].media.value)
        info = renamer.extract_all_info(file_val.file_name or "")
        s = int(info['season'].upper().replace("S", "")) if info.get('season') else 0
        e = int(info['episode'].upper().replace("E", "")) if info.get('episode') else 0
        return (s, e)
    except: 
        return (999, 999)

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
# --- QUEUE MANAGER CLASS (DYNAMIC) ---
# ==========================================
class QueueManager:
    """Manages tasks safely with a lock to prevent duplicate Position numbers"""
    def __init__(self):
        self.user_tasks = {}    
        self.upload_queues = {} 
        self.workers = {}       
        self.locks = {} # Prevents multiple files from getting "Position 1"

    async def get_lock(self, user_id):
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        return self.locks[user_id]

    async def add_task(self, user_id, message, rkn_processing, task_id):
        lock = await self.get_lock(user_id)
        async with lock:
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = []
            
            new_item = {'msg': message, 'rkn_processing': rkn_processing, 'task_id': task_id, 'current_pos': 0}
            self.user_tasks[user_id].append(new_item)
            
            # Sort immediately based on Season/Episode
            self.user_tasks[user_id].sort(key=get_sort_key)
            
            # Dynamically update the printed position of every file in the queue
            for index, item in enumerate(self.user_tasks[user_id]):
                true_pos = index + 1
                if item['current_pos'] != true_pos:
                    item['current_pos'] = true_pos
                    try:
                        await item['rkn_processing'].edit(f"✅ **Added to Queue!**\nPosition: {true_pos}")
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                        await item['rkn_processing'].edit(f"✅ **Added to Queue!**\nPosition: {true_pos}")
                    except Exception:
                        pass

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
                # 1. NEW: INSTANTLY DELETE THE OLD FROZEN PROGRESS BAR!
                if getattr(task, "processing_msg_id", 0) != 0:
                    try:
                        await client.delete_messages(task.user_id, task.processing_msg_id)
                    except:
                        pass

                msg = await client.get_messages(task.user_id, task.message_id)
                await task.delete() 
                
                if msg and not msg.empty:
                    resuming_msg = None
                    try:
                        resuming_msg = await msg.reply_text("🔄 **Rᴇꜱᴜᴍɪɴɢ Iɴᴄᴏᴍᴩʟᴇᴛᴇ Tᴀꜱᴋ...**", quote=True)
                    except: pass
                    
                    await rename_start(client, msg)
                    
                    # 2. NEW: SILENT NINJA AUTO-DELETE THE "RESUMING" MESSAGE
                    if resuming_msg:
                        async def auto_delete(m):
                            await asyncio.sleep(3) # Let it show for 3 seconds
                            try: await m.delete()
                            except: pass
                        asyncio.create_task(auto_delete(resuming_msg))
                        
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

    # 1. Generate the progress message FIRST so we have its ID
    rkn_processing = await message.reply_text("⏳ **Calculating Position...**", quote=True)

    # 2. Add Task to MongoDB Backup WITH the processing message ID
    task_id = await digital_botz.add_task(user_id, message.id, rkn_processing.id)

    # 3. Add to Queue Manager
    await manager.add_task(user_id, message, rkn_processing, task_id)
    
    # 4. Check if Workers are already running
    if manager.has_worker(user_id):
        return

    # 5. Initialize Upload Queue and Start Fleet Worker
    manager.init_upload_queue(user_id)
    
    assigned_worker = get_least_busy_worker(client)
    if assigned_worker != client:
        worker_loads[assigned_worker] = worker_loads.get(assigned_worker, 0) + 1

    dl_task = asyncio.create_task(download_worker(client, assigned_worker, user_id))
    ul_task = asyncio.create_task(upload_worker(client, assigned_worker, user_id))
    manager.register_workers(user_id, dl_task, ul_task)

async def download_worker(main_client, worker_client, user_id):
    try:
        while user_id in manager.user_tasks and manager.user_tasks[user_id]:
            lock = await manager.get_lock(user_id)
            async with lock:
                # Pop the perfectly sorted item
                item = manager.user_tasks[user_id].pop(0)
                
                # Update positions of remaining items so Pos 2 shifts up to Pos 1
                for index, queued_item in enumerate(manager.user_tasks[user_id]):
                    true_pos = index + 1
                    if queued_item['current_pos'] != true_pos:
                        queued_item['current_pos'] = true_pos
                        try:
                            await queued_item['rkn_processing'].edit(f"✅ **Added to Queue!**\nPosition: {true_pos}")
                        except Exception:
                            pass
            
            message = item['msg']
            rkn_processing = item['rkn_processing']
            task_id = item['task_id']
            
            # Mark task as processing in DB
            await digital_botz.update_task_status(task_id, "processing")
            
            try:
                rkn_file = getattr(message, message.media.value)
                filename = rkn_file.file_name or "unknown_file"
                filesize = humanbytes(rkn_file.file_size)
                
                await rkn_processing.edit("**🔄 Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ Sᴛᴀʀᴛᴇᴅ...**\n⏳ **Pʀᴏᴄᴇꜱꜱɪɴɢ...**")

                # Rename Logic
                info = renamer.extract_all_info(filename)
                user_data = await digital_botz.get_user_data(user_id)
                format_template = user_data.get('format_template', "{filename}")
                new_filename = renamer.apply_format_template(info, format_template)
                
                # --- SANITIZE: Safely replace only slash/backslash to prevent directory errors ---
                new_filename = str(new_filename).replace("/", "-").replace("\\", "-")
                
                if not new_filename.endswith(f".{info['extension']}"):
                    new_filename += f".{info['extension']}"
                
                # --- UNIQUE FOLDER ISOLATION: Prevent Errno 2 Disk Collisions! ---
                task_renames_dir = f"Renames/{task_id}"
                os.makedirs(task_renames_dir, exist_ok=True)
                file_path = f"{task_renames_dir}/{new_filename}"

                await rkn_processing.edit(f"📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ:**\n`{new_filename}`")
                
                # --- LOG CHANNEL BRIDGE ---
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

                # Download Process
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

                # Determine Upload Type
                upload_type = "document"
                if message.media == MessageMediaType.VIDEO: upload_type = "video"
                elif message.media == MessageMediaType.AUDIO: upload_type = "audio"

                await rkn_processing.edit("⏳ **Rᴇᴀᴅy ᴛᴏ Uᴩʟᴏᴀᴅ...**")
                
                upload_data = {
                    'message': message, 'file_path': file_path, 'ph_path': ph_path,
                    'caption': caption, 'duration': duration, 'rkn_processing': rkn_processing,
                    'upload_type': upload_type, 'file_size': rkn_file.file_size, 'user_id': user_id,
                    'task_id': task_id, 'new_filename': new_filename # Pass pure filename
                }
                
                # Push to Upload Queue
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
                
            uploader = app if (getattr(Config, 'STRING_SESSION', None) and data['file_size'] > 2000 * 1024 * 1024) else worker_client
            is_main_bot = (uploader == main_client)
            
            try:
                # Helper function for cleaner lock execution
                async def perform_upload():
                    if not is_main_bot:
                        filw, error = await upload_files(
                            uploader, 
                            Config.LOG_CHANNEL if uploader == app else Config.LOG_CHANNEL, 
                            data['upload_type'], data['file_path'], data['ph_path'], 
                            data['caption'], data['duration'], data['rkn_processing'], data['new_filename']
                        )

                        if not error and filw:
                            await asyncio.sleep(1.5)
                            try:
                                delivered = False
                                while not delivered:
                                    try:
                                        await main_client.copy_message(user_id, Config.LOG_CHANNEL, filw.id)
                                        delivered = True
                                    except FloodWait as fw:
                                        await asyncio.sleep(fw.value)
                                    except Exception:
                                        try:
                                            await uploader.copy_message(user_id, Config.LOG_CHANNEL, filw.id)
                                            delivered = True
                                        except Exception:
                                            delivered = True 
                            finally:
                                for attempt in range(3):
                                    try:
                                        await main_client.delete_messages(Config.LOG_CHANNEL, filw.id)
                                        break
                                    except FloodWait:
                                        try:
                                            await uploader.delete_messages(Config.LOG_CHANNEL, filw.id)
                                            break
                                        except Exception:
                                            pass
                                    except Exception:
                                        try:
                                            await uploader.delete_messages(Config.LOG_CHANNEL, filw.id)
                                            break
                                        except Exception:
                                            pass
                        return error
                    else:
                        filw, error = await upload_files(
                            uploader, 
                            data['user_id'], 
                            data['upload_type'], data['file_path'], data['ph_path'], 
                            data['caption'], data['duration'], data['rkn_processing'], data['new_filename']
                        )
                        return error

                # --- The FILE_PART_INVALID Lock Fix ---
                if uploader == app:
                    await data['rkn_processing'].edit("📤 **Wᴀɪᴛɪɴɢ ꜰᴏʀ Pʀᴇᴍɪᴜᴍ Sᴇꜱꜱɪᴏɴ...**")
                    async with upload_lock:
                        await data['rkn_processing'].edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                        error = await perform_upload()
                else:
                    await data['rkn_processing'].edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                    error = await perform_upload()

                if not error:
                    # --- FIXED: Active Leaderboard Tracking for EVERYONE ---
                    await digital_botz.update_daily_limit(user_id, data['file_size'])
                    # -------------------------------------------------------
                    
                    # 🎉 TASK COMPLETE: Delete from DB so it doesn't resume!
                    await digital_botz.delete_task(data['task_id'])
                    
                    await data['rkn_processing'].edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟy!**")
                    await asyncio.sleep(2)
                    await data['rkn_processing'].delete()
                else:
                    await digital_botz.delete_task(data['task_id'])
                    await data['rkn_processing'].edit(f"**Eʀʀᴏʀ:** {error}")

            except Exception as e:
                print(f"Upload task failed: {e}")
                await digital_botz.delete_task(data['task_id']) # Clean up failed task

            finally:
                await remove_path(data['ph_path'], data['file_path'])
                # Wipe the isolated task directory to keep VPS clean
                try: shutil.rmtree(f"Renames/{data['task_id']}", ignore_errors=True)
                except: pass
            
    finally:
        manager.cleanup(user_id)
        if worker_client != main_client:
            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)

async def upload_files(bot, sender_id, upload_type, file_path, ph_path, caption, duration, rkn_processing, new_filename):
    try:
        if upload_type == "document":
            filw = await bot.send_document(sender_id, document=file_path, file_name=new_filename, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        elif upload_type == "video":
            filw = await bot.send_video(sender_id, video=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        elif upload_type == "audio":
            filw = await bot.send_audio(sender_id, audio=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        return filw, None
    except Exception as e:
        return None, str(e)

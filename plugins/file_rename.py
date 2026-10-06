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
from pyrogram.errors import FloodWait, MessageIdInvalid
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
        self.locks = {}
        self.worker_locks = {} # NEW: Strict lock to prevent freezing when 50 files drop at once

    async def get_lock(self, user_id):
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        return self.locks[user_id]
        
    async def get_worker_lock(self, user_id):
        if user_id not in self.worker_locks:
            self.worker_locks[user_id] = asyncio.Lock()
        return self.worker_locks[user_id]

    async def add_task(self, user_id, message, rkn_processing, task_id):
        lock = await self.get_lock(user_id)
        
        async with lock:
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = []
            
            new_item = {'msg': message, 'rkn_processing': rkn_processing, 'task_id': task_id}
            self.user_tasks[user_id].append(new_item)
            
            # Sort the queue so seasons stay in order
            self.user_tasks[user_id].sort(key=get_sort_key)
            total_queued = len(self.user_tasks[user_id])
                    
        # 🛡️ THE FIX: Only edit this specific message once. No massive loops, no massive rate limits!
        try:
            await rkn_processing.edit(f"⏳ **Qᴜᴇᴜᴇᴅ...**\n📦 Tᴏᴛᴀʟ ɪɴ Qᴜᴇᴜᴇ: `{total_queued}`")
        except FloodWait:
            pass # Silently ignore the rate limit and keep the queue moving
        except Exception:
            pass

    def has_worker(self, user_id):
        if user_id in self.workers:
            dl_task = self.workers[user_id].get('dl')
            if dl_task and not dl_task.done():
                return True
        return False

    def init_upload_queue(self, user_id):
        self.upload_queues[user_id] = asyncio.Queue()
        return self.upload_queues[user_id]

    def register_workers(self, user_id, dl_task, ul_task):
        self.workers[user_id] = {'dl': dl_task, 'ul': ul_task}

    def cleanup(self, user_id):
        if user_id in self.workers:
            del self.workers[user_id]
        if user_id in self.user_tasks and not self.user_tasks[user_id]:
            del self.user_tasks[user_id]

manager = QueueManager()

# ==========================================
# --- REBOOT RESUME FUNCTION ---
# ==========================================
async def resume_all_tasks(client):
    print("🔄 Checking for incomplete tasks to resume...")
    try:
        tasks = await Task.find_all().to_list()
        count = 0
        for task in tasks:
            try:
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
                    
                    if resuming_msg:
                        async def auto_delete(m):
                            await asyncio.sleep(3)
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
    
    is_premium = await digital_botz.check_premium(user_id)
    
    if not is_premium and rkn_file.file_size > 2000 * 1024 * 1024:
        btn = [[InlineKeyboardButton("💎 Vɪᴇᴡ Pʀᴇᴍɪᴜᴍ Pʟᴀɴꜱ", callback_data="premium_plans")]]
        return await message.reply_text("⚠️ **Fɪʟᴇ Tᴏᴏ Lᴀʀɢᴇ!**\n\nFree users can only rename files up to **2GB**.\nUpgrade to Premium to upload files up to **4GB+**!", reply_markup=InlineKeyboardMarkup(btn))

    if not is_premium:
        can_upload = await digital_botz.check_daily_limit(user_id, rkn_file.file_size)
        if not can_upload:
            btn = [[InlineKeyboardButton("💎 Gᴇᴛ Pʀᴇᴍɪᴜᴍ", callback_data="premium_plans")]]
            return await message.reply_text("🚫 **Dᴀɪʟʏ Lɪᴍɪᴛ Exᴄᴇᴇᴅᴇᴅ!**\n\nYou have used your **6GB free daily limit**.", reply_markup=InlineKeyboardMarkup(btn))

    rkn_processing = await message.reply_text("⏳ **Aᴅᴅɪɴɢ ᴛᴏ Qᴜᴇᴜᴇ...**", quote=True)
    task_id = await digital_botz.add_task(user_id, message.id, rkn_processing.id)

    await manager.add_task(user_id, message, rkn_processing, task_id)
    
    # 🛡️ THE FIX: Strict worker lock to prevent the massive concurrent spawn freeze
    worker_lock = await manager.get_worker_lock(user_id)
    async with worker_lock:
        if manager.has_worker(user_id):
            return

        manager.init_upload_queue(user_id)
        
        assigned_worker = get_least_busy_worker(client)
        if assigned_worker != client:
            worker_loads[assigned_worker] = worker_loads.get(assigned_worker, 0) + 1

        dl_task = asyncio.create_task(download_worker(client, assigned_worker, user_id))
        ul_task = asyncio.create_task(upload_worker(client, assigned_worker, user_id))
        manager.register_workers(user_id, dl_task, ul_task)

async def download_worker(main_client, worker_client, user_id):
    processed_count = 0
    batch_start_time = time.time()
    
    try:
        while True:
            lock = await manager.get_lock(user_id)
            item = None
            remaining = 0
            
            async with lock:
                if not manager.user_tasks.get(user_id):
                    break 
                item = manager.user_tasks[user_id].pop(0)
                remaining = len(manager.user_tasks[user_id])
            
            processed_count += 1
            message = item['msg']
            rkn_processing = item['rkn_processing']
            task_id = item['task_id']
            
            try:
                await digital_botz.update_task_status(task_id, "processing")
                
                rkn_file = getattr(message, message.media.value)
                filename = rkn_file.file_name or "unknown_file"
                filesize = humanbytes(rkn_file.file_size)
                
                # 📊 Live Processing Stats UI
                elapsed_minutes = (time.time() - batch_start_time) / 60.0
                avg_speed = (processed_count / elapsed_minutes) if elapsed_minutes > 0 else 0.0
                
                stats_msg = (
                    f"**🔄 Pʀᴏᴄᴇꜱꜱɪɴɢ Aᴄᴛɪᴠᴇ...**\n"
                    f"✅ **Pʀᴏᴄᴇꜱꜱᴇᴅ:** `{processed_count}`\n"
                    f"⏳ **Rᴇᴍᴀɪɴɪɴɢ:** `{remaining}`\n"
                    f"⚡ **Aᴠɢ Sᴘᴇᴇᴅ:** `{avg_speed:.1f} ꜰɪʟᴇꜱ/ᴍɪɴ`"
                )
                
                try:
                    await rkn_processing.edit(stats_msg)
                except FloodWait:
                    pass

                info = renamer.extract_all_info(filename)
                user_data = await digital_botz.get_user_data(user_id)
                format_template = user_data.get('format_template', "{filename}")
                new_filename = renamer.apply_format_template(info, format_template)
                
                new_filename = str(new_filename).replace("/", "-").replace("\\", "-")
                if not new_filename.endswith(f".{info['extension']}"):
                    new_filename += f".{info['extension']}"
                
                task_renames_dir = f"Renames/{task_id}"
                os.makedirs(task_renames_dir, exist_ok=True)
                file_path = f"{task_renames_dir}/{new_filename}"

                try:
                    await rkn_processing.edit(f"{stats_msg}\n\n📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ:**\n`{new_filename}`")
                except FloodWait:
                    pass
                
                dl_path = None
                log_msg = None
                attempts = 0
                while attempts < 3:
                    try:
                        if worker_client != main_client:
                            log_msg = await message.copy(Config.LOG_CHANNEL)
                            target_msg = await worker_client.get_messages(Config.LOG_CHANNEL, log_msg.id)
                        else:
                            target_msg = message

                        dl_path = await worker_client.download_media(
                            message=target_msg, 
                            file_name=file_path,
                            progress=progress_for_pyrogram, 
                            progress_args=(DOWNLOAD_TEXT, rkn_processing, time.time())
                        )
                        break 
                        
                    except FloodWait as fw:
                        attempts += 1
                        if log_msg:
                            try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg.id)
                            except: pass
                            
                        workers_list = getattr(Config, "WORKER_CLIENTS", [])
                        if len(workers_list) > 1 and worker_client != main_client:
                            try: await rkn_processing.edit(f"⚠️ **Worker Limited:** Switching to idle worker...")
                            except: pass
                            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)
                            worker_client = get_least_busy_worker(main_client)
                            worker_loads[worker_client] = worker_loads.get(worker_client, 0) + 1
                            await asyncio.sleep(2)
                        else:
                            try: await rkn_processing.edit(f"⚠️ **Rate Limited:** Waiting {fw.value}s...")
                            except: pass
                            await asyncio.sleep(fw.value)
                            
                    except MessageIdInvalid:
                        raise Exception("Task Cancelled")
                    except Exception as e:
                        raise e 
                
                if not dl_path:
                    raise Exception("Failed to download file after retries.")

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

                try:
                    await rkn_processing.edit(f"{stats_msg}\n\n⏳ **Rᴇᴀᴅy ᴛᴏ Uᴩʟᴏᴀᴅ...**")
                except FloodWait:
                    pass
                
                upload_data = {
                    'message': message, 'file_path': file_path, 'ph_path': ph_path,
                    'caption': caption, 'duration': duration, 'rkn_processing': rkn_processing,
                    'upload_type': upload_type, 'file_size': rkn_file.file_size, 'user_id': user_id,
                    'task_id': task_id, 'new_filename': new_filename, 'stats_msg': stats_msg
                }
                
                await manager.upload_queues[user_id].put(upload_data)
                
            except Exception as inner_e:
                print(f"Download Error for Task {task_id}: {inner_e}")
                await digital_botz.delete_task(task_id)
                if "MESSAGE_ID_INVALID" not in str(inner_e) and "Task Cancelled" not in str(inner_e):
                    try: await main_client.send_message(user_id, f"**Error:** {inner_e}", reply_to_message_id=message.id)
                    except: pass
            finally:
                if log_msg:
                    try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg.id)
                    except: pass
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"Critical Download Worker Error: {e}")
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
            
            try:
                uploader = app if (getattr(Config, 'STRING_SESSION', None) and data['file_size'] > 2000 * 1024 * 1024) else worker_client
                is_main_bot = (uploader == main_client)
                stats_msg = data.get('stats_msg', '')
                
                upload_attempts = 0
                while upload_attempts < 3:
                    try:
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

                        if uploader == app:
                            try:
                                await data['rkn_processing'].edit(f"{stats_msg}\n\n📤 **Wᴀɪᴛɪɴɢ ꜰᴏʀ Pʀᴇᴍɪᴜᴍ Sᴇꜱꜱɪᴏɴ...**")
                            except FloodWait:
                                pass
                            async with upload_lock:
                                try:
                                    await data['rkn_processing'].edit(f"{stats_msg}\n\n📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                                except FloodWait:
                                    pass
                                error = await perform_upload()
                        else:
                            try:
                                await data['rkn_processing'].edit(f"{stats_msg}\n\n📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                            except FloodWait:
                                pass
                            error = await perform_upload()

                        if error and str(error).startswith("FLOODWAIT:"):
                            wait_time = int(str(error).split(":")[1])
                            workers_list = getattr(Config, "WORKER_CLIENTS", [])
                            if uploader != app and len(workers_list) > 1 and not is_main_bot:
                                worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)
                                worker_client = get_least_busy_worker(main_client)
                                worker_loads[worker_client] = worker_loads.get(worker_client, 0) + 1
                                uploader = worker_client
                                is_main_bot = False
                                upload_attempts += 1
                                await asyncio.sleep(2)
                                continue
                            else:
                                await asyncio.sleep(wait_time)
                                upload_attempts += 1
                                continue
                                
                        elif error:
                            await digital_botz.delete_task(data['task_id'])
                            if "MESSAGE_ID_INVALID" not in str(error):
                                try: await main_client.send_message(user_id, f"**Eʀʀᴏʀ:** {error}", reply_to_message_id=data['message'].id)
                                except: pass
                            break
                        else:
                            await digital_botz.update_daily_limit(user_id, data['file_size'])
                            await digital_botz.delete_task(data['task_id'])
                            try: 
                                await data['rkn_processing'].edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟy!**")
                                await asyncio.sleep(2)
                                await data['rkn_processing'].delete()
                            except FloodWait:
                                try: await data['rkn_processing'].delete()
                                except: pass
                            except: 
                                pass
                            break

                    except Exception as perform_e:
                        print(f"Upload loop crash: {perform_e}")
                        await digital_botz.delete_task(data['task_id'])
                        break

            except Exception as inner_e:
                print(f"Upload Inner Error: {inner_e}")
                await digital_botz.delete_task(data['task_id'])
                if "MESSAGE_ID_INVALID" not in str(inner_e):
                    try: await main_client.send_message(user_id, f"**Upload Error:** {inner_e}", reply_to_message_id=data['message'].id)
                    except: pass
            finally:
                await remove_path(data['ph_path'], data['file_path'])
                try: shutil.rmtree(f"Renames/{data['task_id']}", ignore_errors=True)
                except: pass
            
    except Exception as e:
        print(f"Critical Upload Worker Error: {e}")
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
    except FloodWait as fw:
        return None, f"FLOODWAIT:{fw.value}"
    except Exception as e:
        return None, str(e)

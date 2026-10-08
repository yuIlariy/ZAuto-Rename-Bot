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
# ==========================================
upload_lock = asyncio.Lock()

# ==========================================
# --- SEQUENCE SORTER ---
# ==========================================
def get_sort_key(item):
    """Extracts S/E, but uses Telegram Message ID as the ultimate sequential fallback for ANY file type."""
    try:
        msg_id = item['msg'].id
        file_val = getattr(item['msg'], item['msg'].media.value)
        info = renamer.extract_all_info(file_val.file_name or "")
        s = int(info['season'].upper().replace("S", "")) if info.get('season') else 0
        e = int(info['episode'].upper().replace("E", "")) if info.get('episode') else 0
        return (s, e, msg_id)
    except Exception: 
        return (float('inf'), float('inf'), item.get('msg').id if item.get('msg') else float('inf'))

# ==========================================
# --- LEAST BUSY WORKER LOAD BALANCER ---
# ==========================================
worker_loads = {}

def get_least_busy_worker(main_client):
    workers = getattr(Config, "WORKER_CLIENTS", [])
    if not workers:
        return main_client
    
    for w in workers:
        if w not in worker_loads:
            worker_loads[w] = 0
            
    least_busy = min(workers, key=lambda w: worker_loads.get(w, 0))
    return least_busy

# ==========================================
# --- QUEUE MANAGER CLASS (BARRIER UPGRADE) ---
# ==========================================
class QueueManager:
    def __init__(self):
        self.user_tasks = {}       
        self.active_downloads = {} 
        self.staging_pool = {}     
        self.upload_events = {}    
        self.workers = {}       
        self.locks = {}
        self.worker_locks = {}
        self.batch_state = {} 

    async def get_lock(self, user_id):
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        return self.locks[user_id]
        
    async def get_worker_lock(self, user_id):
        if user_id not in self.worker_locks:
            self.worker_locks[user_id] = asyncio.Lock()
        return self.worker_locks[user_id]

    async def add_task(self, user_id, message, task_id):
        lock = await self.get_lock(user_id)
        
        async with lock:
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = []
            
            item_sort_key = get_sort_key({'msg': message})
            new_item = {'msg': message, 'task_id': task_id, 'sort_key': item_sort_key}
            
            self.user_tasks[user_id].append(new_item)
            self.user_tasks[user_id].sort(key=lambda x: x['sort_key'])
            
            if user_id in self.batch_state:
                self.batch_state[user_id]['total_files'] += 1
                
            if user_id in self.upload_events:
                self.upload_events[user_id].set()

    async def update_status_msg(self, user_id):
        state = self.batch_state.get(user_id)
        if not state or not state.get('status_msg'): 
            return
        
        processed = state['processed']
        total = state['total_files']
        remaining = total - processed
        
        elapsed_min = (time.time() - state['start_time']) / 60.0
        total_mb = state['total_bytes'] / (1024 * 1024)
        speed = (total_mb / elapsed_min) if elapsed_min > 0 else 0
        
        text = (
            "📊 **Bᴀᴛᴄʜ Sᴛᴀᴛᴜꜱ**\n"
            f"✅ **Pʀᴏᴄᴇꜱꜱᴇᴅ:** `{processed}` / `{total}`\n"
            f"⏳ **Rᴇᴍᴀɪɴɪɴɢ:** `{remaining}`\n"
            f"⚡ **Sᴘᴇᴇᴅ:** `{speed:.2f} MB/min`\n"
        )
        try:
            await state['status_msg'].edit(text)
        except FloodWait: 
            pass
        except Exception: 
            pass

    def has_worker(self, user_id):
        if user_id in self.workers:
            dl_task = self.workers[user_id].get('dl')
            if dl_task and not dl_task.done():
                return True
        return False

    def init_staging(self, user_id):
        self.active_downloads[user_id] = []
        self.staging_pool[user_id] = []
        self.upload_events[user_id] = asyncio.Event()

    def register_workers(self, user_id, dl_task, ul_task):
        self.workers[user_id] = {'dl': dl_task, 'ul': ul_task}

    def cleanup(self, user_id):
        for d in [self.workers, self.user_tasks, self.batch_state, self.active_downloads, self.staging_pool, self.upload_events]:
            d.pop(user_id, None)

manager = QueueManager()

# ==========================================
# --- REBOOT RESUME FUNCTION (CRASH PROOF) ---
# ==========================================
async def resume_all_tasks(client):
    print("🔄 Checking for incomplete tasks to resume...")
    try:
        shutil.rmtree("Renames", ignore_errors=True)
        os.makedirs("Renames", exist_ok=True)
        print("✅ Startup Reaper: Cleared all orphaned temporary data from disk.")
    except Exception: 
        pass

    try:
        # Wipes orphaned log channel transit files on reboot
        async for old_log in client.get_chat_history(Config.LOG_CHANNEL, limit=50):
            try: 
                await old_log.delete()
            except Exception: 
                pass
    except Exception: 
        pass

    try:
        tasks = await Task.find_all().to_list()
        if not tasks:
            print("✅ No pending tasks to resume.")
            return

        user_tasks_map = {}
        for task in tasks:
            if task.user_id not in user_tasks_map:
                user_tasks_map[task.user_id] = []
            user_tasks_map[task.user_id].append(task)

        count = 0
        for user_id, user_task_list in user_tasks_map.items():
            valid_msgs = []
            
            for task in user_task_list:
                try:
                    if getattr(task, "processing_msg_id", 0) != 0:
                        try: 
                            await client.delete_messages(user_id, task.processing_msg_id)
                        except Exception: 
                            pass
                            
                    msg = await client.get_messages(user_id, task.message_id)
                    await task.delete()

                    if msg and not msg.empty:
                        valid_msgs.append(msg)
                except Exception as e:
                    print(f"Failed to fetch task {task.id}: {e}")

            if valid_msgs:
                try:
                    resuming_msg = await client.send_message(user_id, f"🔄 **Rᴇꜱᴜᴍɪɴɢ Bᴀᴛᴄʜ...** (`{len(valid_msgs)}` ꜰɪʟᴇꜱ)")
                    async def auto_delete(m):
                        await asyncio.sleep(5)
                        try: 
                            await m.delete()
                        except Exception: 
                            pass
                    asyncio.create_task(auto_delete(resuming_msg))
                except Exception: 
                    pass

                for msg in valid_msgs:
                    try:
                        await rename_start(client, msg)
                        count += 1
                    except Exception as e:
                        print(f"Failed to resume message ID {msg.id}: {e}")

        if count > 0:
            print(f"✅ Resumed {count} tasks successfully.")
            
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

    task_id = await digital_botz.add_task(user_id, message.id, 0)
    await manager.add_task(user_id, message, task_id)
    
    worker_lock = await manager.get_worker_lock(user_id)
    async with worker_lock:
        if manager.has_worker(user_id):
            return

        manager.init_staging(user_id)
        
        manager.batch_state[user_id] = {
            'status_msg': None,
            'processed': 0,
            'total_bytes': 0,
            'start_time': time.time(),
            'total_files': len(manager.user_tasks.get(user_id, []))
        }
        
        assigned_worker = get_least_busy_worker(client)
        if assigned_worker != client:
            worker_loads[assigned_worker] = worker_loads.get(assigned_worker, 0) + 1

        dl_task = asyncio.create_task(download_worker(client, assigned_worker, user_id))
        ul_task = asyncio.create_task(upload_worker(client, assigned_worker, user_id))
        manager.register_workers(user_id, dl_task, ul_task)


async def download_worker(main_client, worker_client, user_id):
    try:
        while True:
            lock = await manager.get_lock(user_id)
            item = None
            sort_key = None
            
            async with lock:
                if not manager.user_tasks.get(user_id):
                    break 
                item = manager.user_tasks[user_id].pop(0)
                sort_key = item['sort_key']
                manager.active_downloads[user_id].append(sort_key)
            
            message = item['msg']
            task_id = item['task_id']
            
            try:
                state = manager.batch_state.get(user_id)
                if state and not state.get('status_msg'):
                    try: 
                        state['status_msg'] = await main_client.send_message(user_id, "📊 **Iɴɪᴛɪᴀʟɪᴢɪɴɢ Bᴀᴛᴄʜ...**")
                    except Exception: 
                        pass
                    
                await manager.update_status_msg(user_id)
                
                rkn_processing = None
                try: 
                    rkn_processing = await message.reply_text("⏳ **Pʀᴇᴘᴀʀɪɴɢ...**", quote=True)
                    await digital_botz.update_processing_msg(task_id, rkn_processing.id)
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                    rkn_processing = await message.reply_text("⏳ **Pʀᴇᴘᴀʀɪɴɢ...**", quote=True)
                    await digital_botz.update_processing_msg(task_id, rkn_processing.id)
                except Exception: 
                    pass
                
                await digital_botz.update_task_status(task_id, "processing")
                rkn_file = getattr(message, message.media.value)
                filename = rkn_file.file_name or "unknown_file"
                filesize = humanbytes(rkn_file.file_size)

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

                if rkn_processing:
                    try: 
                        await rkn_processing.edit("📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ...**")
                    except Exception: 
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

                        dl_path = await asyncio.wait_for(
                            worker_client.download_media(
                                message=target_msg, 
                                file_name=file_path,
                                progress=progress_for_pyrogram, 
                                progress_args=(DOWNLOAD_TEXT, rkn_processing, time.time()) if rkn_processing else ()
                            ), timeout=7200)
                        break 
                        
                    except asyncio.TimeoutError:
                        attempts += 1
                        if log_msg:
                            try: 
                                await main_client.delete_messages(Config.LOG_CHANNEL, log_msg.id)
                            except Exception: 
                                pass
                        await asyncio.sleep(5)
                        
                    except FloodWait as fw:
                        attempts += 1
                        if log_msg:
                            try: 
                                await main_client.delete_messages(Config.LOG_CHANNEL, log_msg.id)
                            except Exception: 
                                pass
                            
                        workers_list = getattr(Config, "WORKER_CLIENTS", [])
                        if len(workers_list) > 1 and worker_client != main_client:
                            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)
                            worker_client = get_least_busy_worker(main_client)
                            worker_loads[worker_client] = worker_loads.get(worker_client, 0) + 1
                            await asyncio.sleep(2)
                        else:
                            await asyncio.sleep(fw.value)
                            
                    except MessageIdInvalid:
                        raise Exception("Task Cancelled")
                    except Exception as e: 
                        raise e 
                
                if not dl_path:
                    raise Exception("Failed to download file after retries (Network Freeze).")

                duration = 0
                try:
                    parser = createParser(file_path)
                    metadata = extractMetadata(parser)
                    if metadata and metadata.has("duration"):
                        duration = metadata.get('duration').seconds
                    if parser: 
                        parser.close()
                except Exception: 
                    pass
                
                ph_path = None
                c_caption = user_data.get('caption', None)
                c_thumb = user_data.get('file_id', None)
                caption = c_caption.format(filename=new_filename, filesize=filesize, duration=convert(duration)) if c_caption else f"**{new_filename}**"
                
                if c_thumb:
                    ph_path = await main_client.download_media(c_thumb)
                elif getattr(rkn_file, 'thumbs', None):
                    ph_path = await main_client.download_media(rkn_file.thumbs[0].file_id)

                upload_type = "document"
                if message.media == MessageMediaType.VIDEO: 
                    upload_type = "video"
                elif message.media == MessageMediaType.AUDIO: 
                    upload_type = "audio"
                
                upload_data = {
                    'message': message, 'file_path': file_path, 'ph_path': ph_path,
                    'caption': caption, 'duration': duration, 'rkn_processing': rkn_processing,
                    'upload_type': upload_type, 'file_size': rkn_file.file_size, 'user_id': user_id,
                    'task_id': task_id, 'new_filename': new_filename,
                    'sort_key': sort_key
                }
                
                async with lock:
                    if user_id in manager.staging_pool:
                        manager.staging_pool[user_id].append(upload_data)
                        
            except Exception as inner_e:
                print(f"Download Error for Task {task_id}: {inner_e}")
                await digital_botz.delete_task(task_id)
                try: 
                    shutil.rmtree(f"Renames/{task_id}", ignore_errors=True)
                except Exception: 
                    pass
                
                state = manager.batch_state.get(user_id)
                if state:
                    state['processed'] += 1
                    await manager.update_status_msg(user_id)
                    
                if "MESSAGE_ID_INVALID" not in str(inner_e) and "Task Cancelled" not in str(inner_e):
                    try: 
                        await main_client.send_message(user_id, f"**Error:** {inner_e}", reply_to_message_id=message.id)
                    except Exception: 
                        pass
            
            finally:
                async with lock:
                    if user_id in manager.active_downloads and sort_key in manager.active_downloads[user_id]:
                        manager.active_downloads[user_id].remove(sort_key)
                
                if log_msg:
                    try: 
                        await main_client.delete_messages(Config.LOG_CHANNEL, log_msg.id)
                    except Exception: 
                        pass
                    
                if user_id in manager.upload_events:
                    manager.upload_events[user_id].set()
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"Critical Download Worker Error: {e}")
    finally:
        if user_id in manager.upload_events:
            manager.upload_events[user_id].set()

async def upload_worker(main_client, worker_client, user_id):
    try:
        while True:
            await manager.upload_events[user_id].wait()
            manager.upload_events[user_id].clear()
            
            if user_id not in manager.staging_pool:
                break
                
            while True:
                lock = await manager.get_lock(user_id)
                data = None
                
                async with lock:
                    if not manager.staging_pool.get(user_id):
                        if not manager.user_tasks.get(user_id) and not manager.active_downloads.get(user_id):
                            return 
                        break
                        
                    manager.staging_pool[user_id].sort(key=lambda x: x['sort_key'])
                    candidate = manager.staging_pool[user_id][0]
                    
                    min_pending = (float('inf'), float('inf'), float('inf'))
                    if manager.user_tasks.get(user_id):
                        min_pending = min(manager.user_tasks[user_id], key=lambda x: x['sort_key'])['sort_key']
                        
                    min_active = (float('inf'), float('inf'), float('inf'))
                    if manager.active_downloads.get(user_id):
                        min_active = min(manager.active_downloads[user_id])
                        
                    absolute_min_blocking = min(min_pending, min_active)
                    
                    if candidate['sort_key'] <= absolute_min_blocking:
                        data = manager.staging_pool[user_id].pop(0)
                    else:
                        data = None 
                
                if not data:
                    try:
                        if candidate.get('rkn_processing'):
                            await candidate['rkn_processing'].edit("⏳ **Wᴀɪᴛɪɴɢ ɪɴ Qᴜᴇᴜᴇ...**")
                    except FloodWait as fw:
                        await asyncio.sleep(fw.value)
                    except Exception: 
                        pass
                    break 
                    
                rkn_processing = data.get('rkn_processing')
                
                try:
                    uploader = app if (getattr(Config, 'STRING_SESSION', None) and data['file_size'] > 2000 * 1024 * 1024) else worker_client
                    is_main_bot = (uploader == main_client)
                    
                    upload_attempts = 0
                    while upload_attempts < 3:
                        try:
                            async def perform_upload():
                                if not is_main_bot:
                                    filw, error = await upload_files(
                                        uploader, Config.LOG_CHANNEL, data['upload_type'], data['file_path'], 
                                        data['ph_path'], data['caption'], data['duration'], rkn_processing, data['new_filename']
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
                                        uploader, data['user_id'], data['upload_type'], data['file_path'], 
                                        data['ph_path'], data['caption'], data['duration'], rkn_processing, data['new_filename']
                                    )
                                    return error

                            if uploader == app:
                                async with upload_lock:
                                    if rkn_processing:
                                        try: 
                                            await rkn_processing.edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                                        except Exception: 
                                            pass
                                    error = await perform_upload()
                            else:
                                if rkn_processing:
                                    try: 
                                        await rkn_processing.edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                                    except Exception: 
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
                                state = manager.batch_state.get(user_id)
                                if state:
                                    state['processed'] += 1
                                    await manager.update_status_msg(user_id)
                                    
                                if "MESSAGE_ID_INVALID" not in str(error):
                                    try: 
                                        await main_client.send_message(user_id, f"**Eʀʀᴏʀ:** {error}", reply_to_message_id=data['message'].id)
                                    except Exception: 
                                        pass
                                break
                            else:
                                await digital_botz.update_daily_limit(user_id, data['file_size'])
                                await digital_botz.delete_task(data['task_id'])
                                
                                state = manager.batch_state.get(user_id)
                                if state:
                                    state['processed'] += 1
                                    state['total_bytes'] += data['file_size']
                                    await manager.update_status_msg(user_id)
                                    
                                if rkn_processing:
                                    try: 
                                        await rkn_processing.edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟy!**")
                                        await asyncio.sleep(2)
                                        await rkn_processing.delete()
                                    except Exception: 
                                        pass
                                break

                        except Exception as perform_e:
                            print(f"Upload loop crash: {perform_e}")
                            await digital_botz.delete_task(data['task_id'])
                            state = manager.batch_state.get(user_id)
                            if state:
                                state['processed'] += 1
                                await manager.update_status_msg(user_id)
                            break

                except Exception as inner_e:
                    print(f"Upload Inner Error: {inner_e}")
                    await digital_botz.delete_task(data['task_id'])
                    
                    state = manager.batch_state.get(user_id)
                    if state:
                        state['processed'] += 1
                        await manager.update_status_msg(user_id)
                        
                    if "MESSAGE_ID_INVALID" not in str(inner_e):
                        try: 
                            await main_client.send_message(user_id, f"**Upload Error:** {inner_e}", reply_to_message_id=data['message'].id)
                        except Exception: 
                            pass
                finally:
                    await remove_path(data['ph_path'], data['file_path'])
                    try: 
                        shutil.rmtree(f"Renames/{data['task_id']}", ignore_errors=True)
                    except Exception: 
                        pass
                    
                    if user_id in manager.upload_events:
                        manager.upload_events[user_id].set()
            
    except Exception as e:
        print(f"Critical Upload Worker Error: {e}")
    finally:
        state = manager.batch_state.get(user_id)
        if state and state.get('status_msg'):
            try: 
                await state['status_msg'].edit("✅ **Aʟʟ Fɪʟᴇꜱ ɪɴ Bᴀᴛᴄʜ Pʀᴏᴄᴇꜱꜱᴇᴅ!**")
            except Exception: 
                pass
            
        manager.cleanup(user_id)
        if worker_client != main_client:
            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)

async def upload_files(bot, sender_id, upload_type, file_path, ph_path, caption, duration, rkn_processing, new_filename):
    try:
        if upload_type == "document":
            filw = await asyncio.wait_for(bot.send_document(sender_id, document=file_path, file_name=new_filename, thumb=ph_path, caption=caption, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()) if rkn_processing else ()), timeout=7200)
        elif upload_type == "video":
            filw = await asyncio.wait_for(bot.send_video(sender_id, video=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()) if rkn_processing else ()), timeout=7200)
        elif upload_type == "audio":
            filw = await asyncio.wait_for(bot.send_audio(sender_id, audio=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=progress_for_pyrogram, progress_args=(UPLOAD_TEXT, rkn_processing, time.time()) if rkn_processing else ()), timeout=7200)
        return filw, None
    except asyncio.TimeoutError:
        return None, "TIMEOUT: Upload connection froze and was gracefully aborted."
    except FloodWait as fw:
        return None, f"FLOODWAIT:{fw.value}"
    except Exception as e:
        return None, str(e)

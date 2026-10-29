# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Special Thanks To @ReshamOwner
# Update Channel @Digital_Botz & @OthersBees
"""
Apache License 2.0
Copyright (c) 2025 @Digital_Botz
"""

# wzgram imports
from wzgram import Client, filters
from wzgram.enums import MessageMediaType
from wzgram.errors import FloodWait, MessageIdInvalid
from wzgram.file_id import FileId
from wzgram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply

# hachoir imports
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from PIL import Image

# bots imports
from helper.utils import progress_for_wzgram, convert, humanbytes, add_prefix_suffix, remove_path
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
# --- LIVE PROGRESS MEMORY FOR TELEMETRY ---
# ==========================================
active_progress = {}
last_ui_update = {}

async def custom_progress(current, total, text, message, start, task_id, filename):
    """Intercepts progress to update the live web dashboard while maintaining Telegram updates."""
    percentage = round((current / total) * 100, 2) if total else 0
    diff = time.time() - start
    speed = current / diff if diff > 0 else 0
    
    active_progress[str(task_id)] = {
        "filename": filename,
        "status": "Downloading" if "Down" in text else "Uploading",
        "percentage": percentage,
        "speed": f"{humanbytes(speed)}/s" if speed > 0 else "0 B/s",
        "current": humanbytes(current),
        "total": humanbytes(total)
    }
    
    if message:
        now = time.time()
        if now - last_ui_update.get(str(task_id), 0) > 2.0 or current == total:
            last_ui_update[str(task_id)] = now
            try:
                asyncio.create_task(progress_for_wzgram(current, total, text, message, start))
            except Exception:
                pass

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
# --- DYNAMIC ROTATIONAL LOAD BALANCER ---
# ==========================================
worker_loads = {}
last_worker_index = -1  # Remembers who took the last job

def get_least_busy_worker(main_client):
    global last_worker_index
    workers = getattr(Config, "WORKER_CLIENTS", [])
    if not workers:
        return main_client
    
    healthy_workers = [w for w in workers if getattr(w, "is_healthy", True)]
    if not healthy_workers:
        return main_client
        
    for w in healthy_workers:
        if w not in worker_loads:
            worker_loads[w] = 0
            
    min_load = min(worker_loads[w] for w in healthy_workers)
    
    for i in range(len(healthy_workers)):
        check_index = (last_worker_index + 1 + i) % len(healthy_workers)
        worker = healthy_workers[check_index]
        
        if worker_loads[worker] == min_load:
            last_worker_index = workers.index(worker)
            return worker
            
    return main_client

# ==========================================
# --- SAFE DELETE TRACKER ---
# ==========================================
async def safe_delete_task(task_id, user_id, client):
    """Unconditionally hunts down and deletes the processing message from chat and log channel before wiping DB record."""
    try:
        raw_task = await digital_botz.db["tasks"].find_one({"_id": task_id})
        if raw_task:
            # Delete processing message from user's chat
            if raw_task.get("processing_msg_id", 0) != 0:
                try:
                    await client.delete_messages(user_id, raw_task["processing_msg_id"])
                except Exception:
                    pass
            
            # Delete log message from log channel
            if raw_task.get("log_msg_id", 0) != 0:
                try:
                    await client.delete_messages(Config.LOG_CHANNEL, raw_task["log_msg_id"])
                except Exception:
                    pass
    except Exception:
        pass
    await digital_botz.delete_task(task_id)

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
        self.silent_users = set()  

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
        if user_id in self.silent_users:
            if state and state.get('status_msg'):
                try: await state['status_msg'].delete()
                except: pass
                state['status_msg'] = None
            return  
            
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
        except FloodWait as fw:
            if fw.value > 15:
                self.silent_users.add(user_id)
                try: await state['status_msg'].delete()
                except: pass
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
        self.silent_users.discard(user_id)

    def register_workers(self, user_id, dl_task, ul_task):
        self.workers[user_id] = {'dl': dl_task, 'ul': ul_task}

    def cleanup(self, user_id):
        for d in [self.workers, self.user_tasks, self.batch_state, self.active_downloads, self.staging_pool, self.upload_events]:
            d.pop(user_id, None)
        self.silent_users.discard(user_id)

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
        async for batch in digital_botz.db["active_batches"].find():
            try: 
                await client.delete_messages(batch["_id"], batch["status_msg_id"])
            except Exception: 
                pass
        await digital_botz.db["active_batches"].delete_many({})
    except Exception as e:
        print(f"Batch Status DB Cleanup Error: {e}")

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
                    raw_task = await digital_botz.db["tasks"].find_one({"_id": task.id}) or {}

                    if raw_task.get("processing_msg_id", 0) != 0:
                        try: await client.delete_messages(user_id, raw_task["processing_msg_id"])
                        except Exception: pass
                    
                    if raw_task.get("log_msg_id", 0) != 0:
                        try: await client.delete_messages(Config.LOG_CHANNEL, raw_task["log_msg_id"])
                        except Exception: pass
                    
                    msg_id = getattr(task, "file_msg_id", getattr(task, "message_id", None))
                    msg = None
                    if msg_id:
                        try: msg = await client.get_messages(user_id, msg_id)
                        except Exception: pass
                    
                    try: await task.delete()
                    except Exception: pass

                    if msg and not getattr(msg, "empty", False):
                        valid_msgs.append(msg)

                except Exception as e:
                    print(f"Failed to fetch task {getattr(task, 'id', 'unknown')}: {e}")
                    try: await task.delete()
                    except: pass

            if valid_msgs:
                try:
                    resuming_msg = await client.send_message(user_id, f"🔄 **Rᴇꜱᴜᴍɪɴɢ Bᴀᴛᴄʜ...** (`{len(valid_msgs)}` ꜰɪʟᴇꜱ)")
                    async def auto_delete(m):
                        await asyncio.sleep(5)
                        try: await m.delete()
                        except Exception: pass
                    asyncio.create_task(auto_delete(resuming_msg))
                except Exception: 
                    pass

                for msg in valid_msgs:
                    try:
                        if not getattr(msg, "from_user", None):
                            class DummyUser:
                                def __init__(self, uid):
                                    self.id = uid
                            msg.from_user = DummyUser(user_id)
                            
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
            btn = [[InlineKeyboardButton("💎 Gᴇᴛ PʀᴇᴍɪᴜM", callback_data="premium_plans")]]
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

        dl_task = asyncio.create_task(download_worker(client, user_id))
        ul_task = asyncio.create_task(upload_worker(client, user_id))
        manager.register_workers(user_id, dl_task, ul_task)


async def download_worker(main_client, user_id):
    # FIRE NOTIFICATION IMMEDIATELY: Tell user batch is captured before entering dynamic wait
    state = manager.batch_state.get(user_id)
    if state and not state.get('status_msg') and user_id not in manager.silent_users:
        try: 
            state['status_msg'] = await main_client.send_message(user_id, "📊 **Iɴɪᴛɪᴀʟɪᴢɪɴɢ Bᴀᴛᴄʜ...**")
            await digital_botz.db["active_batches"].update_one({"_id": user_id}, {"$set": {"status_msg_id": state['status_msg'].id}}, upsert=True)
            await manager.update_status_msg(user_id)
        except FloodWait as fw:
            if fw.value > 15:
                manager.silent_users.add(user_id)
            else:
                await asyncio.sleep(fw.value)
        except Exception: 
            pass

    # DYNAMIC BATCH SETTLE: Ensure all forwarded files arrive and sort correctly before starting
    last_count = -1
    while True:
        lock = await manager.get_lock(user_id)
        async with lock:
            current_count = len(manager.user_tasks.get(user_id, []))
        if current_count > 0 and current_count == last_count:
            break
        last_count = current_count
        await asyncio.sleep(2.0)

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
            
            worker_client = get_least_busy_worker(main_client)
            current_worker = worker_client
            if worker_client != main_client:
                worker_loads[worker_client] = worker_loads.get(worker_client, 0) + 1
            
            try:
                await manager.update_status_msg(user_id)
                
                rkn_processing = None
                if user_id not in manager.silent_users:
                    try: 
                        rkn_processing = await message.reply_text("⏳ **Pʀᴇᴘᴀʀɪɴɢ...**")
                        await digital_botz.update_processing_msg(task_id, rkn_processing.id)
                    except FloodWait as fw:
                        if fw.value > 15:
                            manager.silent_users.add(user_id)
                        else:
                            await asyncio.sleep(fw.value)
                            try:
                                rkn_processing = await message.reply_text("⏳ **Pʀᴇᴘᴀʀɪɴɢ...**")
                                await digital_botz.update_processing_msg(task_id, rkn_processing.id)
                            except: pass
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

                if rkn_processing and user_id not in manager.silent_users:
                    try: 
                        await rkn_processing.edit("📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ...**")
                    except FloodWait as fw:
                        if fw.value > 15:
                            manager.silent_users.add(user_id)
                            try: await rkn_processing.delete()
                            except: pass
                            rkn_processing = None
                        else:
                            await asyncio.sleep(fw.value)
                    except Exception: 
                        pass
                
                dl_path = None
                log_msg_down = None
                workers_list = getattr(Config, "WORKER_CLIENTS", [])
                
                while True:
                    try:
                        if not worker_client.is_connected:
                            try: await worker_client.connect()
                            except Exception: pass

                        if worker_client != main_client:
                            log_msg_down = await message.copy(Config.LOG_CHANNEL)
                            await digital_botz.db["tasks"].update_one({"_id": task_id}, {"$set": {"log_msg_id": log_msg_down.id}})
                            target_msg = await worker_client.get_messages(Config.LOG_CHANNEL, log_msg_down.id)
                        else:
                            target_msg = message

                        dl_start_time = time.time()
                        dl_path = await asyncio.wait_for(
                            worker_client.download_media(
                                message=target_msg,
                                file_name=file_path,
                                progress=custom_progress,
                                progress_args=(DOWNLOAD_TEXT, rkn_processing if (user_id not in manager.silent_users) else None, dl_start_time, task_id, new_filename)
                            ),
                            timeout=7200
                        )
                        
                        if worker_client != main_client and log_msg_down:
                            try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg_down.id)
                            except Exception: pass
                            log_msg_down = None
                            
                        break 
                        
                    except asyncio.TimeoutError:
                        if worker_client != main_client and log_msg_down:
                            try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg_down.id)
                            except Exception: pass
                            log_msg_down = None
                        
                        if len(workers_list) > 1 and worker_client != main_client:
                            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)
                            worker_client = get_least_busy_worker(main_client)
                            worker_loads[worker_client] = worker_loads.get(worker_client, 0) + 1
                            current_worker = worker_client
                            await asyncio.sleep(2)
                        else:
                            await asyncio.sleep(5)
                        continue
                        
                    except MessageIdInvalid:
                        if worker_client != main_client and log_msg_down:
                            try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg_down.id)
                            except Exception: pass
                            log_msg_down = None
                            
                        if main_client.premium and main_client.uploadlimit:
                            await digital_botz.increment_used_limit(user_id, -rkn_file.file_size)
                        await safe_delete_task(task_id, user_id, main_client)
                        raise Exception("MessageIdInvalid")
                        
                    except Exception as e:
                        if worker_client != main_client and log_msg_down:
                            try: await main_client.delete_messages(Config.LOG_CHANNEL, log_msg_down.id)
                            except Exception: pass
                            log_msg_down = None
                            
                        wait_time = getattr(e, 'value', 5) if isinstance(e, FloodWait) else 5
                        
                        if isinstance(e, FloodWait):
                            if worker_client != main_client:
                                worker_client.is_healthy = False
                            if e.value > 15:
                                manager.silent_users.add(user_id)

                        if len(workers_list) > 1 and worker_client != main_client:
                            worker_loads[worker_client] = max(0, worker_loads.get(worker_client, 0) - 1)
                            worker_client = get_least_busy_worker(main_client)
                            worker_loads[worker_client] = worker_loads.get(worker_client, 0) + 1
                            current_worker = worker_client 
                            await asyncio.sleep(2)
                        else:
                            await asyncio.sleep(wait_time)
                        continue

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
                if str(task_id) in active_progress:
                    del active_progress[str(task_id)]
                await safe_delete_task(task_id, user_id, main_client)
                try: 
                    shutil.rmtree(f"Renames/{task_id}", ignore_errors=True)
                except Exception: 
                    pass
                
                state = manager.batch_state.get(user_id)
                if state:
                    state['processed'] += 1
                    await manager.update_status_msg(user_id)
                continue
            
            finally:
                if current_worker != main_client:
                    worker_loads[current_worker] = max(0, worker_loads.get(current_worker, 0) - 1)
                
                async with lock:
                    if user_id in manager.active_downloads and sort_key in manager.active_downloads[user_id]:
                        manager.active_downloads[user_id].remove(sort_key)
                
                if user_id in manager.upload_events:
                    manager.upload_events[user_id].set()
                await asyncio.sleep(1)
                
    except Exception as e:
        print(f"Critical Download Worker Error: {e}")
    finally:
        if user_id in manager.upload_events:
            manager.upload_events[user_id].set()


async def upload_worker(main_client, user_id):
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
                    if candidate.get('rkn_processing') and user_id not in manager.silent_users:
                        try: 
                            await candidate['rkn_processing'].edit("⏳ **Wᴀɪᴛɪɴɢ ɪɴ Qᴜᴇᴜᴇ...**")
                        except FloodWait as fw:
                            if fw.value > 15:
                                manager.silent_users.add(user_id)
                                try: await candidate['rkn_processing'].delete()
                                except: pass
                            else:
                                await asyncio.sleep(fw.value)
                        except Exception: 
                            pass
                    break 
                    
                rkn_processing = data.get('rkn_processing')
                if user_id in manager.silent_users:
                    rkn_processing = None
                
                worker_client = get_least_busy_worker(main_client)
                uploader = app if (getattr(Config, 'STRING_SESSION', None) and data['file_size'] > 2000 * 1024 * 1024) else worker_client
                is_main_bot = (uploader == main_client)
                
                if uploader != main_client and uploader != app:
                    worker_loads[uploader] = worker_loads.get(uploader, 0) + 1
                
                try:
                    workers_list = getattr(Config, "WORKER_CLIENTS", [])
                    
                    while True:
                        try:
                            async def perform_upload():
                                if not uploader.is_connected:
                                    try: await uploader.connect()
                                    except Exception: pass

                                if not is_main_bot:
                                    filw, error = await upload_files(
                                        uploader, Config.LOG_CHANNEL, data['upload_type'], data['file_path'], 
                                        data['ph_path'], data['caption'], data['duration'], rkn_processing if user_id not in manager.silent_users else None, data['new_filename'], data['task_id']
                                    )
                                    if not error and filw:
                                        await asyncio.sleep(1.5)
                                        delivered = False
                                        while not delivered:
                                            try:
                                                await main_client.copy_message(user_id, Config.LOG_CHANNEL, filw.id)
                                                delivered = True
                                            except FloodWait as fw:
                                                if fw.value > 15:
                                                    manager.silent_users.add(user_id)
                                                    if rkn_processing:
                                                        try: await rkn_processing.delete()
                                                        except: pass
                                                await asyncio.sleep(fw.value)
                                            except Exception:
                                                try:
                                                    await uploader.copy_message(user_id, Config.LOG_CHANNEL, filw.id)
                                                    delivered = True
                                                except Exception:
                                                    delivered = True 
                                        for attempt in range(3):
                                            try:
                                                await main_client.delete_messages(Config.LOG_CHANNEL, filw.id)
                                                break
                                            except Exception:
                                                pass
                                    return error
                                else:
                                    filw, error = await upload_files(
                                        main_client, user_id, data['upload_type'], data['file_path'], 
                                        data['ph_path'], data['caption'], data['duration'], rkn_processing if user_id not in manager.silent_users else None, data['new_filename'], data['task_id']
                                    )
                                    return error

                            if uploader == app:
                                async with upload_lock:
                                    if rkn_processing and user_id not in manager.silent_users:
                                        try: 
                                            await rkn_processing.edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                                        except FloodWait as fw:
                                            if fw.value > 15:
                                                manager.silent_users.add(user_id)
                                                try: await rkn_processing.delete()
                                                except: pass
                                        except Exception: 
                                            pass
                                    error = await perform_upload()
                            else:
                                if rkn_processing and user_id not in manager.silent_users:
                                    try: 
                                        await rkn_processing.edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
                                    except FloodWait as fw:
                                        if fw.value > 15:
                                            manager.silent_users.add(user_id)
                                            try: await rkn_processing.delete()
                                            except: pass
                                    except Exception: 
                                        pass
                                error = await perform_upload()

                            if error:
                                if str(error).startswith("FLOODWAIT:"):
                                    try: wait_time = int(str(error).split(":")[1])
                                    except: wait_time = 5
                                    
                                    if wait_time > 15:
                                        manager.silent_users.add(user_id)
                                        if rkn_processing:
                                            try: await rkn_processing.delete()
                                            except: pass
                                            rkn_processing = None
                                else:
                                    wait_time = 5

                                if uploader != app and len(workers_list) > 1 and not is_main_bot:
                                    worker_loads[uploader] = max(0, worker_loads.get(uploader, 0) - 1)
                                    uploader = get_least_busy_worker(main_client)
                                    worker_loads[uploader] = worker_loads.get(uploader, 0) + 1
                                    is_main_bot = (uploader == main_client)
                                    await asyncio.sleep(2)
                                    continue
                                else:
                                    await asyncio.sleep(wait_time)
                                    continue
                                    
                            else:
                                await digital_botz.update_daily_limit(user_id, data['file_size'])
                                await safe_delete_task(data['task_id'], user_id, main_client)
                                
                                state = manager.batch_state.get(user_id)
                                if state:
                                    state['processed'] += 1
                                    state['total_bytes'] += data['file_size']
                                    await manager.update_status_msg(user_id)
                                    
                                if rkn_processing and user_id not in manager.silent_users:
                                    try: 
                                        await rkn_processing.edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜰᴜʟʟy!**")
                                        await asyncio.sleep(2)
                                        await rkn_processing.delete()
                                    except Exception: 
                                        pass
                                break

                        except asyncio.TimeoutError:
                            if uploader != app and len(workers_list) > 1 and not is_main_bot:
                                worker_loads[uploader] = max(0, worker_loads.get(uploader, 0) - 1)
                                uploader = get_least_busy_worker(main_client)
                                worker_loads[uploader] = worker_loads.get(uploader, 0) + 1
                                is_main_bot = (uploader == main_client)
                                await asyncio.sleep(2)
                                continue
                            else:
                                await asyncio.sleep(5)
                                continue

                        except MessageIdInvalid:
                            if main_client.premium and main_client.uploadlimit:
                                await digital_botz.increment_used_limit(user_id, -data['file_size'])
                            await safe_delete_task(data['task_id'], user_id, main_client)
                            raise Exception("MessageIdInvalid")
                            
                        except Exception as perform_e:
                            if isinstance(perform_e, FloodWait):
                                if uploader != app and not is_main_bot:
                                    uploader.is_healthy = False
                                if perform_e.value > 15:
                                    manager.silent_users.add(user_id)
                                    if rkn_processing:
                                        try: await rkn_processing.delete()
                                        except: pass
                                        rkn_processing = None
                            print(f"Upload loop crash: {perform_e}")
                            break

                except Exception as inner_e:
                    print(f"Upload Inner Error: {inner_e}")
                    await safe_delete_task(data['task_id'], user_id, main_client)
                    
                    state = manager.batch_state.get(user_id)
                    if state:
                        state['processed'] += 1
                        await manager.update_status_msg(user_id)
                        
                finally:
                    if str(data['task_id']) in active_progress:
                        del active_progress[str(data['task_id'])]

                    if str(data['task_id']) in last_ui_update:
                        del last_ui_update[str(data['task_id'])]

                    if uploader != main_client and uploader != app:
                        worker_loads[uploader] = max(0, worker_loads.get(uploader, 0) - 1)

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
            if user_id not in manager.silent_users:
                try: 
                    await state['status_msg'].edit("✅ **Bᴀᴛᴄʜ Pʀᴏᴄᴇꜱꜱɪɴɢ Cᴏᴍᴘʟᴇᴛᴇ!**")
                except Exception: 
                    pass
            else:
                try:
                    await state['status_msg'].delete()
                except Exception:
                    pass
                    
        try: await digital_botz.db["active_batches"].delete_one({"_id": user_id})
        except: pass
            
        manager.cleanup(user_id)


async def upload_files(bot, sender_id, upload_type, file_path, ph_path, caption, duration, rkn_processing, new_filename, task_id):
    try:
        up_start_time = time.time()
        active_prog = custom_progress
        active_args = (UPLOAD_TEXT, rkn_processing, up_start_time, task_id, new_filename)

        if upload_type == "document":
            filw = await asyncio.wait_for(bot.send_document(sender_id, document=file_path, file_name=new_filename, thumb=ph_path, caption=caption, progress=active_prog, progress_args=active_args), timeout=7200)
        elif upload_type == "video":
            filw = await asyncio.wait_for(bot.send_video(sender_id, video=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=active_prog, progress_args=active_args), timeout=7200)
        elif upload_type == "audio":
            filw = await asyncio.wait_for(bot.send_audio(sender_id, audio=file_path, file_name=new_filename, caption=caption, thumb=ph_path, duration=duration, progress=active_prog, progress_args=active_args), timeout=7200)
        return filw, None
    except asyncio.TimeoutError:
        return None, "TIMEOUT: Upload connection froze and was gracefully aborted."
    except FloodWait as fw:
        return None, f"FLOODWAIT:{fw.value}"
    except Exception as e:
        return None, str(e)

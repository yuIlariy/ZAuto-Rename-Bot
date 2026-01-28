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

# --- QUEUE VARIABLES ---
# Structure: { user_id: [message1, message2, ...] }
USER_QUEUE = {}
# Structure: { user_id: True/False }
IS_RUNNING = {}
# -----------------------

@Client.on_message(filters.private & (filters.audio | filters.document | filters.video))
async def rename_start(client, message):
    user_id = message.from_user.id

    # 1. Initialize Queue for User if not exists
    if user_id not in USER_QUEUE:
        USER_QUEUE[user_id] = []
    
    # 2. Add Message to Queue
    USER_QUEUE[user_id].append(message)
    
    # 3. Check if a worker is already running for this user
    if user_id in IS_RUNNING and IS_RUNNING[user_id]:
        # Bot is already working on a file, so just add this new one to the list and return.
        return

    # 4. Start the Worker (if not running)
    IS_RUNNING[user_id] = True
    await process_queue(client, user_id)

async def process_queue(client, user_id):
    try:
        while user_id in USER_QUEUE and USER_QUEUE[user_id]:
            # --- SORTING LOGIC ---
            # Sort the pending messages by Season THEN Episode
            def get_sort_key(msg):
                try:
                    # Get filename from the message media
                    file_val = getattr(msg, msg.media.value)
                    fname = file_val.file_name or ""
                    
                    # Extract info using your AutoRenamer logic
                    info = renamer.extract_all_info(fname)
                    
                    # Parse Season (Default to 0 if not found)
                    season = 0
                    if info.get('season'):
                        # Removes "S" and converts to int (e.g. "S01" -> 1)
                        season = int(info['season'].upper().replace("S", ""))
                    
                    # Parse Episode (Default to 0 if not found)
                    episode = 0
                    if info.get('episode'):
                        # Removes "E" and converts to int (e.g. "E05" -> 5)
                        episode = int(info['episode'].upper().replace("E", ""))
                        
                    # Return tuple: (Season Number, Episode Number)
                    # This ensures S01E01 comes before S01E02, and S01 comes before S02
                    return (season, episode)
                except:
                    # If parsing fails, push to end of queue
                    return (999, 999)

            # Apply the sort to the user's queue
            USER_QUEUE[user_id].sort(key=get_sort_key)
            # ---------------------

            # Take the FIRST message (which is now the lowest Season/Episode)
            message = USER_QUEUE[user_id].pop(0)

            # Process this single file
            await process_file_logic(client, message)
            
            # Wait a moment before starting the next file to prevent floodwaits
            await asyncio.sleep(2)

    except Exception as e:
        print(f"Queue Error: {e}")
    finally:
        # Mark worker as finished when queue is empty
        IS_RUNNING[user_id] = False
        # Clean up empty list key
        if user_id in USER_QUEUE and not USER_QUEUE[user_id]:
            del USER_QUEUE[user_id]

async def process_file_logic(client, message):
    """
    Core renaming logic. This runs for ONE file at a time.
    """
    try:
        # 1. Check File Size for Non-Premium/Non-Session users
        rkn_file = getattr(message, message.media.value)
        if not Config.STRING_SESSION:
            if rkn_file.file_size > 2000 * 1024 * 1024:
                await message.reply_text("Sᴏʀʀy Bʀᴏ Tʜɪꜱ Bᴏᴛ Iꜱ Dᴏᴇꜱɴ'ᴛ Sᴜᴩᴩᴏʀᴛ Uᴩʟᴏᴀᴅɪɴɢ Fɪʟᴇꜱ Bɪɢɢᴇʀ Tʜᴀɴ 2Gʙ+")
                return

        # 2. Gather File Info & Emojis
        filename = rkn_file.file_name
        if not filename:
            filename = "unknown_file"
            
        if not "." in filename:
            if "." in filename:
                extn = filename.rsplit('.', 1)[-1]
            else:
                extn = "mkv"
            filename = filename + "." + extn
            
        filesize = humanbytes(rkn_file.file_size)
        mime_type = rkn_file.mime_type
        dcid = FileId.decode(rkn_file.file_id).dc_id
        extension_type = mime_type.split('/')[0]

        # --- EMOJI LOGIC ---
        file_ext = filename.split('.')[-1].lower() if "." in filename else "unknown"

        FILE_TYPE_EMOJIS = {
            "audio": "🎵", "video": "🎬", "image": "🖼️", "application": "📦",
            "text": "📄", "font": "🔤", "message": "💬", "multipart": "🧩", "default": "📁"
        }
        EXTENSION_EMOJIS = {
            "zip": "🗜️", "rar": "📚", "7z": "🧳", "tar": "🗂️", "gz": "🧪", "xz": "🧬",
            "pdf": "📕", "apk": "🤖", "exe": "💻", "msi": "🛠️", "doc": "📄", "docx": "📄",
            "ppt": "📊", "pptx": "📊", "xls": "📈", "xlsx": "📈", "csv": "📑", "txt": "📝",
            "json": "🧾", "xml": "🧬", "html": "🌐", "py": "🐍", "js": "📜", "ts": "📜",
            "java": "☕", "c": "🔧", "cpp": "🔩", "mp3": "🎶", "wav": "🔊", "flac": "🎼",
            "mp4": "🎥", "mkv": "📽️", "mov": "🎞️", "webm": "🌐", "jpg": "🖼️", "jpeg": "🖼️",
            "png": "🖼️", "gif": "🌀", "svg": "📐", "ttf": "🔤", "otf": "🔤", "woff": "🔤", "eot": "🔤"
        }
        emoji = EXTENSION_EMOJIS.get(file_ext) or FILE_TYPE_EMOJIS.get(extension_type, FILE_TYPE_EMOJIS["default"])
        # -------------------

        # 3. Send Initial Status Message
        rkn_processing = await message.reply_text(
            text=f"**🔄 Aᴜᴛᴏ-Rᴇɴᴀᴍᴇ Sᴛᴀʀᴛᴇᴅ...**\n\n"
                 f"**__{emoji} Fɪʟᴇ Iɴꜰᴏ:__**\n"
                 f"🗃️ Oʀɪɢɪɴᴀʟ: `{filename}`\n"
                 f"💾 Sɪᴢᴇ: `{filesize}`\n"
                 f"🧬 Tyᴩᴇ: `{mime_type}`\n\n"
                 f"⏳ **Pʀᴏᴄᴇꜱꜱɪɴɢ...**"
        )

        user_id = message.from_user.id
        
        # 4. Generate New Filename
        info = renamer.extract_all_info(filename)
        user_data = await digital_botz.get_user_data(user_id)
        format_template = user_data.get('format_template', None)
        
        if not format_template:
            format_template = "{original}.{ext}"

        new_name = renamer.apply_format_template(info, format_template)
        
        if not new_name.endswith(f".{info['extension']}"):
            new_name += f".{info['extension']}"
        
        new_filename = new_name.replace("/", "_").replace("\\", "_")
        
        # 5. Create Directory & Paths
        if not os.path.isdir("Renames"):
            os.makedirs("Renames", exist_ok=True)
            
        file_path = f"Renames/{new_filename}"
        
        # 6. Download
        await rkn_processing.edit(f"📥 **Dᴏᴡɴʟᴏᴀᴅɪɴɢ:**\n`{new_filename}`")
        try:            
            dl_path = await client.download_media(
                message=message, 
                file_name=file_path, 
                progress=progress_for_pyrogram, 
                progress_args=(DOWNLOAD_TEXT, rkn_processing, time.time())
            )                    
        except Exception as e:        
            await rkn_processing.edit(f"⚠️ Download Error: {e}")
            return
        
        # 7. Extract Duration
        duration = 0
        try:
            parser = createParser(file_path)
            metadata = extractMetadata(parser)
            if metadata and metadata.has("duration"):
                duration = metadata.get('duration').seconds
            if parser:
                parser.close()
        except:
            pass
            
        # 8. Handle Thumbnail & Caption
        ph_path = None
        c_caption = user_data.get('caption', None)
        c_thumb = user_data.get('file_id', None)

        if c_caption:
            try:
                caption = c_caption.format(filename=new_filename, filesize=filesize, duration=convert(duration))
            except Exception as e:             
                caption = f"**{new_filename}**"          
        else:
            caption = f"**{new_filename}**"
    
        media_thumbs = getattr(rkn_file, 'thumbs', None)
        if (media_thumbs or c_thumb):
            try:
                if c_thumb:
                    ph_path = await client.download_media(c_thumb) 
                else:
                    ph_path = await client.download_media(media_thumbs[0].file_id)
                
                if ph_path and os.path.exists(ph_path):
                    Image.open(ph_path).convert("RGB").save(ph_path)
                    img = Image.open(ph_path)
                    img.resize((320, 320))
                    img.save(ph_path, "JPEG")
            except Exception as e:
                ph_path = None

        # 9. Determine Upload Type
        upload_type = "document"
        if message.media == MessageMediaType.VIDEO:
            upload_type = "video"
        elif message.media == MessageMediaType.AUDIO:
            upload_type = "audio"
        
        await rkn_processing.edit("📤 **Uᴩʟᴏᴀᴅɪɴɢ...**")
        
        # 10. Upload Logic
        if rkn_file.file_size > 2000 * 1024 * 1024:
            filw, error = await upload_files(
                app, Config.LOG_CHANNEL, upload_type, file_path, 
                ph_path, caption, duration, rkn_processing
            )
            if error:            
                await remove_path(ph_path, file_path, dl_path)
                await rkn_processing.edit(f"⚠️ Upload Error: {error}")
                return
            
            from_chat = filw.chat.id
            mg_id = filw.id
            await asyncio.sleep(2)
            await client.copy_message(message.from_user.id, from_chat, mg_id)     
        else:
            filw, error = await upload_files(
                client, message.chat.id, upload_type, file_path, 
                ph_path, caption, duration, rkn_processing
            )
            if error:            
                await remove_path(ph_path, file_path, dl_path)
                await rkn_processing.edit(f"⚠️ Upload Error: {error}")
                return

        # 11. Cleanup & Success
        await remove_path(ph_path, file_path, dl_path)
        await rkn_processing.edit("✅ **Uᴩʟᴏᴀᴅᴇᴅ Sᴜᴄᴄᴇꜱꜱꜰᴜʟʟy!**")
        await asyncio.sleep(2) 
        await rkn_processing.delete()

    except Exception as e:
        # Fallback cleanup in case of crash
        print(f"Error in process_file_logic: {e}")
        try:
            if 'ph_path' in locals(): await remove_path(ph_path)
            if 'file_path' in locals(): await remove_path(file_path)
            if 'dl_path' in locals(): await remove_path(dl_path)
        except:
            pass

async def upload_files(bot, sender_id, upload_type, file_path, ph_path, caption, duration, rkn_processing):
    """
    Unified function to upload files based on type
    """
    try:
        if not os.path.exists(file_path):
            return None, f"File not found: {file_path}"
            
        if upload_type == "document":
            filw = await bot.send_document(
                sender_id,
                document=file_path,
                thumb=ph_path,
                caption=caption,
                progress=progress_for_pyrogram,
                progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        
        elif upload_type == "video":
            filw = await bot.send_video(
                sender_id,
                video=file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        
        elif upload_type == "audio":
            filw = await bot.send_audio(
                sender_id,
                audio=file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=(UPLOAD_TEXT, rkn_processing, time.time()))
        else:
            return None, f"Unknown upload type: {upload_type}"
        
        return filw, None
        
    except Exception as e:
        return None, str(e)

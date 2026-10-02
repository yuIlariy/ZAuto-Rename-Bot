# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz & @Rkn_Bots_Updates
# Developer @RknDeveloperr
# Special Thanks To @ReshamOwner
# Update Channel @Digital_Botz & @DigitalBotz_Support
"""
Apache License 2.0
Copyright (c) 2025 @Digital_Botz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Telegram Link : https://t.me/Digital_Botz 
Repo Link : https://github.com/DigitalBotz/Digital-Rename-Bot
License Link : https://github.com/DigitalBotz/Digital-Rename-Bot/blob/main/LICENSE
"""

# imports
from pyrogram import Client, filters 
from pyrogram.errors import FloodWait
from helper.database import digital_botz

# --- THE IMMORTAL BYPASS HELPER ---
async def send_safely(message, rkn_msg, text):
    """Attempts to edit the message. If rate-limited, deletes and sends a new message."""
    try:
        await rkn_msg.edit(text)
    except FloodWait:
        try: 
            await rkn_msg.delete()
        except: 
            pass
        try: 
            await message.reply_text(text, quote=True)
        except: 
            pass
    except Exception:
        pass
# ----------------------------------

@Client.on_message(filters.private & filters.command('set_caption'))
async def add_caption(client, message):
    rkn = await message.reply_text("__**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**__")
    try:
        if len(message.command) == 1:
           text = "**__Gɪᴠᴇ Tʜᴇ Cᴀᴩᴛɪᴏɴ__\n\nExᴀᴍᴩʟᴇ:- `/set_caption {filename}\n\n💾 Sɪᴢᴇ: {filesize}\n\n⏰ Dᴜʀᴀᴛɪᴏɴ: {duration}\n\bBy: @OtherBs`**"
           return await send_safely(message, rkn, text)
           
        caption = message.text.split(" ", 1)[1]
        await digital_botz.set_caption(message.from_user.id, caption=caption)
        await send_safely(message, rkn, "__**✅ Cᴀᴩᴛɪᴏɴ Sᴀᴠᴇᴅ**__")
    except Exception as e:
        print(f"Error in set_caption: {e}")
        await send_safely(message, rkn, f"⚠️ **Error:** `{e}`\n\n__Tip: Try sending /start to refresh your database profile.__")
   
@Client.on_message(filters.private & filters.command(['del_caption', 'delete_caption', 'delcaption']))
async def delete_caption(client, message):
    rkn = await message.reply_text("__**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**__")
    try:
        caption = await digital_botz.get_caption(message.from_user.id)  
        if not caption:
           return await send_safely(message, rkn, "__**😔 Yᴏᴜ Dᴏɴ'ᴛ Hᴀᴠᴇ Aɴy Cᴀᴩᴛɪᴏɴ**__")
           
        await digital_botz.set_caption(message.from_user.id, caption=None)
        await send_safely(message, rkn, "__**❌️ Cᴀᴩᴛɪᴏɴ Dᴇʟᴇᴛᴇᴅ**__")
    except Exception as e:
        print(f"Error in del_caption: {e}")
        await send_safely(message, rkn, f"⚠️ **Error:** `{e}`\n\n__Tip: Try sending /start to refresh your database profile.__")
                                       
@Client.on_message(filters.private & filters.command(['see_caption', 'view_caption']))
async def see_caption(client, message):
    rkn = await message.reply_text("__**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**__")
    try:
        caption = await digital_botz.get_caption(message.from_user.id)  
        if caption:
           await send_safely(message, rkn, f"**Yᴏᴜ'ʀᴇ Cᴀᴩᴛɪᴏɴ:-**\n\n`{caption}`")
        else:
           await send_safely(message, rkn, "__**😔 Yᴏᴜ Dᴏɴ'ᴛ Hᴀᴠᴇ Aɴy Cᴀᴩᴛɪᴏɴ**__")
    except Exception as e:
        print(f"Error in see_caption: {e}")
        await send_safely(message, rkn, f"⚠️ **Error:** `{e}`\n\n__Tip: Try sending /start to refresh your database profile.__")

@Client.on_message(filters.private & filters.command(['view_thumb', 'viewthumb']))
async def viewthumb(client, message):
    rkn = await message.reply_text("__**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**__")
    try:
        thumb = await digital_botz.get_thumbnail(message.from_user.id)
        if thumb:
            try:
                await client.send_photo(chat_id=message.chat.id, photo=thumb)
                await rkn.delete()
            except FloodWait:
                pass # If sending the photo gets blocked, ignore it safely
        else:
            await send_safely(message, rkn, "😔 __**Yᴏᴜ Dᴏɴ'ᴛ Hᴀᴠᴇ Aɴy Tʜᴜᴍʙɴᴀɪʟ**__") 
    except Exception as e:
        print(f"Error in viewthumb: {e}")
        await send_safely(message, rkn, f"⚠️ **Error:** `{e}`\n\n__Tip: Try sending /start to refresh your database profile.__")
		
@Client.on_message(filters.private & filters.command(['del_thumb', 'delete_thumb', 'delthumb']))
async def removethumb(client, message):
    rkn = await message.reply_text("__**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**__")
    try:
        thumb = await digital_botz.get_thumbnail(message.from_user.id)
        if thumb:
            await digital_botz.set_thumbnail(message.from_user.id, file_id=None)
            await send_safely(message, rkn, "❌️ __**Tʜᴜᴍʙɴᴀɪʟ Dᴇʟᴇᴛᴇᴅ**__")
            return
            
        await send_safely(message, rkn, "😔 __**Yᴏᴜ Dᴏɴ'ᴛ Hᴀᴠᴇ Aɴy Tʜᴜᴍʙɴᴀɪʟ**__")
    except Exception as e:
        print(f"Error in removethumb: {e}")
        await send_safely(message, rkn, f"⚠️ **Error:** `{e}`\n\n__Tip: Try sending /start to refresh your database profile.__")

@Client.on_message(filters.private & filters.photo)
async def addthumbs(client, message):
    rkn = await message.reply_text("__**ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ**__")
    try:
        await digital_botz.set_thumbnail(message.from_user.id, file_id=message.photo.file_id)                
        await send_safely(message, rkn, "✅️ __**Tʜᴜᴍʙɴᴀɪʟ Sᴀᴠᴇᴅ**__")
    except Exception as e:
        print(f"Error in addthumbs: {e}")
        await send_safely(message, rkn, f"⚠️ **Error:** `{e}`\n\n__Tip: Try sending /start to refresh your database profile.__")

# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Update Channel @Digital_Botz & @DigitalBotz_Support

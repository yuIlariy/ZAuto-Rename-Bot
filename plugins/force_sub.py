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
"""

# pyrogram imports
from pyrogram import Client, filters, enums 
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import UserNotParticipant
from pyrogram import StopPropagation # <--- The Magic Kill Switch

# extra imports
from config import Config
from helper.database import digital_botz
import datetime 

# ==========================================
# --- GLOBAL MESSAGE GATEKEEPER ---
# Runs at group=-1 (Before ANY other command or file upload)
# ==========================================
@Client.on_message(filters.private & filters.incoming, group=-1)
async def global_message_gatekeeper(client, message):
    user_id = message.from_user.id
    await digital_botz.add_user(client, message)

    # --- 1. BAN CHECK ---
    ban_status = await digital_botz.get_ban_status(user_id)
    if ban_status.get("is_banned", False):
        try:
            banned_on_str = ban_status["banned_on"]
            if "T" in banned_on_str or ":" in banned_on_str:
                banned_on = datetime.datetime.fromisoformat(banned_on_str).date()
            else:
                banned_on = datetime.date.fromisoformat(banned_on_str)
                
            if (datetime.date.today() - banned_on).days > ban_status.get("ban_duration", 0):
                await digital_botz.remove_ban(user_id)
            else:
                await message.reply_text("🚫 **Sᴏʀʀy, Yᴏᴜ ᴀʀᴇ Bᴀɴɴᴇᴅ!**\n\nPlease Contact Admin: @xspes") 
                raise StopPropagation # Kills the process here
        except StopPropagation:
            raise
        except Exception as e:
            print(f"Error checking ban status: {e}")

    # --- 2. FORCE SUB CHECK ---
    if Config.FORCE_SUB:
        try:
            user = await client.get_chat_member(Config.FORCE_SUB, user_id)
            if user.status == enums.ChatMemberStatus.BANNED:
                await message.reply_text("🚫 **Sᴏʀʀy, Yᴏᴜ ᴀʀᴇ Bᴀɴɴᴇᴅ ꜰʀᴏᴍ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ!**")
                raise StopPropagation
            elif user.status not in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                raise UserNotParticipant
        except UserNotParticipant:
            buttons = [[InlineKeyboardButton(text="📢 Jᴏɪɴ Uᴩᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ 📢", url=f"https://t.me/{Config.FORCE_SUB}")]]
            text = "**⚠️ Pʟᴇᴀꜱᴇ Jᴏɪɴ Oᴜʀ Uᴩᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ Tᴏ Cᴏɴᴛɪɴᴜᴇ Uꜱɪɴɢ Mᴇ!**\n\n_Join the channel then send your file or command again._"
            await message.reply_text(text=text, reply_markup=InlineKeyboardMarkup(buttons))
            raise StopPropagation # Kills the process here, file rename will NEVER trigger
        except StopPropagation:
            raise
        except Exception as e:
            print(f"Force Sub Error: {e}")


# ==========================================
# --- GLOBAL BUTTON (CALLBACK) GATEKEEPER ---
# Runs at group=-1 (Secures all inline button clicks)
# ==========================================
@Client.on_callback_query(group=-1)
async def global_cb_gatekeeper(client, query):
    # Let them click "Close" on error messages without being blocked
    if query.data == "close":
        return
        
    user_id = query.from_user.id
    
    # --- 1. BAN CHECK ---
    ban_status = await digital_botz.get_ban_status(user_id)
    if ban_status.get("is_banned", False):
        await query.answer("🚫 You are Banned! Contact Admin.", show_alert=True)
        raise StopPropagation
        
    # --- 2. FORCE SUB CHECK ---
    if Config.FORCE_SUB:
        try:
            user = await client.get_chat_member(Config.FORCE_SUB, user_id)
            if user.status not in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                raise UserNotParticipant
        except UserNotParticipant:
            await query.answer("⚠️ Please Join the Update Channel first!", show_alert=True)
            raise StopPropagation
        except StopPropagation:
            raise
        except Exception as e:
            pass

# Rkn Developer 
# Update Channel @Digital_Botz & @DigitalBotz_Support

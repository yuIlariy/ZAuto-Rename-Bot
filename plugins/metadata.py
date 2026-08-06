# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Special Thanks To @ReshamOwner
# Update Channel @Digital_Botz & @DigitalBotz_Support

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import ListenerTimeout

# extra imports
from helper.database import digital_botz
from config import rkn

# Fixed callback_data typo: 'cutom_metadata' -> 'custom_metadata'
TRUE = [[InlineKeyboardButton('ᴍᴇᴛᴀᴅᴀᴛᴀ ᴏɴ', callback_data='metadata_1'),
       InlineKeyboardButton('✅', callback_data='metadata_1')
       ],[
       InlineKeyboardButton('Sᴇᴛ Cᴜsᴛᴏᴍ Mᴇᴛᴀᴅᴀᴛᴀ', callback_data='custom_metadata')]]

FALSE = [[InlineKeyboardButton('ᴍᴇᴛᴀᴅᴀᴛᴀ ᴏғғ', callback_data='metadata_0'),
        InlineKeyboardButton('❌', callback_data='metadata_0')
       ],[
       InlineKeyboardButton('Sᴇᴛ Cᴜsᴛᴏᴍ Mᴇᴛᴀᴅᴀᴛᴀ', callback_data='custom_metadata')]]


@Client.on_message(filters.private & filters.command('metadata'))
async def handle_metadata(bot: Client, message: Message):
    RknDev = await message.reply_text("**Please Wait...**", reply_to_message_id=message.id)
    bool_metadata = await digital_botz.get_metadata_mode(message.from_user.id)
    user_metadata = await digital_botz.get_metadata_code(message.from_user.id)

    await RknDev.edit(
        f"Your Current Metadata:-\n\n➜ `{user_metadata}`",
        reply_markup=InlineKeyboardMarkup(TRUE if bool_metadata else FALSE)
    )


@Client.on_callback_query(filters.regex('.*?(custom_metadata|metadata).*?'))
async def query_metadata(bot: Client, query: CallbackQuery):
    data = query.data
    if data.startswith('metadata_'):
        _bool = data.split('_')[1]
        user_metadata = await digital_botz.get_metadata_code(query.from_user.id)
        bool_meta = bool(eval(_bool))
        await digital_botz.set_metadata_mode(query.from_user.id, bool_meta=not bool_meta)
        await query.message.edit(f"Your Current Metadata:-\n\n➜ `{user_metadata}`", reply_markup=InlineKeyboardMarkup(FALSE if bool_meta else TRUE))
           
    elif data == 'custom_metadata':
        await query.message.delete()
        try:
            # Note: bot.ask requires the 'pyromod' library to be installed and initialized
            metadata = await bot.ask(text=rkn.SEND_METADATA, chat_id=query.from_user.id, filters=filters.text, timeout=30, disable_web_page_preview=True)
            RknDev = await query.message.reply_text("**Please Wait...**", reply_to_message_id=metadata.id)
            await digital_botz.set_metadata_code(query.from_user.id, metadata_code=metadata.text)
            await RknDev.edit("**Your Metadata Code Set Successfully ✅**")
        except ListenerTimeout:
            await query.message.reply_text("⚠️ Error!!\n\n**Request timed out.**\nRestart by using /metadata", reply_to_message_id=query.message.id)
        except Exception as e:
            print(e)

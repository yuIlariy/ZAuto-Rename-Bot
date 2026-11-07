# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
"""
Apache License 2.0
Copyright (c) 2025 @Digital_Botz
"""

import re
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from wzgram import Client, filters
from wzgram.enums import ButtonStyle
from wzgram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from wzgram.errors import MessageNotModified
from datetime import datetime
import asyncio
from helper.database import digital_botz

# Track guide message IDs in memory to avoid restricted history scans
custom_format_state = {}

class EnhancedAutoRenamer:
    def __init__(self):
        self.renaming_operations = {} 
        
    def extract_all_info(self, filename: str) -> Dict:
        """Extract all possible information from filename"""
        info = {
            'title': '',
            'year': '',
            'season': '',
            'episode': '',
            'quality': '',
            'source': '',
            'video_codec': '',
            'audio_codec': '',
            'language': '',
            'bit_depth': '',
            'hdr': '',
            'release_group': '',
            'original_name': Path(filename).stem,
            'extension': Path(filename).suffix.lstrip('.')
        }
        
        # Clean filename for parsing
        clean_name = re.sub(r'[_\.\[\]\(\)]', ' ', filename)
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        # 1. Year extraction
        year_match = re.search(r'\b(19[5-9]\d|20[0-2]\d)\b', clean_name)
        if year_match:
            info['year'] = year_match.group(1)
        
        # 2. Season and Episode extraction (Formats multi-episodes as E01&02)
        multi_ep_match = re.search(r'[Ss](\d{1,2})[Ee](\d{1,4})(?:[Ee](\d{1,4}))+', clean_name)
        if multi_ep_match:
            info['season'] = f"S{multi_ep_match.group(1).zfill(2)}"
            # Collect all episode groups matched
            episodes = [group.zfill(2) for group in multi_ep_match.groups()[1:] if group]
            # Format the first episode with 'E', and subsequent ones with '&'
            info['episode'] = f"E{episodes[0]}" + "".join([f"&{ep}" for ep in episodes[1:]])
        else:
            anime_match = re.search(r'[Ss](\d{1,2})\s*-\s*(\d{1,4})', clean_name)
            if anime_match:
                info['season'] = f"S{anime_match.group(1).zfill(2)}"
                info['episode'] = f"E{anime_match.group(2).zfill(2)}"

        if not info['episode']:
            s_e_match = re.search(r'[Ss](\d{1,2})(?:[Ee][Pp]?|\s+[Ee]?[Pp]?)\s*(\d{1,4})', clean_name)
            if s_e_match:
                info['season'] = f"S{s_e_match.group(1).zfill(2)}"
                info['episode'] = f"E{s_e_match.group(2).zfill(2)}"
        
        if not info['season']:
            season_match = re.search(r'[Ss]eason\s*(\d{1,2})', clean_name, re.IGNORECASE)
            episode_match = re.search(r'[Ee]pisode\s*(\d{1,4})', clean_name, re.IGNORECASE)
            if season_match: info['season'] = f"S{season_match.group(1).zfill(2)}"
            if episode_match: info['episode'] = f"E{episode_match.group(1).zfill(2)}"

        if not info['episode']:
            loose_match = re.search(r'(?:\s-|Ep|E|Episode|^)\s*(\d{1,4})(?=\s|$|\.)', clean_name, re.IGNORECASE)
            bracket_match = re.search(r'\[\s*(\d{1,4})\s*\]', filename)

            found_ep = loose_match.group(1) if loose_match else (bracket_match.group(1) if bracket_match else None)
            if found_ep and found_ep != info['year']:
                info['episode'] = f"E{found_ep.zfill(2)}"

        # 4. Quality extraction (Enforces lowercase 'p' and uppercase 'K')
        quality_match = re.search(r'(\d{3,4}[pP]|4[Kk]|UHD|HD|SD|HDRip|WEBRip|BluRay)', clean_name, re.IGNORECASE)
        if quality_match:
            q = quality_match.group(1)
            if re.match(r'\d{3,4}[pP]', q):
                info['quality'] = q.lower()
            elif re.match(r'4[Kk]', q):
                info['quality'] = '4K'
            else:
                info['quality'] = q
        
        # 5. Video codec (Bulletproof literal search)
        codec_match = re.search(r'(x26[456]|h26[456]|hevc|avc|av1|xvid|divx|mpeg|vp[89])', clean_name, re.IGNORECASE)
        if codec_match:
            info['video_codec'] = codec_match.group(1).lower()
        
        # 6. Audio codec
        audio_match = re.search(r'(DD\+?5\.1|DDP?5\.1|DD5\.1|DD2\.0|AAC|AC3|DTS|Opus|E-?AC-?3|FLAC|MP3)', clean_name, re.IGNORECASE)
        if audio_match:
            info['audio_codec'] = audio_match.group(1)
        
        # 7. Language detection
        languages = ['Hindi', 'English', 'Malayalam', 'Tamil', 'Telugu', 'Kannada', 'Dual', 'Multi']
        for lang in languages:
            if re.search(rf'\b{lang}\b', clean_name, re.IGNORECASE):
                info['language'] = lang
                break
        
        # 8. Source type
        sources = ['BluRay', 'WEBRip', 'WEB-DL', 'HDRip', 'DVDRip', 'TVRip', 'AMZN', 'Netflix', 'Hotstar']
        for source in sources:
            if re.search(rf'\b{source}\b', clean_name, re.IGNORECASE):
                info['source'] = source
                break
        
        # 9. Bit depth and HDR
        if '10bit' in clean_name.lower(): info['bit_depth'] = '10bit'
        if 'hdr' in clean_name.lower(): info['hdr'] = 'HDR'
        
        # --- SUBTRACTIVE TITLE EXTRACTION ---
        raw_title = filename
        
        # Remove Extension
        if info['extension']:
            raw_title = re.sub(rf'\.{info["extension"]}$', '', raw_title, flags=re.IGNORECASE)
            
        # Safely remove domains WITHOUT greedy bracket matching
        raw_title = re.sub(r'\[[^\]]*?\.(?:cc|com|net|org|in|me|site)\]', '', raw_title, flags=re.IGNORECASE)
        raw_title = re.sub(r'\b[A-Za-z0-9\-]+\.(?:cc|com|net|org|in|me|site)\b', '', raw_title, flags=re.IGNORECASE)
        raw_title = re.sub(r'@[A-Za-z0-9_]+', '', raw_title)
        
        # Convert delimiters to space for word-boundary subtraction
        raw_title = re.sub(r'[_\.\[\]\(\)]', ' ', raw_title)
        
        # Subtract explicit metadata
        if info['year']:
            raw_title = re.sub(rf'\b{info["year"]}\b', '', raw_title)
            
        if info['season']:
            s_num = info['season'].replace('S', '').lstrip('0') or '0'
            raw_title = re.sub(rf'\b[Ss]eason\s*0*{s_num}\b', '', raw_title, flags=re.IGNORECASE)
            raw_title = re.sub(rf'\b[Ss]0*{s_num}\b', '', raw_title, flags=re.IGNORECASE)
            
        if info['episode']:
            e_num = info['episode'].replace('E', '').lstrip('0') or '0'
            raw_title = re.sub(rf'\b[Ee]pisode\s*0*{e_num}\b', '', raw_title, flags=re.IGNORECASE)
            raw_title = re.sub(rf'\b[Ee][Pp]?0*{e_num}\b', '', raw_title, flags=re.IGNORECASE)
            if info['season']:
                raw_title = re.sub(rf'\b[Ss]0*{s_num}\s*-\s*0*{e_num}\b', '', raw_title, flags=re.IGNORECASE)
                raw_title = re.sub(rf'\b[Ss]0*{s_num}\s*[Ee][Pp]?\s*0*{e_num}\b', '', raw_title, flags=re.IGNORECASE)
            raw_title = re.sub(rf'\b0*{e_num}\b', '', raw_title)

        # Subtract all found tags
        remove_words = [
            info['quality'], info['video_codec'], info['audio_codec'], 
            info['language'], info['source'], info['bit_depth'], info['hdr']
        ]
        
        common_tags = [
            r'\b480[pP]\b', r'\b720[pP]\b', r'\b1080[pP]\b', r'\b2160[pP]\b', r'\b4[Kk]\b', 
            r'\b[Hh][Ee][Vv][Cc]\b', r'\b[Aa][Vv][Cc]\b', r'\b[Xx]264\b', r'\b[Xx]265\b',
            r'\b[Oo]pus\b', r'\b[Ss]ub\b', r'\b[Dd]ual\b', r'\b[Mm]ulti\b',
            r'\b[Ww][Ee][Bb]-?[Dd][Ll]\b', r'\b[Ww][Ee][Bb][Rr]ip\b', r'\b[Bb]lu[Rr]ay\b'
        ]
        
        for tag in common_tags:
            raw_title = re.sub(tag, '', raw_title, flags=re.IGNORECASE)
            
        for word in remove_words:
            if word:
                safe_word = re.escape(word)
                raw_title = re.sub(rf'\b{safe_word}\b', '', raw_title, flags=re.IGNORECASE)

        info['title'] = self._clean_title(raw_title)
        return info
    
    def _clean_title(self, title: str) -> str:
        """Clean and format title"""
        title = re.sub(r'[@#~\[\]\{\}\(\)]', '', title)
        title = re.sub(r'^\s*-\s*', '', title)  # Strip stray hyphen left by subtraction
        title = re.sub(r'\s+', ' ', title)
        return title.strip().title()
    
    def apply_format_template(self, info: Dict, template: str) -> str:
        """Apply user's format template to extracted info"""
        placeholders = {
            '{title}': info.get('title', ''),
            '{year}': info.get('year', ''),
            '{season}': info.get('season', ''),
            '{episode}': info.get('episode', ''),
            '{quality}': info.get('quality', ''),
            '{source}': info.get('source', ''),
            '{video_codec}': info.get('video_codec', ''),
            '{audio_codec}': info.get('audio_codec', ''),
            '{language}': info.get('language', ''),
            '{bit_depth}': info.get('bit_depth', ''),
            '{hdr}': info.get('hdr', ''),
            '{original}': info.get('original_name', ''),
            '{filename}': info.get('original_name', ''),
            '{ext}': info.get('extension', '')
        }
        
        for placeholder, value in placeholders.items():
            template = template.replace(placeholder, value)
        
        template = re.sub(r'\(\s*\)', '', template)
        template = re.sub(r'\[\s*\]', '', template)
        template = re.sub(r'\s+', ' ', template)
        template = template.strip()
        
        return template

@Client.on_message(filters.command(["autorename", "setformat"]))
async def set_format_command(client: Client, message: Message):
    """Set auto rename format template"""
    user_id = message.from_user.id
    
    if len(message.command) > 1:
        format_template = " ".join(message.command[1:])
        await digital_botz.add_user_format_template(user_id, format_template)
        await message.reply_text(f"✅ Format set successfully!\n\n`{format_template}`")
        return
        
    current_format = await digital_botz.get_format_template(user_id)
    reply_text = f"📝 **Your Current Format:**\n`{current_format}`\n\n" if current_format else "❌ No format set yet!\n\n"
    
    reply_text += "**Available Placeholders:**\n"
    placeholders = [
        "`{filename}` - Original File Name.", 
        "`{title}` - Movie/Series title",
        "`{year}` - Release year",
        "`{season}` - Season number (S01)",
        "`{episode}` - Episode number (E01)",
        "`{quality}` - Video quality (1080p, 4K)",
        "`{source}` - Source type (BluRay, WEBRip)",
        "`{video_codec}` - Video codec (x264, x265)",
        "`{audio_codec}` - Audio codec (DD+5.1)",
        "`{language}` - Language (Hindi, English)",
        "`{bit_depth}` - Bit depth (10bit)",
        "`{hdr}` - HDR info",
        "`{ext}` - File extension"
    ]
    
    reply_text += "\n".join(placeholders)
    reply_text += "\n\n**Usage:** `/autorename {title} ({year}) {quality} {language}.{ext}`"
    
    buttons = [
        [InlineKeyboardButton("🎬 Movie Format", callback_data="format_movie", style=ButtonStyle.PRIMARY), InlineKeyboardButton("📺 Series Format", callback_data="format_series", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🎵 Music Format", callback_data="format_music", style=ButtonStyle.SUCCESS), InlineKeyboardButton("📄 Document Format", callback_data="format_doc", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("✍️ Custom Format", callback_data="format_custom", style=ButtonStyle.DANGER)]
    ]
    
    await message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^format_"), group=1)
async def format_callback(client, callback_query):
    try:
        await callback_query.answer("Processing...", show_alert=False)
    except:
        pass

    try:
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        formats = {
            "format_movie": "{title} ({year}) {quality} {source} {video_codec} {language}.{ext}",
            "format_series": "{title} {season}{episode} {quality} {source} {video_codec}.{ext}",
            "format_music": "{title} - {language} ({year}).{ext}",
            "format_doc": "{title} ({quality}).{ext}"
        }
        
        if data in formats:
            await digital_botz.add_user_format_template(user_id, formats[data])
            try:
                await callback_query.message.edit_text(
                    f"✅ Format set to **{data.split('_')[1].title()}**!\n\n`{formats[data]}`"
                )
            except MessageNotModified:
                pass
                
        elif data == "format_custom":
            custom_format_state[user_id] = callback_query.message.id
            await callback_query.message.reply_text(
                "✍️ **Please send your custom format template below:**\n\n"
                "Example: `{title} - {quality} [{language}].{ext}`",
                reply_markup=ForceReply(True)
            )

    except Exception as e:
        print(f"Format Button Error: {e}")
        try:
            await callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)
        except:
            pass

@Client.on_message(filters.reply & filters.text, group=1)
async def save_custom_format(client: Client, message: Message):
    replied_message = message.reply_to_message

    if not replied_message or not replied_message.text:
        return

    if "Please send your custom format template below:" not in replied_message.text:
        return

    format_template = message.text.strip()
    if not format_template:
        return

    try:
        await digital_botz.add_user_format_template(message.from_user.id, format_template)
        
        try:
            await replied_message.delete()
        except:
            pass
            
        guide_msg_id = custom_format_state.pop(message.from_user.id, None)
        if guide_msg_id:
            try:
                await client.delete_messages(message.chat.id, guide_msg_id)
            except:
                pass
                
        await message.reply_text(
            f"✅ Format set to **Custom!**\n\n`{format_template}`"
        )
    except Exception as e:
        print(f"Custom Format Save Error: {e}")
        await message.reply_text(f"❌ Failed to save custom format: {str(e)}")

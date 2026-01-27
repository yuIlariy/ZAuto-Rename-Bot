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
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import asyncio
from helper.database import digital_botz

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
        clean_name = filename.replace('_', ' ').replace('.', ' ')
        
        # 1. Year extraction
        year_match = re.search(r'[\(\[]?(\d{4})[\)\]]?', clean_name)
        if year_match:
            year_val = int(year_match.group(1))
            if 1900 < year_val < 2100:
                info['year'] = str(year_val)
        
        # 2. Season and Episode extraction
        
        # Pattern 1: Strict (S01E01, S1E1)
        s_e_match = re.search(r'[Ss](\d{1,2})\s*[EePp]?(\d{1,4})', clean_name)
        if s_e_match:
            info['season'] = f"S{s_e_match.group(1).zfill(2)}"
            info['episode'] = f"E{s_e_match.group(2).zfill(2)}"
        
        # Pattern 2: Verbose (Season 1 Episode 1)
        if not info['season']:
            season_match = re.search(r'[Ss]eason\s*(\d{1,2})', clean_name, re.IGNORECASE)
            episode_match = re.search(r'[Ee]pisode\s*(\d{1,4})', clean_name, re.IGNORECASE)
            if season_match:
                info['season'] = f"S{season_match.group(1).zfill(2)}"
            if episode_match:
                info['episode'] = f"E{episode_match.group(1).zfill(2)}"

        # Pattern 3: Loose Sequence (Show - 01, Show Ep 01, [01])
        if not info['episode']:
            # Look for hyphens or "Ep" followed by number
            loose_match = re.search(r'(?:\s-|Ep|E|Episode|^)\s*(\d{1,4})(?=\s|$|\.)', clean_name, re.IGNORECASE)
            # Look for brackets
            bracket_match = re.search(r'[\[\(]\s*(\d{1,4})\s*[\]\)]', clean_name)

            found_ep = None
            if loose_match:
                found_ep = loose_match.group(1)
            elif bracket_match:
                found_ep = bracket_match.group(1)
            
            # Validation: Ensure number found isn't the Year
            if found_ep and found_ep != info['year']:
                info['episode'] = f"E{found_ep.zfill(2)}"

        # 3. Title extraction
        title_match = re.search(r'^([A-Za-z0-9\s\.\-\']+?)(?=\s*[\(\[]?\d{4}[\)\]]?|\s*S\d|\s*E\d|\s*\-\s*\d)', filename.replace('.', ' ').replace('_', ' '), re.IGNORECASE)
        if title_match:
            info['title'] = self._clean_title(title_match.group(1))
        else:
            info['title'] = self._clean_title(info['original_name'])
        
        # 4. Quality extraction
        quality_match = re.search(r'(\d{3,4}p|4[Kk]|UHD|HD|SD|HDRip|WEBRip|BluRay)', clean_name, re.IGNORECASE)
        if quality_match:
            info['quality'] = quality_match.group(1).upper()
        
        # 5. Video codec
        codec_match = re.search(r'(x264|x265|HEVC|H\.264|H\.265|AVC)', clean_name, re.IGNORECASE)
        if codec_match:
            info['video_codec'] = codec_match.group(1).lower()
        
        # 6. Audio codec
        audio_match = re.search(r'(DD\+?5\.1|DDP?5\.1|DD5\.1|DD2\.0|AAC|AC3|DTS)', clean_name, re.IGNORECASE)
        if audio_match:
            info['audio_codec'] = audio_match.group(1).upper()
        
        # 7. Language detection
        languages = ['Hindi', 'English', 'Malayalam', 'Tamil', 'Telugu', 'Kannada', 'Dual', 'Multi']
        for lang in languages:
            if re.search(lang, clean_name, re.IGNORECASE):
                info['language'] = lang
                break
        
        # 8. Source type
        sources = ['BluRay', 'WEBRip', 'WEB-DL', 'HDRip', 'DVDRip', 'TVRip', 'AMZN', 'Netflix', 'Hotstar']
        for source in sources:
            if re.search(source, clean_name, re.IGNORECASE):
                info['source'] = source
                break
        
        # 9. Bit depth and HDR
        if '10bit' in clean_name.lower():
            info['bit_depth'] = '10bit'
        if 'hdr' in clean_name.lower():
            info['hdr'] = 'HDR'
        
        return info
    
    def _clean_title(self, title: str) -> str:
        """Clean and format title"""
        title = re.sub(r'[@#~\[\]\{\}\(\)]', '', title)
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
    
    if len(message.command) < 2:
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
            [InlineKeyboardButton("🎬 Movie Format", callback_data="format_movie"), InlineKeyboardButton("📺 Series Format", callback_data="format_series")],
            [InlineKeyboardButton("🎵 Music Format", callback_data="format_music"), InlineKeyboardButton("📄 Document Format", callback_data="format_doc")],
            [InlineKeyboardButton("✍️ Custom Format", callback_data="format_custom")]
        ]
        
        await message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(buttons))
        return
    
    format_template = " ".join(message.command[1:])
    await digital_botz.add_user_format_template(user_id, format_template)
    await message.reply_text(f"✅ Format set successfully!\n\n`{format_template}`")

@Client.on_callback_query(filters.regex(r"^format_"))
async def format_callback(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    formats = {
        "format_movie": "{title} ({year}) {quality} {source} {video_codec} {language}.{ext}",
        "format_series": "{title} {season}{episode} {quality} {source} {video_codec}.{ext}",
        "format_music": "{title} - {language} ({year}).{ext}",
        "format_doc": "{title} ({quality}).{ext}",
        "format_custom": "{title} {quality} {language}.{ext}"
    }
    
    if data in formats:
        await digital_botz.add_user_format_template(user_id, formats[data])
        await callback_query.message.edit_text(f"✅ Format set to **{data.split('_')[1].title()}**!\n\n`{formats[data]}`")
    await callback_query.answer()

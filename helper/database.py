# (c) @RknDeveloperr
# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Special Thanks To (https://github.com/JayMahakal98)
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
Repo Link : https://github.com/DigitalBotz/Digital-Auto-Rename-Bot
License Link : https://github.com/DigitalBotz/Digital-Auto-Rename-Bot/blob/main/LICENSE
"""

# database imports
import motor.motor_asyncio, datetime, pytz, time

# bots imports
from config import Config
from helper.utils import send_log

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.user
        self.stats_col = self.db.stats  # New collection for persistent stats
        
    def new_user(self, id):
        return dict(
            _id=int(id),
            file_id=None,
            caption=None,
            join_date=datetime.date.today().isoformat(),
            format_template="{filename}",           
            is_premium=False,  # Added to support premium count
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.date.max.isoformat(),
                ban_reason=''
            )
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = self.new_user(u.id)
            await self.col.insert_one(user)            
            await send_log(b, u)

    async def is_user_exist(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count
    
    # --- FIXED: Added missing method to prevent crash ---
    async def total_premium_users_count(self):
        count = await self.col.count_documents({'is_premium': True})
        return count
    # --------------------------------------------------

    async def get_all_users(self):
        all_users = self.col.find({})
        return all_users

    async def delete_user(self, user_id):
        await self.col.delete_many({'_id': int(user_id)})

    async def set_thumbnail(self, id, file_id):
        await self.col.update_one({'_id': int(id)}, {'$set': {'file_id': file_id}})

    async def get_thumbnail(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('file_id', None)

    async def set_caption(self, id, caption):
        await self.col.update_one({'_id': int(id)}, {'$set': {'caption': caption}})
        
    async def get_caption(self, id):
        user = await self.col.find_one({'_id': int(id)})
        return user.get('caption', None)

    async def get_user_data(self, id) -> dict:
        user_data = await self.col.find_one({'_id': int(id)})
        return user_data or None
            
    async def remove_ban(self, id):
        ban_status = dict(
            is_banned=False,
            ban_duration=0,
            banned_on=datetime.date.max.isoformat(),
            ban_reason=''
        )
        await self.col.update_one({'_id': int(id)}, {'$set': {'ban_status': ban_status}})

    async def ban_user(self, user_id, ban_duration, ban_reason):
        ban_status = dict(
            is_banned=True,
            ban_duration=ban_duration,
            banned_on=datetime.date.today().isoformat(),
            ban_reason=ban_reason)
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'ban_status': ban_status}})

    async def get_ban_status(self, id):
        default = dict(
            is_banned=False,
            ban_duration=0,
            banned_on=datetime.date.max.isoformat(),
            ban_reason='')
        user = await self.col.find_one({'_id': int(id)})
        return user.get('ban_status', default)

    async def get_all_banned_users(self):
        banned_users = self.col.find({'ban_status.is_banned': True})
        return banned_users
    
    # Rename format template functions
    async def add_user_format_template(self, user_id: int, template: str):
        """Add user's custom rename format template"""
        await self.col.update_one(
            {"_id": int(user_id)},
            {"$set": {"format_template": template}},
            upsert=True
        )

    async def get_format_template(self, user_id: int):
        """Get user's rename format template"""
        user = await self.col.find_one({"_id": int(user_id)})
        return user.get("format_template") if user else None

    # --- NEW: Persistent Bot Status Functions ---
    async def get_bot_stats(self):
        """Get persistent stats (start time, traffic)"""
        stats = await self.stats_col.find_one({'_id': 'bot_stats'})
        if not stats:
            # Initialize if not exists
            stats = {
                '_id': 'bot_stats',
                'start_time': time.time(),
                'total_sent': 0,
                'total_recv': 0
            }
            await self.stats_col.insert_one(stats)
        return stats

    async def update_traffic(self, sent, recv):
        """Update the cumulative traffic in DB"""
        # We assume sent/recv are cumulative from system start, so we just update the record
        # Note: To be perfectly accurate across reboots, we would need to add difference. 
        # For simplicity in this bot structure, we act as a persistent store.
        await self.stats_col.update_one(
            {'_id': 'bot_stats'},
            {'$set': {'last_updated': time.time()}, '$inc': {'total_sent': sent, 'total_recv': recv}},
            upsert=True
        )
    # ---------------------------------------------
    
    
digital_botz = Database(Config.DB_URL, Config.DB_NAME)

# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Update Channel @Digital_Botz & @DigitalBotz_Support

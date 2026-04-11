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
"""

# database imports
import motor.motor_asyncio, datetime, pytz, time

# bots imports
from config import Config

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.user
        self.stats_col = self.db.stats 
        
    def new_user(self, id):
        return dict(
            _id=int(id),
            file_id=None,
            caption=None,
            join_date=datetime.date.today().isoformat(),
            format_template="{filename}",           
            is_premium=False,
            premium_expiry=None,
            daily_upload_bytes=0,
            last_upload_date=datetime.date.today().isoformat(),
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.date.max.isoformat(),
                ban_reason=''
            )
        )

    async def add_user(self, b, m):
        # Import send_log here to avoid circular dependency
        from helper.utils import send_log
        
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
    
    async def total_premium_users_count(self):
        count = await self.col.count_documents({'is_premium': True})
        return count

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

    # Persistent Bot Status Functions
    async def get_bot_stats(self):
        """Get persistent stats (start time, traffic)"""
        stats = await self.stats_col.find_one({'_id': 'bot_stats'})
        if not stats:
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
        await self.stats_col.update_one(
            {'_id': 'bot_stats'},
            {'$set': {'last_updated': time.time()}, '$inc': {'total_sent': sent, 'total_recv': recv}},
            upsert=True
        )

    async def get_network_stats(self):
        """Fetches total aggregated stats formatted for live status callbacks"""
        stats = await self.get_bot_stats()
        return {
            "sent": stats.get("total_sent", 0), 
            "recv": stats.get("total_recv", 0)
        }
        
    async def update_network_stats(self, sent_delta, recv_delta):
        """Alias for update_traffic to ensure full compatibility across files"""
        await self.update_traffic(sent_delta, recv_delta)
        
    # --- PREMIUM & LIMIT FUNCTIONS ---
    async def add_premium(self, user_id: int, days: int):
        """Upgrades a user to premium with an exact time expiry"""
        # Using datetime.now() for precise 24-hour calculations
        expiry_date = datetime.datetime.now() + datetime.timedelta(days=days)
        await self.col.update_one(
            {'_id': int(user_id)}, 
            {'$set': {'is_premium': True, 'premium_expiry': expiry_date.isoformat()}}
        )
        
    async def remove_premium(self, user_id: int):
        """Removes premium status from a user"""
        await self.col.update_one(
            {'_id': int(user_id)}, 
            {'$set': {'is_premium': False, 'premium_expiry': None}}
        )

    async def check_premium(self, user_id: int):
        """Checks if user is premium and if their subscription is still valid"""
        user = await self.col.find_one({'_id': int(user_id)})
        if user and user.get('is_premium', False):
            expiry = user.get('premium_expiry')
            if expiry:
                # Handle exact timestamp parsing with a fallback for old formats
                try:
                    expiry_dt = datetime.datetime.fromisoformat(expiry)
                except ValueError:
                    # Fallback for old "YYYY-MM-DD" entries
                    expiry_dt = datetime.datetime.combine(datetime.date.fromisoformat(expiry), datetime.time.max)

                # Compare exact timestamps
                if datetime.datetime.now() <= expiry_dt:
                    return True
                else:
                    # Subscription expired, remove premium
                    await self.remove_premium(user_id)
                    return False
            return True # Fallback for lifetime/legacy premium
        return False
        
    async def check_daily_limit(self, user_id: int, file_size: int):
        """Checks if free user has exceeded 6GB daily limit. Premium always returns True."""
        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return True
            
        # Check premium using the new time-aware function
        if await self.check_premium(user_id):
            return True
            
        # Limits reset daily at midnight server time, so date.today() is correct here
        today = datetime.date.today().isoformat()
        last_date = user.get('last_upload_date', today)
        daily_bytes = user.get('daily_upload_bytes', 0)
        
        # Reset if it's a new day
        if last_date != today:
            daily_bytes = 0
            
        FREE_LIMIT = 6 * 1024 * 1024 * 1024 # 6GB in bytes
        if daily_bytes + file_size > FREE_LIMIT:
            return False
        return True

    async def update_daily_limit(self, user_id: int, file_size: int):
        """Adds the processed file size to the user's daily limit tracker"""
        user = await self.col.find_one({'_id': int(user_id)})
        if not user:
            return
            
        today = datetime.date.today().isoformat()
        last_date = user.get('last_upload_date', today)
        daily_bytes = user.get('daily_upload_bytes', 0)
        
        # Reset if it's a new day
        if last_date != today:
            daily_bytes = 0
            
        await self.col.update_one(
            {'_id': int(user_id)},
            {'$set': {
                'daily_upload_bytes': daily_bytes + file_size,
                'last_upload_date': today
            }}
        )
    # ---------------------------------
    
digital_botz = Database(Config.DB_URL, Config.DB_NAME)

# Rkn Developer 
# Don't Remove Credit 😔
# Telegram Channel @RknDeveloper & @Rkn_Botz
# Developer @RknDeveloperr
# Update Channel @Digital_Botz & @DigitalBotz_Support

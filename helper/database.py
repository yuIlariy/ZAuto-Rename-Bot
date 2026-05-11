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
"""

# database imports
import datetime, time, pytz
from typing import Optional, List
from pymongo import AsyncMongoClient 
from pydantic import BaseModel, Field
from beanie import Document, init_beanie
from config import Config
from helper.utils import send_log

# ==========================================
# --- BEANIE & PYDANTIC MODELS ---
# ==========================================
class BanStatus(BaseModel):
    is_banned: bool = False
    ban_duration: int = 0
    banned_on: str = Field(default_factory=lambda: datetime.date.max.isoformat())
    ban_reason: str = ""

class User(Document):
    id: int = Field(alias="_id")
    
    # --- LEADERBOARD DATA CACHE ---
    first_name: Optional[str] = None
    username: Optional[str] = None
    lifetime_upload_bytes: int = 0
    # ------------------------------
    
    file_id: Optional[str] = None
    caption: Optional[str] = None
    join_date: str = Field(default_factory=lambda: datetime.date.today().isoformat())
    format_template: str = "{filename}"
    is_premium: bool = False
    premium_expiry: Optional[str] = None
    notified_24h: bool = False  
    daily_upload_bytes: int = 0
    last_upload_date: str = Field(default_factory=lambda: datetime.date.today().isoformat())
    ban_status: BanStatus = Field(default_factory=BanStatus)

    class Settings:
        name = "user"  # Target MongoDB Collection name

class BotStats(Document):
    id: str = Field(default="bot_stats", alias="_id")
    start_time: float = Field(default_factory=time.time)
    total_sent: int = 0
    total_recv: int = 0
    last_updated: float = Field(default_factory=time.time)

    class Settings:
        name = "stats"

class Task(Document):
    user_id: int
    message_id: int
    processing_msg_id: int = 0 # <--- NEW: Tracks the progress bar message ID!
    status: str = "pending"  
    created_at: float = Field(default_factory=time.time)

    class Settings:
        name = "tasks"

# ==========================================
# --- DATABASE WRAPPER CLASS ---
# ==========================================
class Database:
    def __init__(self, uri, database_name):
        self.uri = uri
        self.database_name = database_name
        self._client = None
        self.db = None
        
    async def init_db(self):
        """Must be called during bot startup to initialize Beanie"""
        self._client = AsyncMongoClient(self.uri)
        self.db = self._client[self.database_name]
        # Initialize the Models
        await init_beanie(database=self.db, document_models=[User, BotStats, Task])
        print("✅ Database Layer Initialized via Beanie/Pydantic")

    async def add_user(self, b, m):
        from helper.utils import send_log
        u = m.from_user
        if not await self.is_user_exist(u.id):
            user = User(id=u.id, first_name=u.first_name, username=u.username)
            await user.insert()
            await send_log(b, u)
        else:
            # Update username cache for the leaderboard if they changed it
            user = await User.get(u.id)
            if user and (getattr(user, "first_name", None) != u.first_name or getattr(user, "username", None) != u.username):
                user.first_name = u.first_name
                user.username = u.username
                await user.save()

    async def is_user_exist(self, id: int):
        return await User.get(id) is not None

    async def total_users_count(self):
        return await User.count()
    
    async def total_premium_users_count(self):
        return await User.find(User.is_premium == True).count()

    async def get_all_users(self):
        # We return dicts to preserve backward compatibility with admin_panel loops
        users = await User.find_all().to_list()
        return [user.model_dump(by_alias=True) for user in users]

    async def delete_user(self, user_id: int):
        user = await User.get(user_id)
        if user: await user.delete()

    async def set_thumbnail(self, id: int, file_id: str):
        user = await User.get(id)
        if user:
            user.file_id = file_id
            await user.save()

    async def get_thumbnail(self, id: int):
        user = await User.get(id)
        return user.file_id if user else None

    async def set_caption(self, id: int, caption: str):
        user = await User.get(id)
        if user:
            user.caption = caption
            await user.save()
        
    async def get_caption(self, id: int):
        user = await User.get(id)
        return user.caption if user else None

    async def get_user_data(self, id: int) -> dict:
        user = await User.get(id)
        return user.model_dump(by_alias=True) if user else None
            
    async def remove_ban(self, id: int):
        user = await User.get(id)
        if user:
            user.ban_status = BanStatus()
            await user.save()

    async def ban_user(self, user_id: int, ban_duration: int, ban_reason: str):
        user = await User.get(user_id)
        if user:
            user.ban_status = BanStatus(
                is_banned=True,
                ban_duration=ban_duration,
                banned_on=datetime.datetime.now().isoformat(),
                ban_reason=ban_reason
            )
            await user.save()

    async def get_ban_status(self, id: int):
        user = await User.get(id)
        return user.ban_status.model_dump() if user else BanStatus().model_dump()

    async def get_all_banned_users(self):
        users = await User.find(User.ban_status.is_banned == True).to_list()
        return [user.model_dump(by_alias=True) for user in users]
    
    async def add_user_format_template(self, user_id: int, template: str):
        user = await User.get(user_id)
        if user:
            user.format_template = template
            await user.save()
        else:
            user = User(id=user_id, format_template=template)
            await user.insert()

    async def get_format_template(self, user_id: int):
        user = await User.get(user_id)
        return user.format_template if user else None

    # --- PERSISTENT BOT STATUS FUNCTIONS ---
    async def get_bot_stats(self):
        stats = await BotStats.get("bot_stats")
        if not stats:
            stats = BotStats()
            await stats.insert()
        return stats.model_dump(by_alias=True)

    async def update_traffic(self, sent: int, recv: int):
        stats = await BotStats.get("bot_stats")
        if not stats:
            stats = BotStats()
        stats.total_sent += sent
        stats.total_recv += recv
        stats.last_updated = time.time()
        await stats.save()

    async def get_network_stats(self):
        stats = await self.get_bot_stats()
        return {
            "sent": stats.get("total_sent", 0), 
            "recv": stats.get("total_recv", 0)
        }
        
    async def update_network_stats(self, sent_delta: int, recv_delta: int):
        await self.update_traffic(sent_delta, recv_delta)
        
    # --- PREMIUM & LIMIT FUNCTIONS ---
    async def add_premium(self, user_id: int, days: int):
        user = await User.get(user_id)
        if user:
            user.is_premium = True
            
            # THE LIFETIME FIX: If days is 0, make it permanent!
            if days == 0:
                user.premium_expiry = None
            else:
                expiry = datetime.datetime.now() + datetime.timedelta(days=days)
                user.premium_expiry = expiry.isoformat()
                
            user.notified_24h = False # <--- NEW: Reset the notification flag when renewed
            await user.save()
        
    async def remove_premium(self, user_id: int):
        user = await User.get(user_id)
        if user:
            user.is_premium = False
            user.premium_expiry = None
            user.notified_24h = False
            await user.save()

    async def check_premium(self, user_id: int):
        user = await User.get(user_id)
        if user and user.is_premium:
            if user.premium_expiry:
                try:
                    expiry_dt = datetime.datetime.fromisoformat(user.premium_expiry)
                except ValueError:
                    # Fallback for old "YYYY-MM-DD" entries
                    expiry_dt = datetime.datetime.combine(datetime.date.fromisoformat(user.premium_expiry), datetime.time.max)

                if datetime.datetime.now() <= expiry_dt:
                    return True
                else:
                    # Subscription expired
                    user.is_premium = False
                    user.premium_expiry = None
                    user.notified_24h = False
                    await user.save()
                    return False
            return True 
        return False
        
    async def check_daily_limit(self, user_id: int, file_size: int):
        user = await User.get(user_id)
        if not user: return True
        if await self.check_premium(user_id): return True
            
        tz = pytz.timezone("Africa/Nairobi")
        today = datetime.datetime.now(tz).date().isoformat()
        if user.last_upload_date != today:
            user.daily_upload_bytes = 0
            user.last_upload_date = today
            await user.save()
            
        FREE_LIMIT = 6 * 1024 * 1024 * 1024 
        return (user.daily_upload_bytes + file_size) <= FREE_LIMIT

    async def update_daily_limit(self, user_id: int, file_size: int):
        user = await User.get(user_id)
        if not user: return
            
        tz = pytz.timezone("Africa/Nairobi")
        today = datetime.datetime.now(tz).date().isoformat()
        if user.last_upload_date != today:
            user.daily_upload_bytes = 0
            user.last_upload_date = today
            
        user.daily_upload_bytes += file_size
        
        # --- LEADERBOARD LIFETIME TRACKER ---
        user.lifetime_upload_bytes = getattr(user, "lifetime_upload_bytes", 0) + file_size
        # ------------------------------------
        
        await user.save()

    # ==========================================
    # --- GLOBAL MIDNIGHT RESETTER ---
    # ==========================================
    async def global_daily_reset(self):
        """Wipes the daily_upload_bytes for ALL users instantly at midnight (Kenya Time)."""
        try:
            tz = pytz.timezone("Africa/Nairobi")
            now_kenya = datetime.datetime.now(tz)
            today_str = now_kenya.date().isoformat()

            # Instant wipe using MongoDB atomic updates
            await self.db["user"].update_many(
                {}, 
                {"$set": {"daily_upload_bytes": 0, "last_upload_date": today_str}}
            )
            print("✅ Successfully wiped daily limits for all users.")
        except Exception as e:
            print(f"Error during global daily reset: {e}")

    # ==========================================
    # --- 24-HOUR EXPIRY NOTIFICATION UTILS ---
    # ==========================================
    async def get_expiring_users(self):
        """Fetches users who expire in the next 24 hours and haven't been notified"""
        now = datetime.datetime.now()
        target_time = now + datetime.timedelta(hours=24)
        
        expiring_users = []
        # Find premium users who haven't received their 24h warning yet
        users = await User.find(User.is_premium == True, User.notified_24h == False).to_list()
        
        for user in users:
            if user.premium_expiry:
                try:
                    expiry_dt = datetime.datetime.fromisoformat(user.premium_expiry)
                except ValueError:
                    expiry_dt = datetime.datetime.combine(datetime.date.fromisoformat(user.premium_expiry), datetime.time.max)
                
                # Check if the expiry is within the 24-hour window
                if now < expiry_dt <= target_time:
                    expiring_users.append(user)
                    
        return expiring_users

    async def mark_notified(self, user_id: int):
        """Marks the user so they don't get spammed every hour"""
        user = await User.get(user_id)
        if user:
            user.notified_24h = True
            await user.save()

    # ==========================================
    # --- LEADERBOARD FETCH UTILS ---
    # ==========================================
    async def get_leaderboard(self, lb_type="lifetime", limit=20):
        """Fetches the top users for the leaderboard. lb_type can be 'lifetime' or 'daily'"""
        if lb_type == "lifetime":
            # SELF-HEALING MIGRATION: 
            # If a user's daily limit is higher than lifetime (due to recent update), instantly sync them in DB!
            await self.db["user"].update_many(
                {"$expr": {"$lt": ["$lifetime_upload_bytes", "$daily_upload_bytes"]}},
                [{"$set": {"lifetime_upload_bytes": "$daily_upload_bytes"}}]
            )
            cursor = self.db["user"].find({"lifetime_upload_bytes": {"$gt": 0}}).sort("lifetime_upload_bytes", -1).limit(limit)
        else:
            cursor = self.db["user"].find({"daily_upload_bytes": {"$gt": 0}}).sort("daily_upload_bytes", -1).limit(limit)
        
        return await cursor.to_list(length=limit)

    # ==========================================
    # --- PERSISTENT QUEUE (TASK) FUNCTIONS ---
    # ==========================================
    async def add_task(self, user_id: int, message_id: int, processing_msg_id: int = 0):
        """Adds a message to the persistent MongoDB task queue with the progress message ID"""
        task = Task(user_id=user_id, message_id=message_id, processing_msg_id=processing_msg_id)
        await task.insert()
        return task.id

    async def get_pending_tasks(self, user_id: int):
        """Fetches all tasks that haven't been completed yet (useful on reboot)"""
        tasks = await Task.find(Task.user_id == user_id, Task.status == "pending").sort(+Task.created_at).to_list()
        return tasks

    async def update_task_status(self, task_id, status: str):
        """Update status to 'processing' to prevent duplicate execution"""
        task = await Task.get(task_id)
        if task:
            task.status = status
            await task.save()

    async def delete_task(self, task_id):
        """Removes the task from DB once upload is completely finished"""
        task = await Task.get(task_id)
        if task:
            await task.delete()

    async def clear_user_tasks(self, user_id: int):
        """Emergency clear all stuck tasks for a user"""
        await Task.find(Task.user_id == user_id).delete()

digital_botz = Database(Config.DB_URL, Config.DB_NAME)

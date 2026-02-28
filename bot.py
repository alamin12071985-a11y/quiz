"""
═══════════════════════════════════════════════════════════════
        💎 PREMIUM TELEGRAM QUIZ EARN BOT 💎
        Language: Bengali | Premium UX Design
        Author: Premium Bot Developer
═══════════════════════════════════════════════════════════════
"""

import os
import sqlite3
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    User as TGUser
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ═══════════════════════════════════════════════════════════════
# 📋 CONFIGURATION
# ═══════════════════════════════════════════════════════════════

# Required Config Variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
FORCE_CHANNEL_IDS = os.getenv("FORCE_CHANNEL_IDS", "-1001234567890,-1001234567891")
WITHDRAW_CHANNEL_ID = int(os.getenv("WITHDRAW_CHANNEL_ID", "-1001234567892"))

# Parse Force Channel IDs
FORCE_CHANNELS = [int(ch.strip()) for ch in FORCE_CHANNEL_IDS.split(",") if ch.strip()]

# Bot Settings (Admin can change these)
DEFAULT_SETTINGS = {
    "quiz_reward": 0.05,
    "quiz_cost": 0.02,
    "referral_bonus": 0.10,
    "min_referral": 0,
    "min_withdraw": 10.0,
    "withdraw_fee": 0.0
}

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Conversation States
(
    STATE_WAITING_VERIFY,
    STATE_QUIZ_PLAYING,
    STATE_WITHDRAW_METHOD,
    STATE_WITHDRAW_NUMBER,
    STATE_WITHDRAW_AMOUNT,
    STATE_WITHDRAW_CONFIRM,
    STATE_ADMIN_ADD_CHANNEL,
    STATE_ADMIN_REMOVE_CHANNEL,
    STATE_ADMIN_FIND_USER,
    STATE_ADMIN_ADD_BALANCE,
    STATE_ADMIN_DEDUCT_BALANCE,
    STATE_ADMIN_BROADCAST,
    STATE_ADMIN_SET_MIN_WITHDRAW,
    STATE_ADMIN_SET_WITHDRAW_FEE,
    STATE_ADMIN_SET_REFERRAL_BONUS,
    STATE_ADMIN_SET_MIN_REFERRAL,
    STATE_ADMIN_SET_QUIZ_REWARD,
    STATE_ADMIN_SET_QUIZ_COST
) = range(18)

# ═══════════════════════════════════════════════════════════════
# 🗄️ DATABASE HANDLER
# ═══════════════════════════════════════════════════════════════

class Database:
    """Premium SQLite Database Handler"""
    
    def __init__(self, db_name: str = "quiz_bot.db"):
        self.db_name = db_name
        self.init_database()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Better performance
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    
    def init_database(self):
        """Initialize all database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT,
                balance REAL DEFAULT 0.0,
                referral_count INTEGER DEFAULT 0,
                referred_by INTEGER,
                quiz_played INTEGER DEFAULT 0,
                join_date TEXT NOT NULL,
                is_banned INTEGER DEFAULT 0
            )
        """)
        
        # Channels Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER UNIQUE NOT NULL,
                channel_name TEXT,
                added_date TEXT NOT NULL
            )
        """)
        
        # Quiz Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz (
                quiz_id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                option1 TEXT NOT NULL,
                option2 TEXT NOT NULL,
                option3 TEXT NOT NULL,
                option4 TEXT NOT NULL,
                correct_option INTEGER NOT NULL,
                added_date TEXT NOT NULL
            )
        """)
        
        # User Quiz Answered Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_quiz_answered (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                quiz_id INTEGER NOT NULL,
                answered_date TEXT NOT NULL,
                is_correct INTEGER DEFAULT 0,
                UNIQUE(user_id, quiz_id)
            )
        """)
        
        # Withdraw Requests Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL,
                number TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                request_date TEXT NOT NULL,
                processed_date TEXT
            )
        """)
        
        # Settings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Broadcast Log Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                message_text TEXT,
                sent_count INTEGER DEFAULT 0,
                sent_date TEXT NOT NULL
            )
        """)
        
        # Insert default settings
        for key, value in DEFAULT_SETTINGS.items():
            cursor.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
        
        # Insert default force channels
        for ch_id in FORCE_CHANNELS:
            cursor.execute(
                "INSERT OR IGNORE INTO channels (channel_id, channel_name, added_date) VALUES (?, ?, ?)",
                (ch_id, f"Channel_{ch_id}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully!")
    
    # ═══════════════════════════════════════════════════════════
    # USER METHODS
    # ═══════════════════════════════════════════════════════════
    
    def add_user(self, user_id: int, name: str, username: str = None, referred_by: int = None) -> bool:
        """Add new user to database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO users 
                   (user_id, name, username, referred_by, join_date) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, name, username, referred_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            
            if cursor.rowcount > 0:
                conn.commit()
                return True
            return False
        finally:
            conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user details"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    
    def update_balance(self, user_id: int, amount: float) -> bool:
        """Update user balance (add or deduct)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (amount, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def set_balance(self, user_id: int, amount: float) -> bool:
        """Set exact balance for user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE users SET balance = ? WHERE user_id = ?",
                (amount, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def increment_referral(self, user_id: int) -> bool:
        """Increment referral count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def increment_quiz_played(self, user_id: int) -> bool:
        """Increment quiz played count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE users SET quiz_played = quiz_played + 1 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def get_all_users(self) -> List[Dict]:
        """Get all users"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM users WHERE is_banned = 0")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def get_total_users_count(self) -> int:
        """Get total users count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    def get_top_referrers(self, limit: int = 10) -> List[Dict]:
        """Get top referrers"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT user_id, name, referral_count FROM users 
                   WHERE referral_count > 0 
                   ORDER BY referral_count DESC LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    # ═══════════════════════════════════════════════════════════
    # CHANNEL METHODS
    # ═══════════════════════════════════════════════════════════
    
    def get_channels(self) -> List[Dict]:
        """Get all force channels"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM channels")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def add_channel(self, channel_id: int, channel_name: str = None) -> bool:
        """Add new channel"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO channels (channel_id, channel_name, added_date) VALUES (?, ?, ?)",
                (channel_id, channel_name or f"Channel_{channel_id}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def remove_channel(self, channel_id: int) -> bool:
        """Remove channel"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    # ═══════════════════════════════════════════════════════════
    # QUIZ METHODS
    # ═══════════════════════════════════════════════════════════
    
    def add_quiz(self, question: str, options: List[str], correct: int) -> int:
        """Add new quiz"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO quiz 
                   (question, option1, option2, option3, option4, correct_option, added_date) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (question, options[0], options[1], options[2], options[3], correct, 
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def get_quiz(self, quiz_id: int) -> Optional[Dict]:
        """Get quiz by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM quiz WHERE quiz_id = ?", (quiz_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    
    def get_unanswered_quiz(self, user_id: int) -> Optional[Dict]:
        """Get random unanswered quiz for user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """SELECT * FROM quiz WHERE quiz_id NOT IN 
                   (SELECT quiz_id FROM user_quiz_answered WHERE user_id = ?) 
                   ORDER BY RANDOM() LIMIT 1""",
                (user_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    
    def get_total_quiz_count(self) -> int:
        """Get total quiz count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM quiz")
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    def answer_quiz(self, user_id: int, quiz_id: int, is_correct: bool) -> bool:
        """Mark quiz as answered by user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO user_quiz_answered 
                   (user_id, quiz_id, answered_date, is_correct) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, quiz_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1 if is_correct else 0)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def has_answered_quiz(self, user_id: int, quiz_id: int) -> bool:
        """Check if user has answered quiz"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT 1 FROM user_quiz_answered WHERE user_id = ? AND quiz_id = ?",
                (user_id, quiz_id)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def get_user_correct_answers(self, user_id: int) -> int:
        """Get count of correct answers by user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM user_quiz_answered WHERE user_id = ? AND is_correct = 1",
                (user_id,)
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    # ═══════════════════════════════════════════════════════════
    # WITHDRAW METHODS
    # ═══════════════════════════════════════════════════════════
    
    def create_withdraw_request(self, user_id: int, amount: float, method: str, number: str) -> int:
        """Create withdraw request"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """INSERT INTO withdraw_requests 
                   (user_id, amount, method, number, request_date) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, amount, method, number, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def get_withdraw_requests(self, status: str = "pending") -> List[Dict]:
        """Get withdraw requests by status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM withdraw_requests WHERE status = ? ORDER BY id DESC",
                (status,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def update_withdraw_status(self, request_id: int, status: str) -> bool:
        """Update withdraw request status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "UPDATE withdraw_requests SET status = ?, processed_date = ? WHERE id = ?",
                (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), request_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    # ═══════════════════════════════════════════════════════════
    # SETTINGS METHODS
    # ═══════════════════════════════════════════════════════════
    
    def get_setting(self, key: str) -> str:
        """Get setting value"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else str(DEFAULT_SETTINGS.get(key, "0"))
        finally:
            conn.close()
    
    def update_setting(self, key: str, value: str) -> bool:
        """Update setting value"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            conn.commit()
            return True
        finally:
            conn.close()
    
    # ═══════════════════════════════════════════════════════════
    # BROADCAST METHODS
    # ═══════════════════════════════════════════════════════════
    
    def log_broadcast(self, admin_id: int, message_text: str, sent_count: int) -> bool:
        """Log broadcast"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO broadcast_log (admin_id, message_text, sent_count, sent_date) VALUES (?, ?, ?, ?)",
                (admin_id, message_text, sent_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            return True
        finally:
            conn.close()


# Initialize Database
db = Database()


# ═══════════════════════════════════════════════════════════════
# 🛠️ HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def check_channel_membership(bot, user_id: int, channel_id: int) -> bool:
    """Check if user is member of a channel"""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]
    except Exception as e:
        logger.error(f"Error checking membership for channel {channel_id}: {e}")
        return False


async def check_all_channels_membership(bot, user_id: int) -> Tuple[bool, List[int]]:
    """Check membership for all force channels"""
    channels = db.get_channels()
    not_joined = []
    
    for channel in channels:
        is_member = await check_channel_membership(bot, user_id, channel["channel_id"])
        if not is_member:
            not_joined.append(channel["channel_id"])
    
    return len(not_joined) == 0, not_joined


async def get_channel_invite_link(bot, channel_id: int) -> str:
    """Get channel invite link"""
    try:
        chat = await bot.get_chat(channel_id)
        if chat.invite_link:
            return chat.invite_link
        else:
            link = await bot.create_chat_invite_link(channel_id)
            return link.invite_link
    except Exception as e:
        logger.error(f"Error getting invite link for channel {channel_id}: {e}")
        return f"https://t.me/c/{str(channel_id)[4:]}"


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id == ADMIN_ID


def get_main_menu_keyboard(is_admin_user: bool = False) -> InlineKeyboardMarkup:
    """Get main menu keyboard"""
    buttons = [
        [InlineKeyboardButton("🧠 Play Quiz", callback_data="play_quiz")],
        [InlineKeyboardButton("👥 Refer & Earn", callback_data="refer_earn"),
         InlineKeyboardButton("💰 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")]
    ]
    
    if is_admin_user:
        buttons.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)


def format_balance(amount: float) -> str:
    """Format balance with currency"""
    return f"{amount:.2f}৳"


def escape_markdown(text: str) -> str:
    """Escape markdown special characters"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


# ═══════════════════════════════════════════════════════════════
# 🚀 COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    # Check for referral parameter
    referrer_id = None
    if context.args and len(context.args) > 0:
        try:
            referrer_id = int(context.args[0])
            if referrer_id == user.id:  # Can't refer self
                referrer_id = None
        except ValueError:
            pass
    
    # Check channel membership
    all_joined, not_joined_channels = await check_all_channels_membership(
        context.bot, user.id
    )
    
    if not all_joined:
        # Show force join message
        channels = db.get_channels()
        buttons = []
        
        for channel in channels:
            if channel["channel_id"] in not_joined_channels:
                link = await get_channel_invite_link(context.bot, channel["channel_id"])
                buttons.append([
                    InlineKeyboardButton(
                        f"📢 Join Channel", 
                        url=link
                    )
                ])
        
        buttons.append([
            InlineKeyboardButton("✅ Joined Verify", callback_data="verify_join")
        ])
        
        text = (
            "😏 *এই যে বস\\! আগে আমাদের VIP চ্যানেলগুলো Join করুন, তারপর টাকা কামান\\!*\n\n"
            "🔥 নিচের সব চ্যানেলে Join করে তারপর *✅ Joined Verify* বাটনে ক্লিক করুন\\!"
        )
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return STATE_WAITING_VERIFY
    
    # User has joined all channels
    # Add user to database
    is_new_user = db.add_user(
        user_id=user.id,
        name=user.full_name,
        username=user.username,
        referred_by=referrer_id
    )
    
    if is_new_user and referrer_id:
        # Add referral bonus
        ref_bonus = float(db.get_setting("referral_bonus"))
        db.update_balance(referrer_id, ref_bonus)
        db.increment_referral(referrer_id)
        
        # Notify referrer
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    f"🎉 *বাহ\\! নতুন রেফারেল পেয়েছেন\\!*\n\n"
                    f"💰 Bonus: \\+{format_balance(ref_bonus)}\n"
                    f"👤 New User: {escape_markdown(user.full_name)}"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
    
    # Check if user already exists
    user_data = db.get_user(user.id)
    
    if user_data and user_data.get("is_banned"):
        await update.message.reply_text(
            "🚫 *দুঃখিত\\! আপনাকে এই Bot থেকে Ban করা হয়েছে\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Show welcome message and main menu
    await show_main_menu(update, context, is_new_user)
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, is_new_user: bool = False):
    """Show main menu"""
    user = update.effective_user
    
    if is_new_user:
        text = (
            f"🎊 *স্বাগতম {escape_markdown(user.full_name)}\\!*\n\n"
            "💎 *Premium Quiz Earn Bot* এ আপনাকে স্বাগত\\!\n"
            "🧠 Quiz খেলে টাকা আয় করুন\\!\n"
            "👥 বন্ধুদের Refer করে বোনাস পান\\!\n"
            "💰 Balance Withdraw করুন সহজেই\\!\n\n"
            "🔥 *নিচের Menu থেকে যেকোনো Option বেছে নিন\\!*"
        )
    else:
        text = (
            f"👋 *স্বাগতম আবার, {escape_markdown(user.full_name)}\\!*\n\n"
            "🔥 *Premium Quiz Earn Bot Main Menu*\n\n"
            "🧠 Quiz খেলে টাকা আয় করুন\n"
            "👥 Refer করে Bonus পান\n"
            "💰 Withdraw করুন সহজেই"
        )
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin(user.id))
    )


# ═══════════════════════════════════════════════════════════════
# 📢 FORCE JOIN HANDLER
# ═══════════════════════════════════════════════════════════════

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle verify join button"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer("🔍 যাচাই করা হচ্ছে...")
    
    # Check membership again
    all_joined, not_joined = await check_all_channels_membership(context.bot, user.id)
    
    if not all_joined:
        await query.answer("❌ সব চ্যানেলে Join করেননি!", show_alert=True)
        return STATE_WAITING_VERIFY
    
    # Check for referral parameter stored in context
    referrer_id = context.user_data.get("referrer_id")
    
    # Add user to database
    is_new_user = db.add_user(
        user_id=user.id,
        name=user.full_name,
        username=user.username,
        referred_by=referrer_id
    )
    
    if is_new_user and referrer_id:
        ref_bonus = float(db.get_setting("referral_bonus"))
        db.update_balance(referrer_id, ref_bonus)
        db.increment_referral(referrer_id)
        
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    f"🎉 *বাহ\\! নতুন রেফারেল পেয়েছেন\\!*\n\n"
                    f"💰 Bonus: \\+{format_balance(ref_bonus)}\n"
                    f"👤 New User: {escape_markdown(user.full_name)}"
                ),
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            pass
    
    user_data = db.get_user(user.id)
    if user_data and user_data.get("is_banned"):
        await query.edit_message_text(
            "🚫 *দুঃখিত\\! আপনাকে এই Bot থেকে Ban করা হয়েছে\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Show main menu
    text = (
        f"✅ *ধন্যবাদ চ্যানেলগুলো Join করার জন্য\\!*\n\n"
        f"🎊 *স্বাগতম {escape_markdown(user.full_name)}\\!*\n\n"
        "💎 *Premium Quiz Earn Bot* এ আপনাকে স্বাগত\\!\n"
        "🧠 Quiz খেলে টাকা আয় করুন\\!\n"
        "👥 বন্ধুদের Refer করে বোনাস পান\\!\n"
        "💰 Balance Withdraw করুন সহজেই\\!"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin(user.id))
    )
    
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════
# 🧠 QUIZ HANDLER
# ═══════════════════════════════════════════════════════════════

async def play_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle play quiz button"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer()
    
    # Get user data
    user_data = db.get_user(user.id)
    if not user_data:
        await query.answer("❌ প্রথমে /start করুন!", show_alert=True)
        return
    
    # Check balance for quiz cost
    quiz_cost = float(db.get_setting("quiz_cost"))
    if user_data["balance"] < quiz_cost:
        await query.edit_message_text(
            f"😅 *আরে বস\\! Balance কম আছে\\!*\n\n"
            f"💰 Quiz খেলতে প্রয়োজন: {format_balance(quiz_cost)}\n"
            f"💵 আপনার Balance: {format_balance(user_data['balance'])}\n\n"
            f"👥 Refer করে Balance বাড়ান\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ])
        )
        return
    
    # Get unanswered quiz
    quiz = db.get_unanswered_quiz(user.id)
    
    if not quiz:
        await query.edit_message_text(
            "😅 *আরে বস\\! এই মুহূর্তে নতুন Quiz নেই\\!*\n\n"
            "⏳ অনুগ্রহ করে পরে আবার চেষ্টা করুন\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ])
        )
        return
    
    # Store current quiz in context
    context.user_data["current_quiz"] = quiz["quiz_id"]
    
    # Show quiz
    quiz_reward = float(db.get_setting("quiz_reward"))
    
    text = (
        f"🧠 *Quiz Time\\!*\n\n"
        f"❓ *Question:*\n{escape_markdown(quiz['question'])}\n\n"
        f"💰 Reward: {format_balance(quiz_reward)}\n"
        f"💸 Cost: {format_balance(quiz_cost)}"
    )
    
    buttons = [
        [InlineKeyboardButton(f"1️⃣ {quiz['option1']}", callback_data=f"quiz_ans_1")],
        [InlineKeyboardButton(f"2️⃣ {quiz['option2']}", callback_data=f"quiz_ans_2")],
        [InlineKeyboardButton(f"3️⃣ {quiz['option3']}", callback_data=f"quiz_ans_3")],
        [InlineKeyboardButton(f"4️⃣ {quiz['option4']}", callback_data=f"quiz_ans_4")],
        [InlineKeyboardButton("❌ Skip Quiz", callback_data="skip_quiz")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def quiz_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz answer"""
    query = update.callback_query
    user = query.from_user
    
    # Get answer
    answer = int(query.data.split("_")[-1])
    quiz_id = context.user_data.get("current_quiz")
    
    if not quiz_id:
        await query.answer("❌ Quiz session expired!", show_alert=True)
        return
    
    # Check if already answered (anti-cheat)
    if db.has_answered_quiz(user.id, quiz_id):
        await query.answer("❌ এই Quiz আগেই উত্তর দিয়েছেন!", show_alert=True)
        return
    
    # Get quiz data
    quiz = db.get_quiz(quiz_id)
    if not quiz:
        await query.answer("❌ Quiz not found!", show_alert=True)
        return
    
    # Deduct quiz cost
    quiz_cost = float(db.get_setting("quiz_cost"))
    db.update_balance(user.id, -quiz_cost)
    
    # Check answer
    is_correct = (answer == quiz["correct_option"])
    
    if is_correct:
        # Add reward
        quiz_reward = float(db.get_setting("quiz_reward"))
        db.update_balance(user.id, quiz_reward)
        
        # Mark as answered
        db.answer_quiz(user.id, quiz_id, True)
        db.increment_quiz_played(user.id)
        
        text = (
            f"🔥 *বস\\! একদম আগুন Answer\\!*\n\n"
            f"✅ সঠিক উত্তর দিয়েছেন\\!\n"
            f"💰 Reward: \\+{format_balance(quiz_reward)}\n"
            f"💸 Cost: \\-{format_balance(quiz_cost)}\n"
            f"💵 Net Profit: \\+{format_balance(quiz_reward - quiz_cost)}"
        )
    else:
        # Wrong answer
        db.answer_quiz(user.id, quiz_id, False)
        db.increment_quiz_played(user.id)
        
        correct_option_text = quiz[f"option{quiz['correct_option']}"]
        
        text = (
            f"😆 *আরে বস\\! ভুল করে ফেলছেন\\!*\n\n"
            f"❌ সঠিক উত্তর ছিল: {escape_markdown(correct_option_text)}\n"
            f"💸 Cost: \\-{format_balance(quiz_cost)}\n\n"
            f"💪 আবার চেষ্টা করুন\\!"
        )
    
    buttons = [
        [InlineKeyboardButton("🧠 Play Again", callback_data="play_quiz")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    # Clear current quiz
    context.user_data.pop("current_quiz", None)


async def skip_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle skip quiz button"""
    query = update.callback_query
    await query.answer()
    
    context.user_data.pop("current_quiz", None)
    
    await query.edit_message_text(
        "⏭️ *Quiz Skip করা হয়েছে\\!*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 Play Another Quiz", callback_data="play_quiz")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
        ])
    )


# ═══════════════════════════════════════════════════════════════
# 👥 REFERRAL HANDLER
# ═══════════════════════════════════════════════════════════════

async def refer_earn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refer & earn button"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer()
    
    user_data = db.get_user(user.id)
    if not user_data:
        await query.answer("❌ প্রথমে /start করুন!", show_alert=True)
        return
    
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    
    ref_bonus = float(db.get_setting("referral_bonus"))
    
    # Get top referrers
    top_refs = db.get_top_referrers(10)
    
    text = (
        f"👥 *Refer & Earn*\n\n"
        f"🔗 *Your Referral Link:*\n`{ref_link}`\n\n"
        f"💰 Referral Bonus: {format_balance(ref_bonus)} per refer\n"
        f"📊 Total Referrals: {user_data['referral_count']}\n\n"
        f"📱 এই Link Share করে বন্ধুদের Invite করুন\\!\n"
        f"🎁 প্রতিটি Successful Referral এ Bonus পাবেন\\!"
    )
    
    buttons = [
        [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join this awesome Quiz Earn Bot and earn money!")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def leaderboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    query = update.callback_query
    await query.answer()
    
    top_refs = db.get_top_referrers(10)
    
    if not top_refs:
        text = "🏆 *Leaderboard*\n\nকেউ Refer করেনি\\!"
    else:
        text = "🏆 *Top 10 Referrers*\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        for i, ref in enumerate(top_refs):
            text += (
                f"{medals[i]} *{escape_markdown(ref['name'])}*\n"
                f"   👥 {ref['referral_count']} Referrals\n\n"
            )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="refer_earn")]
        ])
    )


# ═══════════════════════════════════════════════════════════════
# 💰 WITHDRAW HANDLER
# ═══════════════════════════════════════════════════════════════

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw button"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer()
    
    user_data = db.get_user(user.id)
    if not user_data:
        await query.answer("❌ প্রথমে /start করুন!", show_alert=True)
        return STATE_WITHDRAW_METHOD
    
    min_ref = int(db.get_setting("min_referral"))
    
    # Check minimum referral
    if user_data["referral_count"] < min_ref:
        await query.edit_message_text(
            f"😅 *Withdraw করতে আরো Refer দরকার\\!*\n\n"
            f"👥 Minimum Referral: {min_ref}\n"
            f"📊 Your Referrals: {user_data['referral_count']}\n\n"
            f"🔥 আরো {min_ref - user_data['referral_count']} জন Refer করুন\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ])
        )
        return ConversationHandler.END
    
    min_withdraw = float(db.get_setting("min_withdraw"))
    
    # Check minimum balance
    if user_data["balance"] < min_withdraw:
        await query.edit_message_text(
            f"😅 *Balance কম আছে বস\\!*\n\n"
            f"💰 Minimum Withdraw: {format_balance(min_withdraw)}\n"
            f"💵 Your Balance: {format_balance(user_data['balance'])}\n\n"
            f"🧠 Quiz খেলে বা Refer করে Balance বাড়ান\\!",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
            ])
        )
        return ConversationHandler.END
    
    # Show withdraw method selection
    text = (
        f"💰 *Withdraw Money*\n\n"
        f"💵 Available Balance: {format_balance(user_data['balance'])}\n"
        f"📉 Minimum: {format_balance(min_withdraw)}\n\n"
        f"📱 *Payment Method সিলেক্ট করুন:*"
    )
    
    buttons = [
        [InlineKeyboardButton("📱 bKash", callback_data="withdraw_bkash")],
        [InlineKeyboardButton("📱 Nagad", callback_data="withdraw_nagad")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    return STATE_WITHDRAW_METHOD


async def withdraw_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw method selection"""
    query = update.callback_query
    await query.answer()
    
    method = "bKash" if "bkash" in query.data else "Nagad"
    context.user_data["withdraw_method"] = method
    
    await query.edit_message_text(
        f"📱 *{method} Number দিন*\n\n"
        f"✅ Format: 01XXXXXXXXX\n"
        f"📱 Method: {method}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_withdraw")]
        ])
    )
    
    return STATE_WITHDRAW_NUMBER


async def withdraw_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw number input"""
    user = update.effective_user
    number = update.message.text.strip()
    
    # Validate number
    if not number.startswith("01") or len(number) != 11 or not number.isdigit():
        await update.message.reply_text(
            "❌ *Invalid Number\\!*\n\nসঠিক ফরম্যাটে Number দিন:\n`01XXXXXXXXX`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return STATE_WITHDRAW_NUMBER
    
    context.user_data["withdraw_number"] = number
    
    user_data = db.get_user(user.id)
    min_withdraw = float(db.get_setting("min_withdraw"))
    
    await update.message.reply_text(
        f"💰 *Amount লিখুন*\n\n"
        f"💵 Available: {format_balance(user_data['balance'])}\n"
        f"📉 Minimum: {format_balance(min_withdraw)}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_withdraw")]
        ])
    )
    
    return STATE_WITHDRAW_AMOUNT


async def withdraw_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw amount input"""
    user = update.effective_user
    
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid Amount\\!*\n\nসঠিক Amount লিখুন\\!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return STATE_WITHDRAW_AMOUNT
    
    user_data = db.get_user(user.id)
    min_withdraw = float(db.get_setting("min_withdraw"))
    withdraw_fee = float(db.get_setting("withdraw_fee"))
    
    # Validate amount
    if amount < min_withdraw:
        await update.message.reply_text(
            f"❌ *Minimum {format_balance(min_withdraw)} Withdraw করতে হবে\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return STATE_WITHDRAW_AMOUNT
    
    if amount > user_data["balance"]:
        await update.message.reply_text(
            f"❌ *Balance নেই\\!*\n\n"
            f"💵 Your Balance: {format_balance(user_data['balance'])}\n"
            f"💰 Requested: {format_balance(amount)}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return STATE_WITHDRAW_AMOUNT
    
    # Calculate final amount after fee
    final_amount = amount - withdraw_fee
    if final_amount < 0:
        final_amount = amount
    
    context.user_data["withdraw_amount"] = amount
    context.user_data["final_amount"] = final_amount
    
    # Show confirmation
    text = (
        f"💳 *Withdraw Confirmation*\n\n"
        f"💰 Amount: {format_balance(amount)}\n"
        f"💸 Fee: {format_balance(withdraw_fee)}\n"
        f"💵 You'll Get: {format_balance(final_amount)}\n"
        f"📱 Method: {context.user_data['withdraw_method']}\n"
        f"📞 Number: `{context.user_data['withdraw_number']}`"
    )
    
    buttons = [
        [InlineKeyboardButton("✅ Confirm Withdraw", callback_data="confirm_withdraw")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_withdraw")]
    ]
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    return STATE_WITHDRAW_CONFIRM


async def confirm_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirm withdraw"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer()
    
    user_data = db.get_user(user.id)
    amount = context.user_data["withdraw_amount"]
    final_amount = context.user_data["final_amount"]
    method = context.user_data["withdraw_method"]
    number = context.user_data["withdraw_number"]
    
    # Double check balance
    if user_data["balance"] < amount:
        await query.edit_message_text(
            "❌ *Insufficient Balance\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Deduct balance
    db.update_balance(user.id, -amount)
    
    # Create withdraw request
    request_id = db.create_withdraw_request(user.id, final_amount, method, number)
    
    # Notify admin
    admin_text = (
        f"🚨 *New Withdraw Request*\n\n"
        f"🎫 Request ID: `#{request_id}`\n"
        f"👤 Name: {escape_markdown(user.full_name)}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"💰 Amount: {format_balance(final_amount)}\n"
        f"📱 Method: {method}\n"
        f"📞 Number: `{number}`"
    )
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{request_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{request_id}")
                ]
            ])
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")
    
    # Notify withdraw channel
    try:
        await context.bot.send_message(
            chat_id=WITHDRAW_CHANNEL_ID,
            text=admin_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Failed to notify withdraw channel: {e}")
    
    # Clear withdraw data
    context.user_data.pop("withdraw_method", None)
    context.user_data.pop("withdraw_number", None)
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("final_amount", None)
    
    await query.edit_message_text(
        f"✅ *Withdraw Request Submitted\\!*\n\n"
        f"🎫 Request ID: `#{request_id}`\n"
        f"💰 Amount: {format_balance(final_amount)}\n"
        f"📱 Method: {method}\n"
        f"📞 Number: `{number}`\n\n"
        f"⏳ Admin Approval এর জন্য অপেক্ষা করুন\\!",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
        ])
    )
    
    return ConversationHandler.END


async def cancel_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel withdraw"""
    query = update.callback_query
    await query.answer("❌ Withdraw Cancelled")
    
    # Clear withdraw data
    context.user_data.pop("withdraw_method", None)
    context.user_data.pop("withdraw_number", None)
    context.user_data.pop("withdraw_amount", None)
    context.user_data.pop("final_amount", None)
    
    await query.edit_message_text(
        "❌ *Withdraw Cancelled\\!*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
        ])
    )
    
    return ConversationHandler.END


async def approve_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle approve withdraw (admin only)"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    request_id = int(query.data.split("_")[-1])
    
    db.update_withdraw_status(request_id, "approved")
    
    # Get request details
    # Note: You would need to add a method to get withdraw request by ID
    
    await query.answer("✅ Withdraw Approved!")
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approved", callback_data="none")]
        ])
    )


async def reject_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle reject withdraw (admin only)"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    request_id = int(query.data.split("_")[-1])
    
    db.update_withdraw_status(request_id, "rejected")
    
    await query.answer("❌ Withdraw Rejected!")
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Rejected", callback_data="none")]
        ])
    )


# ═══════════════════════════════════════════════════════════════
# 👤 PROFILE HANDLER
# ═══════════════════════════════════════════════════════════════

async def profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profile button"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer()
    
    user_data = db.get_user(user.id)
    if not user_data:
        await query.answer("❌ প্রথমে /start করুন!", show_alert=True)
        return
    
    correct_answers = db.get_user_correct_answers(user.id)
    
    text = (
        f"👤 *Your Profile*\n\n"
        f"🧑 Name: {escape_markdown(user_data['name'])}\n"
        f"🆔 User ID: `{user.id}`\n"
        f"💰 Balance: {format_balance(user_data['balance'])}\n"
        f"👥 Total Referral: {user_data['referral_count']}\n"
        f"🧠 Quiz Played: {user_data['quiz_played']}\n"
        f"✅ Correct Answers: {correct_answers}\n"
        f"📅 Join Date: {user_data['join_date']}"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
        ])
    )


# ═══════════════════════════════════════════════════════════════
# ⚙️ ADMIN PANEL HANDLER
# ═══════════════════════════════════════════════════════════════

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel button"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    # Get current settings
    min_withdraw = float(db.get_setting("min_withdraw"))
    withdraw_fee = float(db.get_setting("withdraw_fee"))
    ref_bonus = float(db.get_setting("referral_bonus"))
    min_ref = int(db.get_setting("min_referral"))
    quiz_reward = float(db.get_setting("quiz_reward"))
    quiz_cost = float(db.get_setting("quiz_cost"))
    total_users = db.get_total_users_count()
    total_quiz = db.get_total_quiz_count()
    
    text = (
        f"⚙️ *Admin Panel*\n\n"
        f"📊 *Statistics:*\n"
        f"👥 Total Users: {total_users}\n"
        f"🧠 Total Quiz: {total_quiz}\n\n"
        f"💵 *Current Settings:*\n"
        f"💰 Min Withdraw: {format_balance(min_withdraw)}\n"
        f"💸 Withdraw Fee: {format_balance(withdraw_fee)}\n"
        f"🎁 Referral Bonus: {format_balance(ref_bonus)}\n"
        f"📊 Min Referral: {min_ref}\n"
        f"🧠 Quiz Reward: {format_balance(quiz_reward)}\n"
        f"💸 Quiz Cost: {format_balance(quiz_cost)}"
    )
    
    buttons = [
        [InlineKeyboardButton("💰 Withdraw Settings", callback_data="admin_withdraw_settings")],
        [InlineKeyboardButton("👥 Referral Settings", callback_data="admin_referral_settings")],
        [InlineKeyboardButton("🧠 Quiz Settings", callback_data="admin_quiz_settings")],
        [InlineKeyboardButton("📢 Channel Management", callback_data="admin_channels")],
        [InlineKeyboardButton("📝 Add Quiz (TXT)", callback_data="admin_add_quiz")],
        [InlineKeyboardButton("👤 User Management", callback_data="admin_user_mgmt")],
        [InlineKeyboardButton("💳 Balance Management", callback_data="admin_balance_mgmt")],
        [InlineKeyboardButton("📡 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_menu")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_withdraw_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw settings"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    min_withdraw = float(db.get_setting("min_withdraw"))
    withdraw_fee = float(db.get_setting("withdraw_fee"))
    
    text = (
        f"💰 *Withdraw Settings*\n\n"
        f"📉 Minimum Withdraw: {format_balance(min_withdraw)}\n"
        f"💸 Withdraw Fee: {format_balance(withdraw_fee)}"
    )
    
    buttons = [
        [InlineKeyboardButton("📉 Set Min Withdraw", callback_data="admin_set_min_withdraw")],
        [InlineKeyboardButton("💸 Set Withdraw Fee", callback_data="admin_set_withdraw_fee")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_set_min_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set minimum withdraw"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "📉 *New Minimum Withdraw Amount লিখুন:*\n\nExample: `10`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_withdraw_settings")]
        ])
    )
    
    return STATE_ADMIN_SET_MIN_WITHDRAW


async def admin_set_min_withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle min withdraw input"""
    try:
        amount = float(update.message.text.strip())
        db.update_setting("min_withdraw", str(amount))
        
        await update.message.reply_text(
            f"✅ *Minimum Withdraw Updated\\!*\n\nNew Value: {format_balance(amount)}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Amount! Please enter a valid number.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_set_withdraw_fee_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set withdraw fee"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "💸 *New Withdraw Fee Amount লিখুন:*\n\nExample: `1`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_withdraw_settings")]
        ])
    )
    
    return STATE_ADMIN_SET_WITHDRAW_FEE


async def admin_set_withdraw_fee_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw fee input"""
    try:
        amount = float(update.message.text.strip())
        db.update_setting("withdraw_fee", str(amount))
        
        await update.message.reply_text(
            f"✅ *Withdraw Fee Updated\\!*\n\nNew Value: {format_balance(amount)}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Amount!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_referral_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle referral settings"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    ref_bonus = float(db.get_setting("referral_bonus"))
    min_ref = int(db.get_setting("min_referral"))
    
    text = (
        f"👥 *Referral Settings*\n\n"
        f"🎁 Referral Bonus: {format_balance(ref_bonus)}\n"
        f"📊 Minimum Referral for Withdraw: {min_ref}"
    )
    
    buttons = [
        [InlineKeyboardButton("🎁 Set Referral Bonus", callback_data="admin_set_ref_bonus")],
        [InlineKeyboardButton("📊 Set Min Referral", callback_data="admin_set_min_ref")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_set_ref_bonus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set referral bonus"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "🎁 *New Referral Bonus Amount লিখুন:*\n\nExample: `0.1`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_referral_settings")]
        ])
    )
    
    return STATE_ADMIN_SET_REFERRAL_BONUS


async def admin_set_ref_bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle referral bonus input"""
    try:
        amount = float(update.message.text.strip())
        db.update_setting("referral_bonus", str(amount))
        
        await update.message.reply_text(
            f"✅ *Referral Bonus Updated\\!*\n\nNew Value: {format_balance(amount)}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Amount!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_set_min_ref_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set minimum referral"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "📊 *Minimum Referral Count লিখুন:*\n\nExample: `5`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_referral_settings")]
        ])
    )
    
    return STATE_ADMIN_SET_MIN_REFERRAL


async def admin_set_min_ref_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle min referral input"""
    try:
        count = int(update.message.text.strip())
        db.update_setting("min_referral", str(count))
        
        await update.message.reply_text(
            f"✅ *Minimum Referral Updated\\!*\n\nNew Value: {count}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Number!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_quiz_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz settings"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    quiz_reward = float(db.get_setting("quiz_reward"))
    quiz_cost = float(db.get_setting("quiz_cost"))
    
    text = (
        f"🧠 *Quiz Settings*\n\n"
        f"💰 Quiz Reward: {format_balance(quiz_reward)}\n"
        f"💸 Quiz Cost: {format_balance(quiz_cost)}"
    )
    
    buttons = [
        [InlineKeyboardButton("💰 Set Quiz Reward", callback_data="admin_set_quiz_reward")],
        [InlineKeyboardButton("💸 Set Quiz Cost", callback_data="admin_set_quiz_cost")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_set_quiz_reward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set quiz reward"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "💰 *New Quiz Reward Amount লিখুন:*\n\nExample: `0.05`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_quiz_settings")]
        ])
    )
    
    return STATE_ADMIN_SET_QUIZ_REWARD


async def admin_set_quiz_reward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz reward input"""
    try:
        amount = float(update.message.text.strip())
        db.update_setting("quiz_reward", str(amount))
        
        await update.message.reply_text(
            f"✅ *Quiz Reward Updated\\!*\n\nNew Value: {format_balance(amount)}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Amount!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_set_quiz_cost_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set quiz cost"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "💸 *New Quiz Cost Amount লিখুন:*\n\nExample: `0.02`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_quiz_settings")]
        ])
    )
    
    return STATE_ADMIN_SET_QUIZ_COST


async def admin_set_quiz_cost_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz cost input"""
    try:
        amount = float(update.message.text.strip())
        db.update_setting("quiz_cost", str(amount))
        
        await update.message.reply_text(
            f"✅ *Quiz Cost Updated\\!*\n\nNew Value: {format_balance(amount)}",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Amount!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel management"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    channels = db.get_channels()
    
    text = "📢 *Channel Management*\n\n"
    
    if channels:
        text += "📋 *Added Channels:*\n"
        for ch in channels:
            text += f"• `{ch['channel_id']}`\n"
    else:
        text += "❌ No channels added!"
    
    buttons = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="admin_add_channel")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data="admin_remove_channel")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add channel"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "➕ *Channel ID লিখুন:*\n\nExample: `-1001234567890`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_channels")]
        ])
    )
    
    return STATE_ADMIN_ADD_CHANNEL


async def admin_add_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add channel input"""
    try:
        channel_id = int(update.message.text.strip())
        
        if db.add_channel(channel_id):
            await update.message.reply_text(
                f"✅ *Channel Added\\!*\n\nID: `{channel_id}`",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                "❌ Channel already exists!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Channel ID!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_remove_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove channel"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "➖ *Channel ID লিখুন যেটি Remove করতে চান:*\n\nExample: `-1001234567890`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_channels")]
        ])
    )
    
    return STATE_ADMIN_REMOVE_CHANNEL


async def admin_remove_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle remove channel input"""
    try:
        channel_id = int(update.message.text.strip())
        
        if db.remove_channel(channel_id):
            await update.message.reply_text(
                f"✅ *Channel Removed\\!*\n\nID: `{channel_id}`",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                "❌ Channel not found!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid Channel ID!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_add_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add quiz via txt file"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    text = (
        "📝 *Quiz Upload করুন*\n\n"
        "📄 TXT File আপলোড করুন\n\n"
        "*Format:*\n"
        "```\n"
        "Question text here?\n"
        "1|Option 1\n"
        "2|Option 2\n"
        "3|Option 3\n"
        "4|Option 4\n"
        "ANS:3\n"
        "---\n"
        "Question 2...\n"
        "```\n\n"
        "📌 Each quiz separated by `---`\n"
        "📌 ANS: এ সঠিক অপশন নম্বর লিখুন (1\\-4)"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
        ])
    )


async def admin_quiz_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz file upload"""
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    document = update.message.document
    if not document or not document.file_name.endswith('.txt'):
        await update.message.reply_text(
            "❌ *Please upload a \\.txt file\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Download file
    file = await document.get_file()
    file_bytes = await file.download_as_bytearray()
    
    content = file_bytes.decode('utf-8')
    
    # Parse quizzes
    quizzes = content.strip().split('---')
    added_count = 0
    
    for quiz_text in quizzes:
        quiz_text = quiz_text.strip()
        if not quiz_text:
            continue
        
        lines = quiz_text.strip().split('\n')
        
        if len(lines) < 6:
            continue
        
        try:
            question = lines[0].strip()
            options = []
            correct = 1
            
            for line in lines[1:]:
                line = line.strip()
                if line.startswith('ANS:'):
                    correct = int(line.split(':')[1].strip())
                elif '|' in line:
                    parts = line.split('|', 1)
                    if len(parts) == 2:
                        options.append(parts[1].strip())
            
            if len(options) == 4 and 1 <= correct <= 4:
                db.add_quiz(question, options, correct)
                added_count += 1
        except Exception as e:
            logger.error(f"Error parsing quiz: {e}")
            continue
    
    await update.message.reply_text(
        f"✅ *Quiz Upload Complete\\!*\n\n"
        f"📝 Added: {added_count} quizzes",
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def admin_user_mgmt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User management"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "👤 *User Management*\n\n"
        "🆔 User ID লিখুন যার তথ্য দেখতে চান:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
        ])
    )
    
    return STATE_ADMIN_FIND_USER


async def admin_find_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Find user by ID"""
    try:
        user_id = int(update.message.text.strip())
        user_data = db.get_user(user_id)
        
        if user_data:
            correct_answers = db.get_user_correct_answers(user_id)
            
            text = (
                f"👤 *User Info*\n\n"
                f"🧑 Name: {escape_markdown(user_data['name'])}\n"
                f"🆔 User ID: `{user_id}`\n"
                f"💰 Balance: {format_balance(user_data['balance'])}\n"
                f"👥 Referrals: {user_data['referral_count']}\n"
                f"🧠 Quiz Played: {user_data['quiz_played']}\n"
                f"✅ Correct: {correct_answers}\n"
                f"📅 Join Date: {user_data['join_date']}"
            )
        else:
            text = "❌ *User not found\\!*"
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID!",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_balance_mgmt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Balance management"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    text = "💳 *Balance Management*\n\nChoose an option:"
    
    buttons = [
        [InlineKeyboardButton("➕ Add Balance", callback_data="admin_add_balance")],
        [InlineKeyboardButton("➖ Deduct Balance", callback_data="admin_deduct_balance")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_add_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add balance"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "➕ *Add Balance*\n\nFormat: `USER_ID AMOUNT`\nExample: `123456789 10`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_balance_mgmt")]
        ])
    )
    
    return STATE_ADMIN_ADD_BALANCE


async def admin_add_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add balance"""
    try:
        parts = update.message.text.strip().split()
        user_id = int(parts[0])
        amount = float(parts[1])
        
        if db.update_balance(user_id, amount):
            await update.message.reply_text(
                f"✅ *Balance Added\\!*\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"💰 Amount: \\+{format_balance(amount)}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                "❌ User not found!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Invalid format! Use: `USER_ID AMOUNT`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_deduct_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deduct balance"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "➖ *Deduct Balance*\n\nFormat: `USER_ID AMOUNT`\nExample: `123456789 5`",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_balance_mgmt")]
        ])
    )
    
    return STATE_ADMIN_DEDUCT_BALANCE


async def admin_deduct_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deduct balance"""
    try:
        parts = update.message.text.strip().split()
        user_id = int(parts[0])
        amount = float(parts[1])
        
        if db.update_balance(user_id, -amount):
            await update.message.reply_text(
                f"✅ *Balance Deducted\\!*\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"💰 Amount: \\-{format_balance(amount)}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                "❌ User not found!",
                parse_mode=ParseMode.MARKDOWN_V2
            )
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Invalid format! Use: `USER_ID AMOUNT`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message"""
    query = update.callback_query
    
    if not is_admin(query.from_user.id):
        await query.answer("❌ Admin Only!", show_alert=True)
        return
    
    await query.answer()
    
    await query.edit_message_text(
        "📡 *Broadcast Message*\n\n"
        "📝 যে Message সব Users কে পাঠাতে চান সেটি লিখুন\\:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin_panel")]
        ])
    )
    
    return STATE_ADMIN_BROADCAST


async def admin_broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast"""
    admin = update.effective_user
    message_text = update.message.text
    
    # Get all users
    users = db.get_all_users()
    total = len(users)
    
    status_msg = await update.message.reply_text(
        f"📡 *Broadcasting\\.\\.\\.*\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Sent: 0\n"
        f"❌ Failed: 0",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    sent = 0
    failed = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=message_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            sent += 1
        except Exception:
            failed += 1
        
        # Update status every 50 messages
        if (sent + failed) % 50 == 0:
            await status_msg.edit_text(
                f"📡 *Broadcasting\\.\\.\\.*\n\n"
                f"👥 Total Users: {total}\n"
                f"✅ Sent: {sent}\n"
                f"❌ Failed: {failed}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        
        # Small delay to avoid rate limit
        await asyncio.sleep(0.05)
    
    # Log broadcast
    db.log_broadcast(admin.id, message_text, sent)
    
    await status_msg.edit_text(
        f"✅ *Broadcast Complete\\!*\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════
# 🔙 BACK TO MENU HANDLER
# ═══════════════════════════════════════════════════════════════

async def back_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to menu button"""
    query = update.callback_query
    user = query.from_user
    
    await query.answer()
    
    user_data = db.get_user(user.id)
    
    if not user_data:
        await query.edit_message_text(
            "❌ *Please /start again\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    text = (
        f"👋 *স্বাগতম আবার, {escape_markdown(user.full_name)}\\!*\n\n"
        f"🔥 *Premium Quiz Earn Bot Main Menu*\n\n"
        f"💰 Balance: {format_balance(user_data['balance'])}\n\n"
        f"🧠 Quiz খেলে টাকা আয় করুন\n"
        f"👥 Refer করে Bonus পান\n"
        f"💰 Withdraw করুন সহজেই"
    )
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin(user.id))
    )


# ═══════════════════════════════════════════════════════════════
# 📂 MAIN APPLICATION SETUP
# ═══════════════════════════════════════════════════════════════

def setup_application() -> Application:
    """Setup and configure the bot application"""
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ═══════════════════════════════════════════════════════════
    # CONVERSATION HANDLERS
    # ═══════════════════════════════════════════════════════════
    
    # Withdraw Conversation Handler
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_callback, pattern="^withdraw$")],
        states={
            STATE_WITHDRAW_METHOD: [
                CallbackQueryHandler(withdraw_method_callback, pattern="^withdraw_")
            ],
            STATE_WITHDRAW_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_number_handler)
            ],
            STATE_WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_handler)
            ],
            STATE_WITHDRAW_CONFIRM: [
                CallbackQueryHandler(confirm_withdraw_callback, pattern="^confirm_withdraw$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_withdraw_callback, pattern="^cancel_withdraw$")
        ],
        per_user=True,
        per_chat=True
    )
    
    # Admin Settings Conversation Handlers
    admin_settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_set_min_withdraw_callback, pattern="^admin_set_min_withdraw$"),
            CallbackQueryHandler(admin_set_withdraw_fee_callback, pattern="^admin_set_withdraw_fee$"),
            CallbackQueryHandler(admin_set_ref_bonus_callback, pattern="^admin_set_ref_bonus$"),
            CallbackQueryHandler(admin_set_min_ref_callback, pattern="^admin_set_min_ref$"),
            CallbackQueryHandler(admin_set_quiz_reward_callback, pattern="^admin_set_quiz_reward$"),
            CallbackQueryHandler(admin_set_quiz_cost_callback, pattern="^admin_set_quiz_cost$"),
            CallbackQueryHandler(admin_add_channel_callback, pattern="^admin_add_channel$"),
            CallbackQueryHandler(admin_remove_channel_callback, pattern="^admin_remove_channel$"),
            CallbackQueryHandler(admin_find_user_handler, pattern="^admin_find_user$"),
            CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$"),
            CallbackQueryHandler(admin_user_mgmt_callback, pattern="^admin_user_mgmt$"),
            CallbackQueryHandler(admin_add_balance_callback, pattern="^admin_add_balance$"),
            CallbackQueryHandler(admin_deduct_balance_callback, pattern="^admin_deduct_balance$")
        ],
        states={
            STATE_ADMIN_SET_MIN_WITHDRAW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_min_withdraw_handler)
            ],
            STATE_ADMIN_SET_WITHDRAW_FEE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_withdraw_fee_handler)
            ],
            STATE_ADMIN_SET_REFERRAL_BONUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_ref_bonus_handler)
            ],
            STATE_ADMIN_SET_MIN_REFERRAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_min_ref_handler)
            ],
            STATE_ADMIN_SET_QUIZ_REWARD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_quiz_reward_handler)
            ],
            STATE_ADMIN_SET_QUIZ_COST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_quiz_cost_handler)
            ],
            STATE_ADMIN_ADD_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_channel_handler)
            ],
            STATE_ADMIN_REMOVE_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_remove_channel_handler)
            ],
            STATE_ADMIN_FIND_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_find_user_handler)
            ],
            STATE_ADMIN_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_handler)
            ],
            STATE_ADMIN_ADD_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_balance_handler)
            ],
            STATE_ADMIN_DEDUCT_BALANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_deduct_balance_handler)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"),
            CallbackQueryHandler(back_menu_callback, pattern="^back_menu$")
        ],
        per_user=True,
        per_chat=True
    )
    
    # ═══════════════════════════════════════════════════════════
    # ADD HANDLERS
    # ═══════════════════════════════════════════════════════════
    
    # Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    
    # Callback Query Handlers
    application.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    application.add_handler(CallbackQueryHandler(play_quiz_callback, pattern="^play_quiz$"))
    application.add_handler(CallbackQueryHandler(quiz_answer_callback, pattern="^quiz_ans_"))
    application.add_handler(CallbackQueryHandler(skip_quiz_callback, pattern="^skip_quiz$"))
    application.add_handler(CallbackQueryHandler(refer_earn_callback, pattern="^refer_earn$"))
    application.add_handler(CallbackQueryHandler(leaderboard_callback, pattern="^leaderboard$"))
    application.add_handler(CallbackQueryHandler(profile_callback, pattern="^profile$"))
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_withdraw_settings_callback, pattern="^admin_withdraw_settings$"))
    application.add_handler(CallbackQueryHandler(admin_referral_settings_callback, pattern="^admin_referral_settings$"))
    application.add_handler(CallbackQueryHandler(admin_quiz_settings_callback, pattern="^admin_quiz_settings$"))
    application.add_handler(CallbackQueryHandler(admin_channels_callback, pattern="^admin_channels$"))
    application.add_handler(CallbackQueryHandler(admin_add_quiz_callback, pattern="^admin_add_quiz$"))
    application.add_handler(CallbackQueryHandler(admin_balance_mgmt_callback, pattern="^admin_balance_mgmt$"))
    application.add_handler(CallbackQueryHandler(back_menu_callback, pattern="^back_menu$"))
    application.add_handler(CallbackQueryHandler(approve_withdraw_callback, pattern="^approve_withdraw_"))
    application.add_handler(CallbackQueryHandler(reject_withdraw_callback, pattern="^reject_withdraw_"))
    
    # Conversation Handlers
    application.add_handler(withdraw_conv)
    application.add_handler(admin_settings_conv)
    
    # Message Handler for Quiz File Upload
    application.add_handler(MessageHandler(filters.Document.TXT, admin_quiz_file_handler))
    
    return application


async def post_init(application: Application):
    """Post initialization setup"""
    # Set bot commands
    commands = [
        BotCommand("start", "🚀 Start the bot")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Bot commands set!")


# ═══════════════════════════════════════════════════════════════
# 🚀 MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    """Main entry point"""
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║         💎 PREMIUM TELEGRAM QUIZ EARN BOT 💎              ║
    ║                                                           ║
    ║         🇧🇩 Bengali Language | Premium UX                  ║
    ║         📊 SQLite Database | High Performance             ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Setup application
    application = setup_application()
    application.post_init = post_init
    
    # Run bot
    logger.info("🤖 Bot starting...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

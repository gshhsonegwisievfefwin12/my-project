import json
import os
import re
import time
import pyotp
import asyncio
from datetime import datetime, timedelta

API_TOKEN = '7821963799:AAHrCqKgJq-d8GinupjT8-yrBWyuiVqq2Lk'  
ADMIN_IDS = [6920696519, 7025982706]  
GROUP_ID = -1002427238294  
REPORT_GROUP_ID = -1003003696948  

WEBHOOK_PORT = 8080
WEBHOOK_HOST = '0.0.0.0'
WEBHOOK_ENDPOINT = '/aroshi/arosh'
WEBHOOK_URL = f'https://your-domain.com:8080/aroshi/arosh'

DB_FILE = 'database.json'
SESSIONS_FILE = 'sessions.json'
USERS_FILE = 'users.json'
TWO_FA_FILE = '2fa_secrets.json'
BALANCES_FILE = 'balances.json'
NAMES_FILE = 'names_database.json'
USER_ACTIVITY_FILE = 'user_activity.json'  
REFERRAL_FILE = 'referrals.json'  

REQUIRED_CHANNELS = [
    {"name": "Official Channel", "id": -1002844626822, "url": "https://t.me/Digital_marketing_Top_1"},
    {"name": "Official Group", "id": -1002715416273, "url": "https://t.me/Digital_marketing_Top"},
    {"name": "Number Channel", "id": -1003192780609, "url": "https://t.me/New_Number_Chanel"},
    {"name": "OTP Group", "id": -1002427238294, "url": "https://t.me/otpgroup_all"}
]

MENU_BUTTONS = [
    "📱 Get Number", "🅾️ Get OTP", "🔐 Get 2FA", "👤 Get Name",
    "📞 Support", "⚙️ Admin Panel", "➖ Remove Numbers",
    "👥 View Users", "📢 Broadcast", "📊 Inventory", "🔙 Back to User Menu",
    "💰 My Account", "💰 Add Balance", "💰 Remove Balance",
    "🗑 Remove Names", "📋 User Report", "🔗 Invite Friends", "🔗 Referral Settings"
]

db_lock = asyncio.Lock()

async def load_json(filename):
    """Load JSON file with error handling"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, (dict, list)) else ({} if filename != USERS_FILE else [])
        except: 
            return {} if filename != USERS_FILE else []
    return {} if filename != USERS_FILE else []

async def save_json(filename, data):
    """Save JSON file with thread safety"""
    async with db_lock:
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving {filename}: {e}")

async def add_user_to_db(chat_id):
    """Add new user to database"""
    users = await load_json(USERS_FILE)
    if not isinstance(users, list): 
        users = []
    if chat_id not in users:
        users.append(chat_id)
        await save_json(USERS_FILE, users)

async def add_balance(chat_id, amount):
    """Add or subtract balance from user account"""
    balances = await load_json(BALANCES_FILE)
    str_id = str(chat_id)
    current = balances.get(str_id, 0.0)
    balances[str_id] = current + float(amount)
    await save_json(BALANCES_FILE, balances)

async def get_balance(chat_id):
    """Get user balance"""
    balances = await load_json(BALANCES_FILE)
    return balances.get(str(chat_id), 0.0)

def escape_md(text):
    """Escape markdown special characters"""
    if not text: 
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(text))

def mask_number(number):
    """Mask phone number for privacy"""
    num_str = str(number).strip().replace("+", "")
    if len(num_str) > 8:
        return f"{num_str[:5]}***{num_str[-3:]}"
    return num_str

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS

async def get_stocks_text():
    """Get available services stock information"""
    db = await load_json(DB_FILE)
    if not db:
        return "🚫 No services currently available."
    text = "📊 *Available Services:*\n\n"
    has_stock = False
    for service, countries in db.items():
        if isinstance(countries, dict):
            text += f"🌐 *{service}:*\n"
            for country, details in countries.items():
                count = len(details.get('numbers', []))
                price = details.get('price', 0)
                if count > 0:
                    text += f"  🔹 {country} (Price: ৳{price})\n"
                    has_stock = True
            text += "\n"
    if not has_stock:
        return "🚫 No active services available."
    return text

def generate_2fa_secret():
    """Generate 2FA secret key"""
    return pyotp.random_base32()

def sanitize_secret(text):
    """Sanitize 2FA secret"""
    sanitized = ''.join(c for c in text.upper() if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567' or c.isdigit())
    return sanitized if sanitized else text.upper().replace(' ', '')

def get_2fa_code_from_input(user_input):
    """Generate 2FA code from user input"""
    try:
        cleaned_input = user_input.upper().replace(' ', '').strip()
        try:
            totp = pyotp.TOTP(cleaned_input)
            return totp.now(), cleaned_input
        except: 
            pass
        sanitized = sanitize_secret(cleaned_input)
        try:
            totp = pyotp.TOTP(sanitized)
            return totp.now(), sanitized
        except: 
            pass
        padded = sanitized + 'A' * (32 - len(sanitized)) if len(sanitized) < 32 else sanitized[:32]
        totp = pyotp.TOTP(padded)
        return totp.now(), padded
    except:
        return None, None

def get_2fa_remaining_seconds():
    """Get remaining seconds for 2FA code"""
    return 30 - (int(time.time()) % 30)

async def save_2fa_secret(chat_id, secret):
    """Save 2FA secret for user"""
    secrets = await load_json(TWO_FA_FILE)
    secrets[str(chat_id)] = secret
    await save_json(TWO_FA_FILE, secrets)

async def log_user_activity(user_id, activity_type, details=None):
    """Log user activity for analytics"""
    activity_log = await load_json(USER_ACTIVITY_FILE)
    
    if not isinstance(activity_log, dict):
        activity_log = {}
    
    str_user_id = str(user_id)
    if str_user_id not in activity_log:
        activity_log[str_user_id] = []
    
    activity_entry = {
        "type": activity_type,
        "timestamp": datetime.now().isoformat(),
        "details": details
    }
    
    activity_log[str_user_id].append(activity_entry)
    await save_json(USER_ACTIVITY_FILE, activity_log)

async def get_user_activity_count(user_id, activity_type, days=0):
    """Get user activity count for specific days"""
    activity_log = await load_json(USER_ACTIVITY_FILE)
    str_user_id = str(user_id)
    
    if str_user_id not in activity_log:
        return 0
    
    if days == 0:  
        today = datetime.now().date()
        count = sum(1 for log in activity_log[str_user_id] 
                   if log.get('type') == activity_type 
                   and datetime.fromisoformat(log.get('timestamp', '')).date() == today)
    else:  
        start_date = (datetime.now() - timedelta(days=days)).date()
        count = sum(1 for log in activity_log[str_user_id] 
                   if log.get('type') == activity_type 
                   and datetime.fromisoformat(log.get('timestamp', '')).date() >= start_date)
    
    return count

async def get_user_details_for_report(user_id):
    """Get comprehensive user details for report"""
    balance = await get_balance(user_id)
    
    try:
        from aiogram import Bot
        from utils import API_TOKEN
        bot = Bot(token=API_TOKEN)
        chat = await bot.get_chat(user_id)
        username = chat.username or "N/A"
        first_name = chat.first_name or "User"
    except:
        username = "N/A"
        first_name = "User"
    
    today_numbers = await get_user_activity_count(user_id, "number_received", 0)
    today_sms = await get_user_activity_count(user_id, "sms_received", 0)
    
    two_days_numbers = await get_user_activity_count(user_id, "number_received", 2)
    two_days_sms = await get_user_activity_count(user_id, "sms_received", 2)
    
    return {
        "user_id": user_id,
        "name": first_name,
        "username": username,
        "balance": balance,
        "today_numbers": today_numbers,
        "today_sms": today_sms,
        "two_days_numbers": two_days_numbers,
        "two_days_sms": two_days_sms
    }

async def format_user_report(user_details):
    """Format user details into beautiful report format"""
    report_text = (
        "╔════════════════════════════════╗\n"
        "║      👤 USER DETAILS 👤       ║\n"
        "╚════════════════════════════════╝\n\n"
        f"👤 Name : `{user_details['name']}`\n"
        f"🆔 User ID : `{user_details['user_id']}`\n"
        f"🏧 Balance : `৳{user_details['balance']}`\n"
        f"🖇️ Username : `@{user_details['username']}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 TODAY LIST 🟢\n"
        f"📱 Numbers : `{user_details['today_numbers']}`\n"
        f"📬 Received SMS : `{user_details['today_sms']}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🟢 LAST 2 DAYS LIST 🟢\n"
        f"📱 Numbers : `{user_details['two_days_numbers']}`\n"
        f"📬 Received SMS : `{user_details['two_days_sms']}`\n\n"
        "╔════════════════════════════════╗\n"
        f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "╚════════════════════════════════╝"
    )
    
    return report_text

async def init_names_file():
    """Initialize names database file"""
    if not os.path.exists(NAMES_FILE):
        await save_json(NAMES_FILE, {})

async def add_names_to_country(country, names_list):
    """Add names to a specific country"""
    await init_names_file()
    names_db = await load_json(NAMES_FILE)
    
    if country not in names_db:
        names_db[country] = []
    
    for name in names_list:
        name = name.strip()
        if name and name not in names_db[country]:
            names_db[country].append(name)
    
    await save_json(NAMES_FILE, names_db)

async def get_name_from_country(country):
    """Get a name from specific country"""
    await init_names_file()
    names_db = await load_json(NAMES_FILE)
    
    if country in names_db and names_db[country]:
        name = names_db[country].pop(0)
        await save_json(NAMES_FILE, names_db)
        return name
    
    return None

async def get_available_name_countries():
    """Get all countries that have names available"""
    await init_names_file()
    names_db = await load_json(NAMES_FILE)
    
    return {country: names for country, names in names_db.items() if names}

async def remove_all_names_for_country(country):
    """Remove all names for a specific country"""
    await init_names_file()
    names_db = await load_json(NAMES_FILE)
    
    if country in names_db:
        del names_db[country]
        await save_json(NAMES_FILE, names_db)

async def get_names_stats():
    """Get statistics about available names"""
    await init_names_file()
    names_db = await load_json(NAMES_FILE)
    
    stats = {}
    for country, names in names_db.items():
        stats[country] = len(names)
    
    return stats

async def init_referrals_file():
    """Initialize referrals file with default structure"""
    if not os.path.exists(REFERRAL_FILE):
        default = {
            "settings": {"amount": 0},
            "pending": {},
            "referred": {},
            "refs": {}
        }
        await save_json(REFERRAL_FILE, default)

async def set_referral_amount(amount):
    """Set amount rewarded per referral"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    referrals_data = referrals if isinstance(referrals, dict) else {}
    referrals_data.setdefault("settings", {})["amount"] = float(amount)
    await save_json(REFERRAL_FILE, referrals_data)

async def get_referral_amount():
    """Get current referral amount"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    try:
        return float(referrals.get("settings", {}).get("amount", 0))
    except:
        return 0.0

async def clear_referral_amount():
    """Clear the referral amount (set to 0)"""
    await set_referral_amount(0)

async def has_been_referred(user_id):
    """Check if this user was already referred (finalized)"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    return str(user_id) in referrals.get("referred", {})

async def add_pending_referral(referrer_id, referred_id):
    """Add a pending referral mapping."""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    pending = referrals.get("pending", {})
    referred = referrals.get("referred", {})

    ref_str = str(referrer_id)
    r_str = str(referred_id)

    if referrer_id == referred_id:
        return False

    if r_str in referred:
        return False

    if r_str in pending:
        return False

    pending[r_str] = ref_str
    referrals["pending"] = pending
    await save_json(REFERRAL_FILE, referrals)
    return True

async def pop_pending_referral(referred_id):
    """Remove and return pending referrer for a referred_id"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    pending = referrals.get("pending", {})
    r_str = str(referred_id)
    ref_str = pending.pop(r_str, None)
    referrals["pending"] = pending
    await save_json(REFERRAL_FILE, referrals)
    return int(ref_str) if ref_str else None

async def get_pending_referrer(referred_id):
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    pending = referrals.get("pending", {})
    ref = pending.get(str(referred_id))
    return int(ref) if ref else None

async def get_referrer_of(referred_id):
    """Return final referrer id (if finalized), else None"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    referred = referrals.get("referred", {})
    ref = referred.get(str(referred_id))
    return int(ref) if ref else None

async def finalize_pending_referral(referred_id):
    """Finalize a pending referral for referred_id"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    pending = referrals.get("pending", {})
    referred = referrals.get("referred", {})
    refs_map = referrals.get("refs", {})

    r_str = str(referred_id)

    if r_str in referred:
        return False, 0.0

    ref_str = pending.pop(r_str, None)
    if not ref_str:
        return False, 0.0

    if ref_str == r_str:
        referrals["pending"] = pending
        await save_json(REFERRAL_FILE, referrals)
        return False, 0.0

    referred[r_str] = ref_str
    refs_map.setdefault(ref_str, [])
    if r_str not in refs_map[ref_str]:
        refs_map[ref_str].append(r_str)

    referrals["pending"] = pending
    referrals["referred"] = referred
    referrals["refs"] = refs_map

    amount = float(referrals.get("settings", {}).get("amount", 0))
    if amount > 0:
        try:
            await add_balance(int(ref_str), amount)
            await log_user_activity(int(ref_str), "referral_earned", {"referred_user": int(r_str), "amount": amount})
            await log_user_activity(int(r_str), "referred_by", {"referrer": int(ref_str)})
        except Exception as e:
            print(f"Error applying referral reward: {e}")

    await save_json(REFERRAL_FILE, referrals)
    return True, amount

async def get_referral_count(referrer_id):
    """Return how many users this referrer has referred"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    refs = referrals.get("refs", {})
    return len(refs.get(str(referrer_id), []))

async def record_referral(referrer_id, referred_id):
    """Backwards-compatible alias to finalize immediately"""
    added = await add_pending_referral(referrer_id, referred_id)
    if added:
        return False, 0.0
    return await finalize_pending_referral(referred_id)

async def get_referral_overview(referrer_id):
    """Return dict with count, list and total earned"""
    await init_referrals_file()
    referrals = await load_json(REFERRAL_FILE)
    refs_map = referrals.get("refs", {})
    ref_list = refs_map.get(str(referrer_id), [])
    amount_per = float(referrals.get("settings", {}).get("amount", 0))
    total_earned = amount_per * len(ref_list)
    return {
        "count": len(ref_list),
        "referrals": [int(x) for x in ref_list],
        "amount_per": amount_per,
        "total_earned": total_earned
    }
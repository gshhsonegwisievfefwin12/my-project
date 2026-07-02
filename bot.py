import io
import time
import asyncio
import socket
import json
import logging
import re
import urllib.parse
import sys
from datetime import datetime
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, Filter, Command
from aiogram.client.default import DefaultBotProperties
from utils import *
import vultex

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()
router = Router()
dp.include_router(router)

BOT_NAME = "Bot"
BOT_USERNAME = None  
WITHDRAWAL_GROUP_ID = -1003788034255

processed_otps = set()

def clean_phone_number(number: str) -> str:
    number = str(number).replace("\\", "").replace(" ", "").replace("\n", "").strip()
    return number

# 🟢 নতুন পাওয়ারফুল OTP এক্সট্রাক্টর (WhatsApp এর ড্যাশ সাপোর্ট সহ)
def extract_otp_from_message(message: str) -> str:
    message = str(message).strip()
    if not message:
        return "No OTP"
        
    # 1. WhatsApp style with dash (e.g., 749-990)
    dash_match = re.search(r'\b\d{3}-\d{3}\b', message)
    if dash_match:
        return dash_match.group(0).strip()
        
    # 2. Google style (e.g., G-123456)
    g_match = re.search(r'\bG-\d{4,8}\b', message)
    if g_match:
        return g_match.group(0).strip()
        
    # 3. Explicit code mentions like "code: 1234"
    keyword_patterns = [
        r'(?i)code[:\s]+(\d{4,8})',
        r'(?i)otp[:\s]+(\d{4,8})',
        r'(?i)verification code[:\s]+(\d{4,8})'
    ]
    for pattern in keyword_patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
            
    # 4. Spaced 6-digit codes (e.g., 123 456)
    space_match = re.search(r'\b(\d{3})\s+(\d{3})\b', message)
    if space_match:
        return f"{space_match.group(1)}{space_match.group(2)}"
        
    # 5. Hashtag format
    hash_match = re.search(r'#\s*(\d{4,8})', message)
    if hash_match:
        return hash_match.group(1).strip()
        
    # 6. Any standalone 4-8 digit number
    general_match = re.search(r'\b\d{4,8}\b', message)
    if general_match:
        return general_match.group(0).strip()
        
    return "No OTP"

def get_service_from_msg(msg: str) -> str:
    msg_lower = msg.lower()
    if "whatsapp" in msg_lower or "wa.me" in msg_lower: return "WhatsApp"
    if "instagram" in msg_lower or "ig" in msg_lower: return "Instagram"
    if "facebook" in msg_lower or "fb" in msg_lower: return "Facebook"
    if "telegram" in msg_lower: return "Telegram"
    if "tiktok" in msg_lower: return "TikTok"
    if "google" in msg_lower or "g-" in msg_lower: return "Google"
    return "Unknown"

COUNTRY_MAP = {
    "Bangladesh": {"flag": "🇧🇩", "code": "BD", "prefixes": ["880", "+880"]},
    "Myanmar": {"flag": "🇲🇲", "code": "MM", "prefixes": ["95", "+95"]},
    "Peru": {"flag": "🇵🇪", "code": "PE", "prefixes": ["51", "+51"]},
    "Madagascar": {"flag": "🇲🇬", "code": "MG", "prefixes": ["261", "+261"]},
    "Liberia": {"flag": "🇱🇷", "code": "LR", "prefixes": ["231", "+231"]},
    "Ukraine": {"flag": "🇺🇦", "code": "UA", "prefixes": ["380", "+380"]},
    "Ethiopia": {"flag": "🇪🇹", "code": "ET", "prefixes": ["251", "+251"]},
    "Kuwait": {"flag": "🇰🇼", "code": "KW", "prefixes": ["965", "+965"]},
    "Zambia": {"flag": "🇿🇲", "code": "ZM", "prefixes": ["260", "+260"]},
    "Sudan": {"flag": "🇸🇩", "code": "SD", "prefixes": ["249", "+249"]},
    "Afghanistan": {"flag": "🇦🇫", "code": "AF", "prefixes": ["93", "+93"]},
    "Uzbekistan": {"flag": "🇺🇿", "code": "UZ", "prefixes": ["998", "+998"]},
    "Venezuela": {"flag": "🇻🇪", "code": "VE", "prefixes": ["58", "+58"]},
    "Tanzania": {"flag": "🇹🇿", "code": "TZ", "prefixes": ["255", "+255"]},
    "Malaysia": {"flag": "🇲🇾", "code": "MY", "prefixes": ["60", "+60"]},
    "Ivory Coast": {"flag": "🇨🇮", "code": "CI", "prefixes": ["225", "+225"]},
    "Tunisia": {"flag": "🇹🇳", "code": "TN", "prefixes": ["216", "+216"]},
    "Ghana": {"flag": "🇬🇭", "code": "GH", "prefixes": ["233", "+233"]},
    "Guinea": {"flag": "🇬🇳", "code": "GN", "prefixes": ["224", "+224"]},
    "Guinea-Bissau": {"flag": "🇬🇼", "code": "GW", "prefixes": ["245", "+245"]},
    "Mali": {"flag": "🇲🇱", "code": "ML", "prefixes": ["223", "+223"]},
    "Lebanon": {"flag": "🇱🇧", "code": "LB", "prefixes": ["961", "+961"]},
    "Oman": {"flag": "🇴🇲", "code": "OM", "prefixes": ["968", "+968"]},
    "Syria": {"flag": "🇸🇾", "code": "SY", "prefixes": ["963", "+963"]},
    "Israel": {"flag": "🇮🇱", "code": "IL", "prefixes": ["972", "+972"]},
    "Ecuador": {"flag": "🇪🇨", "code": "EC", "prefixes": ["593", "+593"]},
    "Zimbabwe": {"flag": "🇿🇼", "code": "ZW", "prefixes": ["263", "+263"]},
    "Central African Republic": {"flag": "🇨🇫", "code": "CF", "prefixes": ["236", "+236"]},
    "Nigeria": {"flag": "🇳🇬", "code": "NG", "prefixes": ["234", "+234"]},
    "South Africa": {"flag": "🇿🇦", "code": "ZA", "prefixes": ["27", "+27"]},
    "Egypt": {"flag": "🇪🇬", "code": "EG", "prefixes": ["20", "+20"]},
    "Kenya": {"flag": "🇰🇪", "code": "KE", "prefixes": ["254", "+254"]},
    "Morocco": {"flag": "🇲🇦", "code": "MA", "prefixes": ["212", "+212"]},
}

def detect_country_from_number(phone_number: str):
    clean_number = clean_phone_number(phone_number).replace("+", "").strip()
    for country, info in sorted(COUNTRY_MAP.items(), key=lambda x: max(len(p.replace("+", "")) for p in x[1]["prefixes"]), reverse=True):
        for prefix in info["prefixes"]:
            prefix_clean = prefix.replace("+", "")
            if clean_number.startswith(prefix_clean):
                return country, info
    return "Unknown", {"flag": "🌍", "code": "UN"}

def capitalize_service_name(service: str) -> str:
    return ' '.join(word.capitalize() for word in service.split())

class AdminAdd(StatesGroup):
    service = State()
    price = State()
    country = State()
    temp_nums = State()

class VIPAddCustomRule(StatesGroup):
    country = State()
    prefix = State()

class BroadcastState(StatesGroup):
    message = State()

class TwoFAState(StatesGroup):
    waiting = State()

class WithdrawState(StatesGroup):
    method = State()
    account = State()

class AddBalanceState(StatesGroup):
    user_id = State()
    amount = State()

class RemoveBalanceState(StatesGroup):
    user_id = State()
    amount = State()

class AddNamesState(StatesGroup):
    country = State()
    names = State()

class UserReportState(StatesGroup):
    user_id = State()

class ReferralConfigState(StatesGroup):
    set_amount = State()

class VIPAddService(StatesGroup):
    name = State()
    price = State()

class BulkUploadFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        if not is_admin(message.chat.id):
            return False
        if message.document:
            return True
        if message.text:
            if message.text in MENU_BUTTONS:
                return False
            lines = [n.strip() for n in message.text.splitlines() if n.strip()]
            return len(lines) >= 10
        return False

async def check_subscription(user_id):
    if is_admin(user_id): return []
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel['id'], user_id)
            if member.status not in ['creator', 'administrator', 'member', 'restricted']:
                not_joined.append(channel)
        except Exception as e:
            not_joined.append(channel)
    return not_joined

def get_subscription_markup(not_joined_channels):
    keyboard = []
    for channel in not_joined_channels:
        keyboard.append([InlineKeyboardButton(text=f"👉 {channel['name']}", url=channel['url'], style="primary")])
    keyboard.append([InlineKeyboardButton(text="✅ Verify", callback_data="check_join", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def user_keyboard(is_admin_user=False):
    kb = [
        [KeyboardButton(text="💎 VIP NUMBER", style="primary"), KeyboardButton(text="📱 Get Number", style="primary")],
        [KeyboardButton(text="🅾️ Get OTP", style="success"), KeyboardButton(text="👤 Get Name", style="primary")],
        [KeyboardButton(text="🔐 Get 2FA", style="primary"), KeyboardButton(text="💰 My Account", style="success")],
        [KeyboardButton(text="🔗 Invite Friends", style="success"), KeyboardButton(text="📞 Support", style="primary")]
    ]
    if is_admin_user:
        kb.append([KeyboardButton(text="⚙️ Admin Panel", style="danger")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_keyboard():
    kb = [
        [KeyboardButton(text="➖ Remove Numbers", style="danger"), KeyboardButton(text="👥 View Users", style="primary")],
        [KeyboardButton(text="📢 Broadcast", style="primary"), KeyboardButton(text="📊 Inventory", style="primary")],
        [KeyboardButton(text="💰 Add Balance", style="success"), KeyboardButton(text="💰 Remove Balance", style="danger")],
        [KeyboardButton(text="🗑 Remove Names", style="danger"), KeyboardButton(text="📋 User Report", style="primary")],
        [KeyboardButton(text="🔗 Referral Settings", style="primary"), KeyboardButton(text="🔙 Back to User Menu", style="success")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def handle_received_otp(sender_num, otp, msg_content, source_service="Unknown"):
    current_sessions = await load_json(SESSIONS_FILE)
    clean_sender = clean_phone_number(sender_num).replace("+", "").strip()
    found_user = None
    
    if clean_sender in current_sessions: found_user = current_sessions.pop(clean_sender)
    elif f"+{clean_sender}" in current_sessions: found_user = current_sessions.pop(f"+{clean_sender}")
        
    await save_json(SESSIONS_FILE, current_sessions)
    
    detected_country, country_info = detect_country_from_number(sender_num)
    
    service_type = source_service
    if found_user:
        service_type = found_user.get('service', service_type)
        if service_type.startswith("VIP "):
            service_type = service_type.replace("VIP ", "")
    
    if service_type == "Unknown" or service_type == "API":
        service_type = get_service_from_msg(msg_content)
        
    service_type_upper = service_type.capitalize()
    
    range_str = (clean_sender[:5] + "XXX" if len(clean_sender) >= 5 else clean_sender + "XXX").strip()
    flag = country_info["flag"]
    display_country = f"{flag} {detected_country}" if detected_country != "Unknown" else "🌍 Unknown"
    
    # 🟢 নতুন ডিজাইন (Blockquote সহ)
    otp = str(otp).strip()
    msg_content_clean = str(msg_content).strip()

    base_msg = (
        f"<b>𝐒   𓆩𓆩𝙾𝚃𝙿 𝚁𝙴𝙲𝙴𝙸𝚅𝙴𝙳𓆪𓆪   𝐑</b>\n"
        f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        f"╭────❖\n"
        f"│ 𝙲𝙾𝚄𝙽𝚃𝚁𝚈 : {display_country}\n"
        f"│ 𝚂𝙴𝚁𝚅𝙸𝙲𝙴 : {service_type_upper}\n"
        f"│ 𝚁𝙰𝙽𝙶𝙴   : <code>{range_str}</code>\n"
        f"│ 𝙾𝚃𝙿     : <code>{otp}</code>\n"
        f"╰─────────❖\n"
        f"│ 𝙵𝚄𝙻𝙻 𝚂𝙼𝚂 :\n│\n"
        f"<blockquote>{msg_content_clean}</blockquote>\n"
        f"╰─────────❖"
    )
    
    if found_user:
        price_earned = float(found_user.get('price', 0))
        user_chat_id = found_user.get('chat_id')
        
        if price_earned > 0:
            await add_balance(user_chat_id, price_earned)

        await log_user_activity(user_chat_id, "sms_received", {
            "service": service_type_upper,
            "country": detected_country,
            "amount": price_earned
        })

        user_msg = f"{base_msg}\n\n💰 <b>Earned:</b> <code>৳{price_earned}</code>"
        try:
            await bot.send_message(user_chat_id, user_msg)
        except Exception as e:
            logger.error(f"Failed to send user message: {e}")

    # 🟢 প্রথম বাটনটি Green (success) এবং দ্বিতীয়টি Blue (primary)
    group_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="╭━━ 🇧🇩  𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃  🇧🇩 ━━╮", url="https://t.me/Best_Number_Top_Bot?start=6920696519", style="success")],
        [InlineKeyboardButton(text="╰━━🧑‍💻𝙱𝙾𝚃 𝙳𝙴𝚅𝙴𝙻𝙾𝙿𝙴𝚁🧑‍💻━━╯", url="https://t.me/Private_Zone_Admin", style="primary")]
    ])
    
    try:
        await bot.send_message(GROUP_ID, base_msg, reply_markup=group_kb)
    except Exception: pass

async def monitor_api_otps():
    while True:
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(vultex.SUCCESS_OTP_URL, headers=vultex.get_headers(), ssl=False, timeout=10) as resp:
                    if resp.status == 200:
                        res = await resp.json(content_type=None)
                        if res.get('meta', {}).get('status') == 'ok' or res.get('meta', {}).get('code') == 200:
                            otps_list = res.get('data', {}).get('otps', [])
                            for item in otps_list:
                                otp_id = item.get('otp_id')
                                if not otp_id: continue
                                if otp_id in processed_otps: continue
                                processed_otps.add(otp_id)
                                
                                if len(processed_otps) > 5000:
                                    processed_otps.clear()
                                    
                                number = str(item.get('number', '')).strip()
                                msg = str(item.get('message', '')).strip()
                                
                                if not number or not msg: continue
                                
                                otp_code = extract_otp_from_message(msg)
                                if not otp_code or otp_code == "No OTP": continue
                                
                                await handle_received_otp(number, otp_code, msg, "API")
        except Exception as e:
            logger.error(f"OTP Polling error: {e}")
        
        await asyncio.sleep(10)

async def otp_handler(request):
    try:
        try: data = await request.json()
        except Exception as e: return web.json_response({"status": "error", "message": f"Invalid JSON: {str(e)}"}, status=400)
        
        if not data: return web.json_response({"status": "error", "message": "No JSON payload"}, status=400)
        
        sender_num = clean_phone_number(str(data.get("number", "")).strip())
        otp_from_api = str(data.get("otp", "")).strip()
        msg_content = data.get("full_msg", data.get("full_message", ""))
        service_type = data.get("service", "Unknown")
        
        extracted_otp = extract_otp_from_message(msg_content)
        otp = extracted_otp if (otp_from_api == "" or otp_from_api == "No OTP") else otp_from_api

        await handle_received_otp(sender_num, otp, msg_content, service_type)
        return web.json_response({"status": "success", "message": "OTP Dispatched successfully"}, status=200)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext, start_param: str | None = None):
    await state.clear()
    await add_user_to_db(message.chat.id)
    await init_names_file()
    await init_referrals_file()
    
    param = start_param
    if not param:
        try:
            parts = (message.text or "").split()
            if len(parts) > 1: param = parts[1]
        except: param = None

    if param:
        token = param.strip()
        try:
            referrer_id = int(token)
            if referrer_id != message.chat.id:
                added = await add_pending_referral(referrer_id, message.chat.id)
                if added:
                    try: await bot.send_message(message.chat.id, f"✅ You were referred by user <code>{referrer_id}</code>. To complete referral, please join required channels and press ✅ Verify.")
                    except: pass
        except Exception: pass

    not_joined = await check_subscription(message.chat.id)
    if not_joined:
        await message.answer("⚠️ <b>Please join the following channels to use the bot:</b> ⚠️", reply_markup=get_subscription_markup(not_joined))
        return
    
    welcome_text = (
        "<b>𓆩𓆩𝚆𝙴𝙻𝙲𝙾𝙼𝙴 𝚃𝙾 𝚂𝚁 𝙳𝙸𝙶𝙸𝚃𝙰𝙻 𝙼𝙰𝚁𝙺𝙴𝚃𝙸𝙽𝙶 𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃𓆪𓆪</b>\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "🤖 𝚂𝚁 𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃 এ আপনাকে স্বাগতম!\n\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "『☠︎ 𝙿𝙾𝚆𝙴𝚁𝙴𝙳 𝙱𝚈 𝚁𝙸𝙵𝙰𝚃𝚄𝙻 𝙸𝚂𝙻𝙰𝙼"
    )
    await message.answer(welcome_text, reply_markup=user_keyboard(is_admin(message.chat.id)))

@router.callback_query(F.data == "check_join")
async def verify_join(call: CallbackQuery):
    user_id = call.message.chat.id
    not_joined = await check_subscription(user_id)
    if not_joined:
        await call.answer("❌ You haven't joined all channels yet!", show_alert=True)
    else:
        try:
            recorded, amount = await finalize_pending_referral(user_id)
            welcome_text = (
                "<b>𓆩𓆩𝚆𝙴𝙻𝙲𝙾𝙼𝙴 𝚃𝙾 𝚂𝚁 𝙳𝙸𝙶𝙸𝚃𝙰𝙻 𝙼𝙰𝚁𝙺𝙴𝚃𝙸𝙽𝙶 𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃𓆪𓆪</b>\n"
                "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                "🤖 𝚂𝚁 𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃 এ আপনাকে স্বাগতম!\n\n"
                "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                "『☠︎ 𝙿𝙾𝚆𝙴𝚁𝙴𝙳 𝙱𝚈 𝚁𝙸𝙵𝙰𝚃𝚄𝙻 𝙸𝚂𝙻𝙰𝙼"
            )
            if recorded:
                amt_display = f"{amount:.2f}" if isinstance(amount, float) else str(amount)
                try:
                    referrer_id = await get_referrer_of(user_id)
                    if referrer_id:
                        caption = f"🎉 <b>Referral Completed!</b> 🎉\n\n💰 You earned: <code>৳{amt_display}</code>\n\n🆔 User ID: <code>{user_id}</code>\n\nThank you for inviting new users! 🚀"
                        await bot.send_message(referrer_id, caption)
                except: pass
                try: await bot.send_message(user_id, f"🎉 Referral completed! Your referrer received <code>৳{amt_display}</code>.")
                except: pass
            
            await call.message.edit_text(welcome_text, reply_markup=user_keyboard(is_admin(call.message.chat.id)))
        except Exception:
            await call.answer("✅ Verified!", show_alert=False)

@router.message(Command("wdd"))
async def admin_wdd_command(message: Message, state: FSMContext):
    if not is_admin(message.chat.id):
        return
    await state.clear()
    vip_db = await vultex.load_vip_db()
    
    keyboard = []
    for service in vip_db.keys():
        keyboard.append([InlineKeyboardButton(text=f"⚙️ {service}", callback_data=f"vip_manage_srv_{service}", style="primary")])
    
    keyboard.append([InlineKeyboardButton(text="➕ New Service", callback_data="vip_new_service", style="success")])
    
    text = (
        "<b>💎 VIP SERVICES 💎</b>\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "Manage VIP Services:"
    )
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("vip_manage_srv_"))
async def vip_manage_service_menu(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    service = call.data.split("_", 3)[3]
    vip_db = await vultex.load_vip_db()
    
    if service not in vip_db:
        await call.answer("Service not found.", show_alert=True)
        return
        
    keyboard = []
    
    custom_rules = vip_db[service].get("custom_rules", {})
    for prefix, cname in custom_rules.items():
        keyboard.append([InlineKeyboardButton(text=f"🗑 Rule: {prefix} -> {cname}", callback_data=f"vip_del_rule_{service}_{prefix}", style="danger")])

    countries = vip_db[service].get("countries", {})
    for country in countries.keys():
        keyboard.append([InlineKeyboardButton(text=f"🗑 {country}", callback_data=f"vip_del_cty_{service}_{country}", style="danger")])
        
    keyboard.append([InlineKeyboardButton(text="➕ Add Custom Range (Prefix)", callback_data=f"vip_add_rule_{service}", style="success")])
    keyboard.append([InlineKeyboardButton(text=f"❌ Delete Entire '{service}'", callback_data=f"vip_del_entire_{service}", style="danger")])
    
    msg_text = f"Manage <b>{service}</b>:\n\n<i>Note: If you add a Custom Range Prefix, ONLY those prefixes will be auto-updated for this service.</i>"
    await call.message.edit_text(msg_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("vip_del_rule_"))
async def vip_del_rule(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    parts = call.data.split("_", 4)
    service = parts[3]
    prefix = parts[4]
    
    vip_db = await vultex.load_vip_db()
    if service in vip_db and "custom_rules" in vip_db[service]:
        if prefix in vip_db[service]["custom_rules"]:
            del vip_db[service]["custom_rules"][prefix]
            await vultex.save_vip_db(vip_db)
            await call.answer(f"Deleted custom prefix rule for {prefix}", show_alert=True)
            
            keyboard = []
            custom_rules = vip_db[service].get("custom_rules", {})
            for pfx, cname in custom_rules.items():
                keyboard.append([InlineKeyboardButton(text=f"🗑 Rule: {pfx} -> {cname}", callback_data=f"vip_del_rule_{service}_{pfx}", style="danger")])

            countries = vip_db[service].get("countries", {})
            for country in countries.keys():
                keyboard.append([InlineKeyboardButton(text=f"🗑 {country}", callback_data=f"vip_del_cty_{service}_{country}", style="danger")])
                
            keyboard.append([InlineKeyboardButton(text="➕ Add Custom Range (Prefix)", callback_data=f"vip_add_rule_{service}", style="success")])
            keyboard.append([InlineKeyboardButton(text=f"❌ Delete Entire '{service}'", callback_data=f"vip_del_entire_{service}", style="danger")])
            
            await call.message.edit_text(f"Manage <b>{service}</b>:\n\n<i>Note: If you add a Custom Range Prefix, ONLY those prefixes will be auto-updated for this service.</i>", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("vip_add_rule_"))
async def vip_add_rule_start(call: CallbackQuery, state: FSMContext):
    service = call.data.split("_", 3)[3]
    await state.update_data(rule_service=service)
    await state.set_state(VIPAddCustomRule.country)
    await call.message.edit_text(f"Service: <b>{service}</b>\nEnter the <b>Country Name</b> for this rule (e.g., Ivory Coast):")

@router.message(VIPAddCustomRule.country)
async def vip_add_rule_country(message: Message, state: FSMContext):
    await state.update_data(rule_country=message.text.strip())
    await state.set_state(VIPAddCustomRule.prefix)
    await message.answer("Enter the <b>Prefix</b> (e.g., 225):")

@router.message(VIPAddCustomRule.prefix)
async def vip_add_rule_prefix(message: Message, state: FSMContext):
    prefix = message.text.strip().replace("+", "")
    data = await state.get_data()
    service = data.get("rule_service")
    country = data.get("rule_country")
    
    vip_db = await vultex.load_vip_db()
    if service in vip_db:
        if "custom_rules" not in vip_db[service]:
            vip_db[service]["custom_rules"] = {}
        vip_db[service]["custom_rules"][prefix] = country
        await vultex.save_vip_db(vip_db)
        await message.answer(f"✅ Custom Prefix Rule Added!\nService: {service}\nPrefix: <b>{prefix}</b> -> Country: <b>{country}</b>", reply_markup=admin_keyboard())
    await state.clear()

@router.callback_query(F.data == "vip_new_service")
async def vip_new_service(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    await state.set_state(VIPAddService.name)
    await call.message.edit_text("Enter the New VIP Service Name (e.g., WhatsApp, Facebook):")

@router.message(VIPAddService.name)
async def vip_new_service_name(message: Message, state: FSMContext):
    service_name = message.text.strip()
    await state.update_data(service_name=service_name)
    await state.set_state(VIPAddService.price)
    await message.answer(f"Service Name: <code>{service_name}</code>\n\nEnter the OTP Price (Enter 0 for no price):")

@router.message(VIPAddService.price)
async def vip_new_service_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
        data = await state.get_data()
        service_name = data.get("service_name")
        
        vip_db = await vultex.load_vip_db()
        if service_name not in vip_db:
            vip_db[service_name] = {"price": price, "countries": {}}
        else:
            vip_db[service_name]["price"] = price
            
        await vultex.save_vip_db(vip_db)
        
        await message.answer(f"✅ VIP Service <code>{service_name}</code> successfully created/updated with price <code>৳{price}</code>.", reply_markup=admin_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Invalid price. Please enter a number.")

@router.callback_query(F.data.startswith("vip_del_cty_"))
async def vip_del_country(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    parts = call.data.split("_", 4)
    service = parts[3]
    country = parts[4]
    
    vip_db = await vultex.load_vip_db()
    if service in vip_db and country in vip_db[service].get("countries", {}):
        del vip_db[service]["countries"][country]
        await vultex.save_vip_db(vip_db)
        await call.answer(f"Deleted {country} from {service}", show_alert=True)
        
        keyboard = []
        custom_rules = vip_db[service].get("custom_rules", {})
        for pfx, cname in custom_rules.items():
            keyboard.append([InlineKeyboardButton(text=f"🗑 Rule: {pfx} -> {cname}", callback_data=f"vip_del_rule_{service}_{pfx}", style="danger")])

        for c in vip_db[service].get("countries", {}).keys():
            keyboard.append([InlineKeyboardButton(text=f"🗑 {c}", callback_data=f"vip_del_cty_{service}_{c}", style="danger")])
            
        keyboard.append([InlineKeyboardButton(text="➕ Add Custom Range (Prefix)", callback_data=f"vip_add_rule_{service}", style="success")])
        keyboard.append([InlineKeyboardButton(text=f"❌ Delete Entire '{service}'", callback_data=f"vip_del_entire_{service}", style="danger")])
        
        await call.message.edit_text(f"Manage deletions for <b>{service}</b>:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    else:
        await call.answer("Not found.", show_alert=True)

@router.callback_query(F.data.startswith("vip_del_entire_"))
async def vip_del_entire_service(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    service = call.data.split("_", 3)[3]
    vip_db = await vultex.load_vip_db()
    
    if service in vip_db:
        del vip_db[service]
        await vultex.save_vip_db(vip_db)
        await call.answer(f"Deleted entire service: {service}", show_alert=True)
        await call.message.edit_text("✅ Service completely deleted.")
    else:
        await call.answer("Not found.", show_alert=True)

@router.message(F.text == "💎 VIP NUMBER")
async def vip_number_menu(message: Message, state: FSMContext):
    await state.clear()
    if await check_subscription(message.chat.id):
        await start_command(message, state)
        return
        
    vip_db = await vultex.fetch_and_update_vip_countries()
    
    if not vip_db:
        await message.answer("🚫 No VIP Services currently available.")
        return
        
    keyboard = []
    has_services = False
    for service, details in vip_db.items():
        countries = details.get("countries", {})
        if countries:
            keyboard.append([InlineKeyboardButton(text=f"💎 {service}", callback_data=f"vip_sel_{service}", style="primary")])
            has_services = True
        
    if not has_services:
        await message.answer("🚫 No VIP Services available.")
    else:
        text = (
            "<b>💎 VIP SERVICES 💎</b>\n"
            "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
            "Select a VIP Service:"
        )
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("vip_sel_"))
async def vip_service_selected(call: CallbackQuery):
    if await check_subscription(call.message.chat.id): return
    service = call.data.split("_", 2)[2]
    vip_db = await vultex.load_vip_db()
    
    if service not in vip_db:
        await call.answer("❌ Service not found!")
        return
        
    keyboard = []
    countries = vip_db[service].get("countries", {})
    price = vip_db[service].get("price", 0)
    
    has_countries = False
    for country, details in countries.items():
        keyboard.append([InlineKeyboardButton(text=f"{country} (৳{price})", callback_data=f"vip_get_{service}_{country}", style="primary")])
        has_countries = True
        
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="vip_back", style="danger")])
    
    if has_countries:
        text = f"💎 <b>{service}</b> - Select Country:\n<i>Price: ৳{price}</i>"
        formatted_keyboard = []
        for i in range(0, len(keyboard) - 1, 2):
            if i + 1 < len(keyboard) - 1: formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
            else: formatted_keyboard.append([keyboard[i][0]])
        formatted_keyboard.append(keyboard[-1])
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))
    else:
        await call.answer("❌ No VIP countries available for this service yet!", show_alert=True)

@router.callback_query(F.data == "vip_back")
async def vip_back_menu(call: CallbackQuery):
    vip_db = await vultex.load_vip_db()
    keyboard = []
    for service, details in vip_db.items():
        countries = details.get("countries", {})
        if countries:
            keyboard.append([InlineKeyboardButton(text=f"💎 {service}", callback_data=f"vip_sel_{service}", style="primary")])
    
    text = (
        "<b>💎 VIP SERVICES 💎</b>\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "Select a VIP Service:"
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("vip_get_"))
async def vip_get_number(call: CallbackQuery):
    if await check_subscription(call.message.chat.id): return
    parts = call.data.split("_", 3)
    service = parts[2]
    country = parts[3]
    
    vip_db = await vultex.load_vip_db()
    
    try:
        if service in vip_db and country in vip_db[service].get("countries", {}):
            country_data = vip_db[service]["countries"][country]
            rid = country_data.get("rid")
            price = vip_db[service].get('price', 0)
            
            number = None
            
            if rid:
                number = await vultex.get_vip_number_from_api(rid)
            
            if not number and country_data.get("numbers"):
                number = country_data["numbers"].pop(0)
                await vultex.save_vip_db(vip_db)
            
            if number:
                number = clean_phone_number(number)
                clean_num = number.replace("+", "").strip()
                sessions = await load_json(SESSIONS_FILE)
                sessions[clean_num] = {
                    'chat_id': call.message.chat.id, 
                    'service': f"VIP {service}",
                    'country': country, 
                    'price': price,
                    'timestamp': time.time()
                }
                await save_json(SESSIONS_FILE, sessions)
                
                await log_user_activity(call.message.chat.id, "vip_number_received", {
                    "service": service,
                    "country": country,
                    "number": number,
                    "price": price
                })
                
                display_number = number if number.startswith('+') else '+' + number
                
                response = (
                    f"<b>𝐒 𓆩𓆩𝐍𝐔𝐌𝐁𝐄𝐑 𝐑𝐄𝐂𝐄𝐈𝐕𝐄𓆪𓆪 𝐑</b>\n"
                    f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"╭────❖\n"
                    f"│ 📱 𝚂𝙴𝚁𝚅𝙸𝙲𝙴 : {service}\n"
                    f"│ 🌎 𝙲𝙾𝚄𝙽𝚃𝚁𝚈 : {country}\n"
                    f"│ 📞 𝙽𝚄𝙼𝙱𝙴𝚁 : <code>{display_number}</code>\n"
                    f"│ ⏳ 𝚂𝚃𝙰𝚃𝚄𝚂 : 𝚆𝙰𝙸𝚃𝙸𝙽𝙶.....\n"
                    f"╰─────────❖\n\n"
                    f"『☠︎ 𝙿𝙾𝚆𝙴𝚁𝙴𝙳 𝙱𝚈 𝚁𝙸𝙵𝙰𝚃𝚄𝙻 𝙸𝚂𝙻𝙰𝙼"
                )
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Change Number", callback_data=f"vip_get_{service}_{country}", style="primary")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data=f"vip_sel_{service}", style="danger")]
                ])
                
                await call.message.edit_text(response, reply_markup=kb)
            else:
                await call.answer("❌ No numbers available right now! API Limit or Stock empty.", show_alert=True)
        else:
            await call.answer("❌ Service or Country not found!", show_alert=True)
    except Exception as e:
        logger.error(f"Error assigning VIP number: {e}")
        await call.answer("❌ Error assigning number.", show_alert=True)

@router.message(F.text == "⚙️ Admin Panel")
async def open_admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.clear()
    await init_names_file()
    
    admin_text = (
        "<b>👑 ADMIN PANEL 👑</b>\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "<i>Note: To add numbers or names, paste 10+ items or send a .txt file here.</i>"
    )
    await message.answer(admin_text, reply_markup=admin_keyboard())

@router.message(F.text == "🔙 Back to User Menu")
async def back_to_user_menu(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "<b>𓆩𓆩𝚆𝙴𝙻𝙲𝙾𝙼𝙴 𝚃𝙾 𝚂𝚁 𝙳𝙸𝙶𝙸𝚃𝙰𝙻 𝙼𝙰𝚁𝙺𝙴𝚃𝙸𝙽𝙶 𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃𓆪𓆪</b>\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "🤖 𝚂𝚁 𝙽𝚄𝙼𝙱𝙴𝚁 𝙱𝙾𝚃 এ আপনাকে স্বাগতম!\n\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        "『☠︎ 𝙿𝙾𝚆𝙴𝚁𝙴𝙳 𝙱𝚈 𝚁𝙸𝙵𝙰𝚃𝚄𝙻 𝙸𝚂𝙻𝙰𝙼"
    )
    await message.answer(welcome_text, reply_markup=user_keyboard(is_admin(message.chat.id)))

@router.message(BulkUploadFilter())
async def handle_bulk_upload(message: Message, state: FSMContext):
    valid_items = []
    if message.document:
        try:
            file_in_memory = io.BytesIO()
            await bot.download(message.document, file_in_memory)
            text_data = file_in_memory.getvalue().decode('utf-8', errors='ignore').splitlines()
            valid_items = [n.strip() for n in text_data if n.strip()]
        except Exception as e:
            await message.answer(f"❌ File read error: {e}")
            return
    elif message.text:
        lines = message.text.splitlines()
        valid_items = [n.strip() for n in lines if n.strip()]
    
    if len(valid_items) >= 10:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📱 Add as Numbers", callback_data="addnums_service", style="primary"),
            InlineKeyboardButton(text="👤 Add as Names", callback_data="addname_country", style="primary")
        ], [
            InlineKeyboardButton(text="💎 Add VIP Numbers", callback_data="addvip_num", style="success")
        ]])
        
        detect_text = (
            f"<b>✅ ITEMS DETECTED ✅</b>\n"
            f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
            f"📝 Total: {len(valid_items)} Items\n\n"
            f"What do you want to do?"
        )
        await state.update_data(temp_items=valid_items)
        await message.answer(detect_text, reply_markup=kb)

@router.callback_query(F.data == "addvip_num")
async def addvip_num_service(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    data = await state.get_data()
    items = data.get('temp_items', [])
    await state.update_data(temp_nums=items)
    
    vip_db = await vultex.load_vip_db()
    if not vip_db:
        await call.message.edit_text("No VIP Services found. Please create one with /wdd first.")
        return
    keyboard = []
    for srv in vip_db.keys():
        keyboard.append([InlineKeyboardButton(text=f"💎 {srv}", callback_data=f"vipaddsrv_{srv}", style="primary")])
    await call.message.edit_text("Select VIP Service to add numbers:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("vipaddsrv_"))
async def vipaddsrv_select_country(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    service = call.data.split("_", 1)[1]
    await state.update_data(vip_service=service)
    
    vip_db = await vultex.load_vip_db()
    keyboard = []
    for cty in vip_db[service].get("countries", {}).keys():
        keyboard.append([InlineKeyboardButton(text=f"🌐 {cty}", callback_data=f"vipaddcty_{service}_{cty}", style="primary")])
    if not keyboard:
        await call.message.edit_text("No countries available in this VIP service. Click 'VIP NUMBER' from user menu to auto-add countries from API first.")
        return
    
    formatted_keyboard = []
    for i in range(0, len(keyboard), 2):
        if i + 1 < len(keyboard):
            formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
        else:
            formatted_keyboard.append([keyboard[i][0]])
            
    await call.message.edit_text(f"Select Country for {service}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))

@router.callback_query(F.data.startswith("vipaddcty_"))
async def vipaddcty_confirm(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    parts = call.data.split("_", 2)
    service = parts[1]
    country = parts[2]
    
    data = await state.get_data()
    nums = data.get('temp_nums', [])
    formatted_nums = []
    for num in nums:
        num = clean_phone_number(num)
        if not num.startswith("+"): formatted_nums.append("+" + num)
        else: formatted_nums.append(num)
            
    vip_db = await vultex.load_vip_db()
    vip_db[service]["countries"][country]["numbers"].extend(formatted_nums)
    await vultex.save_vip_db(vip_db)
    
    await call.message.edit_text(f"✅ Added {len(formatted_nums)} VIP numbers to {service} - {country}")
    await state.clear()


@router.callback_query(F.data == "addnums_service")
async def select_service_for_numbers(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    data = await state.get_data()
    items = data.get('temp_items', [])
    await state.update_data(temp_nums=items, upload_type='numbers')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="WhatsApp", callback_data="addsrv_WhatsApp", style="primary"), InlineKeyboardButton(text="Telegram", callback_data="addsrv_Telegram", style="primary")],
        [InlineKeyboardButton(text="Facebook", callback_data="addsrv_Facebook", style="primary"), InlineKeyboardButton(text="Instagram", callback_data="addsrv_Instagram", style="primary")],
        [InlineKeyboardButton(text="Google", callback_data="addsrv_Google", style="primary"), InlineKeyboardButton(text="Others App", callback_data="addsrv_Others App", style="primary")]
    ])
    
    service_text = (f"<b>🌟 SELECT SERVICE 🌟</b>\n"
                    f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"📝 Numbers: {len(items)}\n\nPlease Select Service:")
    await call.message.edit_text(service_text, reply_markup=kb)

@router.callback_query(F.data == "addname_country")
async def add_name_from_bulk(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    data = await state.get_data()
    names_list = data.get('temp_items', [])
    await state.update_data(temp_names=names_list, upload_type='names')
    await state.set_state(AddNamesState.country)
    
    country_text = ("<b>👤 ADD NAMES 👤</b>\n"
                    "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"📝 Names to add: {len(names_list)}\n\nEnter the country name:")
    await call.message.edit_text(country_text)

@router.message(AddNamesState.country)
async def add_names_get_country(message: Message, state: FSMContext):
    country = message.text.strip()
    data = await state.get_data()
    names_list = data.get('temp_names', [])
    await add_names_to_country(country, names_list)
    success_text = ("<b>🎉 NAMES ADDED! 🎉</b>\n"
                    "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"Country: <b>{country}</b>\nNames Added: <b>{len(names_list)}</b>")
    await message.answer(success_text, reply_markup=admin_keyboard())
    await state.clear()

@router.callback_query(F.data.startswith("addsrv_"))
async def admin_select_service(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    data = await state.get_data()
    service = call.data.split("_", 1)[1]
    formatted_nums = []
    for num in data.get('temp_nums', []):
        num = clean_phone_number(num)
        if not num.startswith("+"): formatted_nums.append("+" + num)
        else: formatted_nums.append(num)
    
    await state.update_data(temp_nums=formatted_nums, service=service)
    await state.set_state(AdminAdd.price)
    
    service_text = (f"<b>✅ SERVICE SELECTED ✅</b>\n"
                    f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"Service: <b>{capitalize_service_name(service)}</b>\nNumbers: {len(formatted_nums)}\n\n💰 Enter the price for these numbers (e.g., 15):")
    await call.message.edit_text(service_text)

@router.message(AdminAdd.price)
async def admin_enter_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip())
        await state.update_data(price=price)
        await state.set_state(AdminAdd.country)
        price_text = (f"<b>✅ PRICE SET ✅</b>\n"
                      f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                      f"Price: <code>৳{price}</code>\n\n🌍 Enter the Country Name (e.g., Bangladesh):")
        await message.answer(price_text)
    except ValueError: await message.answer("❌ Please enter a valid number for price.")

@router.message(AdminAdd.country)
async def admin_enter_country(message: Message, state: FSMContext):
    country = message.text.strip()
    data = await state.get_data()
    service, price, nums = data['service'], data['price'], data['temp_nums']
    
    db = await load_json(DB_FILE)
    if service not in db: db[service] = {}
    if country not in db[service]: db[service][country] = {'price': price, 'numbers':[]}
    
    db[service][country]['price'] = price
    db[service][country]['numbers'].extend(nums)
    await save_json(DB_FILE, db)
    
    success_text = ("<b>🎉 SUCCESSFULLY ADDED! 🎉</b>\n"
                    "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"Service: <b>{capitalize_service_name(service)}</b>\nCountry: <b>{country}</b>\nPrice: <code>৳{price}</code>\nNumbers Added: <b>{len(nums)}</b>")
    await message.answer(success_text, reply_markup=admin_keyboard())
    await state.clear()

@router.message(F.text == "🔗 Referral Settings")
async def referral_settings_menu(message: Message):
    if not is_admin(message.chat.id): return
    await init_referrals_file()
    amount = await get_referral_amount()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Set Amount", callback_data="set_ref_amount", style="primary"), InlineKeyboardButton(text="Remove Amount", callback_data="del_ref_amount", style="danger")]
    ])
    await message.answer(f"🔗 Current referral amount: <code>৳{amount}</code>\n\nChoose an action:", reply_markup=kb)

@router.callback_query(F.data == "set_ref_amount")
async def callback_set_ref_amount(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.message.chat.id): return
    await state.set_state(ReferralConfigState.set_amount)
    await call.message.edit_text("Enter referral amount (e.g., 5):")

@router.callback_query(F.data == "del_ref_amount")
async def callback_del_ref_amount(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    await clear_referral_amount()
    await call.message.edit_text("✅ Referral amount cleared (set to ৳0).")

@router.message(ReferralConfigState.set_amount)
async def set_ref_amount_message(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    try:
        amount = float(message.text.strip())
        await set_referral_amount(amount)
        await message.answer(f"✅ Referral amount set to <code>৳{amount}</code>", reply_markup=admin_keyboard())
    except ValueError: await message.answer("❌ Invalid number. Please send a valid amount.")
    await state.clear()

@router.message(F.text == "💰 My Account")
async def my_account(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.chat.id
    total_bal = await get_balance(user_id)
    ref_over = await get_referral_overview(user_id)
    ref_earned, ref_count = ref_over.get("total_earned", 0), ref_over.get("count", 0)
    
    account_text = (
        "<b>💳 MY PROFILE 💳</b>\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
        f"🆔 User ID: <code>{user_id}</code>\n💰 Total Balance: <code>৳{total_bal}</code>\n🔗 Referral Earned: <code>৳{ref_earned}</code> (Referrals: {ref_count})\n\n"
        "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n⚠️ Minimum withdrawal: <code>৳25</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Request Withdrawal", callback_data="req_withdraw", style="success")]])
    await message.answer(account_text, reply_markup=kb)

@router.callback_query(F.data == "req_withdraw")
async def withdraw_request(call: CallbackQuery, state: FSMContext):
    total_bal = await get_balance(call.message.chat.id)
    if total_bal >= 25:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟡 Binance", callback_data="with_method_Binance", style="primary"), InlineKeyboardButton(text="🦅 BKash", callback_data="with_method_BKash", style="primary")]
        ])
        withdraw_text = (f"<b>💸 WITHDRAWAL REQUEST 💸</b>\n"
                         f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                         f"💰 Total Balance: <code>৳{total_bal}</code>\n\nSelect payment method:")
        await call.message.edit_text(withdraw_text, reply_markup=kb)
    else: await call.answer(f"❌ Insufficient Balance!\nMinimum withdraw is ৳25\nYour total balance: ৳{total_bal}", show_alert=True)

@router.callback_query(F.data.startswith("with_method_"))
async def withdraw_method_selected(call: CallbackQuery, state: FSMContext):
    method = call.data.split("_")[2]
    await state.update_data(method=method)
    await state.set_state(WithdrawState.account)
    account_text = ("<b>🟡 BINANCE WITHDRAWAL 🟡</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nEnter your <b>Binance ID</b>:\n<i>(Numbers only, e.g., 38387000)</i>" 
                    if method == "Binance" else 
                    "<b>🦅 BKASH WITHDRAWAL 🦅</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nEnter your <b>BKash Number</b>:\n<i>(e.g., 01700000000)</i>")
    await call.message.edit_text(account_text)

@router.message(WithdrawState.account)
async def withdraw_account_input(message: Message, state: FSMContext):
    account_id = message.text.strip()
    if not account_id.isdigit():
        await message.answer("❌ <b>Invalid Format!</b> Please use numbers only.")
        return
    
    total_bal = await get_balance(message.chat.id)
    await state.update_data(account=account_id, amount=total_bal)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Confirm", callback_data="with_confirm", style="success")], [InlineKeyboardButton(text="❌ Cancel", callback_data="with_cancel", style="danger")]])
    confirm_text = ("<b>📝 CONFIRM WITHDRAWAL 📝</b>\n"
                    "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                    f"💰 <b>Amount:</b> <code>৳{total_bal}</code>\n🏦 <b>Method:</b> <code>{await state.get_value('method')}</code>\n🔑 <b>Account ID:</b> <code>{account_id}</code>\n\nClick <b>Confirm</b> to proceed.")
    await message.answer(confirm_text, reply_markup=kb)

@router.callback_query(F.data == "with_cancel")
async def withdraw_cancel_by_user(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("<b>❌ CANCELLED ❌</b>")

@router.callback_query(F.data == "with_confirm")
async def withdraw_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    method, account, amount, user_id = data.get("method"), data.get("account"), data.get("amount"), call.message.chat.id
    current_bal = await get_balance(user_id)
    
    if current_bal < amount:
        await call.answer("❌ Balance Error! Please try again.", show_alert=True)
        await state.clear()
        return
    
    await add_balance(user_id, -amount)
    submit_text = ("<b>✅ REQUEST SUBMITTED ✅</b>\n"
                   "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                   f"<code>৳{amount}</code> has been deducted from your account. You will receive payment shortly after admin approval.")
    await call.message.edit_text(submit_text)
    
    admin_text = (f"<b>🔔 NEW WITHDRAWAL REQUEST 🔔</b>\n"
                  f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                  f"👤 <b>User ID:</b> <code>{user_id}</code>\n💰 <b>Amount:</b> <code>৳{amount}</code>\n🏦 <b>Method:</b> <code>{method}</code>\n🔑 <b>Account ID:</b> <code>{account}</code>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"admapv_{user_id}_{amount}", style="success"),
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"admrej_{user_id}_{amount}", style="danger")
    ]])
    try: await bot.send_message(WITHDRAWAL_GROUP_ID, admin_text, reply_markup=kb)
    except: pass
    await state.clear()

@router.callback_query(F.data.startswith("admapv_"))
async def admin_approve_withdraw(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return await call.answer("❌ You don't have permission!", show_alert=True)
    user_id, amount = int(call.data.split("_")[1]), call.data.split("_")[2]
    
    user_msg = ("<b>🎉 APPROVED 🎉</b>\n"
                "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                f"Your withdrawal request for <code>৳{amount}</code> has been approved. You will receive payment within 24 hours.\n\nThank you for using our service! ❤️")
    try: await bot.send_message(user_id, user_msg)
    except: pass
    
    admin_msg = ("<b>✅ WITHDRAWAL APPROVED ✅</b>\n"
                 "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                 f"User ID: <code>{user_id}</code>\nAmount: <code>৳{amount}</code>\nStatus: ✅ Payment Approved")
    await call.message.edit_text(admin_msg)

@router.callback_query(F.data.startswith("admrej_"))
async def admin_reject_withdraw(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return await call.answer("❌ You don't have permission!", show_alert=True)
    user_id, amount = int(call.data.split("_")[1]), float(call.data.split("_")[2])
    
    await add_balance(user_id, amount)
    user_msg = ("<b>❌ REQUEST CANCELLED ❌</b>\n"
                "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                f"Your withdrawal request for <code>৳{amount}</code> has been cancelled.\n\nYour funds have been refunded to your account.")
    try: await bot.send_message(user_id, user_msg)
    except: pass
    
    admin_msg = ("<b>❌ WITHDRAWAL CANCELLED ❌</b>\n"
                 "﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                 f"User ID: <code>{user_id}</code>\nAmount: <code>৳{amount}</code>\nStatus: ✅ Amount Refunded")
    await call.message.edit_text(admin_msg)

@router.message(F.text == "💰 Add Balance")
async def add_balance_start(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.clear()
    await state.set_state(AddBalanceState.user_id)
    await message.answer("<b>💰 ADD BALANCE 💰</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nEnter User ID:")

@router.message(AddBalanceState.user_id)
async def add_balance_get_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        await state.update_data(user_id=user_id)
        await state.set_state(AddBalanceState.amount)
        await message.answer(f"<b>✅ USER ID SET ✅</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n✅ User ID: <code>{user_id}</code>\n\nEnter the amount to add (e.g., 50):")
    except ValueError: await message.answer("❌ Invalid format! Please enter only numbers.")

@router.message(AddBalanceState.amount)
async def add_balance_get_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        user_id = (await state.get_data()).get('user_id')
        await add_balance(user_id, amount)
        current_bal = await get_balance(user_id)
        balance_text = (f"<b>✅ BALANCE ADDED ✅</b>\n"
                        f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n"
                        f"👤 User ID: <code>{user_id}</code>\n➕ Added: <code>৳{amount}</code>\n💰 New Balance: <code>৳{current_bal}</code>")
        await message.answer(balance_text, reply_markup=admin_keyboard())
        await state.clear()
    except ValueError: await message.answer("❌ Invalid format!")

@router.message(F.text == "💰 Remove Balance")
async def remove_balance_start(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.clear()
    await state.set_state(RemoveBalanceState.user_id)
    await message.answer("<b>💰 REMOVE BALANCE 💰</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nEnter User ID:")

@router.message(RemoveBalanceState.user_id)
async def remove_balance_get_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        current_bal = await get_balance(user_id)
        await state.update_data(user_id=user_id)
        await state.set_state(RemoveBalanceState.amount)
        await message.answer(f"<b>✅ USER ID FOUND ✅</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n✅ User ID: <code>{user_id}</code>\n💰 Current Balance: <code>৳{current_bal}</code>\n\nEnter amount to remove:")
    except ValueError: await message.answer("❌ Invalid format!")

@router.message(RemoveBalanceState.amount)
async def remove_balance_get_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        user_id = (await state.get_data()).get('user_id')
        current_bal = await get_balance(user_id)
        if current_bal < amount:
            await message.answer(f"❌ INSUFFICIENT BALANCE\nCurrent Balance: ৳{current_bal}", reply_markup=admin_keyboard())
        else:
            await add_balance(user_id, -amount)
            new_bal = await get_balance(user_id)
            await message.answer(f"✅ BALANCE REMOVED\nRemoved: ৳{amount}\nNew Balance: ৳{new_bal}", reply_markup=admin_keyboard())
        await state.clear()
    except ValueError: await message.answer("❌ Invalid format!")

@router.message(F.text == "📋 User Report")
async def user_report_start(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.clear()
    await state.set_state(UserReportState.user_id)
    await message.answer("<b>📋 USER REPORT 📋</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nEnter the User ID to get their detailed report:")

@router.message(UserReportState.user_id)
async def user_report_get_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        user_details = await get_user_details_for_report(user_id)
        report_text = await format_user_report(user_details)
        try: await bot.send_message(REPORT_GROUP_ID, report_text)
        except Exception as e: await message.answer(f"❌ Failed to send report: {e}")
        await message.answer(f"✅ REPORT SENT\nUser ID: <code>{user_id}</code>\nReport sent to admin group successfully!", reply_markup=admin_keyboard())
        await state.clear()
    except ValueError: await message.answer("❌ Invalid User ID!")

@router.message(F.text == "👤 Get Name")
async def user_get_name_start(message: Message, state: FSMContext):
    await state.clear()
    if await check_subscription(message.chat.id):
        await start_command(message, state)
        return
    available_countries = await get_available_name_countries()
    if not available_countries:
        await message.answer("🚫 No names currently available.")
        return
    keyboard = []
    for country in available_countries.keys():
        keyboard.append([InlineKeyboardButton(text=f"{country}", callback_data=f"selname_{country}", style="primary")])
    
    formatted_keyboard = []
    for i in range(0, len(keyboard), 2):
        if i + 1 < len(keyboard): formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
        else: formatted_keyboard.append([keyboard[i][0]])
    
    await message.answer("<b>👤 SELECT COUNTRY 👤</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))

@router.callback_query(F.data.startswith("selname_"))
async def assign_name(call: CallbackQuery):
    if await check_subscription(call.message.chat.id): return
    country = call.data.split("_", 1)[1]
    name = await get_name_from_country(country)
    
    if not name:
        await call.answer("❌ No names available in this country!", show_alert=True)
        return
    
    await log_user_activity(call.message.chat.id, "name_received", {"country": country, "name": name})
    name_msg = (f"<b>✅ NAME ASSIGNED ✅</b>\n"
                f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\n🌐 Country: {country}\n\n👤 Name: <code>{name}</code>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨‍💻 Developer", url="https://t.me/Private_Zone_Admin", style="primary"),
        InlineKeyboardButton(text="Official Channel", url="https://t.me/Digital_marketing_Top_1", style="primary")
    ]])
    await call.message.edit_text(name_msg, reply_markup=kb)

@router.message(F.text == "🗑 Remove Names")
async def remove_names_start(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.clear()
    await init_names_file()
    stats = await get_names_stats()
    if not stats: return await message.answer("🚫 No names to remove.", reply_markup=admin_keyboard())
    
    keyboard = []
    for country, count in stats.items():
        keyboard.append([InlineKeyboardButton(text=f"🗑 {country} ({count} names)", callback_data=f"remname_select_{country}", style="danger")])
    
    formatted_keyboard = []
    for i in range(0, len(keyboard), 2):
        if i + 1 < len(keyboard): formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
        else: formatted_keyboard.append([keyboard[i][0]])
    
    await message.answer("<b>🗑 REMOVE NAMES 🗑</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nSelect country to remove all names:", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))

@router.callback_query(F.data.startswith("remname_select_"))
async def remove_names_confirm(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    country = call.data.split("_", 2)[2]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm", callback_data=f"remname_confirm_{country}", style="danger"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="remname_cancel", style="primary")
    ]])
    await call.message.edit_text(f"<b>⚠️ CONFIRM DELETE ⚠️</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nAre you sure you want to remove all names from <b>{country}</b>?", reply_markup=kb)

@router.callback_query(F.data.startswith("remname_confirm_"))
async def remove_names_execute(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    country = call.data.split("_", 2)[2]
    await remove_all_names_for_country(country)
    await call.message.edit_text(f"<b>✅ DELETED ✅</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nAll names from <b>{country}</b> have been removed.")

@router.callback_query(F.data == "remname_cancel")
async def remove_names_cancel(call: CallbackQuery):
    await call.message.edit_text("<b>❌ CANCELLED ❌</b>")

@router.message(F.text == "📱 Get Number")
async def user_get_number_service(message: Message, state: FSMContext):
    await state.clear()
    if await check_subscription(message.chat.id):
        await start_command(message, state)
        return
    db = await load_json(DB_FILE)
    if not db:
        await message.answer("🚫 No numbers currently available.")
        return
    keyboard = []
    has_services = False
    for service, countries in db.items():
        if any(len(c_details.get('numbers',[])) > 0 for c_details in countries.values()):
            service_display = capitalize_service_name(service)
            keyboard.append([InlineKeyboardButton(text=f"{service_display}", callback_data=f"selsrv_{service}", style="primary")])
            has_services = True
    
    if not has_services:
        await message.answer("🚫 No active numbers available.")
    else:
        formatted_keyboard = []
        for i in range(0, len(keyboard), 2):
            if i + 1 < len(keyboard): formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
            else: formatted_keyboard.append([keyboard[i][0]])
        await message.answer("<b>🌟 SELECT SERVICE 🌟</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))

@router.callback_query(F.data.startswith("selsrv_"))
async def select_country_for_service(call: CallbackQuery):
    if await check_subscription(call.message.chat.id): return
    service = call.data.split("_", 1)[1]
    db = await load_json(DB_FILE)
    if service not in db: return await call.answer("❌ Service not found!")
    
    keyboard = []
    has_countries = False
    for country, details in db[service].items():
        count = len(details.get('numbers',[]))
        if count > 0:
            price = details.get('price', 0)
            keyboard.append([InlineKeyboardButton(text=f"{country} (৳{price})", callback_data=f"getnum_{service}_{country}", style="primary")])
            has_countries = True
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_services", style="danger")])
    
    if has_countries:
        formatted_keyboard = []
        for i in range(0, len(keyboard) - 1, 2):
            if i + 1 < len(keyboard) - 1: formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
            else: formatted_keyboard.append([keyboard[i][0]])
        formatted_keyboard.append(keyboard[-1])
        await call.message.edit_text(f"🌟 <b>{capitalize_service_name(service)}</b> - Select Country:", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))
    else:
        await call.answer("❌ No numbers left in this service!", show_alert=True)

@router.callback_query(F.data == "back_to_services")
async def back_to_services(call: CallbackQuery):
    db = await load_json(DB_FILE)
    keyboard = []
    for service, countries in db.items():
        if any(len(c_details.get('numbers',[])) > 0 for c_details in countries.values()):
            service_display = capitalize_service_name(service)
            keyboard.append([InlineKeyboardButton(text=f"{service_display}", callback_data=f"selsrv_{service}", style="primary")])
    
    formatted_keyboard = []
    for i in range(0, len(keyboard), 2):
        if i + 1 < len(keyboard): formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
        else: formatted_keyboard.append([keyboard[i][0]])
    await call.message.edit_text("<b>🌟 SELECT SERVICE 🌟</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))

@router.callback_query(F.data.startswith("getnum_"))
async def assign_number(call: CallbackQuery):
    if await check_subscription(call.message.chat.id): return
    parts = call.data.split("_", 2)
    service = parts[1]
    country = parts[2]
    db = await load_json(DB_FILE)
    try:
        if db[service][country]['numbers']:
            number = db[service][country]['numbers'].pop(0)
            number = clean_phone_number(number)
            price = db[service][country].get('price', 0)
            await save_json(DB_FILE, db)
            
            clean_num = number.replace("+", "").strip()
            sessions = await load_json(SESSIONS_FILE)
            sessions[clean_num] = {
                'chat_id': call.message.chat.id, 
                'service': service,
                'country': country, 
                'price': price,
                'timestamp': time.time()
            }
            await save_json(SESSIONS_FILE, sessions)
            
            await log_user_activity(call.message.chat.id, "number_received", {
                "service": service,
                "country": country,
                "number": number,
                "price": price
            })
            
            country_info = COUNTRY_MAP.get(country, {"flag": "🌍", "code": country[:2].upper()})
            flag = country_info["flag"]
            code = country_info["code"]
            display_number = number if number.startswith("+") else f"+{number}"
            
            response = (
                f"<b>✅ NUMBER ASSIGNED ✅</b>\n"
                f"﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\n"
                f"⚙️ Service : {capitalize_service_name(service)}\n"
                f"🌐 Country : {flag} {code}\n"
                f"💰 Reward : <code>৳{price}</code>\n\n"
                f"Number : <code>{display_number}</code>\n\n"
                f"⏳ Status : Waiting for OTP..."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔄 Change Number", callback_data=f"getnum_{service}_{country}", style="primary"),
                InlineKeyboardButton(text="🔙 Back", callback_data=f"selsrv_{service}", style="danger")
            ]])
            await call.message.edit_text(response, reply_markup=kb)
        else:
            await call.answer("❌ No numbers left!", show_alert=True)
    except Exception as e:
        await call.answer("❌ Error assigning number.", show_alert=True)

@router.message(F.text == "🅾️ Get OTP")
async def user_get_otp_info(message: Message):
    otp_text = ("<b>📬 LIVE OTP UPDATES 📬</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\nJoin our OTP group to see live updates in real-time!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Join OTP Group", url="https://t.me/otpgroup_all", style="primary")]])
    await message.answer(otp_text, reply_markup=kb)

@router.message(F.text == "📞 Support")
async def help_line(message: Message):
    support_text = (f"<b>🛜 {BOT_NAME} SUPPORT 🛜</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\nFor any issues, click the button below to contact our live support team:")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🟢 Live Chat 24/7", url="https://t.me/Help_Line_And_Review_bot", style="primary")]])
    await message.answer(support_text, reply_markup=kb)

@router.message(F.text == "🔐 Get 2FA")
async def user_get_2fa(message: Message, state: FSMContext):
    if await check_subscription(message.chat.id): return
    secret = generate_2fa_secret()
    await save_2fa_secret(message.chat.id, secret)
    
    twofa_text = (f"<b>🔐 2FA AUTHENTICATOR 🔐</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\nSend your 2FA Secret Key (spaces allowed).\n\nExample:\n<code>{secret}</code>\n\nSend /cancel to quit.")
    await message.answer(twofa_text, reply_markup=user_keyboard(is_admin(message.chat.id)))
    await state.set_state(TwoFAState.waiting)

@router.message(F.text == "/cancel")
async def cancel_2fa(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == TwoFAState.waiting.state:
        await state.clear()
        await message.answer("❌ 2FA Cancelled.", reply_markup=user_keyboard(is_admin(message.chat.id)))

@router.message(TwoFAState.waiting)
async def process_2fa_input(message: Message, state: FSMContext):
    if message.text in MENU_BUTTONS: return
    user_input = message.text.strip()
    code, sanitized_secret = get_2fa_code_from_input(user_input)
    if code is None:
        await message.answer("❌ Code generation failed. Please try again.")
        return
    
    twofa_code_text = (f"<b>🔐 2FA CODE GENERATED 🔐</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\n🔑 Secret Key: {user_input.upper()}\n🔢 Code: <code>{code}</code>\n⏱ Remaining: {get_2fa_remaining_seconds()} seconds\n⏳ Code expires in: 30 seconds\n")
    await message.answer(twofa_code_text)
    await state.clear()

@router.message(F.text == "➖ Remove Numbers")
async def remove_number_menu(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.clear()
    db = await load_json(DB_FILE)
    keyboard = []
    for service, countries in db.items():
        for country in countries.keys():
            keyboard.append([InlineKeyboardButton(text=f"🗑 {capitalize_service_name(service)} - {country}", callback_data=f"del_{service}_{country}", style="danger")])
    
    formatted_keyboard = []
    for i in range(0, len(keyboard), 2):
        if i + 1 < len(keyboard): formatted_keyboard.append([keyboard[i][0], keyboard[i+1][0]])
        else: formatted_keyboard.append([keyboard[i][0]])
    
    await message.answer("<b>🔻 REMOVE NUMBERS 🔻</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nSelect to remove:", reply_markup=InlineKeyboardMarkup(inline_keyboard=formatted_keyboard))

@router.callback_query(F.data.startswith("del_"))
async def delete_country(call: CallbackQuery):
    if not is_admin(call.message.chat.id): return
    parts = call.data.split("_", 2)
    service = parts[1]
    country = parts[2]
    db = await load_json(DB_FILE)
    if service in db and country in db[service]:
        del db[service][country]
        if not db[service]: del db[service]
        await save_json(DB_FILE, db)
        await call.message.edit_text(f"<b>✅ REMOVED ✅</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nRemoved {capitalize_service_name(service)} - {country}")

@router.message(F.text == "👥 View Users")
async def view_users(message: Message):
    if not is_admin(message.chat.id): return
    users = await load_json(USERS_FILE)
    await message.answer(f"<b>👥 TOTAL USERS 👥</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n📊 Total Users: {len(users)}")

@router.message(F.text == "📢 Broadcast")
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.chat.id): return
    await state.set_state(BroadcastState.message)
    await message.answer("<b>📢 BROADCAST MESSAGE 📢</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\nSend your message (Text/Photo):")

@router.message(BroadcastState.message)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text in MENU_BUTTONS: return
    users = await load_json(USERS_FILE)
    sent = 0
    await message.answer(f"<b>🚀 BROADCASTING 🚀</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n🚀 Sending to {len(users)} users...")
    
    for uid in users:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            sent += 1
            await asyncio.sleep(0.05)
        except: continue
    
    await message.answer(f"<b>✅ BROADCAST COMPLETE ✅</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n✅ Done! Sent to {sent}/{len(users)} users.", reply_markup=admin_keyboard())
    await state.clear()

@router.message(F.text == "📊 Inventory")
async def admin_view_stocks(message: Message):
    if not is_admin(message.chat.id): return
    text = await get_stocks_text()
    await message.answer(text)

@router.message(F.text == "🔗 Invite Friends")
async def invite_friends_handler(message: Message):
    await init_referrals_file()
    amount = await get_referral_amount()
    try:
        invite_url = f"https://t.me/{BOT_USERNAME}?start={message.chat.id}" if BOT_USERNAME else f"https://t.me/{BOT_NAME}?start={message.chat.id}"
    except Exception:
        invite_url = f"https://t.me/{BOT_NAME}?start={message.chat.id}"

    share_text = f"Join this bot and enjoy! Use my invite link: {invite_url}"
    share_url = "https://t.me/share/url?"+urllib.parse.urlencode({"url": invite_url, "text": share_text})
    
    invite_text = (f"<b>🔗 INVITE FRIENDS 🔗</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\n"
                   f"Invite friends using the button below.\n🎁 You will earn: <code>৳{amount}</code> per successful referral.\n\n"
                   "Share your invite link — when a friend joins and VERIFY, you'll get the reward automatically!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👉 Share Invite", url=share_url, style="success")]])
    await message.answer(invite_text + f"\n🔗 Your link:\n<code>{invite_url}</code>", reply_markup=kb)

@router.callback_query(F.data == "show_my_refs")
async def show_my_refs(call: CallbackQuery):
    ref_over = await get_referral_overview(call.from_user.id)
    count, amount_per, total, refs = ref_over.get("count", 0), ref_over.get("amount_per", 0), ref_over.get("total_earned", 0), ref_over.get("referrals", [])
    
    refs_list_text = ("\n\nReferred User IDs:\n" + "\n".join([f"<code>{uid}</code>" for uid in refs[:50]])) if refs else ""
    if len(refs) > 50: refs_list_text += f"\n... and {len(refs)-50} more"

    text = (f"<b>📊 MY REFERRALS 📊</b>\n﹌﹌﹌﹌﹌﹌﹌﹌﹌﹌\n\n"
            f"🧾 Total Referrals: <code>{count}</code>\n💵 Per Referral: <code>৳{amount_per}</code>\n🏆 Total Earned: <code>৳{total}</code>{refs_list_text}\n\nShare your invite link to earn more!")
    try: await call.message.edit_text(text)
    except: await call.answer(text, show_alert=True)

async def main():
    try:
        me = await bot.get_me()
        global BOT_NAME, BOT_USERNAME
        BOT_NAME = me.first_name if me.first_name else "Bot"
        BOT_USERNAME = me.username if getattr(me, 'username', None) else None
        logger.info(f"✅ Bot logged in as: {BOT_NAME} (@{BOT_USERNAME})")
    except Exception as e:
        logger.error(f"❌ Error getting bot info: {e}")

    await init_names_file()
    await init_referrals_file()
    
    asyncio.create_task(vultex.auto_update_loop())
    asyncio.create_task(monitor_api_otps())

    app = web.Application()
    app.router.add_post(WEBHOOK_ENDPOINT, otp_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT)
    await site.start()

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    print("\n" + "="*70)
    print("🚀 AROSHI OTP BOT - WEBHOOK MODE ACTIVE")
    print("="*70)
    
    logger.info(f"✅ Webhook Server started at http://{local_ip}:{WEBHOOK_PORT}{WEBHOOK_ENDPOINT}")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
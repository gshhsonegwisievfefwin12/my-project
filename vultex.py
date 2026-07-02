import asyncio
import aiohttp
import json
import os
import phonenumbers
from phonenumbers import geocoder
import logging

VIP_DB_FILE = 'vip_database.json'
API_TOKEN = "MTJJ2II38D9"

CONSOLE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api/console"
GETNUM_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api/getnum"
SUCCESS_OTP_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api/success-otp"

logger = logging.getLogger(__name__)

def get_headers():
    return {
        "mauthapi": API_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

async def load_vip_db():
    if os.path.exists(VIP_DB_FILE):
        try:
            with open(VIP_DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

async def save_vip_db(data):
    try:
        with open(VIP_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving VIP DB: {e}")

FALLBACK_PREFIXES = {
    "224": "Guinea",
    "225": "Ivory Coast",
    "236": "Central African Republic",
    "233": "Ghana",
    "261": "Madagascar",
    "249": "Sudan",
    "234": "Nigeria",
    "251": "Ethiopia",
    "212": "Morocco",
    "27": "South Africa",
    "20": "Egypt",
    "254": "Kenya"
}

async def get_country_name_from_range(range_str):
    try:
        clean_range = str(range_str).upper().replace("X", "0")
        num_str = "+" + clean_range
        pn = phonenumbers.parse(num_str)
        country_name = geocoder.country_name_for_number(pn, "en")
        if country_name:
            return country_name
    except Exception:
        pass
        
    clean_range = str(range_str).upper().replace("X", "0")
    for length in [4, 3, 2, 1]:
        prefix = clean_range[:length]
        if prefix in FALLBACK_PREFIXES:
            return FALLBACK_PREFIXES[prefix]
            
    return "Unknown"

async def fetch_console_data():
    for attempt in range(3):
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(CONSOLE_URL, headers=get_headers(), ssl=False, timeout=10) as resp:
                    if resp.status == 200:
                        res = await resp.json(content_type=None)
                        if res.get('meta', {}).get('status') == 'ok' or res.get('meta', {}).get('code') == 200:
                            return res.get('data', {})
        except Exception as e:
            logger.error(f"Fetch console error (Attempt {attempt+1}/3): {e}")
        await asyncio.sleep(2)
    return None

async def update_vip_data_from_api():
    vip_db = await load_vip_db()
    if not vip_db:
        return vip_db
        
    console_data = await fetch_console_data()
    if console_data and 'hits' in console_data:
        hits = console_data.get('hits', [])
        service_map = {k.lower().strip(): k for k in vip_db.keys()}
        updated = False
        
        for hit in hits:
            sid = str(hit.get("sid", "")).lower().strip()
            range_str = str(hit.get("range", "")).strip()
            
            if sid in service_map and range_str:
                real_sid = service_map[sid]
                custom_rules = vip_db[real_sid].get("custom_rules", {})
                country = None
                
                if custom_rules:
                    for prefix, c_name in custom_rules.items():
                        if range_str.startswith(prefix):
                            country = c_name
                            break
                    if not country:
                        continue 
                else:
                    country = await get_country_name_from_range(range_str)
                
                if country and country != "Unknown":
                    country_d1 = f"{country} D1"
                    rid = range_str.upper().replace("X", "") 
                    
                    if "countries" not in vip_db[real_sid]:
                        vip_db[real_sid]["countries"] = {}
                    
                    if country_d1 not in vip_db[real_sid]["countries"]:
                        vip_db[real_sid]["countries"][country_d1] = {
                            "numbers": [],
                            "rid": rid
                        }
                        updated = True
                    else:
                        if vip_db[real_sid]["countries"][country_d1]["rid"] != rid:
                            vip_db[real_sid]["countries"][country_d1]["rid"] = rid
                            updated = True
        
        if updated:
            await save_vip_db(vip_db)
            
    return await load_vip_db()

async def auto_update_loop():
    while True:
        await update_vip_data_from_api()
        await asyncio.sleep(300)

async def fetch_and_update_vip_countries():
    return await update_vip_data_from_api()

async def get_vip_number_from_api(rid):
    for attempt in range(3):
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(GETNUM_URL, headers=get_headers(), json={"rid": rid}, timeout=10, ssl=False) as resp:
                    if resp.status == 200:
                        res = await resp.json(content_type=None)
                        if res.get('meta', {}).get('status') == 'ok' or res.get('meta', {}).get('code') == 200:
                            data = res.get('data', {})
                            num = str(data.get('no_plus_number', '')).replace('+', '')
                            if num:
                                return num
        except Exception as e:
            logger.error(f"Error calling getnum API (Attempt {attempt+1}/3): {e}")
        await asyncio.sleep(2)
    return None
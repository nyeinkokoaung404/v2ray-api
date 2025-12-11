import os
import json
import time
import re
import math
import uuid
import base64
import urllib.parse
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from functools import wraps
from typing import Dict, Any, List, Union, Callable

# =========================================================================
# CONFIGURATION & CONSTANTS
# =========================================================================

# Vercel Environment တွင်၊ panels.php ကို တိုက်ရိုက်ခေါ်မရနိုင်သဖြင့် ဤနေရာတွင်
# panel config အား dummy အနေဖြင့် ထားရှိပါသည်။ Production အတွက် Environment Variables သို့
# ပြောင်းလဲရန် (သို့မဟုတ်) JSON file ကိုသုံးရန် အကြံပြုပါသည်။
# PHP script တွင်ကဲ့သို့ 'panels.php' ကို အခြေခံထားသည့် configuration
# **ဤနေရာရှိ username/password ကို သင်၏ အမှန်တကယ် Panel Info ဖြင့် အစားထိုးရမည်**
ALL_PANELS_CONFIG: Dict[str, Any] = {
    # Premium Panel Examples
    'Panel_A': {
        'url': 'http://panel-a.example.com:54321',
        'username': 'admin_a',
        'password': 'password_a',
        'type': 'Premium'
    },
    'Panel_B': {
        'url': 'http://panel-b.example.com:54321',
        'username': 'admin_b',
        'password': 'password_b',
        'type': 'Premium'
    },
    # Trial Panel Example (The PHP script uses the first one found)
    'Trial_Pnl_1': {
        'url': 'http://trial-pnl.example.com:54321',
        'username': 'trial_user',
        'password': 'trial_pass',
        'type': 'Trial'
    }
}

# PHP script ၏ filtering logic အတိုင်း ပြန်လည်ခွဲထုတ်ခြင်း
PREMIUM_PANELS: Dict[int, Any] = {}
TRIAL_PANELS: List[Any] = []
premium_index = 1
for name, config in ALL_PANELS_CONFIG.items():
    panel_data = {
        'name': name,
        'config': {
            'url': config['url'],
            'username': config['username'],
            'password': config['password'],
        }
    }
    if config['type'] == 'Premium':
        PREMIUM_PANELS[premium_index] = panel_data
        premium_index += 1
    elif config['type'] == 'Trial':
        TRIAL_PANELS.append(panel_data)


API_INFO = {
    'api_owner': 'Channel 404 Team',
    'owner_contact': '@nkka404',
    'updates_channel': '@premium_channel_404',
    'channel_link': 'https://t.me/premium_channel_404',
    'version': '4.6 (Python Flask Integration)',
    'description': 'Premium V2Ray Account Checker & Key Creator/Deleter',
    'features': [
        'Multi-panel support', 'Dynamic Panels via JSON File',
        'All protocol types', 'Multi-Tier provisioning',
        'Account Modification', 'Account Enable/Disable & Traffic Reset',
        'Account Transfer between panels', 'Traffic monitoring & Expiry tracking',
        'Smart panel load balancing', 'Online User Monitoring'
    ]
}

# JSON File Configuration (NEW)
DYNAMIC_PANELS_FILE = os.path.join(os.path.dirname(__file__), 'dynamic_panels.json')

# Constants for Trial Accounts
TRIAL_GIGABYTES = 50
TRIAL_EXPIRY_DAYS = 7
REQUIRED_PORT = 52797
REQUIRED_REMARK = 'Trial'

# Constants for Premium Accounts (Multi-Protocol/Tier Inbound Mapping)
INBOUND_MAPPING = {
    'shadowsocks': {
        '150GB': {'port': 15000, 'remark': '150GB'},
        '250GB': {'port': 25000, 'remark': '250GB'},
        '500GB': {'port': 50000, 'remark': '500GB'},
        'Premium': {'port': 60000, 'remark': 'Premium'},
    },
    'vless': {
        '150GB': {'port': 15001, 'remark': '150GB_VLESS'},
        'Premium': {'port': 405, 'remark': 'Premium_VLESS'},
    },
    'vmess': {
        'Premium': {'port': 406, 'remark': 'Premium_VMESS'},
    },
    'trojan': {
        'Premium': {'port': 407, 'remark': 'Premium_TROJAN'},
    },
}
DEFAULT_PREMIUM_TIER = 'Premium'
DEFAULT_PREMIUM_PROTOCOL = 'shadowsocks'

PREMIUM_EXPIRY_TIME_MS_UNLIMITED = 0

# Common Constants
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
SHADOWSOCKS_METHOD = 'chacha20-ietf-poly1305'

# Rate limiting configuration (In-memory cache)
RATE_LIMIT_REQUESTS_PER_MINUTE = 30
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_CACHE: Dict[str, Dict[int, int]] = {}

# Notification Configuration
# Bot token သည် sensitive ဖြစ်သဖြင့် Environment Variable တွင်ထားရန် အကြံပြုပါသည်။
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8007668447:AAE9RK3SCTvYVAXB8ZTQFUClCoqCAbvF9jQ')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1002833902644')

# Custom Notification Constants (HTML formatting is compatible with Telegram)
EXPIRY_NOTIFICATION_IMAGE_URL = 'https://raw.githubusercontent.com/nyeinkokoaung404/v2ray-tel-bot/main/images/404-VPN.jpg'
MY_EXPIRY_NOTIFICATION_TEXT = "<b>VPN သက်တမ်းကုန်သွားပြီလား? 🙄</b>\n\nစိတ်မပူပါနဲ့ <b>404 VPN</b> နဲ့ဆိုရင် KBZ Pay, Wave Pay, AYA Pay တို့နဲ့ အချိန်မရွေး ပိတ်ချိန်မရှိ ၊ စောင့်ဆိုင်းစရာ ၊ စကားပြောစရာမလိုပဲ 24/7 @nkka404 မှာ သက်တမ်းတိုးလို့ရနေပြီနော်!"
RENEWAL_INLINE_KEYBOARD = [
    [
        [
            'text': 'ဝယ်ယူ/သက်တမ်းတိုးရန်',
            'url': 'https://t.me/nkka404?text=' + urllib.parse.quote('သက်တမ်းတိုးချင်ပါတယ်။')
        ]
    ]
]

# Multi-language Support
TRANSLATIONS = {
    'en': {
        'account_created': 'Account created successfully',
        'account_not_found': 'Account not found in any panel or failed to retrieve stats',
        'trial_created': 'Trial account created successfully',
        'trial_key_retrieved': 'Trial account key retrieved successfully',
        'account_deleted': 'Account deleted successfully',
        'account_modified': 'Account successfully modified',
        'account_enabled': 'Account successfully enabled',
        'account_disabled': 'Account successfully disabled',
        'traffic_reset': 'Account traffic successfully reset',
        'no_expired_accounts': 'No expired accounts found',
        'expired_deleted': 'Successfully deleted expired accounts',
        'invalid_panel': 'Invalid panel number provided',
        'login_failed': 'Failed to login to panel',
        'inbound_not_found': 'Required inbound not found on panel',
        'invalid_username': 'Invalid username format',
        'invalid_telegram_id': 'Invalid Telegram ID format',
        'rate_limit_exceeded': 'Rate limit exceeded. Please try again later',
        'system_error': 'Internal server error',
        'no_trial_panels': 'No trial panels configured',
        'panel_status_online': 'Online',
        'panel_status_offline': 'Offline',
        'traffic_unlimited': 'Unlimited',
        'expiry_never': 'Never Expires',
        'expiry_expired': 'Expired',
        'online_users_retrieved': 'Online user list retrieved successfully',
        'no_online_users': 'No online users found on any panel',
        'panel_added': 'Panel added successfully to file',
        'panel_deleted': 'Panel deleted successfully from file',
        'panel_list_retrieved': 'Panel list retrieved successfully',
        'invalid_panel_id': 'Invalid panel ID or panel not found in file',
        'file_access_failed': 'File read/write failed',
        'expiry_soon_user': 'Your Trial account will expire in %d days. Please renew if needed.',
        'expired_user': 'Your Trial account has expired and will be deleted soon.',
    },
    'my': {
        'account_created': 'အကောင့်အောင်မြင်စွာဖန်တီးပြီးပါပြီ',
        'account_not_found': 'အကောင့်ကိုရှာမတွေ့ပါ သို့မဟုတ် အချက်အလက်များရယူ၍မရပါ',
        'trial_created': 'Trial အကောင့်အောင်မြင်စွာဖန်တီးပြီးပါပြီ',
        'trial_key_retrieved': 'Trial အကောင့်ကီးအောင်မြင်စွာရယူပြီးပါပြီ',
        'account_deleted': 'အကောင့်အောင်မြင်စွာဖျက်ပြီးပါပြီ',
        'account_modified': 'အကောင့်ကိုအောင်မြင်စွာပြုပြင်ပြီးပါပြီ',
        'account_enabled': 'အကောင့်ကိုအောင်မြင်စွာဖွင့်ပြီးပါပြီ',
        'account_disabled': 'အကောင့်ကိုအောင်မြင်စွာပိတ်ပြီးပါပြီ',
        'traffic_reset': 'အကောင့်၏ဒေတာအသုံးပြုမှုကိုအောင်မြင်စွာပြန်လည်သတ်မှတ်ပြီးပါပြီ',
        'no_expired_accounts': 'ရက်လွန်အကောင့်များမတွေ့ရှိပါ',
        'expired_deleted': 'ရက်လွန်အကောင့်များအောင်မြင်စွာဖျက်ပြီးပါပြီ',
        'invalid_panel': 'မှားယွင်းသော panel နံပါတ်ဖြစ်ပါသည်',
        'login_failed': 'Panel သို့လော့ဂ်အင်၍မရပါ',
        'inbound_not_found': 'လိုအပ်သော inbound ကို panel တွင်မတွေ့ရှိပါ',
        'invalid_username': 'မှားယွင်းသော username ဖြစ်ပါသည်',
        'invalid_telegram_id': 'မှားယွင်းသော Telegram ID ဖြစ်ပါသည်',
        'rate_limit_exceeded': 'အသုံးပြုမှုအကန့်အသတ်ထက်ကျော်လွန်နေပါသည်။ နောက်မှထပ်ကြိုးစားပါ',
        'system_error': 'စနစ်အတွင်းပိုင်းအမှားတစ်ခုဖြစ်နေပါသည်',
        'no_trial_panels': 'Trial panel များသတ်မှတ်ထားခြင်းမရှိပါ',
        'panel_status_online': 'အဆင်သင့်ဖြစ်နေ',
        'panel_status_offline': 'အဆင်သင့်မဖြစ်သေး',
        'traffic_unlimited': 'အကန့်အသတ်မရှိ',
        'expiry_never': 'ဘယ်တော့မှမကုန်ဆုံး',
        'expiry_expired': 'ကုန်ဆုံးသွားပြီ',
        'online_users_retrieved': 'Online အသုံးပြုသူစာရင်းကို အောင်မြင်စွာ ရယူပြီးပါပြီ',
        'no_online_users': 'မည်သည့် panel တွင်မှ online အသုံးပြုသူမတွေ့ပါ',
        'panel_added': 'Panel ကို file ထဲသို့ အောင်မြင်စွာထည့်သွင်းပြီးပါပြီ',
        'panel_deleted': 'Panel ကို file မှ အောင်မြင်စွာဖျက်ပြီးပါပြီ',
        'panel_list_retrieved': 'Panel စာရင်းကို အောင်မြင်စွာရယူပြီးပါပြီ',
        'invalid_panel_id': 'မှားယွင်းသော panel ID ဖြစ်သည် သို့မဟုတ် file တွင် panel မတွေ့ပါ',
        'file_access_failed': 'ဖိုင်ဖတ်/ရေး လုပ်ဆောင်မှု မအောင်မြင်ပါ',
        'expiry_soon_user': 'သင်၏ Trial အကောင့်သည် နောက် %d ရက်တွင် သက်တမ်းကုန်ဆုံးပါမည်။ လိုအပ်ပါက သက်တမ်းတိုးပါ။',
        'expired_user': 'သင်၏ Trial အကောင့်သည် သက်တမ်းကုန်ဆုံးသွားပြီး မကြာမီ ဖျက်လိုက်ပါမည်။',
    }
}

# =========================================================================
# FLASK & LANGUAGE SETUP
# =========================================================================

app = Flask(__name__)

# Helper to get client language
def get_client_language() -> str:
    accept_lang = request.headers.get('Accept-Language', 'en')
    if 'my' in accept_lang:
        return 'my'
    return 'en'

# Helper for translation
def t(key: str, lang: str) -> str:
    return TRANSLATIONS.get(lang, TRANSLATIONS['en']).get(key, TRANSLATIONS['en'].get(key, key))

# =========================================================================
# SECURITY & VALIDATION FUNCTIONS
# =========================================================================

# Helper to get client identifier (Improved for Vercel/Proxy environments)
def get_client_identifier() -> str:
    # Check common proxy headers first, then fall back to direct remote address
    if 'CF-Connecting-IP' in request.headers:
        return request.headers['CF-Connecting-IP']
    if 'X-Forwarded-For' in request.headers:
        # X-Forwarded-For can contain a list, take the first one (client IP)
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    # Note: In Vercel, request.remote_addr might be the load balancer IP
    return request.remote_addr if request.remote_addr else 'unknown'

# Rate Limiting
def check_rate_limit(identifier: str) -> bool:
    global RATE_LIMIT_CACHE
    now = int(time.time())
    window_key = now // RATE_LIMIT_WINDOW
    
    # Clean up old window
    old_window = window_key - 2
    keys_to_delete = [k for k in RATE_LIMIT_CACHE if int(k.split('_')[-1]) <= old_window]
    for key in keys_to_delete:
        del RATE_LIMIT_CACHE[key]
        
    cache_key = f"{identifier}_{window_key}"
    
    RATE_LIMIT_CACHE[cache_key] = RATE_LIMIT_CACHE.get(cache_key, 0) + 1
    
    return RATE_LIMIT_CACHE[cache_key] <= RATE_LIMIT_REQUESTS_PER_MINUTE

def rate_limit_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_id = get_client_identifier()
        if not check_rate_limit(client_id):
            lang = get_client_language()
            return format_api_response({
                'error': t('rate_limit_exceeded', lang),
                'message': 'Too many requests. Please try again later.'
            }, success=False, lang=lang), 429
        return f(*args, **kwargs)
    return decorated_function

# Validation functions (Direct translation of PHP regex)
def validate_user_name(name: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9_\-@.]+$', name)) and len(name) <= 50

def validate_panel_index(index: int, panels: Dict) -> bool:
    return index > 0 and index <= len(panels)

def validate_telegram_id(id_str: str) -> bool:
    return bool(re.match(r'^\d+$', id_str)) and len(id_str) <= 32


# =========================================================================
# JSON FLAT FILE FUNCTIONS (File Locking is simulated with OS/Atomicity)
# =========================================================================

def get_dynamic_panels_from_json() -> Dict[str, Any]:
    if not os.path.exists(DYNAMIC_PANELS_FILE):
        return {}
    try:
        with open(DYNAMIC_PANELS_FILE, 'r') as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}
    
    dynamic_panels = {}
    for panel in data:
        name = panel.get('name', f"DB_Panel_{panel.get('id', uuid.uuid4().hex)}")
        dynamic_panels[name] = {
            'url': panel.get('url', ''),
            'username': panel.get('username', ''),
            'password': panel.get('password', ''),
            'type': panel.get('type', 'Premium'),
            'id': panel.get('id', uuid.uuid4().hex),
        }
    return dynamic_panels

def save_panels_to_json(panels: Dict[str, Any]) -> bool:
    # Convert associative dict back to simple list format for JSON storage
    panel_list = list(panels.values())
    content = json.dumps(panel_list, indent=4, ensure_ascii=False)
    
    try:
        # Using atomic write operation (write to temp, rename) for basic safety
        temp_file = DYNAMIC_PANELS_FILE + '.tmp'
        with open(temp_file, 'w') as f:
            f.write(content)
        os.replace(temp_file, DYNAMIC_PANELS_FILE)
        return True
    except Exception:
        return False

# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

# Generate Random Key
def generate_random_key(length: int = 32) -> str:
    characters = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()-_+=[]{}:;,.|'
    return ''.join(os.urandom(length).hex() for _ in range(math.ceil(length / 2)))[:length]

# Format Bytes
def format_bytes(bytes_val: int, precision: int = 2) -> Dict[str, Union[int, str]]:
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB']
    if bytes_val <= 0:
        return {'value': 0, 'unit': 'B', 'text': '0 B'}
    if bytes_val == -1:
        return {'value': 0, 'unit': t('traffic_unlimited', 'en'), 'text': t('traffic_unlimited', 'en')}
    
    power = min(int(math.floor(math.log(bytes_val, 1024))), len(units) - 1)
    value = round(bytes_val / (1024 ** power), precision)
    return {'value': value, 'unit': units[power], 'text': f"{value} {units[power]}"}

# Format Expiry Time
def format_expiry_time(timestamp: int, lang: str = 'en') -> Dict[str, Union[int, str]]:
    if timestamp > 1000000000000:
        timestamp //= 1000
    
    if timestamp == 0:
        return {
            'timestamp': 0, 'formatted': t('expiry_never', lang),
            'detailed': t('expiry_never', lang), 'days_remaining': -1, 'status': 'active'
        }
    
    now = int(time.time())
    remaining = timestamp - now
    
    if remaining <= 0:
        return {
            'timestamp': timestamp, 'formatted': t('expiry_expired', lang),
            'detailed': t('expiry_expired', lang), 'days_remaining': 0, 'status': 'expired'
        }
    
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    minutes = (remaining % 3600) // 60
    
    time_parts = []
    if days > 0: time_parts.append(f"{days} Day{'s' if days != 1 else ''}")
    if hours > 0: time_parts.append(f"{hours} Hour{'s' if hours != 1 else ''}")
    if minutes > 0 or not time_parts: time_parts.append(f"{minutes} Minute{'s' if minutes != 1 else ''}")

    return {
        'timestamp': timestamp, 'formatted': ' '.join(filter(None, time_parts)),
        'detailed': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S'),
        'days_remaining': days, 'status': 'expiring_soon' if days <= 7 else 'active'
    }

def clean_percentage(percentage: float) -> str:
    return f"{min(100, max(0, int(round(percentage))))}%"

# Parse V2Ray Config (simplified for Python)
def parse_v2ray_config(config: str) -> Dict[str, str]:
    config = config.strip()
    
    if '@' in config and '.' in config:
        if config.startswith('vmess://'):
            try:
                decoded = base64.b64decode(config[8:], validate=True).decode()
                json_data = json.loads(decoded)
                id_val = json_data.get('id', '')
                return {'type': 'vmess', 'value': id_val, 'email': json_data.get('ps', id_val), 'method': json_data.get('scy', 'auto')}
            except Exception:
                pass
        elif config.startswith('vless://'):
            uuid_val = config[8:].split('@')[0]
            return {'type': 'vless', 'value': uuid_val, 'email': uuid_val, 'method': 'none'}
        elif config.startswith('trojan://'):
            password = config[9:].split('@')[0]
            return {'type': 'trojan', 'value': password, 'email': password, 'method': 'tls'}
        elif config.startswith('ss://'):
            parts = config[5:].split('@')
            if len(parts) == 2:
                try:
                    auth_decoded = base64.b64decode(parts[0] + '=' * (-len(parts[0]) % 4)).decode()
                    auth_parts = auth_decoded.split(':')
                    password = auth_parts[-1]
                    method = auth_parts[0] if len(auth_parts) > 1 else SHADOWSOCKS_METHOD
                    return {'type': 'shadowsocks', 'value': password, 'email': password, 'method': method}
                except Exception:
                    pass
    
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', config, re.IGNORECASE):
        return {'type': 'uuid', 'value': config, 'email': config, 'method': 'auto'}
        
    if validate_user_name(config):
        return {'type': 'email', 'value': config, 'email': config}
        
    return {'error': 'Configuration parsing failed: Invalid or unsupported format.'}

# Create Config Link
def create_config_link(panel_url: str, port: int, client: Dict[str, Any], protocol: str) -> str:
    match = re.search(r'https?:\/\/([^\/:]+)', panel_url)
    server_host = match.group(1) if match else 'unknown_host'
    email = client.get('email', 'Account')
    remark = urllib.parse.quote(email.replace(' ', '-'))

    if protocol == 'shadowsocks':
        password = client.get('password', '')
        method = client.get('method', SHADOWSOCKS_METHOD)
        encoded_auth = base64.b64encode(f"{method}:{password}".encode()).decode().rstrip('=')
        return f"ss://{encoded_auth}@{server_host}:{port}#{remark}"
    elif protocol == 'vless':
        id_val = client.get('id', '')
        return f"vless://{id_val}@{server_host}:{port}?security=none&type=tcp#{remark}"
    elif protocol == 'vmess':
        id_val = client.get('id', '')
        vmess_json = {
            "v": "2", "ps": email.replace(' ', '-'), "add": server_host, "port": port,
            "id": id_val, "aid": 0, "net": "tcp", "type": "none", "host": "", "path": "", "tls": ""
        }
        encoded_json = base64.b64encode(json.dumps(vmess_json).encode()).decode()
        return f"vmess://{encoded_json}"
    elif protocol == 'trojan':
        password = client.get('password', '')
        return f"trojan://{password}@{server_host}:{port}?security=tls&type=tcp#{remark}"
    else:
        return "N/A - Protocol Not Supported in Link Generation"

# Format API Response
def format_api_response(data: Dict[str, Any], success: bool = True, lang: str = 'en') -> str:
    if 'up' in data or 'down' in data or 'total' in data:
        total = int(data.get('total', 0))
        used = int(data.get('up', 0)) + int(data.get('down', 0))
        data['traffic'] = {
            'upload': format_bytes(int(data.get('up', 0))),
            'download': format_bytes(int(data.get('down', 0))),
            'total': format_bytes(-1) if total <= 0 else format_bytes(total),
            'used': format_bytes(used),
            'remaining': format_bytes(-1) if total <= 0 else format_bytes(max(0, total - used)),
            'usage_percentage': clean_percentage((used / total) * 100) if total > 0 else '0%'
        }
    if 'expiryTime' in data:
        expiry = format_expiry_time(int(data['expiryTime']), lang)
        data['expiry'] = {'remaining_time': expiry['formatted'], 'expiry_date': expiry['detailed'], 'days_remaining': expiry['days_remaining'], 'status': expiry['status']}
        del data['expiryTime']
    
    if 'status' in data and data['status'] in TRANSLATIONS[lang]:
        data['status'] = t(data['status'], lang)
    
    response = {
        'api': API_INFO,
        'data': data,
        'timestamp': int(time.time()),
        'success': success and 'error' not in data,
        'language': lang
    }
    return json.dumps(response, indent=4, ensure_ascii=False)


# =========================================================================
# API HELPER FUNCTIONS (Using Python Requests)
# =========================================================================

import requests

def api_login(panel_url: str, username: str, password: str) -> Union[str, bool]:
    url = f"{panel_url.rstrip('/')}/login"
    data = {'username': username, 'password': password}
    try:
        response = requests.post(url, data=data, headers={'User-Agent': USER_AGENT}, timeout=15, verify=False, allow_redirects=True)
        response.raise_for_status() # Raises an exception for 4xx or 5xx status codes
        
        # Extract cookie from response headers
        if 'set-cookie' in response.headers:
            # Join multiple set-cookie headers into a single Cookie header string
            cookie_header = "; ".join([cookie.split(';')[0] for cookie in response.headers.get_all('set-cookie')])
            return cookie_header if cookie_header else False
        return False
    except requests.RequestException as e:
        # print(f"Login failed for {panel_url}: {e}")
        return False

def api_call(panel_url: str, cookie_header: str, endpoint: str, data: Dict[str, Any] = None) -> Union[Dict[str, Any], bool]:
    def do_call():
        url = f"{panel_url.rstrip('/')}/{endpoint}"
        headers = {
            "Cookie": cookie_header,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT
        }
        
        try:
            if data is not None:
                response = requests.post(url, json=data, headers=headers, timeout=15, verify=False)
            else:
                response = requests.post(url, headers=headers, timeout=15, verify=False)
                
            response.raise_for_status()
            
            json_data = response.json()
            if isinstance(json_data, dict) and 'success' in json_data:
                return json_data
            return False
        except requests.RequestException as e:
            # print(f"API call failed on {url}: {e}")
            return False
        except json.JSONDecodeError:
            # print(f"API call failed: Invalid JSON response from {url}")
            return False

    return handle_api_call_with_retry(do_call)

def handle_api_call_with_retry(api_call_func: Callable, max_retries: int = 2) -> Union[Dict[str, Any], bool]:
    for attempt in range(max_retries + 1):
        result = api_call_func()
        if result is not False:
            return result
        if attempt < max_retries:
            time.sleep(1)
    return False

# Find Client in All Panels
def find_client_in_all_panels(user_name: str, panels: Dict[int, Any]) -> Union[Dict[str, Any], bool]:
    # Merge Premium panels with dynamic JSON panels for comprehensive search
    all_panels_to_check = panels.copy()
    dynamic_panels = get_dynamic_panels_from_json()
    
    # Add dynamic panels as new numbered indices if they are 'Premium' type
    dynamic_premium_index = len(PREMIUM_PANELS) + 1
    for name, config in dynamic_panels.items():
        if config.get('type') == 'Premium':
            all_panels_to_check[dynamic_premium_index] = {
                'name': name,
                'config': config
            }
            dynamic_premium_index += 1

    for panel_index, panel in all_panels_to_check.items():
        panel_url = panel['config']['url']
        panel_name = panel['name']
        cookie_header = api_login(panel_url, panel['config']['username'], panel['config']['password'])

        if not cookie_header:
            continue

        inbound_list = api_call(panel_url, cookie_header, 'xui/inbound/list')
        if not inbound_list or 'obj' not in inbound_list:
            continue

        for inbound in inbound_list['obj']:
            try:
                settings = json.loads(inbound.get('settings', '[]'))
            except json.JSONDecodeError:
                settings = {}

            clients = settings.get('clients', [])

            for client_index, client in enumerate(clients):
                # Check if the email matches the username
                if client.get('email', '') == user_name:
                    
                    protocol = inbound.get('protocol', 'unknown').lower()
                    client_uid = client.get('id') or client.get('password') or client.get('email')

                    return {
                        'panel_index': panel_index,
                        'panel_name': panel_name,
                        'panel_url': panel_url,
                        'cookie_header': cookie_header,
                        'inbound_id': inbound['id'],
                        'inbound_port': inbound['port'],
                        'client_index': client_index,
                        'client_email': user_name,
                        'protocol': protocol,
                        'client_data': client,
                        'client_uid': client_uid,
                        'inbound_protocol_settings': settings,
                        'all_clients': clients
                    }
    return False

# =========================================================================
# ACCOUNT MANAGEMENT FUNCTIONS (Direct PHP Logic Translation)
# =========================================================================

# (All PHP management functions are directly translated, with network calls
# using the new Python helper functions. For brevity, only the main structure
# is shown here, as the functions' logic is extensive and mostly identical
# to the PHP version's implementation details.)

# Helper to load all panels, including dynamic ones, for main check function
def get_all_panels_for_check() -> Dict[str, Any]:
    # panels.php format (nested)
    static_panels: Dict[str, Any] = {}
    for name, data in ALL_PANELS_CONFIG.items():
        static_panels[name] = data
    
    # JSON file format (flat)
    dynamic_panels = get_dynamic_panels_from_json()
    
    # Merge, prioritizing static names if clash (though structure is different)
    return {**static_panels, **dynamic_panels}


# This function's logic is nearly identical to the PHP version, using the
# Python helper functions and data structures.
def check_v2ray_account(parsed_config: Dict[str, str], all_panels_config: Dict[str, Any]) -> Dict[str, Any]:
    all_panels_to_check = get_all_panels_for_check()
    lang = get_client_language()

    for panel_name, panel_config in all_panels_to_check.items():
        # Handle two possible structures: panels.php (nested 'config') vs JSON (flat)
        panel_url = panel_config.get('url') or panel_config.get('config', {}).get('url')
        username = panel_config.get('username') or panel_config.get('config', {}).get('username')
        password = panel_config.get('password') or panel_config.get('config', {}).get('password')
        
        if not panel_url or not username or not password:
            continue
            
        cookie_header = api_login(panel_url, username, password)

        if not cookie_header:
            continue
            
        inbound_list = api_call(panel_url, cookie_header, 'xui/inbound/list')
        if not inbound_list or 'obj' not in inbound_list:
            continue

        for inbound in inbound_list['obj']:
            try:
                settings = json.loads(inbound.get('settings', '[]'))
            except json.JSONDecodeError:
                settings = {}
            clients = settings.get('clients', [])
            client_stats = inbound.get('clientStats') or inbound.get('clientInfo', [])
            
            for client in clients:
                client_id = ''
                match parsed_config['type']:
                    case 'email':
                        client_id = client.get('email', '')
                    case 'vmess' | 'vless' | 'uuid':
                        client_id = client.get('id', '')
                    case 'shadowsocks' | 'trojan':
                        client_id = client.get('password', '')
                
                if client_id.lower() == parsed_config['value'].lower():
                    client_email = client.get('email', '')
                    stat = next((s for s in client_stats if s.get('email') == client_email), None)
                    
                    if stat:
                        total_gb = client.get('totalGB', 0)
                        total_bytes = total_gb if total_gb > 1000000 else total_gb * 1073741824
                        
                        return {
                            'panel_name': panel_name,
                            'protocol': inbound.get('protocol', 'unknown').lower(),
                            'email': client_email,
                            'up': int(stat.get('up', 0)),
                            'down': int(stat.get('down', 0)),
                            'total': total_bytes,
                            'expiryTime': int(client.get('expiryTime', 0)),
                            'enable': bool(client.get('enable', True)),
                            'matched_by': parsed_config['type']
                        }

    return {'error': t('account_not_found', lang)}

# ... (Other main functions like create_trial_account, create_premium_account,
# delete_premium_account, modify_account_details, toggle_account_status,
# reset_account_traffic, transfer_account, get_online_users, and
# delete_expired_trial_accounts would be fully implemented here.)

# --- Dummy implementation for required management functions ---
def modify_account_details(user_name: str, panel_index: int, new_gb_limit: int, new_expiry_days: int, lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Modification function not fully implemented in Python placeholder.'}

def toggle_account_status(user_name: str, panel_index: int, enable: bool, lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Toggle status function not fully implemented in Python placeholder.'}

def reset_account_traffic(user_name: str, panel_index: int, lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Traffic reset function not fully implemented in Python placeholder.'}

def transfer_account(user_name: str, from_panel_index: int, to_panel_index: int, panels: Dict[int, Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Transfer function not fully implemented in Python placeholder.'}

def delete_premium_account(user_name: str, panel_index: int, panels: Dict[int, Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Premium delete function not fully implemented in Python placeholder.'}

def create_trial_account(telegram_user_id: str, trial_panels: List[Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Trial create function not fully implemented in Python placeholder.'}

def delete_trial_account(telegram_user_id: str, trial_panels: List[Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Trial delete function not fully implemented in Python placeholder.'}

def get_trial_account_key(telegram_user_id: str, trial_panels: List[Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Trial key retrieve function not fully implemented in Python placeholder.'}

def delete_expired_trial_accounts(trial_panels: List[Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Expired trial delete function not fully implemented in Python placeholder.'}

def get_online_users(all_panels_config: Dict[str, Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Online users function not fully implemented in Python placeholder.'}

def get_system_stats(premium_panels: Dict[int, Any], trial_panels: List[Any], all_panels_config: Dict[str, Any]) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'System stats function not fully implemented in Python placeholder.'}

def get_traffic_analytics(all_panels_config: Dict[str, Any], period: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Traffic analytics function not fully implemented in Python placeholder.'}

def get_optimal_panel_for_creation(panels: Dict[int, Any], account_type: str) -> int:
    # Placeholder for the actual logic
    return next(iter(panels.keys()), 1)

def create_premium_account(gb_limit: int, user_name: str, time_limit_days: int, panel_index: int, protocol: str, tier: str, premium_panels: Dict[int, Any], lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Premium create function not fully implemented in Python placeholder.'}

# JSON Panel Management Dummies
def add_panel_to_json(name: str, url: str, username: str, password: str, type_str: str, lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Add panel function not fully implemented in Python placeholder.'}

def delete_panel_from_json(id_str: str, lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'Delete panel function not fully implemented in Python placeholder.'}

def list_panels_from_json(lang: str) -> Dict[str, Any]:
    # Placeholder for the actual logic
    return {'error': t('system_error', lang), 'details': 'List panels function not fully implemented in Python placeholder.'}


# =========================================================================
# FLASK ROUTING (PHP's main Request Handler)
# =========================================================================

@app.route('/', methods=['GET', 'POST', 'OPTIONS'])
@rate_limit_required
def handle_request_route():
    lang = get_client_language()
    
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response, 200

    # Parse input from GET or POST JSON body
    input_data = {}
    if request.method == 'POST':
        try:
            input_data = request.json
        except:
            input_data = {}
            
    # Merge GET args with POST body, prioritizing GET
    args = request.args.to_dict()
    for key, value in input_data.items():
        if key not in args:
            args[key] = value

    try:
        # Extract parameters (similar to PHP's $_GET / $input)
        gb_limit = int(args.get('key', 0))
        user_name = args.get('name', '')
        time_limit = int(args.get('exp', 0))
        panel_index = int(args.get('panel', 0))
        config = args.get('config', '')
        
        protocol = args.get('protocol', DEFAULT_PREMIUM_PROTOCOL).lower()
        tier = args.get('tier', DEFAULT_PREMIUM_TIER)

        mod_user = args.get('mod', '')
        # mod_pass is removed
        toggle_user = args.get('toggle', '')
        enable_status = args.get('status', 'true').lower() in ('true', '1')
        reset_user = args.get('reset_traffic', '')
        
        delete_id = args.get('delete', '')
        delete_expired = 'delexp' in args
        trial_key_id = args.get('trialkey', '')
        trial_id = args.get('trial', '')
        stats = 'stats' in args
        analytics = 'analytics' in args
        
        transfer = args.get('transfer', '')
        from_panel = int(args.get('from_panel', 0))
        to_panel = int(args.get('to_panel', 0))
        optimal_panel = 'optimal' in args
        online_users = 'online' in args
        
        # JSON Bot Parameters
        add_panel_name = args.get('add_panel', '')
        add_url = args.get('add_url', '')
        add_user = args.get('add_user', '')
        add_pass = args.get('add_pass', '')
        add_type = args.get('add_type', 'Premium')
        delete_panel_id = args.get('del_panel', '')
        list_panels = 'list_panels' in args

        # --- NEW ENDPOINT ROUTING (JSON Panel Management for Bot) ---
        if list_panels:
            list_result = list_panels_from_json(lang)
            return format_api_response(list_result, not list_result.get('error'), lang), 200

        if add_panel_name and add_url and add_user and add_pass:
            if not re.match(r'https?:\/\/[^\s]+', add_url):
                return format_api_response({'error': 'Invalid panel URL format.'}, False, lang), 400
            add_result = add_panel_to_json(add_panel_name, add_url, add_user, add_pass, add_type, lang)
            return format_api_response(add_result, not add_result.get('error'), lang), 200
            
        if delete_panel_id:
            delete_result = delete_panel_from_json(delete_panel_id, lang)
            return format_api_response(delete_result, not delete_result.get('error'), lang), 200

        # --- EXISTING ENDPOINT ROUTING ---
        if online_users:
            online_result = get_online_users(ALL_PANELS_CONFIG, lang)
            return format_api_response(online_result, not online_result.get('error'), lang), 200

        if mod_user and panel_index > 0:
            if not validate_user_name(mod_user):
                 return format_api_response({'error': t('invalid_username', lang) + ' for modification'}, False, lang), 400
            mod_result = modify_account_details(mod_user, panel_index, gb_limit, time_limit, lang)
            return format_api_response(mod_result, True, lang), 200

        if toggle_user and panel_index > 0:
            if not validate_user_name(toggle_user):
                 return format_api_response({'error': t('invalid_username', lang) + ' for toggle'}, False, lang), 400
            toggle_result = toggle_account_status(toggle_user, panel_index, enable_status, lang)
            return format_api_response(toggle_result, True, lang), 200
            
        if reset_user and panel_index > 0:
            if not validate_user_name(reset_user):
                 return format_api_response({'error': t('invalid_username', lang) + ' for traffic reset'}, False, lang), 400
            reset_result = reset_account_traffic(reset_user, panel_index, lang)
            return format_api_response(reset_result, True, lang), 200

        if gb_limit > 0 and user_name and panel_index > 0:
            premium_result = create_premium_account(gb_limit, user_name, time_limit, panel_index, protocol, tier, PREMIUM_PANELS, lang)
            return format_api_response(premium_result, True, lang), 200

        if stats:
            system_stats = get_system_stats(PREMIUM_PANELS, TRIAL_PANELS, ALL_PANELS_CONFIG)
            return format_api_response(system_stats, True, lang), 200

        if analytics:
            period = args.get('period', '7d')
            traffic_analytics = get_traffic_analytics(ALL_PANELS_CONFIG, period)
            return format_api_response(traffic_analytics, True, lang), 200

        if optimal_panel:
            account_type = args.get('type', 'premium')
            panels_to_use = PREMIUM_PANELS if account_type == 'premium' else TRIAL_PANELS
            optimal_index = get_optimal_panel_for_creation(panels_to_use, account_type)
            panel_name = panels_to_use.get(optimal_index, {}).get('name', 'Unknown')
            return format_api_response({'optimal_panel': optimal_index, 'panel_name': panel_name, 'account_type': account_type}, True, lang), 200

        if transfer and from_panel > 0 and to_panel > 0:
            if not validate_user_name(transfer):
                return format_api_response({'error': t('invalid_username', lang) + ' for transfer'}, False, lang), 400
            if from_panel == to_panel:
                return format_api_response({'error': 'Source and destination panels cannot be the same.'}, False, lang), 400
            
            transfer_result = transfer_account(transfer, from_panel, to_panel, PREMIUM_PANELS, lang)
            return format_api_response(transfer_result, not transfer_result.get('error'), lang), 200

        if config:
            parsed = parse_v2ray_config(config)
            if 'error' in parsed:
                return format_api_response(parsed, False, lang), 400
            account_info = check_v2ray_account(parsed, ALL_PANELS_CONFIG)
            return format_api_response(account_info, True, lang), 200

        if trial_key_id:
            if not validate_telegram_id(trial_key_id):
                return format_api_response({'error': t('invalid_telegram_id', lang)}, False, lang), 400
            key_result = get_trial_account_key(trial_key_id, TRIAL_PANELS, lang)
            return format_api_response(key_result, True, lang), 200

        if delete_expired:
            if panel_index > 0:
                if not validate_panel_index(panel_index, PREMIUM_PANELS):
                    return format_api_response({'error': t('invalid_panel', lang) + ' for premium deletion'}, False, lang), 400
                delete_result = {'error': 'Delete Expired Premium function is omitted.'} # Original PHP comment preserved
            else:
                delete_result = delete_expired_trial_accounts(TRIAL_PANELS, lang)
            return format_api_response(delete_result, True, lang), 200

        if delete_id:
            identifier = delete_id
            if panel_index > 0:
                if not validate_panel_index(panel_index, PREMIUM_PANELS):
                    return format_api_response({'error': t('invalid_panel', lang) + ' for premium deletion'}, False, lang), 400
                if not validate_user_name(identifier):
                    return format_api_response({'error': t('invalid_username', lang) + ' for deletion'}, False, lang), 400
                delete_result = delete_premium_account(identifier, panel_index, PREMIUM_PANELS, lang)
            else:
                if not validate_telegram_id(identifier):
                    return format_api_response({'error': t('invalid_telegram_id', lang) + ' for deletion'}, False, lang), 400
                delete_result = delete_trial_account(identifier, TRIAL_PANELS, lang)
            return format_api_response(delete_result, True, lang), 200

        if trial_id:
            if not validate_telegram_id(trial_id):
                return format_api_response({'error': t('invalid_telegram_id', lang)}, False, lang), 400
            trial_result = create_trial_account(trial_id, TRIAL_PANELS, lang)
            return format_api_response(trial_result, True, lang), 200

        # Default Response
        return format_api_response({
            'status': 'API is running',
            'language': lang,
            'message': 'No valid action provided. Check documentation for usage.'
        }, True, lang), 200
        
    except Exception as e:
        import traceback
        app.logger.error(f'API Error: {e}\n{traceback.format_exc()}')
        
        error_response = {
            'error': t('system_error', lang),
            'message': f'An unexpected error occurred. Details: {str(e)}'
        }
        return format_api_response(error_response, False, lang), 500

# =========================================================================
# RUN APPLICATION (For local development or Gunicorn on Vercel)
# =========================================================================

if __name__ == '__main__':
    # Vercel-specific configuration: Vercel sets the port via environment variables.
    port = int(os.environ.get("PORT", 8080))
    # Note: On Vercel, the entry point is usually a WSGI server (like Gunicorn)
    # running 'app:app', but this ensures local testing works as requested.
    app.run(host="0.0.0.0", port=port, debug=True)

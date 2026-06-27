#!/usr/bin/env python3
"""
FarmTown Auth Module
Supports 3 auth methods:
1. Manual token (paste from browser)
2. 2captcha Turnstile solver
3. Selenium/Playwright with Phantom wallet
"""

import json
import os
import sys
import time
import base64
import asyncio
from typing import Optional, Dict

try:
    import httpx
    from solders.keypair import Keypair
except ImportError:
    print("Missing deps. Run: pip install httpx solders")
    sys.exit(1)


SUPABASE_URL = "https://irarxwyrpmmxacrbvpnz.supabase.co"

# Load Supabase anon key from file (auto-fetched from game JS)
_key_file = os.path.join(os.path.dirname(__file__), 'supabase_key.txt')
if os.path.exists(_key_file):
    with open(_key_file) as f:
        SUPABASE_ANON_KEY = f.read().strip()
else:
    SUPABASE_ANON_KEY = ""

TURNSTILE_SITEKEY = "0x4AAAAAADn068lY1uOdr9LV"
FARM_DOMAIN = "play.farmtown.online"

TOKEN_FILE = "session.json"
WALLET_FILE = "wallet.json"


# ============================================================
# METHOD 1: Manual Token
# ============================================================

def auth_manual_token() -> Optional[dict]:
    """Paste Supabase token from browser DevTools"""
    print("\n" + "="*50)
    print("  MANUAL TOKEN EXTRACTION")
    print("="*50)
    print("""
Langkah:
1. Buka https://play.farmtown.online di browser
2. Login dengan Phantom wallet
3. Buka DevTools (F12) → Application → Local Storage
4. Cari key yang mengandung 'supabase' dan 'auth-token'
5. Copy value-nya (JSON dengan access_token)
6. Paste di sini

Atau lebih gampang:
1. Buka Console di DevTools
2. Ketik: JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.includes('auth-token'))))
3. Copy output-nya
""")
    
    raw = input("Paste token JSON (atau langsung access_token string): ").strip()
    
    if not raw:
        return None
    
    try:
        data = json.loads(raw)
        if 'access_token' in data:
            return {
                'access_token': data['access_token'],
                'refresh_token': data.get('refresh_token'),
                'user_id': data.get('user', {}).get('id') or data.get('user_id'),
            }
        # Maybe it's the full Supabase session format
        if 'currentSession' in data:
            session = data['currentSession']
            return {
                'access_token': session.get('access_token'),
                'refresh_token': session.get('refresh_token'),
                'user_id': session.get('user', {}).get('id'),
            }
    except json.JSONDecodeError:
        # Maybe it's just the raw token string
        if len(raw) > 100 and '.' in raw:
            return {'access_token': raw}
    
    print("[ERROR] Format token tidak dikenali")
    return None


# ============================================================
# METHOD 2: 2captcha Turnstile Solver
# ============================================================

async def auth_2captcha(api_key: str, keypair: Keypair) -> Optional[dict]:
    """Use 2captcha to solve Turnstile, then authenticate with Supabase"""
    
    print(f"\n[2CAPTCHA] Solving Turnstile (sitekey: {TURNSTILE_SITEKEY})...")
    
    async with httpx.AsyncClient(timeout=120) as client:
        # Submit Turnstile task
        submit_resp = await client.post("https://api.2captcha.com/createTask", json={
            "clientKey": api_key,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": f"https://{FARM_DOMAIN}",
                "websiteKey": TURNSTILE_SITEKEY,
            }
        })
        
        submit_data = submit_resp.json()
        if submit_data.get('errorId'):
            print(f"[2CAPTCHA] Error: {submit_data.get('errorDescription')}")
            return None
        
        task_id = submit_data.get('taskId')
        print(f"[2CAPTCHA] Task submitted: {task_id}")
        
        # Poll for result
        for i in range(60):
            await asyncio.sleep(3)
            
            result_resp = await client.post("https://api.2captcha.com/getTaskResult", json={
                "clientKey": api_key,
                "taskId": task_id,
            })
            
            result_data = result_resp.json()
            
            if result_data.get('status') == 'ready':
                captcha_token = result_data.get('solution', {}).get('token')
                print(f"[2CAPTCHA] Solved! Token: {captcha_token[:40]}...")
                
                # Now authenticate with Supabase
                return await _authenticate_solana(keypair, captcha_token)
            
            if result_data.get('errorId'):
                print(f"[2CAPTCHA] Error: {result_data.get('errorDescription')}")
                return None
            
            if i % 5 == 0:
                print(f"[2CAPTCHA] Waiting for solve... ({i*3}s)")
    
    print("[2CAPTCHA] Timeout waiting for solve")
    return None


# ============================================================
# METHOD 3: Selenium/Playwright with Phantom Wallet
# ============================================================

async def auth_phantom_browser(keypair: Keypair, headless: bool = False) -> Optional[dict]:
    """Use Playwright to open FarmTown, inject wallet, authenticate"""
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[PHANTOM] Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None
    
    public_key = str(keypair.pubkey())
    secret_bytes = list(bytes(keypair))
    
    print(f"\n[PHANTOM] Opening browser with wallet: {public_key[:20]}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        # Track Supabase token from network
        token_data = {}
        
        async def on_response(response):
            url = response.url
            if 'supabase.co/auth/v1/token' in url:
                try:
                    body = await response.json()
                    if 'access_token' in body:
                        token_data['access_token'] = body['access_token']
                        token_data['refresh_token'] = body.get('refresh_token')
                        token_data['user_id'] = body.get('user', {}).get('id')
                        print(f"[PHANTOM] Got token! User: {token_data.get('user_id')}")
                except:
                    pass
        
        page.on('response', on_response)
        
        # Inject Phantom wallet before page loads
        await page.add_init_script(f"""
            // Minimal Phantom wallet shim
            const SECRET_KEY = new Uint8Array({json.dumps(secret_bytes)});
            const PUBLIC_KEY = "{public_key}";
            
            // Ed25519 signing using tweetnacl (loaded from CDN)
            async function loadNacl() {{
                if (window._nacl) return window._nacl;
                return new Promise((resolve, reject) => {{
                    const s = document.createElement('script');
                    s.src = 'https://cdn.jsdelivr.net/npm/tweetnacl@1.0.3/nacl-fast.min.js';
                    s.onload = () => {{ window._nacl = window.nacl; resolve(window.nacl); }};
                    s.onerror = reject;
                    document.head.appendChild(s);
                }});
            }}
            
            async function ed25519Sign(message) {{
                const nacl = await loadNacl();
                const msgBytes = typeof message === 'string' 
                    ? new TextEncoder().encode(message) 
                    : message;
                const sig = nacl.sign.detached(msgBytes, SECRET_KEY);
                return sig;
            }}
            
            // Base58 decode for public key bytes
            function base58Decode(str) {{
                const ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
                let num = BigInt(0);
                for (const c of str) {{
                    num = num * BigInt(58) + BigInt(ALPHABET.indexOf(c));
                }}
                const bytes = new Uint8Array(32);
                for (let i = 31; i >= 0; i--) {{
                    bytes[i] = Number(num & BigInt(255));
                    num >>= BigInt(8);
                }}
                return bytes;
            }}
            
            const pubKeyBytes = base58Decode(PUBLIC_KEY);
            
            const phantomProvider = {{
                isPhantom: true,
                isConnected: false,
                publicKey: {{
                    toString: () => PUBLIC_KEY,
                    toBase58: () => PUBLIC_KEY,
                    toBytes: () => pubKeyBytes,
                    _bn: null,
                }},
                connect: async (opts) => {{
                    phantomProvider.isConnected = true;
                    console.log('[PHANTOM] Connected');
                    return {{ publicKey: phantomProvider.publicKey }};
                }},
                disconnect: async () => {{
                    phantomProvider.isConnected = false;
                }},
                signMessage: async (message, encoding) => {{
                    console.log('[PHANTOM] Signing message');
                    const sig = await ed25519Sign(
                        typeof message === 'string' ? message : new TextDecoder().decode(message)
                    );
                    if (encoding === 'utf8') {{
                        return {{ signature: sig, publicKey: phantomProvider.publicKey }};
                    }}
                    return sig;
                }},
                signIn: async (input) => {{
                    console.log('[PHANTOM] signIn called');
                    const domain = input?.domain || window.location.host;
                    const uri = input?.uri || window.location.href;
                    const issuedAt = input?.issuedAt || new Date().toISOString();
                    
                    const message = [
                        domain + ' wants you to sign in with your Solana account:',
                        PUBLIC_KEY,
                        '',
                        (input?.statement || ''),
                        '',
                        'Version: 1',
                        'URI: ' + uri,
                        'Issued At: ' + issuedAt,
                    ].join('\\n');
                    
                    const sig = await ed25519Sign(message);
                    
                    return [{{
                        signedMessage: message,
                        signature: sig
                    }}];
                }},
                _events: {{}},
                on(event, fn) {{ (this._events[event] = this._events[event] || []).push(fn); }},
                emit(event, ...args) {{ (this._events[event] || []).forEach(fn => fn(...args)); }},
                removeAllListeners() {{ this._events = {{}}; }},
            }};
            
            window.phantom = {{ solana: phantomProvider, isPhantom: true }};
            window.solana = phantomProvider;
            console.log('[PHANTOM] Wallet shim installed');
        """)
        
        # Navigate
        await page.goto(f"https://{FARM_DOMAIN}", wait_until='networkidle', timeout=30000)
        print("[PHANTOM] Page loaded")
        
        # Set farmer name
        await asyncio.sleep(2)
        name_input = page.locator('input[type="text"]').first
        if await name_input.count() > 0:
            await name_input.fill(f"Bot_{int(time.time()) % 10000}")
        
        # Click "Connect Phantom"
        connect_btn = page.locator('button:has-text("Connect Phantom")')
        if await connect_btn.count() > 0:
            print("[PHANTOM] Clicking Connect Phantom...")
            await connect_btn.click()
            await asyncio.sleep(8)
        
        # Wait for token
        print("[PHANTOM] Waiting for auth token...")
        for i in range(30):
            if 'access_token' in token_data:
                break
            
            # Check localStorage
            stored = await page.evaluate("""() => {
                const keys = Object.keys(localStorage);
                for (const k of keys) {
                    if (k.includes('auth-token') || k.includes('supabase')) {
                        try {
                            const v = JSON.parse(localStorage.getItem(k));
                            if (v && v.access_token) return v;
                            if (v && v.currentSession) return v.currentSession;
                        } catch(e) {}
                    }
                }
                return null;
            }""")
            
            if stored and stored.get('access_token'):
                token_data = stored
                print("[PHANTOM] Got token from localStorage!")
                break
            
            if i % 5 == 0 and i > 0:
                print(f"[PHANTOM] Waiting... ({i*2}s)")
            
            await asyncio.sleep(2)
        
        await browser.close()
    
    if 'access_token' in token_data:
        return token_data
    
    print("[PHANTOM] Failed to get token")
    return None


# ============================================================
# SHARED: Supabase Authentication
# ============================================================

async def _authenticate_solana(keypair: Keypair, captcha_token: str) -> Optional[dict]:
    """Call Supabase signInWithSolana with captcha token"""
    
    public_key = str(keypair.pubkey())
    domain = FARM_DOMAIN
    uri = f"https://{domain}"
    issued_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    message = "\n".join([
        f"{domain} wants you to sign in with your Solana account:",
        public_key,
        "", "",
        "Version: 1",
        f"URI: {uri}",
        f"Issued At: {issued_at}",
    ])
    
    sig = keypair.sign_message(message.encode('utf-8'))
    sig_b64 = base64.b64encode(bytes(sig)).decode()
    
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=web3"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Origin": f"https://{domain}",
    }
    payload = {
        "chain": "solana",
        "message": message,
        "signature": sig_b64,
        "wallet": public_key,
        "gotrue_meta_security": {"captcha_token": captcha_token},
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "user_id": data.get("user", {}).get("id"),
            }
        else:
            print(f"[AUTH] Failed: {resp.status_code} - {resp.text[:300]}")
            return None


# ============================================================
# Token Management
# ============================================================

def save_token(token_data: dict, filepath: str = TOKEN_FILE):
    """Save token to file"""
    with open(filepath, 'w') as f:
        json.dump(token_data, f, indent=2)
    print(f"[TOKEN] Saved to {filepath}")


def load_token(filepath: str = TOKEN_FILE) -> Optional[dict]:
    """Load token from file"""
    if not os.path.exists(filepath):
        return None
    
    with open(filepath) as f:
        data = json.load(f)
    
    token = data.get('access_token', '')
    if not token:
        return None
    
    # Check if token is still valid
    try:
        parts = token.split('.')
        if len(parts) == 3:
            payload = json.loads(base64.b64decode(parts[1] + '=='))
            exp = payload.get('exp', 0)
            if exp < time.time():
                print("[TOKEN] Token expired, attempting refresh...")
                refreshed = refresh_token(data)
                if refreshed:
                    return refreshed
                print("[TOKEN] Refresh failed")
                return None
            remaining = exp - time.time()
            print(f"[TOKEN] Token valid for {remaining/60:.0f} more minutes")
    except:
        pass
    
    return data


def refresh_token(token_data: dict, filepath: str = TOKEN_FILE) -> Optional[dict]:
    """Refresh Supabase access token using refresh_token"""
    refresh = token_data.get('refresh_token')
    if not refresh:
        print("[TOKEN] No refresh_token available")
        return None
    
    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            json={"refresh_token": refresh},
            timeout=15,
        )
        
        if resp.status_code == 200:
            data = resp.json()
            new_token = {
                'access_token': data.get('access_token'),
                'refresh_token': data.get('refresh_token', refresh),
                'expires_in': data.get('expires_in', 3600),
                'expires_at': int(time.time()) + data.get('expires_in', 3600),
                'user': token_data.get('user', {}),
            }
            save_token(new_token, filepath)
            print(f"[TOKEN] Refreshed! Valid for {new_token['expires_in']/60:.0f} minutes")
            return new_token
        else:
            print(f"[TOKEN] Refresh failed: {resp.status_code} - {resp.text[:100]}")
            return None
    except Exception as e:
        print(f"[TOKEN] Refresh error: {e}")
        return None


def load_wallet(filepath: str = WALLET_FILE) -> Keypair:
    """Load or generate wallet"""
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            return Keypair.from_bytes(f.read())
    else:
        kp = Keypair()
        with open(filepath, 'wb') as f:
            f.write(bytes(kp))
        print(f"[WALLET] Generated new wallet: {str(kp.pubkey())}")
        return kp


# ============================================================
# Wallet Verification
# ============================================================

FARMTOWN_API = "https://farmtown-three.vercel.app"

async def verify_wallet(access_token: str, keypair: Keypair, display_name: str = None) -> Optional[str]:
    """Verify wallet and return wallet_session_token"""
    import base64
    
    wallet_address = str(keypair.pubkey())
    if not display_name:
        display_name = f"Bot_{int(time.time()) % 10000}"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Step 1: Request challenge
        print(f"[WALLET] Requesting challenge for {wallet_address[:20]}...")
        challenge_resp = await client.post(
            f'{FARMTOWN_API}/api/auth/wallet/challenge',
            headers=headers,
            json={'walletAddress': wallet_address}
        )
        
        if challenge_resp.status_code != 200:
            print(f"[WALLET] Challenge failed: {challenge_resp.status_code}")
            return None
        
        cd = challenge_resp.json()
        if not cd.get('ok'):
            print(f"[WALLET] Challenge error: {cd.get('message')}")
            return None
        
        # Step 2: Sign message
        signed_message = cd['message']
        sig = keypair.sign_message(signed_message.encode('utf-8'))
        sig_b64 = base64.b64encode(bytes(sig)).decode()
        
        # Step 3: Verify
        print(f"[WALLET] Verifying signature...")
        verify_resp = await client.post(
            f'{FARMTOWN_API}/api/auth/wallet/verify',
            headers=headers,
            json={
                'challengeId': cd['challengeId'],
                'nonce': cd['nonce'],
                'walletAddress': wallet_address,
                'message': signed_message,
                'signature': sig_b64,
                'displayName': display_name,
            }
        )
        
        if verify_resp.status_code != 200:
            print(f"[WALLET] Verify failed: {verify_resp.status_code}")
            return None
        
        vr = verify_resp.json()
        if vr.get('walletVerified'):
            wst = vr.get('walletSessionToken', '')
            print(f"[WALLET] Verified! Session expires: {vr.get('walletSessionExpiresAt', '?')}")
            return wst
        else:
            print(f"[WALLET] Verification rejected: {vr.get('message')}")
            return None

#!/usr/bin/env python3
"""
FarmTown Token Extractor v3
1. Open page with Playwright
2. Wait for Turnstile to auto-render and extract the widget ID
3. Execute turnstile to get captcha token
4. Use captcha token + Solana keypair to authenticate with Supabase
"""

import asyncio
import json
import os
import sys
import time
import base64

try:
    from playwright.async_api import async_playwright
    from solders.keypair import Keypair
    import httpx
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)


FARM_URL = "https://play.farmtown.online"
SUPABASE_URL = "https://irarxwyrpmmxacrbvpnz.supabase.co"

# Load Supabase anon key from file (auto-fetched from game JS)
_key_file = os.path.join(os.path.dirname(__file__), 'supabase_key.txt')
if os.path.exists(_key_file):
    with open(_key_file) as f:
        SUPABASE_ANON_KEY = f.read().strip()
else:
    SUPABASE_ANON_KEY = ""

WALLET_FILE = "wallet.json"
TOKEN_FILE = "session.json"


async def get_turnstile_token(headless: bool = False) -> str:
    """Get Cloudflare Turnstile token using Playwright"""
    print("[TURNSTILE] Opening browser...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        # Capture any network request that contains a captcha token
        captured_tokens = []
        
        async def handle_request(request):
            post = request.post_data or ''
            if 'captcha_token' in post or 'cf-turnstile-response' in post:
                try:
                    body = json.loads(post)
                    token = body.get('gotrue_meta_security', {}).get('captcha_token')
                    if token:
                        captured_tokens.append(token)
                except:
                    pass
        
        page.on('request', handle_request)
        
        # Navigate
        await page.goto(FARM_URL, wait_until='networkidle', timeout=30000)
        print("[TURNSTILE] Page loaded")
        
        # Wait for Turnstile to load
        await asyncio.sleep(3)
        
        # Check if Turnstile iframe is present
        turnstile_info = await page.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe[src*="turnstile"], iframe[src*="challenges.cloudflare"]');
            const widgets = document.querySelectorAll('[data-sitekey]');
            const responses = document.querySelectorAll('input[name="cf-turnstile-response"]');
            let responseValues = [];
            responses.forEach(r => { if (r.value) responseValues.push(r.value.substring(0,30) + '...'); });
            return {
                iframeCount: iframes.length,
                widgetCount: widgets.length,
                responseCount: responses.length,
                responseValues: responseValues,
                turnstileExists: !!window.turnstile,
            };
        }""")
        print(f"[TURNSTILE] Info: {turnstile_info}")
        
        # Wait for turnstile to auto-solve (up to 30s)
        for i in range(30):
            # Check for response value
            token = await page.evaluate("""() => {
                const responses = document.querySelectorAll('input[name="cf-turnstile-response"]');
                for (const r of responses) {
                    if (r.value && r.value.length > 20) return r.value;
                }
                return null;
            }""")
            
            if token:
                print(f"[TURNSTILE] Got token from widget!")
                await browser.close()
                return token
            
            # Also check captured tokens
            if captured_tokens:
                print(f"[TURNSTILE] Got token from intercepted request!")
                await browser.close()
                return captured_tokens[0]
            
            if i % 5 == 0 and i > 0:
                print(f"[TURNSTILE] Waiting... ({i}s)")
            
            await asyncio.sleep(1)
        
        await browser.close()
        return None


async def authenticate_solana(keypair: Keypair, captcha_token: str = None) -> dict:
    """Authenticate with Supabase using Solana wallet sign-in"""
    
    public_key = str(keypair.pubkey())
    print(f"[AUTH] Wallet: {public_key}")
    
    domain = "play.farmtown.online"
    uri = f"https://{domain}"
    issued_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Build SIWS message (Sign-In with Solana)
    message = "\n".join([
        f"{domain} wants you to sign in with your Solana account:",
        public_key,
        "",
        "",
        "Version: 1",
        f"URI: {uri}",
        f"Issued At: {issued_at}",
    ])
    
    # Sign the message
    sig = keypair.sign_message(message.encode('utf-8'))
    sig_b64 = base64.b64encode(bytes(sig)).decode()
    msg_b64 = base64.b64encode(message.encode('utf-8')).decode()
    
    print(f"[AUTH] Signed message, calling Supabase...")
    
    # Supabase signInWithSolana endpoint
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=web3"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Origin": f"https://{domain}",
        "Referer": f"https://{domain}/",
    }
    
    payload = {
        "chain": "solana",
        "message": message,
        "signature": sig_b64,
        "wallet": public_key,
    }
    
    if captcha_token:
        payload["gotrue_meta_security"] = {"captcha_token": captcha_token}
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        
        print(f"[AUTH] Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "user_id": data.get("user", {}).get("id"),
            }
        else:
            print(f"[AUTH] Response: {resp.text[:500]}")
            
            # If captcha failed, try anonymous sign-in
            if 'captcha' in resp.text.lower():
                print("[AUTH] Captcha required. Trying anonymous sign-in...")
                return await authenticate_anonymous(captcha_token)
            
            return None


async def authenticate_anonymous(captcha_token: str = None) -> dict:
    """Try anonymous sign-in"""
    
    url = f"{SUPABASE_URL}/auth/v1/signup"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Origin": "https://play.farmtown.online",
    }
    
    payload = {}
    if captcha_token:
        payload["gotrue_meta_security"] = {"captcha_token": captcha_token}
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        print(f"[AUTH-Anon] Status: {resp.status_code}")
        print(f"[AUTH-Anon] Response: {resp.text[:500]}")
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "user_id": data.get("user", {}).get("id"),
            }
        return None


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='FarmTown Token Extractor')
    parser.add_argument('--headless', action='store_true', help='Run browser headless')
    parser.add_argument('--skip-captcha', action='store_true', help='Skip Turnstile')
    
    args = parser.parse_args()
    
    # Load wallet
    if os.path.exists(WALLET_FILE):
        with open(WALLET_FILE, 'rb') as f:
            keypair = Keypair.from_bytes(f.read())
    else:
        keypair = Keypair()
        with open(WALLET_FILE, 'wb') as f:
            f.write(bytes(keypair))
    
    print(f"[WALLET] {str(keypair.pubkey())}")
    
    # Get captcha token
    captcha_token = None
    if not args.skip_captcha:
        captcha_token = await get_turnstile_token(headless=args.headless)
        if captcha_token:
            print(f"[TURNSTILE] Token: {captcha_token[:40]}...")
        else:
            print("[TURNSTILE] Failed to get token, trying without...")
    
    # Authenticate
    result = await authenticate_solana(keypair, captcha_token)
    
    if result and result.get('access_token'):
        with open(TOKEN_FILE, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n{'='*50}")
        print(f"  SUCCESS! Token saved to {TOKEN_FILE}")
        print(f"  User: {result.get('user_id')}")
        print(f"{'='*50}")
    else:
        print(f"\nFAILED - No token obtained")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

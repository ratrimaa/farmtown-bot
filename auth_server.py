#!/usr/bin/env python3
"""
FarmTown Auth Server v3
Explicitly renders Turnstile widget, includes captcha token in auth
"""

import json
import os
import time
import re
import urllib.request
from aiohttp import web

# Fetch the real Supabase anon key
def get_supabase_key():
    try:
        url = "https://play.farmtown.online/assets/index-Df_GViRl.js"
        resp = urllib.request.urlopen(url, timeout=10)
        js = resp.read().decode('utf-8')
        match = re.search(r'anonKey[:=]`([^`]+)`', js)
        if match:
            return match.group(1)
    except:
        pass
    return None

SUPABASE_URL = "https://irarxwyrpmmxacrbvpnz.supabase.co"
SUPABASE_KEY = get_supabase_key() or ""
TOKEN_FILE = "token.json"

print(f"[INIT] Supabase key: {len(SUPABASE_KEY)} chars")

AUTH_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>FarmTown Bot Auth</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0a0a0a; color: #e0e0e0;
            min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; justify-content: center; padding: 20px;
        }}
        .card {{
            background: #1a1a1a; border: 1px solid #2a2a2a;
            border-radius: 16px; padding: 32px 24px;
            max-width: 400px; width: 100%; text-align: center;
        }}
        h1 {{ font-size: 24px; margin-bottom: 8px; color: #fff; }}
        .sub {{ color: #888; font-size: 14px; margin-bottom: 24px; }}
        .status {{
            padding: 12px 16px; border-radius: 8px;
            margin: 16px 0; font-size: 14px; font-weight: 500;
        }}
        .status.loading {{ background: #1a2a3a; color: #5b9bd5; }}
        .status.success {{ background: #1a3a1a; color: #5bd55b; }}
        .status.error {{ background: #3a1a1a; color: #d55b5b; }}
        .status.info {{ background: #2a2a1a; color: #d5c55b; }}
        button {{
            width: 100%; padding: 14px 20px; border: none;
            border-radius: 10px; font-size: 16px; font-weight: 600;
            cursor: pointer; margin: 8px 0; transition: all 0.2s;
        }}
        button:active {{ transform: scale(0.98); }}
        button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .btn-main {{
            background: linear-gradient(135deg, #ab9ff2, #7c3aed);
            color: white;
        }}
        .cf-turnstile {{
            margin: 16px auto;
            display: flex;
            justify-content: center;
        }}
        .hidden {{ display: none; }}
        .spinner {{
            display: inline-block; width: 20px; height: 20px;
            border: 2px solid #555; border-top-color: #5b9bd5;
            border-radius: 50%; animation: spin 0.8s linear infinite;
            margin-right: 8px; vertical-align: middle;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .steps {{
            text-align: left; margin: 16px 0; padding: 16px;
            background: #111; border-radius: 8px;
            font-size: 13px; line-height: 1.8;
        }}
        .steps li {{ margin-left: 16px; }}
        textarea {{
            width: 100%; height: 80px; background: #111; color: #5bd5a0;
            border: 1px solid #333; border-radius: 8px; padding: 12px;
            font-family: monospace; font-size: 12px; resize: vertical;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🌾 FarmTown Bot</h1>
        <p class="sub">Authenticate untuk auto-farming</p>
        
        <div id="status" class="status info">
            Loading security check...
        </div>

        <!-- Turnstile widget -->
        <div id="turnstile-container" class="cf-turnstile"
             data-sitekey="0x4AAAAAADn068lY1uOdr9LV"
             data-callback="onTurnstileSuccess"
             data-error-callback="onTurnstileError"
             data-expired-callback="onTurnstileExpired">
        </div>

        <!-- Main button -->
        <button class="btn-main" id="btn-auth" onclick="doAuth()" disabled>
            Connect Phantom & Sign In
        </button>

        <!-- Manual fallback -->
        <div style="margin-top: 24px; border-top: 1px solid #2a2a2a; padding-top: 16px;">
            <p style="font-size: 12px; color: #666; margin-bottom: 12px;">Atau paste token manual:</p>
            <textarea id="token-input" placeholder="Paste access_token JSON di sini..."></textarea>
            <button onclick="submitManual()" style="background: #1a3a2a; color: #5bd5a0; border: 1px solid #2a5a3a;">
                Submit Token
            </button>
        </div>
    </div>

    <!-- Turnstile script -->
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
    
    <!-- Supabase -->
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    
    <script>
        const SUPABASE_URL = "{SUPABASE_URL}";
        const SUPABASE_KEY = "{SUPABASE_KEY}";
        const SERVER_URL = window.location.origin;
        
        let turnstileToken = null;
        let supabaseClient = null;
        
        function setStatus(msg, type) {{
            const el = document.getElementById('status');
            el.className = 'status ' + type;
            el.innerHTML = msg;
        }}
        
        // Turnstile callbacks
        function onTurnstileSuccess(token) {{
            console.log('[Turnstile] Solved!', token.substring(0, 30));
            turnstileToken = token;
            document.getElementById('btn-auth').disabled = false;
            setStatus('✅ Security check passed! Tap button to sign in.', 'success');
        }}
        
        function onTurnstileError(e) {{
            console.error('[Turnstile] Error:', e);
            setStatus('❌ Security check failed. Try refreshing.', 'error');
        }}
        
        function onTurnstileExpired() {{
            console.log('[Turnstile] Expired');
            turnstileToken = null;
            document.getElementById('btn-auth').disabled = true;
            setStatus('⏰ Security check expired. Refreshing...', 'info');
            // Reset turnstile
            if (window.turnstile) {{
                turnstile.reset();
            }}
        }}
        
        // Check if Turnstile loaded
        setTimeout(() => {{
            if (!turnstileToken) {{
                const container = document.getElementById('turnstile-container');
                if (container && container.children.length === 0) {{
                    setStatus('⚠️ Security widget blocked. Try "Submit Token Manual" below.', 'error');
                }}
            }}
        }}, 10000);
        
        async function doAuth() {{
            const btn = document.getElementById('btn-auth');
            btn.disabled = true;
            
            if (!turnstileToken) {{
                setStatus('❌ No security token. Please wait for check to complete.', 'error');
                btn.disabled = false;
                return;
            }}
            
            try {{
                // Init Supabase
                if (!supabaseClient) {{
                    supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {{
                        auth: {{
                            autoRefreshToken: false,
                            persistSession: false,
                        }}
                    }});
                }}
                
                setStatus('<span class="spinner"></span>Connecting Phantom wallet...', 'loading');
                
                // Get wallet provider
                let provider = window.phantom?.solana || window.solana;
                if (!provider) {{
                    setStatus('❌ Phantom wallet not found. Open this page in Phantom app.', 'error');
                    btn.disabled = false;
                    return;
                }}
                
                // Connect wallet
                const connectResult = await provider.connect();
                const publicKey = connectResult.publicKey.toString();
                setStatus('<span class="spinner"></span>Wallet connected! Signing in...', 'loading');
                
                // Sign in with Supabase + turnstile token
                const {{ data, error }} = await supabaseClient.auth.signInWithWeb3({{
                    chain: 'solana',
                    wallet: provider,
                    statement: 'Sign in to FarmTown Bot',
                    options: {{
                        captchaToken: turnstileToken,
                    }}
                }});
                
                if (error) {{
                    setStatus('❌ Auth error: ' + error.message, 'error');
                    btn.disabled = false;
                    return;
                }}
                
                const session = data.session;
                if (session?.access_token) {{
                    setStatus('<span class="spinner"></span>Sending token to server...', 'loading');
                    await sendToken({{
                        access_token: session.access_token,
                        refresh_token: session.refresh_token,
                        user_id: data.user?.id,
                        wallet: publicKey,
                    }});
                }} else {{
                    setStatus('❌ No session returned', 'error');
                }}
            }} catch(e) {{
                setStatus('❌ ' + e.message, 'error');
            }}
            
            btn.disabled = false;
        }}
        
        async function sendToken(tokenData) {{
            try {{
                const resp = await fetch(SERVER_URL + '/save-token', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(tokenData),
                }});
                const result = await resp.json();
                
                if (result.ok) {{
                    setStatus('✅ Token tersimpan! Bot siap jalan di server.', 'success');
                }} else {{
                    setStatus('❌ Gagal simpan: ' + result.error, 'error');
                }}
            }} catch(e) {{
                setStatus('❌ Error: ' + e.message, 'error');
            }}
        }}
        
        async function submitManual() {{
            const input = document.getElementById('token-input').value.trim();
            if (!input) {{ setStatus('❌ Paste token dulu', 'error'); return; }}
            
            try {{
                let tokenData;
                const parsed = JSON.parse(input);
                
                if (parsed.access_token) {{ tokenData = parsed; }}
                else if (parsed.currentSession?.access_token) {{ tokenData = parsed.currentSession; }}
                else {{ setStatus('❌ Format tidak dikenali', 'error'); return; }}
                
                setStatus('<span class="spinner"></span>Mengirim...', 'loading');
                await sendToken({{
                    access_token: tokenData.access_token,
                    refresh_token: tokenData.refresh_token,
                    user_id: tokenData.user?.id || tokenData.user_id,
                }});
            }} catch(e) {{
                if (input.includes('.') && input.length > 100) {{
                    await sendToken({{ access_token: input }});
                }} else {{
                    setStatus('❌ JSON tidak valid', 'error');
                }}
            }}
        }}
    </script>
</body>
</html>
"""

async def handle_index(request):
    return web.Response(text=AUTH_PAGE, content_type='text/html')

async def handle_save_token(request):
    try:
        data = await request.json()
        access_token = data.get('access_token')
        if not access_token:
            return web.json_response({'ok': False, 'error': 'No access_token'})
        
        token_data = {
            'access_token': access_token,
            'refresh_token': data.get('refresh_token'),
            'user_id': data.get('user_id'),
            'wallet': data.get('wallet'),
            'saved_at': time.time(),
        }
        
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print(f"[AUTH] Token saved! User: {data.get('user_id', 'unknown')}")
        return web.json_response({'ok': True, 'user_id': data.get('user_id')})
    except Exception as e:
        return web.json_response({'ok': False, 'error': str(e)})

async def handle_status(request):
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        return web.json_response({'ok': True, 'has_token': True, 'user_id': data.get('user_id')})
    return web.json_response({'ok': True, 'has_token': False})

app = web.Application()
app.router.add_get('/', handle_index)
app.router.add_post('/save-token', handle_save_token)
app.router.add_get('/status', handle_status)

if __name__ == '__main__':
    print(f"\n{'='*50}")
    print(f"  FarmTown Auth Server v3")
    print(f"  Supabase key: {len(SUPABASE_KEY)} chars")
    print(f"{'='*50}\n")
    web.run_app(app, host='0.0.0.0', port=9999)

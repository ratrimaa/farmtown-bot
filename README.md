# FarmTown Bot

Automation bot for [FarmTown](https://play.farmtown.online) — browser-based farming game on Solana.

## Features

- Auto hoe (grass + dead crops)
- Auto plant (buy seeds + plant)
- Auto harvest ready crops
- Auto clear blockers (trees/rocks)
- Auto buy adjacent land
- Auto complete orders
- Auto complete starter tasks
- Multi-account support (parallel farming)
- Interactive CLI menu

## Setup

```bash
cd farmtown-bot
pip install -r requirements.txt

# Create your Supabase anon key file (get from game's JS)
echo "YOUR_ANON_KEY" > supabase_key.txt
```

## Usage

```bash
python farmtown_bot.py
```

Interactive menu:
```
========================================
  FARM TOWN BOT
========================================
  1. Tambah akun (masukkan token)
  2. Jalankan 1 akun
  3. Jalankan semua akun
  4. Lihat daftar akun
  5. Lihat wallet (private key)
  6. Hapus akun
  7. Keluar
========================================
```

### Adding an account

1. Open play.farmtown.online, login with Phantom wallet
2. Open browser DevTools (F12) → Console
3. Run: `JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.includes('auth-token'))))`
4. Copy the full JSON output
5. In the bot menu, paste the token directly (auto-detected)

## Game Actions (Verified)

| Action | Tool | Description |
|--------|------|-------------|
| `hoe` | hoe | Till grass → tilled, clear dead → tilled |
| `plant` | seed_bag | Plant seed on tilled tile |
| `harvest` | hand | Harvest ready crops |
| `clear` | axe | Clear blocker (when blocker != 'none') |
| `buySeed` | seed_bag | Buy seeds from shop |
| `buyPlot` | hand | Buy adjacent locked tile |
| `completeOrder` | hand | Complete farm orders |
| `completeStarterTask` | hand | Claim starter task rewards |

## Architecture

```
Phantom Wallet → Supabase Auth → Socket.IO Realtime Server
                                      ↓
                                 FarmBot (this)
                                  ├── categorize tiles
                                  ├── hoe dead/grass
                                  ├── clear blockers
                                  ├── harvest ready
                                  ├── buy seeds + plant
                                  ├── buy land
                                  ├── complete orders
                                  └── claim starters
```

## Files

| File | Purpose |
|------|---------|
| `farmtown_bot.py` | Main bot + interactive CLI |
| `auth.py` | Auth module (manual token, 2captcha, browser) |
| `get_token.py` | Token extraction helper |
| `debug_farm.py` | Debug tool — dump farm state |
| `test_action.py` | Test individual game actions |
| `token_extractor.py` | Browser-based token extraction |

## Config

Sensitive files (auto-ignored by .gitignore):
- `session.json` — Supabase auth token (~1h lifetime)
- `wallet.json` — Solana keypair (binary)
- `supabase_key.txt` — Supabase anon key
- `accounts/` — Per-account data (tokens + wallets)

## Token Refresh

Tokens expire after ~1 hour. The bot auto-refreshes if the refresh token is still valid. If refresh fails, re-add the account via menu.

## Notes

- Server: `realtime.farmtown.online` (Socket.IO)
- Farm room: `farmtown-dev`
- Cloudflare Turnstile CAPTCHA on login
- No quest/job system implemented server-side yet

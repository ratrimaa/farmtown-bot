# Quick Setup

```bash
# 1. Install dependencies
pip install httpx python-socketio[sync] solders base58

# 2. Create supabase_key.txt
# Get the anon key from the game's JS bundle:
curl -sL 'https://play.farmtown.online/assets/index-CVX4Chdz.js' | grep -oP 'eyJhbG[^"]+' | head -1 > supabase_key.txt

# 3. Run the bot
python farmtown_bot.py
```

## Auth Flow

1. Bot loads token from `accounts/<name>/session.json`
2. Verifies Solana wallet signature against Supabase
3. Gets `walletSessionToken` for Socket.IO auth
4. Connects to `realtime.farmtown.online` via Socket.IO
5. Joins farm room and starts farming loop

## Token Format

The bot expects the full auth token JSON from localStorage:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "...",
  "expires_in": 3600,
  "expires_at": 1782547594,
  "token_type": "bearer",
  "user": { "id": "...", ... }
}
```

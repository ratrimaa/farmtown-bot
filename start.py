#!/usr/bin/env python3
"""
Quick token setup - paste token from browser, start bot
Usage: python3 start.py
"""

import json
import os
import sys

TOKEN_FILE = "token.json"

def main():
    print("="*50)
    print("  FarmTown Bot - Quick Setup")
    print("="*50)
    
    # Check if token exists
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        if data.get('access_token'):
            print(f"\nToken sudah ada! (User: {data.get('user_id', 'unknown')})")
            choice = input("Gunakan token ini? (y/n): ").strip().lower()
            if choice == 'y' or choice == '':
                start_bot()
                return
    
    # Get new token
    print("""
CARA AMBIL TOKEN:

1. Buka Chrome/Safari di PC/Mac
2. Kunjungi: play.farmtown.online
3. Login dengan Phantom wallet
4. Buka DevTools (tekan F12)
5. Klik tab "Console"
6. Ketik command ini, tekan Enter:

   JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.includes('auth-token'))))

7. Copy SELURUH hasil output (klik kanan → Copy)
8. Paste di sini
""")
    
    raw = input("Paste token di sini: ").strip()
    if not raw:
        print("Tidak ada token. Keluar.")
        return
    
    try:
        data = json.loads(raw)
        
        # Handle different formats
        if 'access_token' in data:
            token_data = data
        elif 'currentSession' in data:
            token_data = data['currentSession']
        else:
            print("Format tidak dikenali. Pastikan ada 'access_token'.")
            return
        
        # Save
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)
        
        print(f"\nToken tersimpan! (User: {token_data.get('user', {}).get('id', 'unknown')})")
        start_bot()
        
    except json.JSONDecodeError:
        print("JSON tidak valid. Coba lagi.")
    except Exception as e:
        print(f"Error: {e}")

def start_bot():
    print("\nMemulai bot...")
    os.system("python3 farmtown_bot.py farm --crop potato")

if __name__ == "__main__":
    main()

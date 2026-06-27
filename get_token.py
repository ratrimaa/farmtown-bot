#!/usr/bin/env python3
"""
Quick helper to extract Supabase token from FarmTown
Run this in browser console (F12) on play.farmtown.online:

Copy-paste this into browser console:
"""

CONSOLE_SCRIPT = """
// Run this in browser console on play.farmtown.online
(() => {
  const keys = Object.keys(localStorage);
  for (const k of keys) {
    try {
      const v = JSON.parse(localStorage.getItem(k));
      if (v && v.access_token) {
        console.log('TOKEN FOUND! Copy this:');
        console.log(JSON.stringify(v, null, 2));
        return;
      }
      if (v && v.currentSession && v.currentSession.access_token) {
        console.log('TOKEN FOUND! Copy this:');
        console.log(JSON.stringify(v.currentSession, null, 2));
        return;
      }
    } catch(e) {}
  }
  // Also try sessionStorage
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i);
    try {
      const v = JSON.parse(sessionStorage.getItem(k));
      if (v && v.access_token) {
        console.log('TOKEN FOUND in sessionStorage! Copy this:');
        console.log(JSON.stringify(v, null, 2));
        return;
      }
    } catch(e) {}
  }
  console.log('No token found. Make sure you are logged in.');
})();
"""

if __name__ == "__main__":
    print("="*50)
    print("  FarmTown Token Extractor")
    print("="*50)
    print()
    print("1. Buka https://play.farmtown.online")
    print("2. Login dengan Phantom wallet")
    print("3. Buka DevTools (F12) → Console")
    print("4. Paste script ini dan tekan Enter:")
    print()
    print(CONSOLE_SCRIPT)
    print()
    print("5. Copy output JSON-nya")
    print("6. Jalankan: python farmtown_bot.py auth --method manual")
    print("7. Paste token-nya")

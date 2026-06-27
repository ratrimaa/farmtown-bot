#!/usr/bin/env python3
"""Minimal test: connect, try ONE plant, observe result."""

import json, os, sys, time, asyncio
import socketio
from auth import load_token, load_wallet, verify_wallet

REALTIME_URL = "https://realtime.farmtown.online"
FARM_ROOM_ID = "farmtown-dev"

def main():
    token_data = load_token()
    if not token_data:
        print("No token"); return

    wallet = load_wallet()
    print("[1] Verifying wallet...")
    wt = asyncio.run(verify_wallet(token_data['access_token'], wallet, display_name="TestBot"))
    if not wt:
        print("Wallet verify failed"); return

    sio = socketio.Client(logger=False, engineio_logger=False)
    state = {'farm': None, 'player': None, 'tiles': [], 'events': []}
    action_results = []

    @sio.on('connect')
    def on_connect():
        print("[2] Connected")
        sio.emit('farm:join', {
            'roomId': FARM_ROOM_ID, 'name': 'TestBot',
            'accessToken': token_data['access_token'],
            'walletSessionToken': wt,
        })

    @sio.on('farm:state/sync')
    def on_farm(data):
        state['farm'] = data
        state['tiles'] = data.get('tiles', [])
        owned = [t for t in state['tiles'] if t.get('ownerState') == 'owned']
        print(f"[3] Farm synced: {len(owned)} owned tiles")
        for t in owned:
            print(f"    ({t['x']},{t['y']}): groundState={t.get('groundState')}, cropId={t.get('cropId')}, plantedAt={t.get('plantedAt')}, readyAt={t.get('readyAt')}, diesAt={t.get('diesAt')}")

    @sio.on('player:farmState/sync')
    def on_player(data):
        fs = data.get('farmState', data)
        state['player'] = fs
        inv = fs.get('inventory', {})
        seeds = {k:v for k,v in inv.items() if k.endswith('_seed') and v > 0}
        print(f"[4] Player: gold={fs.get('gold')}, level={fs.get('level')}, xp={fs.get('xp')}, seeds={seeds}")

    @sio.on('tile:update')
    def on_tile_update(data):
        print(f"[TILE UPDATE] ({data.get('x')},{data.get('y')}): {json.dumps(data, default=str)[:200]}")
        # Update local tiles
        for i, t in enumerate(state['tiles']):
            if t.get('x') == data.get('x') and t.get('y') == data.get('y'):
                state['tiles'][i].update(data)
                break

    @sio.on('game:actionResult')
    def on_result(data):
        action_results.append(data)
        ok = data.get('ok')
        atype = data.get('type', '?')
        msg = data.get('message', data.get('error', ''))
        status = "OK" if ok else "FAIL"
        print(f"[RESULT] {atype}: {status} - {msg}")
        if data.get('xp') is not None:
            print(f"    xp={data.get('xp')}, gold={data.get('gold')}, level={data.get('level')}")

    @sio.on('*')
    def on_any(event, data):
        known = {'connect', 'disconnect', 'farm:state/sync', 'player:farmState/sync',
                 'playerFarmState', 'game:actionResult', 'tile:update', 'farm:joined',
                 'roomJoined', 'farm:snapshot', 'presence:list', 'playerList',
                 'stats:update', 'chat:received', 'serverNotice', 'animal:sync/state',
                 'store:buySeed/result', 'game:error', 'farm:error'}
        if event not in known:
            print(f"[EVENT] {event}: {str(data)[:150]}")

    print(f"[0] Connecting...")
    sio.connect(REALTIME_URL, auth={
        'accessToken': token_data['access_token'],
        'walletSessionToken': wt,
    }, transports=['websocket', 'polling'], wait=True, wait_timeout=15)

    # Wait for state
    print("[5] Waiting for state (5s)...")
    time.sleep(5)

    if not state['tiles']:
        print("ERROR: No tiles received!")
        sio.disconnect()
        return

    # Find first tilled owned tile
    tilled = [t for t in state['tiles'] if t.get('ownerState') == 'owned' and t.get('groundState') == 'tilled' and not t.get('cropId')]
    planted = [t for t in state['tiles'] if t.get('ownerState') == 'owned' and t.get('cropId')]
    ready = [t for t in state['tiles'] if t.get('ownerState') == 'owned' and t.get('readyAt') and int(time.time()*1000) >= t.get('readyAt', 0)]
    dead = [t for t in state['tiles'] if t.get('ownerState') == 'owned' and t.get('diesAt') and int(time.time()*1000) >= t.get('diesAt', 0)]

    print(f"\n[6] Tile analysis:")
    print(f"    Tilled (empty): {len(tilled)}")
    print(f"    Planted (growing): {len(planted)}")
    print(f"    Ready (harvest): {len(ready)}")
    print(f"    Dead (withered): {len(dead)}")

    # Check inventory
    inv = state['player'].get('inventory', {}) if state['player'] else {}
    carrot_seeds = inv.get('carrot_seed', 0)
    gold = state['player'].get('gold', 0) if state['player'] else 0

    print(f"\n[7] Inventory: carrot_seed={carrot_seeds}, gold={gold}")

    # Try actions based on state
    if ready:
        t = ready[0]
        print(f"\n[8] TEST: Harvest ({t['x']},{t['y']})")
        sio.emit('game:action', {
            "roomId": FARM_ROOM_ID,
            "action": "harvest",
            "actionId": f"test:harvest:{int(time.time())}",
            "clientSentAt": int(time.time() * 1000),
            "selectedTool": "hand",
            "tileX": t['x'], "tileY": t['y'],
        })
        time.sleep(2)

    if dead:
        t = dead[0]
        print(f"\n[8] TEST: clearDead ({t['x']},{t['y']})")
        sio.emit('game:action', {
            "roomId": FARM_ROOM_ID,
            "action": "clearDead",
            "actionId": f"test:clearDead:{int(time.time())}",
            "clientSentAt": int(time.time() * 1000),
            "selectedTool": "hoe",
            "tileX": t['x'], "tileY": t['y'],
        })
        time.sleep(2)

    if tilled:
        t = tilled[0]
        print(f"\n[8] TEST: Plant carrot ({t['x']},{t['y']})")
        print(f"    Sending: action=plant, tileX={t['x']}, tileY={t['y']}, seedId=carrot_seed")
        sio.emit('game:action', {
            "roomId": FARM_ROOM_ID,
            "action": "plant",
            "actionId": f"test:plant:{int(time.time())}",
            "clientSentAt": int(time.time() * 1000),
            "selectedTool": "seed_bag",
            "tileX": t['x'], "tileY": t['y'],
            "seedId": "carrot_seed",
        })
        time.sleep(2)

        # Check if tile updated
        print(f"\n[9] Checking tile after plant...")
        for t2 in state['tiles']:
            if t2.get('x') == t['x'] and t2.get('y') == t['y']:
                print(f"    ({t2['x']},{t2['y']}): groundState={t2.get('groundState')}, cropId={t2.get('cropId')}")
                break

        # Try water
        print(f"\n[8b] TEST: Water ({t['x']},{t['y']})")
        sio.emit('game:action', {
            "roomId": FARM_ROOM_ID,
            "action": "water",
            "actionId": f"test:water:{int(time.time())}",
            "clientSentAt": int(time.time() * 1000),
            "selectedTool": "watering_can",
            "tileX": t['x'], "tileY": t['y'],
        })
        time.sleep(2)

    if not tilled and not ready and not dead:
        print("\n[8] No tilled/ready/dead tiles. Trying to till a cleared tile...")
        cleared = [t for t in state['tiles'] if t.get('ownerState') == 'owned' and t.get('groundState') in ('grass', 'cleared')]
        if cleared:
            t = cleared[0]
            print(f"    Hoe ({t['x']},{t['y']})")
            sio.emit('game:action', {
                "roomId": FARM_ROOM_ID,
                "action": "hoe",
                "actionId": f"test:hoe:{int(time.time())}",
                "clientSentAt": int(time.time() * 1000),
                "selectedTool": "hoe",
                "tileX": t['x'], "tileY": t['y'],
            })
            time.sleep(2)
        else:
            print("    No cleared tiles either!")

    # Wait for any more events
    print(f"\n[10] Waiting 3s for events...")
    time.sleep(3)

    # Re-check state
    owned = [t for t in state['tiles'] if t.get('ownerState') == 'owned']
    print(f"\n[FINAL] Owned tiles after actions:")
    for t in owned:
        print(f"    ({t['x']},{t['y']}): groundState={t.get('groundState')}, cropId={t.get('cropId')}")

    print(f"\n[FINAL] Action results: {len(action_results)}")
    for r in action_results:
        print(f"    {r.get('type')}: {'OK' if r.get('ok') else 'FAIL'} - {r.get('message', r.get('error', ''))}")

    sio.disconnect()
    print("\n[DONE]")

if __name__ == "__main__":
    main()

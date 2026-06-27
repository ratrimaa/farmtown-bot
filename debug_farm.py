#!/usr/bin/env python3
"""Diagnostic: Connect to FarmTown, dump raw state, then exit."""

import json
import os
import sys
import time
import asyncio

import socketio
from auth import load_token, load_wallet, verify_wallet

REALTIME_URL = "https://realtime.farmtown.online"
FARM_ROOM_ID = "farmtown-dev"

def main():
    token_data = load_token()
    if not token_data:
        print("[ERROR] No token. Run auth first.")
        sys.exit(1)

    wallet = load_wallet()
    print("[AUTH] Verifying wallet...")
    wallet_token = asyncio.run(verify_wallet(
        token_data['access_token'], wallet, display_name="DebugBot"
    ))
    if not wallet_token:
        print("[ERROR] Wallet verify failed")
        sys.exit(1)

    sio = socketio.Client(logger=False, engineio_logger=False)
    state = {'farm': None, 'player': None, 'tiles_raw': None, 'events': []}

    @sio.on('connect')
    def on_connect():
        print("[SOCKET] Connected")
        sio.emit('farm:join', {
            'roomId': FARM_ROOM_ID,
            'name': 'DebugBot',
            'accessToken': token_data['access_token'],
            'walletSessionToken': wallet_token,
        })

    @sio.on('farm:state/sync')
    def on_state(data):
        state['farm'] = data
        tiles = data.get('tiles', [])
        state['tiles_raw'] = tiles
        print(f"\n[FARM STATE] {len(tiles)} tiles")
        # Dump first 5 tiles in full
        for t in tiles[:5]:
            print(f"  TILE: {json.dumps(t, default=str)[:200]}")
        # Count states
        states = {}
        for t in tiles:
            gs = t.get('groundState', t.get('state', 'UNKNOWN'))
            owner = t.get('ownerState', t.get('owner', 'UNKNOWN'))
            crop = t.get('cropId', t.get('crop', None))
            key = f"gs={gs},owner={owner},crop={crop}"
            states[key] = states.get(key, 0) + 1
        print("\n[TILE STATES SUMMARY]")
        for k, v in sorted(states.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v} tiles")

    @sio.on('player:farmState/sync')
    def on_player(data):
        state['player'] = data
        print(f"\n[PLAYER STATE] {json.dumps(data, default=str)[:500]}")

    @sio.on('playerFarmState')
    def on_player2(data):
        state['player'] = data
        print(f"\n[PLAYER FARM STATE] {json.dumps(data, default=str)[:500]}")

    @sio.on('*')
    def on_any(event, data):
        if event not in {'connect', 'disconnect', 'farm:state/sync', 'player:farmState/sync',
                         'playerFarmState', 'game:actionResult', 'presence:list', 'playerList',
                         'stats:update', 'chat:received', 'serverNotice', 'tile:update'}:
            state['events'].append((event, str(data)[:100]))
            print(f"[EVENT] {event}: {str(data)[:100]}")

    @sio.on('tile:update')
    def on_tile_update(data):
        print(f"[TILE UPDATE] {json.dumps(data, default=str)[:200]}")

    print(f"[SOCKET] Connecting to {REALTIME_URL}...")
    sio.connect(REALTIME_URL, auth={
        'accessToken': token_data['access_token'],
        'walletSessionToken': wallet_token,
    }, transports=['websocket', 'polling'], wait=True, wait_timeout=15)

    print("\n[WAIT] Collecting events for 10 seconds...")
    time.sleep(10)

    print("\n" + "=" * 60)
    print("FINAL STATE DUMP")
    print("=" * 60)

    if state['player']:
        print(f"\nPLAYER: {json.dumps(state['player'], default=str)[:500]}")

    if state['farm']:
        farm = state['farm']
        tiles = farm.get('tiles', [])
        print(f"\nFARM: {len(tiles)} tiles")

        # Full dump of ALL tile keys for first tile
        if tiles:
            print(f"\nFIRST TILE KEYS: {list(tiles[0].keys())}")

        # Categorize properly
        owned = [t for t in tiles if _is_owned(t)]
        print(f"OWNED TILES: {len(owned)}")
        for t in owned:
            print(f"  ({t.get('x')},{t.get('y')}): "
                  f"groundState={t.get('groundState','?')}, "
                  f"state={t.get('state','?')}, "
                  f"cropId={t.get('cropId','none')}, "
                  f"crop={t.get('crop','none')}, "
                  f"growthStage={t.get('growthStage','?')}, "
                  f"needsWater={t.get('needsWater','?')}, "
                  f"withered={t.get('withered','?')}")

    print(f"\nOTHER EVENTS ({len(state['events'])}):")
    for ev, d in state['events'][:20]:
        print(f"  {ev}: {d}")

    sio.disconnect()

def _is_owned(tile):
    """Check if tile is owned by the player"""
    owner = tile.get('ownerState', tile.get('owner', ''))
    if owner == 'owned':
        return True
    if owner is True:
        return True
    # Some games use playerId match
    return False

if __name__ == "__main__":
    main()

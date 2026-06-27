#!/usr/bin/env python3
"""
FarmTown Bot v4 — Interactive setup + multi-account farming.
"""

import json, os, sys, time, asyncio, random, threading

try:
    import socketio
    import httpx
    from solders.keypair import Keypair
except ImportError as e:
    print(f"Missing deps. Run: pip install httpx python-socketio[sync] solders base58")
    sys.exit(1)

REALTIME_URL = "https://realtime.farmtown.online"
FARM_ROOM_ID = "farmtown-dev"
ACCOUNTS_DIR = "accounts"
WALLET_FILE = "wallet.json"
TOKEN_FILE = "session.json"

CROPS = {
    "potato":     {"seed": "potato_seed",     "cost": 5,     "grow_s": 45,    "reward": 8,       "xp": 1,    "level": 1},
    "carrot":     {"seed": "carrot_seed",     "cost": 20,    "grow_s": 120,   "reward": 40,      "xp": 4,    "level": 1},
    "corn":       {"seed": "corn_seed",       "cost": 45,    "grow_s": 300,   "reward": 95,      "xp": 8,    "level": 1},
    "tomato":     {"seed": "tomato_seed",     "cost": 90,    "grow_s": 480,   "reward": 200,     "xp": 14,   "level": 5},
    "onion":      {"seed": "onion_seed",      "cost": 140,   "grow_s": 720,   "reward": 330,     "xp": 22,   "level": 5},
    "wheat":      {"seed": "wheat_seed",      "cost": 220,   "grow_s": 1080,  "reward": 560,     "xp": 32,   "level": 5},
    "pumpkin":    {"seed": "pumpkin_seed",    "cost": 400,   "grow_s": 1800,  "reward": 1050,    "xp": 55,   "level": 10},
    "melon":      {"seed": "melon_seed",      "cost": 650,   "grow_s": 2700,  "reward": 1800,    "xp": 80,   "level": 10},
    "cucumber":   {"seed": "cucumber_seed",   "cost": 850,   "grow_s": 3600,  "reward": 2400,    "xp": 105,  "level": 10},
    "pepper":     {"seed": "pepper_seed",     "cost": 1300,  "grow_s": 5400,  "reward": 4000,    "xp": 150,  "level": 15},
    "strawberry": {"seed": "strawberry_seed", "cost": 1900,  "grow_s": 7200,  "reward": 6200,    "xp": 210,  "level": 15},
    "blueberry":  {"seed": "blueberry_seed",  "cost": 2600,  "grow_s": 10800, "reward": 8800,    "xp": 280,  "level": 15},
    "grape":      {"seed": "grape_seed",      "cost": 4000,  "grow_s": 14400, "reward": 9500,    "xp": 220,  "level": 20},
    "eggplant":   {"seed": "eggplant_seed",   "cost": 5500,  "grow_s": 18000, "reward": 13000,   "xp": 280,  "level": 20},
    "watermelon": {"seed": "watermelon_seed", "cost": 7500,  "grow_s": 21600, "reward": 18000,   "xp": 360,  "level": 20},
    "dragonfruit":{"seed": "dragonfruit_seed","cost": 12000, "grow_s": 28800, "reward": 28000,   "xp": 500,  "level": 25},
    "pineapple":  {"seed": "pineapple_seed",  "cost": 18000, "grow_s": 36000, "reward": 42000,   "xp": 700,  "level": 25},
    "starfruit":  {"seed": "starfruit_seed",  "cost": 50000, "grow_s": 64800, "reward": 100000,  "xp": 1200, "level": 30},
    "moonberry":  {"seed": "moonberry_seed",  "cost": 70000, "grow_s": 72000, "reward": 150000,  "xp": 1500, "level": 33},
    "goldroot":   {"seed": "goldroot_seed",   "cost": 175000,"grow_s": 93600, "reward": 390000,  "xp": 3000, "level": 42},
}


def get_account_dir(name):
    d = os.path.join(ACCOUNTS_DIR, name)
    os.makedirs(d, exist_ok=True)
    return d


def parse_token(raw):
    """Parse any token format into dict."""
    raw = raw.strip().strip('"').strip("'")
    try:
        data = json.loads(raw)
        if 'access_token' in data:
            return data
        if 'currentSession' in data:
            s = data['currentSession']
            return {'access_token': s.get('access_token'), 'refresh_token': s.get('refresh_token'), 'user_id': s.get('user',{}).get('id')}
        # Maybe nested deeper
        for v in data.values():
            if isinstance(v, dict) and 'access_token' in v:
                return v
    except json.JSONDecodeError:
        pass
    # Raw JWT string
    if len(raw) > 100 and '.' in raw:
        return {'access_token': raw}
    return None


def save_token(token_data, filepath):
    with open(filepath, 'w') as f:
        json.dump(token_data, f, indent=2)


def load_token(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        data = json.load(f)
    token = data.get('access_token', '')
    if not token:
        return None
    # Check expiry
    try:
        import base64
        parts = token.split('.')
        if len(parts) == 3:
            payload = json.loads(base64.b64decode(parts[1] + '=='))
            exp = payload.get('exp', 0)
            if exp < time.time():
                print("[TOKEN] Expired, trying refresh...")
                refreshed = refresh_token(data, filepath)
                if refreshed:
                    return refreshed
                return None
            remaining = exp - time.time()
            print(f"[TOKEN] Valid for {remaining/60:.0f}m")
    except:
        pass
    return data


def refresh_token(token_data, filepath):
    refresh = token_data.get('refresh_token')
    if not refresh:
        return None
    SUPABASE_URL = "https://irarxwyrpmmxacrbvpnz.supabase.co"
    key_file = os.path.join(os.path.dirname(__file__), 'supabase_key.txt')
    anon_key = open(key_file).read().strip() if os.path.exists(key_file) else ""
    try:
        resp = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": anon_key, "Content-Type": "application/json"},
            json={"refresh_token": refresh}, timeout=15)
        if resp.status_code == 200:
            d = resp.json()
            new = {'access_token': d.get('access_token'), 'refresh_token': d.get('refresh_token', refresh), 'user_id': token_data.get('user_id')}
            save_token(new, filepath)
            print("[TOKEN] Refreshed!")
            return new
    except Exception as e:
        print(f"[TOKEN] Refresh error: {e}")
    return None


def load_wallet(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            return Keypair.from_bytes(f.read())
    kp = Keypair()
    with open(filepath, 'wb') as f:
        f.write(bytes(kp))
    print(f"[WALLET] New wallet: {str(kp.pubkey())[:20]}...")
    return kp


# ============================================================
# FarmConn + FarmBot
# ============================================================

class FarmConn:
    def __init__(self, token, wallet_token, name=""):
        self.token = token
        self.wallet_token = wallet_token
        self.name = name
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self.connected = False
        self.tiles = {}
        self.player = {}
        self.orders = []   # active orders from server
        self.jobs = []      # active farm jobs from server
        self.room_id = None
        self._results = []
        self._setup()

    def _p(self, msg):
        return f"[{self.name}]{msg}" if self.name else msg

    def _setup(self):
        sio = self.sio
        @sio.on('connect')
        def on_connect():
            self.connected = True
            print(self._p("[CONN] Connected"))
            sio.emit('farm:join', {'roomId': FARM_ROOM_ID, 'name': self.name or 'Bot',
                'accessToken': self.token, 'walletSessionToken': self.wallet_token})
        @sio.on('disconnect')
        def on_disconnect():
            self.connected = False
        @sio.on('roomJoined')
        def on_room(data):
            self.room_id = data.get('roomId', FARM_ROOM_ID)
            self.player_id = data.get('playerId') or data.get('localPlayerId')
            print(self._p(f"[CONN] Room: {self.room_id}"))
            # Request orders and jobs after joining
            try:
                sio.emit('orders:request', {'roomId': self.room_id})
                sio.emit('jobs:request', {'roomId': self.room_id})
                sio.emit('farmJob:list/request', {'roomId': self.room_id})
                sio.emit('order:list/request', {'roomId': self.room_id})
            except: pass
        @sio.on('farm:state/sync')
        def on_farm(data):
            n = 0
            for t in data.get('tiles', []):
                self.tiles[(t['x'], t['y'])] = t
                if t.get('ownerState') == 'owned':
                    n += 1
            print(self._p(f"[FARM] {n} tiles"))
        @sio.on('player:farmState/sync')
        def on_p1(data): self.player = data.get('farmState', data)
        @sio.on('playerFarmState')
        def on_p2(data): self.player = data.get('farmState', data)
        @sio.on('tile:update')
        def on_tu(data):
            tile = data.get('tile', data)
            x, y = tile.get('x'), tile.get('y')
            if x is not None and y is not None:
                self.tiles[(x, y)] = tile
        @sio.on('game:actionResult')
        def on_res(data):
            self._results.append(data)
            # Track orders and jobs from action results
            if 'orders' in data and data['orders'] is not None:
                self.orders = data['orders'] if isinstance(data['orders'], list) else self.orders
            if 'jobs' in data and data['jobs'] is not None:
                self.jobs = data['jobs'] if isinstance(data['jobs'], list) else self.jobs
            if not data.get('ok'):
                print(self._p(f"[FAIL] {data.get('type','?')}: {data.get('message','')}"))

        # Listen for order/job state updates
        @sio.on('orders:sync')
        def on_orders_sync(data):
            if isinstance(data, list):
                self.orders = data
            elif isinstance(data, dict) and 'orders' in data:
                self.orders = data['orders']
            print(self._p(f"[ORDERS] {len(self.orders)} loaded"))

        @sio.on('jobs:sync')
        def on_jobs_sync(data):
            if isinstance(data, list):
                self.jobs = data
            elif isinstance(data, dict) and 'jobs' in data:
                self.jobs = data['jobs']
            print(self._p(f"[JOBS] {len(self.jobs)} loaded"))

        @sio.on('player:orders/sync')
        def on_orders2(data):
            if isinstance(data, list):
                self.orders = data
            elif isinstance(data, dict) and 'orders' in data:
                self.orders = data['orders']

        @sio.on('player:jobs/sync')
        def on_jobs2(data):
            if isinstance(data, list):
                self.jobs = data
            elif isinstance(data, dict) and 'jobs' in data:
                self.jobs = data['jobs']

    def connect(self):
        try:
            self.sio.connect(REALTIME_URL,
                auth={'accessToken': self.token, 'walletSessionToken': self.wallet_token},
                transports=['websocket', 'polling'], wait=True, wait_timeout=15)
            return True
        except Exception as e:
            print(self._p(f"[CONN] Failed: {e}"))
            return False

    def disconnect(self):
        if self.connected: self.sio.disconnect()

    def act(self, action, **kw):
        self._results.clear()
        rid = f"{action}:{int(time.time()*1000)}:{random.randint(1000,9999)}"
        tool = kw.pop('selectedTool', 'hand')
        payload = {"roomId": self.room_id or FARM_ROOM_ID, "action": action,
                   "actionId": rid, "clientSentAt": int(time.time()*1000),
                   "selectedTool": tool, **kw}
        try:
            self.sio.emit('game:action', payload)
            for _ in range(10):
                time.sleep(0.1)
                if self._results: return self._results[-1]
            return {'ok': False, 'type': action, 'message': 'timeout'}
        except Exception as e:
            return {'ok': False, 'type': action, 'message': str(e)}

    def owned_tiles(self):
        return [t for t in self.tiles.values() if t.get('ownerState') == 'owned']


class FarmBot:
    def __init__(self, conn, target=10, crop=None, auto_land=True, auto_axe=True, auto_pickaxe=True, auto_orders=True, auto_jobs=True, auto_starter=True):
        self.conn = conn
        self.name = conn.name
        self.target = target
        self.crop = crop
        self.auto_land = auto_land
        self.auto_axe = auto_axe
        self.auto_pickaxe = auto_pickaxe
        self.auto_orders = auto_orders
        self.auto_jobs = auto_jobs
        self.auto_starter = auto_starter
        self.running = False
        self.stats = {'cycles':0, 'harvested':0, 'planted':0, 'tilled':0, 'bought':0,
                      'axed':0, 'pickaxed':0, 'cleared':0, 'land_bought':0, 'orders':0, 'jobs':0, 'starters':0, 'start':time.time()}
        self.last_print = 0
        self.empty_streak = 0

    def _p(self, m): return f"[{self.name}]{m}" if self.name else m
    @property
    def gold(self): return self.conn.player.get('gold', 0)
    @property
    def level(self): return self.conn.player.get('level', 1)
    @property
    def xp(self): return self.conn.player.get('xp', 0)
    @property
    def inv(self): return self.conn.player.get('inventory', {})

    def best_crop(self):
        if self.crop: return self.crop, CROPS.get(self.crop, CROPS['carrot'])
        best, bl = None, -1
        for n, c in CROPS.items():
            if self.level >= c['level'] and (self.inv.get(c['seed'],0) > 0 or self.gold >= c['cost']):
                if c['level'] > bl:
                    bl, best = c['level'], (n, c)
        return best or ('carrot', CROPS['carrot'])

    def run(self, interval=2.0):
        self.running = True
        cn, _ = self.best_crop()
        print(self._p(f"\n[BOT] {cn} → L{self.target}"))
        print(self._p(f"[BOT] Gold:{self.gold} L{self.level} XP:{self.xp}\n"))
        last_ref = time.time()

        while self.running:
            try:
                if time.time() - last_ref > 3000:
                    self._do_refresh()
                    last_ref = time.time()
                if self.conn.connected and self.conn.tiles:
                    self._tick()
                self.stats['cycles'] += 1
                if time.time() - self.last_print > 15:
                    self._stats()
                    self.last_print = time.time()
                if self.level >= self.target:
                    print(self._p(f"\n[DONE] L{self.level}!"))
                    break
                time.sleep(5 if self.empty_streak > 3 else interval)
            except KeyboardInterrupt:
                print(self._p("\n[STOP]")); break
            except Exception as e:
                print(self._p(f"[ERR] {e}")); time.sleep(3)

        self._stats()
        self.conn.disconnect()

    def _tick(self):
        tiles = self.conn.owned_tiles()
        now = int(time.time()*1000)
        cn, ci = self.best_crop()
        sid = ci['seed']

        # Categorize tiles
        ready, dead, tilled, grass, blocked, trees, rocks = [], [], [], [], [], [], []

        for t in tiles:
            gs = t.get('groundState','')
            obj = t.get('objectId','')
            blk = t.get('blocker', 'none')
            crop = t.get('cropId')
            ra = t.get('readyAt') or 0
            da = t.get('diesAt') or 0

            # Check for trees/rocks (objects on tile)
            if obj in ('tree', 'oak_tree', 'pine_tree', 'tree_1', 'tree_2'):
                trees.append(t)
            elif obj in ('rock', 'stone', 'rock_1', 'rock_2', 'boulder'):
                rocks.append(t)
            elif crop:
                if da and now >= da: dead.append(t)
                elif ra and now >= ra: ready.append(t)
            elif blk and blk != 'none':
                blocked.append(t)      # has blocker, need clear first
            elif gs == 'grass' or gs == 'cleared':
                grass.append(t)        # grass/cleared, hoe to till
            elif gs == 'tilled':
                tilled.append(t)

        acted = False

        # 0. Auto buy land (reserve 2000 gold for seeds)
        if self.auto_land and self.gold >= 2000 + ci['cost'] * 5:
            acted |= self._do_buy_land()

        # 1. Auto axe trees
        if self.auto_axe:
            for t in trees:
                r = self.conn.act('axe', tileX=t['x'], tileY=t['y'], selectedTool='axe')
                if r.get('ok'):
                    self.stats['axed'] += 1; acted = True
                time.sleep(0.3)

        # 2. Auto pickaxe rocks
        if self.auto_pickaxe:
            for t in rocks:
                r = self.conn.act('pickaxe', tileX=t['x'], tileY=t['y'], selectedTool='pickaxe')
                if r.get('ok'):
                    self.stats['pickaxed'] += 1; acted = True
                time.sleep(0.3)

        # 3. Harvest ready crops
        for t in ready:
            if self.conn.act('harvest', tileX=t['x'], tileY=t['y'], selectedTool='hand').get('ok'):
                self.stats['harvested'] += 1; acted = True
            time.sleep(0.3)

        # 4. Clear blockers (blocker != 'none')
        for t in blocked:
            r = self.conn.act('clear', tileX=t['x'], tileY=t['y'], selectedTool='axe')
            if r.get('ok'):
                self.stats['cleared'] += 1; acted = True
            time.sleep(0.3)

        # 5. Hoe dead crops + grass tiles (hoe handles both!)
        for t in dead + grass:
            r = self.conn.act('hoe', tileX=t['x'], tileY=t['y'], selectedTool='hoe')
            if r.get('ok'):
                self.stats['tilled'] += 1; acted = True
            elif 'Clear blocker' in r.get('message', ''):
                # Tile has blocker, clear first then hoe
                self.conn.act('clear', tileX=t['x'], tileY=t['y'], selectedTool='axe')
                time.sleep(0.3)
                r2 = self.conn.act('hoe', tileX=t['x'], tileY=t['y'], selectedTool='hoe')
                if r2.get('ok'):
                    self.stats['tilled'] += 1; acted = True
            time.sleep(0.3)

        # 6. Buy seeds + plant on tilled tiles
        tilled2 = [t for t in self.conn.owned_tiles() if t.get('groundState')=='tilled' and not t.get('cropId')]
        have = self.inv.get(sid, 0)

        if tilled2 and have <= 0 and self.gold >= ci['cost']:
            n = min(len(tilled2), self.gold // ci['cost'])
            if n:
                self.conn.act('buySeed', seedId=sid, quantity=n, selectedTool='seed_bag')
                self.stats['bought'] += n; time.sleep(0.3)
                have = self.inv.get(sid, 0)

        for t in tilled2[:min(len(tilled2), have)]:
            if self.conn.act('plant', tileX=t['x'], tileY=t['y'], seedId=sid, selectedTool='seed_bag').get('ok'):
                self.stats['planted'] += 1; acted = True
            time.sleep(0.3)

        # 7. Auto complete orders
        if self.auto_orders:
            acted |= self._do_orders()

        # 8. Auto claim farm jobs
        if self.auto_jobs:
            acted |= self._do_jobs()

        # 9. Auto complete starter tasks
        if self.auto_starter:
            acted |= self._do_starter()

        self.empty_streak = 0 if acted else self.empty_streak + 1

    def _do_buy_land(self):
        """Buy unowned tiles adjacent to owned tiles, then hoe them."""
        acted = False
        owned = set((t['x'], t['y']) for t in self.conn.owned_tiles())
        # Find adjacent unowned tiles
        for (x, y) in list(owned):
            for dx, dy in [(0,1),(0,-1),(1,0),(-1,0)]:
                nx, ny = x+dx, y+dy
                if (nx, ny) not in owned:
                    tile = self.conn.tiles.get((nx, ny))
                    if tile and tile.get('ownerState') != 'owned':
                        # Check gold before buying (reserve 2000 for seeds)
                        if self.gold < 2100:
                            return acted
                        r = self.conn.act('buyPlot', tileX=nx, tileY=ny)
                        if r.get('ok'):
                            self.stats['land_bought'] += 1
                            acted = True
                            print(self._p(f"[LAND] Bought ({nx},{ny})"))
                            time.sleep(0.3)
                            # Hoe immediately, handle blocker if needed
                            r2 = self.conn.act('hoe', tileX=nx, tileY=ny, selectedTool='hoe')
                            if not r2.get('ok') and 'Clear blocker' in r2.get('message', ''):
                                self.conn.act('clear', tileX=nx, tileY=ny, selectedTool='axe')
                                time.sleep(0.3)
                                r2 = self.conn.act('hoe', tileX=nx, tileY=ny, selectedTool='hoe')
                            if r2.get('ok'):
                                self.stats['tilled'] += 1
                                print(self._p(f"[LAND] Hoed ({nx},{ny})"))
                        time.sleep(0.3)
        return acted

    def _do_orders(self):
        """Complete orders where we have the required items."""
        acted = False
        for order in self.conn.orders:
            oid = order.get('id') or order.get('orderId')
            requires = order.get('requires', {})
            if not oid or not requires:
                continue
            # Check if we have all required items
            can_complete = True
            for item_id, qty_needed in requires.items():
                have = self.inv.get(item_id, 0)
                if have < qty_needed:
                    can_complete = False
                    break
            if can_complete:
                # Use direct socket emit (same as frontend)
                try:
                    self.conn.sio.emit('order:complete/request', {
                        'roomId': self.conn.room_id or FARM_ROOM_ID,
                        'orderId': oid
                    })
                    self.stats['orders'] += 1
                    acted = True
                    print(self._p(f"[ORDER] Completed order {oid}!"))
                    self.conn.orders = [o for o in self.conn.orders if (o.get('id') or o.get('orderId')) != oid]
                except Exception as e:
                    print(self._p(f"[ORDER] Error: {e}"))
                time.sleep(0.5)
        return acted

    def _do_jobs(self):
        """Claim completed farm jobs."""
        acted = False
        for job in self.conn.jobs:
            jid = job.get('id') or job.get('jobId')
            status = job.get('status', '')
            if not jid:
                continue
            # Claim jobs that are ready/completed
            if status in ('ready', 'completed', 'claimable', 'done'):
                try:
                    self.conn.sio.emit('farmJob:claim/request', {
                        'roomId': self.conn.room_id or FARM_ROOM_ID,
                        'jobId': jid
                    })
                    self.stats['jobs'] += 1
                    acted = True
                    print(self._p(f"[JOB] Claimed job {jid}!"))
                    self.conn.jobs = [j for j in self.conn.jobs if (j.get('id') or j.get('jobId')) != jid]
                except Exception as e:
                    print(self._p(f"[JOB] Error: {e}"))
                time.sleep(0.5)
        return acted

    def _do_starter(self):
        """Complete starter tasks via direct socket emit."""
        acted = False
        try:
            self.conn.sio.emit('starter:complete/request', {
                'roomId': self.conn.room_id or FARM_ROOM_ID,
            })
            # Check if we got an OK result
            time.sleep(0.5)
            if self.conn._results:
                r = self.conn._results[-1]
                if r.get('ok') and r.get('type') == 'completeStarterTask':
                    self.stats['starters'] += 1
                    acted = True
                    print(self._p(f"[STARTER] Task completed!"))
        except Exception as e:
            pass  # silently ignore starter errors
        return acted

    def _do_refresh(self):
        tf = os.path.join(ACCOUNTS_DIR, self.name, "session.json")
        td = load_token(tf)
        if td:
            new = refresh_token(td, tf)
            if new:
                self.conn.token = new['access_token']
                try:
                    self.conn.disconnect(); time.sleep(1)
                    if self.conn.connect():
                        print(self._p("[TOKEN] Reconnected")); time.sleep(3)
                except: pass

    def _stats(self):
        e = (time.time()-self.stats['start'])/60
        cn, ci = self.best_crop()
        seeds = self.inv.get(ci['seed'], 0)
        nr = min(((t.get('readyAt',0)-int(time.time()*1000))/1000
                  for t in self.conn.owned_tiles()
                  if t.get('cropId') and t.get('readyAt',0) > int(time.time()*1000)), default=None)
        eta = f" next:{nr:.0f}s" if nr else ""
        s = self.stats
        print(self._p(
            f"[STAT] {e:.0f}m G:{self.gold} L{self.level} XP:{self.xp}"
            f" H:{s['harvested']} P:{s['planted']} T:{s['tilled']}"
            f" Axe:{s['axed']} Pick:{s['pickaxed']} Clr:{s['cleared']} Land:{s['land_bought']}"
            f" Ord:{s['orders']} Job:{s['jobs']} Start:{s['starters']}"
            f" {seeds}s{eta} {cn}"))


# ============================================================
# Wallet verify
# ============================================================

FARMTOWN_API = "https://farmtown-three.vercel.app"

async def verify_wallet(access_token, keypair, name="Bot"):
    import base64
    addr = str(keypair.pubkey())
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    async with httpx.AsyncClient(timeout=30) as client:
        print(f"[WALLET] Challenge for {addr[:20]}...")
        r = await client.post(f'{FARMTOWN_API}/api/auth/wallet/challenge', headers=headers, json={'walletAddress': addr})
        if r.status_code != 200: print(f"[WALLET] Failed: {r.status_code}"); return None
        cd = r.json()
        if not cd.get('ok'): print(f"[WALLET] Error: {cd.get('message')}"); return None
        sig = keypair.sign_message(cd['message'].encode('utf-8'))
        sig_b64 = base64.b64encode(bytes(sig)).decode()
        print("[WALLET] Verifying...")
        r2 = await client.post(f'{FARMTOWN_API}/api/auth/wallet/verify', headers=headers, json={
            'challengeId': cd['challengeId'], 'nonce': cd['nonce'], 'walletAddress': addr,
            'message': cd['message'], 'signature': sig_b64, 'displayName': name})
        if r2.status_code == 200 and r2.json().get('walletVerified'):
            wst = r2.json().get('walletSessionToken','')
            print(f"[WALLET] OK! Session: {r2.json().get('walletSessionExpiresAt','?')}")
            return wst
        print(f"[WALLET] Verify failed"); return None


# ============================================================
# INTERACTIVE MENU
# ============================================================

def menu():
    while True:
        print("\n" + "="*40)
        print("  FARM TOWN BOT")
        print("="*40)
        print("  1. Tambah akun (masukkan token)")
        print("  2. Jalankan 1 akun")
        print("  3. Jalankan semua akun")
        print("  4. Lihat daftar akun")
        print("  5. Lihat wallet (private key)")
        print("  6. Hapus akun")
        print("  7. Keluar")
        print("="*40)
        print("  Atau langsung paste token JSON di sini:")
        choice = input("Pilih (1-7) atau paste token: ").strip()

        # Auto-detect if user pasted a token instead of menu number
        if choice and choice not in ('1','2','3','4','5','6','7'):
            if len(choice) > 100 and ('access_token' in choice or 'eyJ' in choice):
                print("\nTerdeteksi token! Lanjut tambah akun...")
                add_account_with_token(choice)
            else:
                print("Pilihan tidak valid")
        elif choice == '1':
            add_account()
        elif choice == '2':
            run_single()
        elif choice == '3':
            run_all()
        elif choice == '4':
            list_accounts()
        elif choice == '5':
            show_wallet()
        elif choice == '6':
            delete_account()
        elif choice == '7':
            print("Bye!"); break


def add_account():
    import base58
    print("\n--- TAMBAH AKUN ---")
    name = input("Nama akun (misal: main, alt1): ").strip()
    if not name: print("Nama kosong"); return

    print("\n[1/2] TOKEN dari browser")
    print("Buka play.farmtown.online → login → F12 → Console → ketik:")
    print("JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.includes('auth-token'))))")
    print("\nCara masukkan token:")
    print("  1. Paste langsung (bisa error kalau JSON panjang)")
    print("  2. Simpan ke file dulu (rekomendasi)")
    method = input("Pilih (1/2): ").strip()

    raw = ""
    if method == '2':
        fpath = input("Path file token (misal: token.txt): ").strip()
        if not os.path.exists(fpath):
            print(f"File tidak ditemukan: {fpath}"); return
        with open(fpath) as f:
            raw = f.read().strip()
    else:
        print("Paste token sekarang:")
        raw = input().strip()

    if not raw:
        print("Token kosong!"); return

    _save_account(name, raw)


def add_account_with_token(raw):
    """Auto-called when token is pasted at main menu."""
    import base58
    name = input("Nama akun (misal: main, alt1): ").strip()
    if not name: print("Nama kosong"); return
    _save_account(name, raw)


def _save_account(name, raw):
    """Parse token + wallet and save to account folder."""
    import base58

    token_data = parse_token(raw)
    if not token_data:
        print("ERROR: Token tidak dikenali!")
        print("Pastikan format JSON lengkap dengan access_token dan refresh_token")
        return

    print("\n[2/2] WALLET PRIVATE KEY")
    print("Buka Phantom → Settings → Show Secret Recovery Phrase → copy")
    print("Atau: Account → Show Private Key")
    phrase = input("Paste seed phrase / private key: ").strip()

    wallet = None
    # Try as base58 private key first
    try:
        raw_bytes = base58.b58decode(phrase)
        if len(raw_bytes) == 64:
            wallet = Keypair.from_bytes(raw_bytes)
        elif len(raw_bytes) == 32:
            wallet = Keypair.from_seed(raw_bytes)
    except:
        pass

    # Try as JSON array (Phantom export format)
    if not wallet:
        try:
            arr = json.loads(phrase)
            if isinstance(arr, list) and all(isinstance(x, int) for x in arr):
                wallet = Keypair.from_bytes(bytes(arr))
        except:
            pass

    if not wallet:
        print("ERROR: Private key tidak valid!")
        print("Format yang diterima: base58 string atau JSON array [1,2,3...]")
        return

    d = get_account_dir(name)
    save_token(token_data, os.path.join(d, "session.json"))
    with open(os.path.join(d, "wallet.json"), 'wb') as f:
        f.write(bytes(wallet))

    print(f"\n✓ Akun '{name}' tersimpan!")
    print(f"  Wallet: {str(wallet.pubkey())[:30]}...")


def list_accounts():
    if not os.path.exists(ACCOUNTS_DIR):
        print("Belum ada akun. Pilih menu 1 dulu.")
        return
    accs = sorted(os.listdir(ACCOUNTS_DIR))
    if not accs:
        print("Belum ada akun.")
        return
    print(f"\n{'Nama':<15} {'Token':<8} {'Wallet':<8}")
    print("-"*31)
    for a in accs:
        ad = os.path.join(ACCOUNTS_DIR, a)
        if not os.path.isdir(ad): continue
        t = "✓" if os.path.exists(os.path.join(ad, "session.json")) else "✗"
        w = "✓" if os.path.exists(os.path.join(ad, "wallet.json")) else "✗"
        print(f"{a:<15} {t:<8} {w:<8}")
    print()


def show_wallet():
    import base58
    if not os.path.exists(ACCOUNTS_DIR):
        print("Belum ada akun."); return
    accs = sorted([d for d in os.listdir(ACCOUNTS_DIR) if os.path.isdir(os.path.join(ACCOUNTS_DIR, d))])
    if not accs: print("Belum ada akun."); return

    print("\nAkun tersedia:")
    for i, a in enumerate(accs, 1): print(f"  {i}. {a}")
    pick = input("Pilih nomor: ").strip()
    try:
        name = accs[int(pick)-1]
    except:
        print("Pilihan salah"); return

    wf = os.path.join(ACCOUNTS_DIR, name, "wallet.json")
    if not os.path.exists(wf):
        print(f"[{name}] Wallet belum ada."); return

    with open(wf, 'rb') as f:
        kp = Keypair.from_bytes(f.read())

    pubkey = str(kp.pubkey())
    # solders Keypair: first 32 bytes = secret key, full 64 bytes = keypair
    secret_bytes = bytes(kp)
    privkey_b58 = base58.b58encode(secret_bytes).decode()

    print(f"\n{'='*40}")
    print(f"  WALLET: {name}")
    print(f"{'='*40}")
    print(f"  Public Key:\n  {pubkey}")
    print(f"\n  Private Key (base58):\n  {privkey_b58}")
    print(f"\n  Private Key (bytes):\n  {list(secret_bytes[:32])}")
    print(f"{'='*40}")
    print("  SIMPAN PRIVATE KEY INI!")
    print("  Bisa diimport ke Phantom/Solflare")
    print(f"{'='*40}\n")


def delete_account():
    import shutil
    if not os.path.exists(ACCOUNTS_DIR):
        print("Belum ada akun."); return
    accs = sorted([d for d in os.listdir(ACCOUNTS_DIR) if os.path.isdir(os.path.join(ACCOUNTS_DIR, d))])
    if not accs: print("Belum ada akun."); return

    print("\nHAPUS AKUN")
    print("-" * 30)
    for i, a in enumerate(accs, 1): print(f"  {i}. {a}")
    print(f"  0. Batal")
    pick = input("Pilih nomor (0=batal): ").strip()

    if pick == '0' or not pick:
        print("Batal."); return
    try:
        idx = int(pick) - 1
        name = accs[idx]
    except:
        print("Pilihan salah"); return

    confirm = input(f"Yakin hapus '{name}'? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Batal."); return

    acc_dir = os.path.join(ACCOUNTS_DIR, name)
    shutil.rmtree(acc_dir)
    print(f"✓ Akun '{name}' dihapus!")


def run_single():
    if not os.path.exists(ACCOUNTS_DIR):
        print("Belum ada akun. Pilih menu 1 dulu.")
        return
    accs = sorted([d for d in os.listdir(ACCOUNTS_DIR) if os.path.isdir(os.path.join(ACCOUNTS_DIR, d))])
    if not accs: print("Belum ada akun."); return

    print("\nAkun tersedia:")
    for i, a in enumerate(accs, 1): print(f"  {i}. {a}")
    pick = input("Pilih nomor: ").strip()
    try:
        name = accs[int(pick)-1]
    except:
        print("Pilihan salah"); return

    crop = input("Crop (carrot/corn/wheat/dll, kosong=auto): ").strip() or None
    target = input("Target level (default 10): ").strip()
    target = int(target) if target else 10

    _launch_account(name, crop, target)


def run_all():
    if not os.path.exists(ACCOUNTS_DIR):
        print("Belum ada akun."); return
    accs = sorted([d for d in os.listdir(ACCOUNTS_DIR)
                   if os.path.isdir(os.path.join(ACCOUNTS_DIR, d))
                   and os.path.exists(os.path.join(ACCOUNTS_DIR, d, "session.json"))])
    if not accs: print("Tidak ada akun valid."); return

    crop = input("Crop (kosong=auto): ").strip() or None
    target = input("Target level (default 10): ").strip()
    target = int(target) if target else 10

    print(f"\n[MULTI] Starting {len(accs)} akun: {', '.join(accs)}")
    threads = []
    for name in accs:
        t = threading.Thread(target=_launch_account, args=(name, crop, target), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(2)

    try:
        for t in threads: t.join()
    except KeyboardInterrupt:
        print("\n[MULTI] Stopped.")


def _launch_account(name, crop=None, target=10):
    tf = os.path.join(ACCOUNTS_DIR, name, "session.json")
    wf = os.path.join(ACCOUNTS_DIR, name, "wallet.json")

    td = load_token(tf)
    if not td:
        print(f"[{name}] Token expired/missing! Tambah ulang via menu 1.")
        return

    wallet = load_wallet(wf)
    print(f"[{name}] Verifying wallet...")
    wt = asyncio.run(verify_wallet(td['access_token'], wallet, name))
    if not wt:
        print(f"[{name}] Wallet failed")
        return

    conn = FarmConn(td['access_token'], wt, name)
    if not conn.connect():
        print(f"[{name}] Connect failed")
        return

    print(f"[{name}] Loading farm...")
    time.sleep(5)

    if not conn.tiles:
        print(f"[{name}] No tiles!")
        return

    bot = FarmBot(conn, target=target, crop=crop)
    bot.run(interval=3)


if __name__ == "__main__":
    menu()

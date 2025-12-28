"""
Echo Realms: The Witness — Visual Prototype v0.7 (Option B)
Single-file pygame prototype: walking avatar + tile world + NPCs + Witness/Glyph/Dream/Ritual/Codex/Journal + Save/Load

Run:
  pip install pygame
  python echo_realms_visual_proto_v0_7.py

Controls:
  WASD / Arrow Keys  - Move
  Mouse Left         - Select NPC (click them)
  E                  - Witness selected NPC (when near)
  G                  - Glyph panel (cast)
  D                  - Dream panel (seed dream for selected NPC; requires presence >= 3)
  R                  - Resolve ritual (only when a ritual is pending)
  J                  - Journal
  C                  - Codex
  F5                 - Save
  F9                 - Load
  ESC                - Close panels / clear selection
  Q                  - Quit
"""

from __future__ import annotations
import os, json, random, math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple, Optional, Any

import pygame

# ---------- Canon ----------
SEASONS = ["Verdance", "Stillmist", "Kindling", "Glimmereave"]
SLICES  = ["Dawn", "Day", "Dusk", "Night"]
TONES   = ["Comfort", "Courage", "Clarity", "Release", "Wonder"]
PULSE_KEYS = ["growth", "harmony", "remembrance", "dream", "veil", "turbulence"]

BASE = {"growth":55, "harmony":55, "remembrance":35, "dream":30, "veil":60, "turbulence":15}
DRIFT = {"growth":0.08, "harmony":0.10, "remembrance":0.06, "dream":0.12, "veil":0.10, "turbulence":0.18}

SAVE_FILE = "save_echo_realms.json"
JOURNAL_FILE = "journal.txt"

GLYPHS: Dict[str, Dict[str, Any]] = {
    "Signal": {"tier":"minor","cost":1,"delta":{"dream":2,"harmony":1}},
    "Veil":   {"tier":"minor","cost":1,"delta":{"veil":2,"turbulence":-1}},
    "Dream":  {"tier":"major","cost":2,"delta":{"dream":6,"remembrance":2}},
    "Anchor": {"tier":"major","cost":2,"delta":{"remembrance":6,"turbulence":-2}},
    "Cycle":  {"tier":"major","cost":2,"delta":{"remembrance":4,"dream":4,"veil":2}},
}

DAILY_LIMITS = {"minor":3, "major":1}

RITUALS = {
    "Lantern Walk": {
        "soft":{"remembrance":6,"dream":3,"turbulence":-3},
        "strong":{"remembrance":10,"dream":5,"veil":2,"turbulence":-5},
        "rare":{"remembrance":14,"dream":7,"veil":3,"turbulence":-7},
        "misaligned":{"turbulence":6,"dream":2},
        "season":"Stillmist","slice":"Night","days":[2,3]
    },
    "Night of the Fifth Silence": {
        "soft":{"turbulence":-8,"remembrance":6,"veil":4},
        "strong":{"turbulence":-12,"remembrance":10,"veil":6,"dream":2},
        "rare":{"turbulence":-18,"remembrance":14,"veil":8,"dream":4},
        "misaligned":{"turbulence":8,"harmony":-4},
        "season":"Glimmereave","slice":"Night","days":[5]
    }
}

CODEX_TEXT = {
    "Awakening: Stage 1":"Noticing begins. Small deviations. A glance held a moment too long.",
    "Awakening: Stage 2":"Symbols recur. The world feels less certain—and more alive.",
    "Ritual: Lantern Walk":"Lanterns carried in stillness. Names unspoken. The village grieves without drowning.",
    "Ritual: Night of the Fifth Silence":"Five breaths without thought. The realm becomes a single ear.",
    "Aya Arc Preview":"The Dream Ladder (7 steps). She sketches spirals… and the air answers."
}

# ---------- Visual ----------
W, H = 1120, 640
FPS = 60
TILE = 32
MAP_W, MAP_H = 70, 45

# Tile IDs
GRASS, PATH, WATER, TREE, HOUSE = 0,1,2,3,4
BLOCKED = {WATER, TREE, HOUSE}

COL = {
    GRASS:(32,120,48),
    PATH:(140,120,80),
    WATER:(20,60,140),
    TREE:(18,90,30),
    HOUSE:(110,70,50),
    "ui_bg":(10,10,10),
    "ui_panel":(18,18,18),
    "ui_border":(70,70,70),
    "ui_text":(240,240,240),
    "ui_dim":(160,160,160),
    "accent":(255,240,140),
    "danger":(255,120,120),
    "player":(220,220,220),
    "npc":(245,245,245),
    "sel":(255,240,140)
}

# Prototype pacing
SLICE_SECONDS = 28.0
DAYS_PER_SEASON = 7

def clamp(v, lo=0.0, hi=100.0): return lo if v < lo else hi if v > hi else v

def tile_center(t: Tuple[int,int]) -> pygame.Vector2:
    x,y = t
    return pygame.Vector2(x*TILE + TILE/2, y*TILE + TILE/2)

def journal_append(lines: List[str], msg: str):
    lines.append(msg)
    if len(lines) > 220:
        del lines[:60]
    try:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def codex_unlock(unlocked: set, journal: List[str], key: str):
    if key not in unlocked:
        unlocked.add(key)
        journal_append(journal, f"[CODEX UNLOCKED] {key}")

# ---------- Map ----------
def make_map() -> List[List[int]]:
    g = [[GRASS for _ in range(MAP_W)] for __ in range(MAP_H)]
    river_x = int(MAP_W*0.78)
    for y in range(MAP_H):
        w = 3 + (1 if y%6==0 else 0)
        for x in range(river_x, min(MAP_W, river_x+w)):
            g[y][x] = WATER

    # border trees
    for y in range(MAP_H):
        for x in range(MAP_W):
            if x<3 or y<3 or x>MAP_W-4 or y>MAP_H-4:
                if g[y][x]==GRASS and random.random()<0.65:
                    g[y][x]=TREE

    # village area
    vcx,vcy = int(MAP_W*0.32), int(MAP_H*0.52)
    for y in range(vcy-6, vcy+6):
        for x in range(vcx-8, vcx+8):
            if 0<=x<MAP_W and 0<=y<MAP_H:
                g[y][x]=GRASS if random.random()>0.08 else TREE

    # houses
    spots = [(vcx-5,vcy-3),(vcx-1,vcy-4),(vcx+3,vcy-2),(vcx-4,vcy+2),(vcx+2,vcy+3),(vcx+5,vcy-1)]
    for hx,hy in spots:
        for dy in range(2):
            for dx in range(2):
                x,y=hx+dx,hy+dy
                if 0<=x<MAP_W and 0<=y<MAP_H:
                    g[y][x]=HOUSE

    # carve simple paths
    def carve(a,b):
        x,y=a; bx,by=b
        for _ in range(2000):
            g[y][x]=PATH
            if (x,y)==(bx,by): break
            if random.random()<0.55: x += 1 if bx>x else -1 if bx<x else 0
            else: y += 1 if by>y else -1 if by<y else 0
            x=max(0,min(MAP_W-1,x)); y=max(0,min(MAP_H-1,y))
        g[by][bx]=PATH

    shrine = (int(MAP_W*0.55), int(MAP_H*0.25))
    bridge = (int(MAP_W*0.75), int(MAP_H*0.55))
    carve((vcx,vcy), shrine)
    carve((vcx,vcy), bridge)

    # extra trees
    for _ in range(420):
        x=random.randrange(MAP_W); y=random.randrange(MAP_H)
        if g[y][x]==GRASS and random.random()<0.22:
            g[y][x]=TREE
    return g

# ---------- State ----------
@dataclass
class NPC:
    name: str
    title: str
    tile: Tuple[int,int]
    pos: Tuple[float,float]
    stage: float = 0.0
    presence: int = 0
    witnessed_today: bool = False
    dream_today: bool = False

@dataclass
class Realm:
    pulse: Dict[str,float] = field(default_factory=lambda: {k:float(v) for k,v in BASE.items()})
    season: int = 0
    day: int = 1
    sl: int = 0
    year: int = 1

    resonance: int = 3
    res_cap: int = 3
    minor_used: int = 0
    major_used: int = 0
    cooldown: Dict[str,int] = field(default_factory=dict)

    ritual_success: int = 0
    fifth_silence: bool = False

    def season_name(self): return SEASONS[self.season]
    def slice_name(self): return SLICES[self.sl]

    def drift_day(self):
        for k,r in DRIFT.items():
            self.pulse[k] += (BASE[k]-self.pulse[k])*r
        for k in PULSE_KEYS:
            self.pulse[k] = clamp(self.pulse[k])

    def apply(self, delta: Dict[str,float]):
        for k,v in delta.items():
            if k in self.pulse:
                self.pulse[k] = clamp(self.pulse[k] + float(v))

    def new_day(self, npcs: List[NPC]):
        self.minor_used = 0
        self.major_used = 0
        self.resonance = min(self.res_cap, self.resonance + 1)
        for n in npcs:
            n.witnessed_today = False
            n.dream_today = False
        for g in list(self.cooldown.keys()):
            self.cooldown[g] = max(0, self.cooldown[g]-1)
            if self.cooldown[g] <= 0:
                del self.cooldown[g]
        self.drift_day()

# ---------- Mechanics ----------
def can_cast(realm: Realm, gname: str) -> Tuple[bool,str]:
    g = GLYPHS[gname]
    if realm.resonance < g["cost"]: return False, "not enough resonance"
    if gname in realm.cooldown and realm.cooldown[gname] > 0: return False, "cooldown"
    if g["tier"]=="minor" and realm.minor_used >= DAILY_LIMITS["minor"]: return False, "minor limit"
    if g["tier"]=="major" and realm.major_used >= DAILY_LIMITS["major"]: return False, "major limit"
    return True,"ok"

def cast_glyph(realm: Realm, journal: List[str], gname: str):
    ok,msg = can_cast(realm,gname)
    if not ok:
        journal_append(journal, f"[GLYPH FAIL] {gname}: {msg}")
        return
    g = GLYPHS[gname]
    realm.resonance -= g["cost"]
    realm.apply(g["delta"])
    if g["tier"]=="minor": realm.minor_used += 1
    else:
        realm.major_used += 1
        realm.cooldown[gname] = 1
    journal_append(journal, f"[GLYPH] {gname} cast. Resonance {realm.resonance}/{realm.res_cap}")

def witness(realm: Realm, npc: NPC, codex: set, journal: List[str]):
    if npc.witnessed_today:
        journal_append(journal, f"[WITNESS] {npc.name} already witnessed today.")
        return
    npc.witnessed_today = True
    npc.presence += 1
    realm.apply({"harmony":+1,"turbulence":-1,"remembrance":+0.5})
    journal_append(journal, f"[WITNESS] You linger near {npc.name}. The air softens.")
    if npc.name.lower()=="aya" and npc.presence == 1:
        codex_unlock(codex, journal, "Aya Arc Preview")

def seed_dream(realm: Realm, npc: NPC, tone: str, embed: str, codex: set, journal: List[str]) -> str:
    if npc.dream_today: return "Already seeded today."
    if npc.presence < 3: return "Not eligible yet (witness 3 days)."
    if realm.resonance < 1: return "Not enough resonance."
    npc.dream_today = True
    realm.resonance -= 1

    # simple outcome model
    p_threshold = 0.05
    if realm.pulse["turbulence"] <= 20: p_threshold += 0.03
    if realm.pulse["dream"] >= 60: p_threshold += 0.02
    if embed == "Anchor": p_threshold += 0.02
    roll = random.random()
    if roll < p_threshold:
        npc.stage = min(4.0, npc.stage + 1.0)
        out = "THRESHOLD"
        realm.apply({"remembrance":+2,"veil":+1})
    else:
        npc.stage = min(4.0, npc.stage + 0.5)
        out = "BEHAVIOR"
        realm.apply({"dream":+1})

    if npc.stage >= 1.0: codex_unlock(codex, journal, "Awakening: Stage 1")
    if npc.stage >= 2.0: codex_unlock(codex, journal, "Awakening: Stage 2")

    journal_append(journal, f"[DREAM] {npc.name} • Tone={tone} • Embedded={embed} • Outcome={out}")
    return f"Dream outcome: {out}"

def maybe_ritual_pending(realm: Realm) -> Optional[str]:
    for name, info in RITUALS.items():
        if realm.season_name() == info["season"] and realm.day in info["days"] and realm.slice_name() == info["slice"]:
            # chance influenced by harmony/turbulence
            chance = 0.65
            if realm.pulse["harmony"] >= 60: chance += 0.08
            if realm.pulse["turbulence"] >= 55: chance -= 0.15
            if name == "Night of the Fifth Silence":
                prereq = realm.pulse["turbulence"] <= 30 and (realm.pulse["dream"] >= 60 or realm.pulse["remembrance"] >= 60)
                if not prereq:
                    continue
            if random.random() < max(0.10, chance):
                return name
    return None

def resolve_ritual(realm: Realm, ritual_name: str, stance: str, bolster: bool, codex: set, journal: List[str]):
    info = RITUALS[ritual_name]
    # weights
    w_soft, w_strong, w_rare, w_mis = 55, 28, 8, 10
    if stance == "Stillness":
        w_mis -= 3
        w_strong += max(0, (25 - realm.pulse["turbulence"]) * 0.08)
    elif stance == "Attunement":
        w_rare += max(0, (realm.pulse["dream"] - 55) * 0.06) + max(0,(realm.pulse["remembrance"]-55)*0.05)
    elif stance == "Offering":
        w_strong += 2
        if realm.pulse["turbulence"] > 55: w_mis += 2

    if bolster and realm.resonance >= 1:
        realm.resonance -= 1
        w_strong += 4; w_rare += 2; w_mis -= 2

    weights = [max(1,w_soft), max(1,w_strong), max(1,w_rare), max(1,w_mis)]
    bands   = ["soft","strong","rare","misaligned"]
    band = random.choices(bands, weights=weights, k=1)[0]

    realm.apply(info[band])
    journal_append(journal, f"[RITUAL] {ritual_name} • Stance={stance} • Outcome={band.upper()}")

    if ritual_name == "Lantern Walk" and band != "misaligned":
        codex_unlock(codex, journal, "Ritual: Lantern Walk")
        realm.ritual_success += 1

    if ritual_name == "Night of the Fifth Silence" and band != "misaligned":
        codex_unlock(codex, journal, "Ritual: Night of the Fifth Silence")
        realm.fifth_silence = True
        realm.ritual_success += 1

# ---------- Drawing ----------
def draw_map(screen: pygame.Surface, grid: List[List[int]], cam: pygame.Vector2):
    x0 = max(0, int(cam.x // TILE) - 1)
    y0 = max(0, int(cam.y // TILE) - 1)
    x1 = min(MAP_W, int((cam.x + W) // TILE) + 2)
    y1 = min(MAP_H, int((cam.y + H) // TILE) + 2)
    for y in range(y0,y1):
        for x in range(x0,x1):
            t = grid[y][x]
            rx = x*TILE - cam.x
            ry = y*TILE - cam.y
            pygame.draw.rect(screen, COL[t], pygame.Rect(rx,ry,TILE,TILE))
            if t == PATH and (x+y) % 7 == 0:
                pygame.draw.circle(screen, (170,150,110), (int(rx+TILE/2), int(ry+TILE/2)), 2)

def draw_panel(screen, rect, border=True):
    pygame.draw.rect(screen, COL["ui_panel"], rect, border_radius=12)
    if border:
        pygame.draw.rect(screen, COL["ui_border"], rect, 1, border_radius=12)

def wrap(font, text, maxw):
    words=text.split()
    lines=[]
    cur=""
    for w in words:
        test=(cur+" "+w).strip()
        if font.size(test)[0] <= maxw:
            cur=test
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return lines

# ---------- Collision ----------
def is_blocked(grid, px, py) -> bool:
    tx = int(px // TILE)
    ty = int(py // TILE)
    if tx<0 or ty<0 or tx>=MAP_W or ty>=MAP_H:
        return True
    return grid[ty][tx] in BLOCKED

def move_with_collision(grid, pos: pygame.Vector2, vel: pygame.Vector2, dt: float, speed: float) -> pygame.Vector2:
    if vel.length_squared() == 0:
        return pos
    v = vel.normalize() * speed * dt
    nxt = pygame.Vector2(pos.x + v.x, pos.y)
    if not is_blocked(grid, nxt.x, nxt.y):
        pos.x = nxt.x
    nxt = pygame.Vector2(pos.x, pos.y + v.y)
    if not is_blocked(grid, nxt.x, nxt.y):
        pos.y = nxt.y
    return pos

# ---------- Save/Load ----------
def save_state(realm: Realm, npcs: List[NPC], codex: set, journal: List[str]):
    data = {
        "realm": asdict(realm),
        "npcs": [asdict(n) for n in npcs],
        "codex": sorted(list(codex)),
        "version":"v0.7"
    }
    with open(SAVE_FILE,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2)
    journal_append(journal, f"[SAVE] Wrote {SAVE_FILE}")

def load_state(realm: Realm, npcs: List[NPC], codex: set, journal: List[str]) -> bool:
    if not os.path.exists(SAVE_FILE):
        journal_append(journal, "[LOAD] No save file found.")
        return False
    with open(SAVE_FILE,"r",encoding="utf-8") as f:
        data = json.load(f)
    r = data["realm"]
    realm.pulse = {k:float(v) for k,v in r["pulse"].items()}
    realm.season = int(r["season"]); realm.day=int(r["day"]); realm.sl=int(r["sl"]); realm.year=int(r["year"])
    realm.resonance=int(r["resonance"]); realm.res_cap=int(r.get("res_cap",3))
    realm.minor_used=int(r.get("minor_used",0)); realm.major_used=int(r.get("major_used",0))
    realm.cooldown={k:int(v) for k,v in r.get("cooldown",{}).items()}
    realm.ritual_success=int(r.get("ritual_success",0)); realm.fifth_silence=bool(r.get("fifth_silence",False))

    loaded = {n["name"]:n for n in data.get("npcs", [])}
    for n in npcs:
        if n.name in loaded:
            ln = loaded[n.name]
            n.tile = tuple(ln["tile"])
            n.pos = tuple(ln["pos"])
            n.stage = float(ln.get("stage",0))
            n.presence = int(ln.get("presence",0))
            n.witnessed_today = bool(ln.get("witnessed_today",False))
            n.dream_today = bool(ln.get("dream_today",False))

    codex.clear()
    for p in data.get("codex", []):
        codex.add(p)

    journal_append(journal, f"[LOAD] Loaded {SAVE_FILE}")
    return True

# ---------- Main ----------
def main():
    pygame.init()
    screen = pygame.display.set_mode((W,H))
    pygame.display.set_caption("Echo Realms — Visual Prototype v0.7")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    small = pygame.font.SysFont(None, 18)
    tiny = pygame.font.SysFont(None, 16)

    grid = make_map()
    journal: List[str] = []
    codex: set = set()
    journal_append(journal, "[SYSTEM] Echo Realms v0.7 started.")

    # Player spawn (village-ish)
    vcx,vcy = int(MAP_W*0.32), int(MAP_H*0.52)
    player = tile_center((vcx, vcy))
    player_speed = 185.0

    # NPCs
    core = [
        ("Aya","Dreamweaver of Fern Ink"),
        ("Eila","Seed Listener"),
        ("Taia","Root Tender"),
        ("Brendon","Forge Hand"),
        ("Myron","Petal Scribe"),
        ("Lucas","Sun Keeper"),
        ("Orwin","Sky Courier"),
    ]
    homes = [(vcx-6,vcy-3),(vcx-2,vcy-5),(vcx+2,vcy-3),(vcx-5,vcy+3),(vcx+3,vcy+4),(vcx+6,vcy+1),(vcx-1,vcy+6)]
    npcs: List[NPC] = []
    for (nm,title), ht in zip(core, homes):
        t = (max(0,min(MAP_W-1,ht[0])), max(0,min(MAP_H-1,ht[1])))
        pos = tile_center(t)
        npcs.append(NPC(nm,title,t,(pos.x,pos.y)))

    realm = Realm()

    # Camera follows player
    cam = pygame.Vector2(0,0)

    # UI
    overlay = None  # None, "glyph","dream","ritual","journal","codex"
    selected: Optional[NPC] = None
    glyph_names = sorted(list(GLYPHS.keys()))
    glyph_idx = 0
    dream_tone = 0
    dream_embed = 0
    ritual_pending: Optional[str] = None
    stance_idx = 0
    bolster = False
    stances = ["Stillness","Offering","Attunement"]
    journal_scroll = 0
    codex_list = []

    slice_timer = 0.0

    def near(a: pygame.Vector2, b: pygame.Vector2, dist=44.0) -> bool:
        return (a-b).length() <= dist

    running=True
    while running:
        dt = clock.tick(FPS)/1000.0

        # Time progression (pause when in overlay)
        if overlay is None:
            slice_timer += dt
            if slice_timer >= SLICE_SECONDS:
                slice_timer = 0.0
                prev = realm.slice_name()
                realm.sl = (realm.sl + 1) % 4
                if realm.sl == 0:  # Dawn => new day
                    realm.day += 1
                    if realm.day > DAYS_PER_SEASON:
                        realm.day = 1
                        realm.season = (realm.season + 1) % 4
                        if realm.season == 0:
                            realm.year += 1
                            realm.ritual_success = 0
                            realm.fifth_silence = False
                    realm.new_day(npcs)
                journal_append(journal, f"[TIME] {prev} → {realm.slice_name()} (Day {realm.day}/7, {realm.season_name()})")

                # maybe ritual triggers now
                rp = maybe_ritual_pending(realm)
                if rp:
                    ritual_pending = rp
                    overlay = "ritual"
                    stance_idx = 0
                    bolster = False
                    journal_append(journal, f"[RITUAL APPROACHES] {rp} — choose alignment (Enter).")

        # Input
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running=False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_q:
                    running=False
                if e.key == pygame.K_ESCAPE:
                    if overlay is not None:
                        overlay = None
                    else:
                        selected = None

                if e.key == pygame.K_F5:
                    save_state(realm, npcs, codex, journal)
                if e.key == pygame.K_F9:
                    load_state(realm, npcs, codex, journal)

                # open overlays
                if overlay is None:
                    if e.key == pygame.K_g: overlay = "glyph"
                    if e.key == pygame.K_d and selected: overlay = "dream"
                    if e.key == pygame.K_j:
                        overlay = "journal"
                        journal_scroll = max(0, len(journal)-22)
                    if e.key == pygame.K_c:
                        overlay = "codex"
                        codex_list = sorted(list(codex))

                    # witness key
                    if e.key == pygame.K_e and selected:
                        sp = pygame.Vector2(selected.pos[0], selected.pos[1])
                        if near(player, sp):
                            witness(realm, selected, codex, journal)
                        else:
                            journal_append(journal, "[WITNESS] Too far. Walk closer.")

                # glyph panel
                if overlay == "glyph":
                    if e.key == pygame.K_UP: glyph_idx = max(0, glyph_idx-1)
                    if e.key == pygame.K_DOWN: glyph_idx = min(len(glyph_names)-1, glyph_idx+1)
                    if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        gname = glyph_names[glyph_idx]
                        cast_glyph(realm, journal, gname)

                # dream panel
                if overlay == "dream" and selected:
                    if e.key == pygame.K_LEFT: dream_tone = (dream_tone-1) % len(TONES)
                    if e.key == pygame.K_RIGHT: dream_tone = (dream_tone+1) % len(TONES)
                    if e.key == pygame.K_UP: dream_embed = (dream_embed-1) % len(glyph_names)
                    if e.key == pygame.K_DOWN: dream_embed = (dream_embed+1) % len(glyph_names)
                    if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        msg = seed_dream(realm, selected, TONES[dream_tone], glyph_names[dream_embed], codex, journal)
                        journal_append(journal, "[DREAM RESULT] " + msg)

                # ritual panel
                if overlay == "ritual" and ritual_pending:
                    if e.key == pygame.K_LEFT: stance_idx = (stance_idx-1) % len(stances)
                    if e.key == pygame.K_RIGHT: stance_idx = (stance_idx+1) % len(stances)
                    if e.key == pygame.K_b: bolster = not bolster
                    if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        resolve_ritual(realm, ritual_pending, stances[stance_idx], bolster, codex, journal)
                        ritual_pending = None
                        overlay = None

                # journal panel
                if overlay == "journal":
                    if e.key == pygame.K_UP: journal_scroll = max(0, journal_scroll-1)
                    if e.key == pygame.K_DOWN: journal_scroll = min(max(0,len(journal)-1), journal_scroll+1)
                    if e.key == pygame.K_PAGEUP: journal_scroll = max(0, journal_scroll-10)
                    if e.key == pygame.K_PAGEDOWN: journal_scroll = min(max(0,len(journal)-1), journal_scroll+10)

                # codex panel
                if overlay == "codex":
                    # just refresh list when you open again
                    pass

            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and overlay is None:
                mx,my = e.pos
                world = pygame.Vector2(mx + cam.x, my + cam.y)
                hit = None
                for n in npcs:
                    np = pygame.Vector2(n.pos[0], n.pos[1])
                    if (np - world).length() <= 16:
                        hit = n
                        break
                if hit:
                    selected = hit
                    journal_append(journal, f"[SELECT] {hit.name}")

        # Movement (only if no overlay)
        if overlay is None:
            keys = pygame.key.get_pressed()
            vel = pygame.Vector2(0,0)
            if keys[pygame.K_a] or keys[pygame.K_LEFT]: vel.x -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: vel.x += 1
            if keys[pygame.K_w] or keys[pygame.K_UP]: vel.y -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]: vel.y += 1
            player = move_with_collision(grid, player, vel, dt, player_speed)

            # simple npc wander
            for n in npcs:
                npos = pygame.Vector2(n.pos[0], n.pos[1])
                # tiny random drift if tile not blocked
                ang = random.random()*math.tau
                step = pygame.Vector2(math.cos(ang), math.sin(ang)) * 18.0 * dt
                nxt = npos + step
                if not is_blocked(grid, nxt.x, nxt.y):
                    n.pos = (nxt.x, nxt.y)

        # Camera follow
        cam.x = clamp(player.x - W/2, 0, MAP_W*TILE - W)
        cam.y = clamp(player.y - H/2, 0, MAP_H*TILE - H)

        # Render
        screen.fill((0,0,0))
        draw_map(screen, grid, cam)

        # NPCs
        for n in npcs:
            p = pygame.Vector2(n.pos[0], n.pos[1]) - cam
            c = COL["sel"] if (selected is n) else COL["npc"]
            pygame.draw.circle(screen, c, (int(p.x), int(p.y)), 10)
            if n.presence >= 3:
                pygame.draw.circle(screen, (200,200,200), (int(p.x), int(p.y)), 14, 1)

        # Player
        pp = player - cam
        pygame.draw.circle(screen, COL["player"], (int(pp.x), int(pp.y)), 9)

        # HUD
        hud = pygame.Rect(10,10,370,H-20)
        pygame.draw.rect(screen, COL["ui_bg"], hud, border_radius=10)
        pygame.draw.rect(screen, COL["ui_border"], hud, 1, border_radius=10)

        def blit(txt, x, y, f=small, col=COL["ui_text"]):
            screen.blit(f.render(txt, True, col), (x,y))

        y = 18
        blit("Echo Realms: The Witness", 18, y, font, COL["accent"]); y += 28
        blit(f"Year {realm.year} • {realm.season_name()} • Day {realm.day}/7 • {realm.slice_name()}", 18, y, small); y += 22
        blit(f"Resonance {realm.resonance}/{realm.res_cap} • Glyphs minor {realm.minor_used}/{DAILY_LIMITS['minor']} major {realm.major_used}/{DAILY_LIMITS['major']}", 18, y, tiny, COL["ui_dim"]); y += 22

        for k in PULSE_KEYS:
            v = realm.pulse[k]
            blit(f"{k.capitalize():12} {int(v):3d}", 18, y, tiny); y += 18

        y += 8
        if selected:
            blit("Selected:", 18, y, tiny, COL["ui_dim"]); y += 18
            blit(f"{selected.name} — {selected.title}", 18, y, small); y += 20
            elig = "✓ dream eligible" if selected.presence >= 3 else "✖ dream locked (witness 3 days)"
            blit(f"Presence {selected.presence} • Stage {selected.stage:.1f} • {elig}", 18, y, tiny); y += 20

        y = H - 150
        blit("Recent Journal:", 18, y, tiny, COL["ui_dim"]); y += 18
        for ln in journal[-6:]:
            blit(ln[:52] + ("…" if len(ln)>52 else ""), 18, y, tiny); y += 18

        # Overlay panels
        if overlay is not None:
            panel = pygame.Rect(410, 70, 690, 500)
            draw_panel(screen, panel)
            if overlay == "glyph":
                blit("Glyphs (Up/Down, Enter cast, Esc close)", panel.x+14, panel.y+12, small, COL["accent"])
                y2 = panel.y+50
                for i, gname in enumerate(glyph_names[:18]):
                    ok,_ = can_cast(realm,gname)
                    col = COL["accent"] if i==glyph_idx else (COL["ui_text"] if ok else COL["ui_dim"])
                    g = GLYPHS[gname]
                    blit(f"{gname} ({g['tier']}, cost {g['cost']})", panel.x+14, y2, small, col)
                    y2 += 24
            elif overlay == "dream" and selected:
                blit("Dream Seeding (Left/Right tone, Up/Down embed, Enter seed, Esc close)", panel.x+14, panel.y+12, tiny, COL["accent"])
                blit(f"Target: {selected.name}", panel.x+14, panel.y+44, small)
                elig = selected.presence >= 3
                blit(f"Eligible: {'YES' if elig else 'NO (witness 3 days)'}", panel.x+14, panel.y+70, small, COL["ui_text"] if elig else COL["danger"])
                blit(f"Tone: {TONES[dream_tone]}", panel.x+14, panel.y+110, small, COL["accent"])
                blit(f"Embedded Glyph: {glyph_names[dream_embed]}", panel.x+14, panel.y+140, small, COL["accent"])
                blit(f"Cost: 1 resonance (you have {realm.resonance}/{realm.res_cap})", panel.x+14, panel.y+176, tiny, COL["ui_dim"])
            elif overlay == "ritual" and ritual_pending:
                blit("Ritual Alignment (Left/Right stance, B bolster, Enter resolve)", panel.x+14, panel.y+12, tiny, COL["accent"])
                blit(f"Ritual: {ritual_pending}", panel.x+14, panel.y+44, small)
                blit(f"Stance: {stances[stance_idx]}", panel.x+14, panel.y+80, small, COL["accent"])
                bcol = COL["accent"] if bolster else COL["ui_dim"]
                blit(f"Bolster: {'ON' if bolster else 'OFF'} (spend 1 resonance)", panel.x+14, panel.y+112, small, bcol)
                blit("Rituals happen to you. You can only choose posture—and prepare the realm.", panel.x+14, panel.y+160, tiny)
            elif overlay == "journal":
                blit("Journal (Up/Down/PageUp/PageDown, Esc close)", panel.x+14, panel.y+12, tiny, COL["accent"])
                y2 = panel.y+48
                lines = journal[journal_scroll:journal_scroll+22]
                for ln in lines:
                    blit((ln[:92] + ("…" if len(ln)>92 else "")), panel.x+14, y2, tiny)
                    y2 += 20
            elif overlay == "codex":
                blit("Codex (Esc close)", panel.x+14, panel.y+12, small, COL["accent"])
                codex_list = sorted(list(codex))
                if not codex_list:
                    blit("No pages unlocked yet.", panel.x+14, panel.y+54, small, COL["ui_dim"])
                else:
                    # show list and first page text
                    left = pygame.Rect(panel.x+14, panel.y+54, 260, 430)
                    right= pygame.Rect(panel.x+290, panel.y+54, 386, 430)
                    pygame.draw.rect(screen, (12,12,12), left, border_radius=10)
                    pygame.draw.rect(screen, COL["ui_border"], left, 1, border_radius=10)
                    pygame.draw.rect(screen, (12,12,12), right, border_radius=10)
                    pygame.draw.rect(screen, COL["ui_border"], right, 1, border_radius=10)

                    y2 = left.y+10
                    for p in codex_list[:20]:
                        blit(p[:30] + ("…" if len(p)>30 else ""), left.x+10, y2, tiny)
                        y2 += 20

                    page = codex_list[0]
                    blit(page, right.x+10, right.y+10, small, COL["accent"])
                    body = CODEX_TEXT.get(page, "(text missing)")
                    y3 = right.y+40
                    for ln in wrap(tiny, body, right.w-20)[:18]:
                        blit(ln, right.x+10, y3, tiny)
                        y3 += 18

        # footer hint
        hint = tiny.render("Move WASD • Click NPC to select • E witness • G glyph • D dream • R ritual • J journal • C codex • F5 save • F9 load • Q quit", True, (240,240,240))
        screen.blit(hint, (W - hint.get_width() - 12, 12))

        pygame.display.flip()

    journal_append(journal, "[SYSTEM] Session ended.")
    pygame.quit()

if __name__ == "__main__":
    main()

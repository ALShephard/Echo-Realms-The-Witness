# Echo Realms — Visual Prototype v0.8
# Single-file pygame prototype for Echo Realms: The Witness
# Drop into: src/echo_realms_visual_proto_v0_8.py
# Run: python src/echo_realms_visual_proto_v0_8.py

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

# -----------------------------
# Paths / files (repo-relative)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # repo root (assuming file is in /src)
SAVES_DIR = BASE_DIR / "saves"
SAVES_DIR.mkdir(parents=True, exist_ok=True)

SAVE_FILE = SAVES_DIR / "save_echo_realms.json"
JOURNAL_FILE = SAVES_DIR / "journal.txt"

# -----------------------------
# Game constants
# -----------------------------
W, H = 1200, 720
FPS = 60

TILE = 40
MAP_W, MAP_H = 48, 32  # tiles
UI_W = 360

SLICE_SECONDS = 22.0
SLICES = ["Dawn", "Day", "Dusk", "Night"]

SEASONS = ["Verdance", "Emberwane", "Glimmereave", "Frostwhisper"]
DAYS_PER_SEASON = 7
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)

COL = {
    "bg": (10, 14, 18),
    "grass": (30, 110, 55),
    "grass2": (28, 100, 50),
    "tree": (18, 70, 35),
    "water": (34, 86, 130),
    "path": (128, 108, 70),
    "rock": (90, 75, 58),
    "ui": (12, 14, 16),
    "ui2": (22, 25, 30),
    "ui_border": (40, 45, 55),
    "ui_text": (230, 230, 230),
    "muted": (170, 170, 170),
    "accent": (255, 240, 140),
    "good": (100, 255, 100),
    "bad": (255, 100, 100),
}

# Tile types
T_GRASS = 0
T_TREE = 1
T_WATER = 2
T_PATH = 3
T_ROCK = 4

# Ritual schedule (simple telegraph + overlay)
RITUALS = {
    "First Bloom":   {"season": "Verdance",    "days": [1, 2], "slice": "Dawn",  "text": "A warmth rises in the roots. The realm remembers spring."},
    "Kindling":      {"season": "Emberwane",   "days": [3, 5], "slice": "Dusk",  "text": "Embers drift in the air. A vow is spoken without words."},
    "Fifth Silence": {"season": "Glimmereave", "days": [5],    "slice": "Dawn",  "text": "The forest holds its breath. Even wind becomes prayer."},
    "Snow Oath":     {"season": "Frostwhisper","days": [6, 7], "slice": "Night", "text": "A hush of snow seals a promise. The veil grows thin."},
}

GLYPHS_MINOR = {
    "Kindle":   {"delta": {"growth": +6, "turbulence": +2}, "desc": "Encourage small growth; slightly stirs the field."},
    "Soften":   {"delta": {"harmony": +6, "veil": +3},      "desc": "Ease tension; a gentle veil settles."},
    "Anchor":   {"delta": {"remembrance": +6},              "desc": "Stabilize memory threads."},
}
GLYPHS_MAJOR = {
    "Veilwalk": {"delta": {"veil": +10, "turbulence": +6},  "desc": "Deepen veil presence; risk more turbulence."},
}

DREAMS = [
    "A lantern floating over the river",
    "A village singing to the moon",
    "A forgotten name returning gently",
    "A door in a tree that opens inward",
    "Warm bread and laughter at dusk",
]

NPC_NAMES = [
    "Ari", "Noa", "Kian", "Mira", "Sable", "Tari", "Eli", "Vera", "Sol", "Nyx",
    "Rune", "Iona", "Cato", "Luz", "Iris", "Oren", "Pax", "Eden", "Juno", "Kai"
]

CODEX_TEXT = {
    "The Witness": "You do not command. You attend.\n\nRecognition is not conquest.\nIt is remembrance made visible.",
    "Forest Haven": "A small realm where paths are soft and trees listen.\n\nNPCs live simple lives here.\nRituals occur in seasons, days, and slices.",
    "Proximity": "To witness someone, you must be close.\n\nA ring appears around your selected NPC:\n• Green = in range\n• Red = too far",
}

# -----------------------------
# Data models
# -----------------------------
@dataclass
class NPC:
    name: str
    x: float
    y: float
    home_tx: int
    home_ty: int
    witnessed: bool = False

    def pos(self) -> pygame.Vector2:
        return pygame.Vector2(self.x, self.y)

    def home_pos(self) -> pygame.Vector2:
        return pygame.Vector2((self.home_tx + 0.5) * TILE, (self.home_ty + 0.5) * TILE)

@dataclass
class RealmState:
    year: int = 1
    day: int = 1
    slice_idx: int = 0
    pulse: Dict[str, int] = None
    resonance: int = 3
    minor_cast: int = 0
    major_cast: int = 0

    def __post_init__(self):
        if self.pulse is None:
            self.pulse = {
                "growth": 55,
                "harmony": 55,
                "remembrance": 35,
                "dream": 30,
                "veil": 60,
                "turbulence": 15,
            }

    def slice_name(self) -> str:
        return SLICES[self.slice_idx]

    def season_name(self) -> str:
        season_idx = (self.day - 1) // DAYS_PER_SEASON
        return SEASONS[max(0, min(len(SEASONS) - 1, season_idx))]

    def day_in_season(self) -> int:
        return ((self.day - 1) % DAYS_PER_SEASON) + 1

# -----------------------------
# Helpers
# -----------------------------
def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def dist(a: pygame.Vector2, b: pygame.Vector2) -> float:
    return (a - b).length()

def near(player_pos: pygame.Vector2, npc_pos: pygame.Vector2, radius: float = 44.0) -> bool:
    return dist(player_pos, npc_pos) <= radius

def journal_append(journal: List[str], text: str):
    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {text}"
    journal.append(line)
    # keep in-memory journal bounded
    if len(journal) > 500:
        del journal[:-500]
    try:
        with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def wrap_text(font: pygame.font.Font, text: str, max_w: int) -> List[str]:
    words = text.replace("\r", "").split()
    out: List[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.size(test)[0] <= max_w:
            cur = test
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out

# -----------------------------
# Map generation / collision
# -----------------------------
def make_grid(seed: int = 7) -> List[List[int]]:
    rnd = random.Random(seed)
    g = [[T_GRASS for _ in range(MAP_W)] for _ in range(MAP_H)]

    # scatter trees
    for y in range(MAP_H):
        for x in range(MAP_W):
            if rnd.random() < 0.08:
                g[y][x] = T_TREE

    # water strip
    ry = rnd.randint(8, MAP_H - 8)
    for x in range(2, MAP_W - 2):
        if rnd.random() < 0.85:
            g[ry][x] = T_WATER
            if rnd.random() < 0.45 and 0 <= ry+1 < MAP_H:
                g[ry+1][x] = T_WATER

    # path (simple drunk walk)
    px, py = rnd.randint(4, 8), rnd.randint(4, MAP_H - 5)
    for _ in range(MAP_W * 3):
        g[py][px] = T_PATH
        if rnd.random() < 0.65:
            px += 1
        else:
            py += rnd.choice([-1, 0, 1])
        px = clamp(px, 1, MAP_W - 2)
        py = clamp(py, 1, MAP_H - 2)

    # rocks near path
    for _ in range(50):
        x = rnd.randint(1, MAP_W - 2)
        y = rnd.randint(1, MAP_H - 2)
        if g[y][x] == T_GRASS and any(g[ny][nx] == T_PATH for ny in range(max(0,y-1), min(MAP_H,y+2)) for nx in range(max(0,x-1), min(MAP_W,x+2))):
            if rnd.random() < 0.30:
                g[y][x] = T_ROCK

    return g

def is_blocked(grid: List[List[int]], wx: float, wy: float) -> bool:
    tx = int(wx // TILE)
    ty = int(wy // TILE)
    if tx < 0 or ty < 0 or tx >= MAP_W or ty >= MAP_H:
        return True
    t = grid[ty][tx]
    return t in (T_TREE, T_WATER, T_ROCK)

def tile_center(tx: int, ty: int) -> pygame.Vector2:
    return pygame.Vector2((tx + 0.5) * TILE, (ty + 0.5) * TILE)

# -----------------------------
# Save / load
# -----------------------------
def save_state(path: Path, realm: RealmState, player: pygame.Vector2, npcs: List[NPC], codex: List[str]):
    data = {
        "realm": {
            "year": realm.year,
            "day": realm.day,
            "slice_idx": realm.slice_idx,
            "pulse": realm.pulse,
            "resonance": realm.resonance,
            "minor_cast": realm.minor_cast,
            "major_cast": realm.major_cast,
        },
        "player": {"x": player.x, "y": player.y},
        "npcs": [asdict(n) for n in npcs],
        "codex": codex,
        "version": "0.8",
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def load_state(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

# -----------------------------
# Gameplay actions
# -----------------------------
def witness(realm: RealmState, npc: NPC, codex: List[str], journal: List[str]):
    if npc.witnessed:
        journal_append(journal, f"[WITNESS] {npc.name} already witnessed.")
        return
    npc.witnessed = True
    realm.resonance = clamp(realm.resonance + 1, 0, 9)
    journal_append(journal, f"[WITNESS] You witness {npc.name}. Resonance +1.")
    page = f"{npc.name} — Seen"
    if page not in codex:
        codex.append(page)

def cast_glyph(realm: RealmState, journal: List[str], name: str):
    if name in GLYPHS_MINOR:
        realm.minor_cast += 1
        d = GLYPHS_MINOR[name]["delta"]
    elif name in GLYPHS_MAJOR:
        realm.major_cast += 1
        d = GLYPHS_MAJOR[name]["delta"]
    else:
        return
    for k, dv in d.items():
        realm.pulse[k] = clamp(int(realm.pulse[k] + dv), 0, 100)
    journal_append(journal, f"[GLYPH] {name} cast. Field shifts: {d}")

def seed_dream(realm: RealmState, journal: List[str], npc: Optional[NPC]):
    dream = random.choice(DREAMS)
    realm.pulse["dream"] = clamp(realm.pulse["dream"] + 6, 0, 100)
    who = npc.name if npc else "the realm"
    journal_append(journal, f"[DREAM] You seed '{dream}' into {who}.")

def ritual_apply(realm: RealmState, journal: List[str], ritual_name: str):
    info = RITUALS.get(ritual_name)
    if not info:
        return
    journal_append(journal, f"[RITUAL] {ritual_name}: {info['text']}")
    # small ritual deltas by theme
    if ritual_name == "First Bloom":
        realm.pulse["growth"] = clamp(realm.pulse["growth"] + 10, 0, 100)
        realm.pulse["harmony"] = clamp(realm.pulse["harmony"] + 4, 0, 100)
    elif ritual_name == "Kindling":
        realm.pulse["turbulence"] = clamp(realm.pulse["turbulence"] + 12, 0, 100)
        realm.pulse["remembrance"] = clamp(realm.pulse["remembrance"] + 6, 0, 100)
    elif ritual_name == "Fifth Silence":
        realm.pulse["veil"] = clamp(realm.pulse["veil"] + 10, 0, 100)
        realm.pulse["turbulence"] = clamp(realm.pulse["turbulence"] - 8, 0, 100)
    elif ritual_name == "Snow Oath":
        realm.pulse["veil"] = clamp(realm.pulse["veil"] + 8, 0, 100)
        realm.pulse["dream"] = clamp(realm.pulse["dream"] + 8, 0, 100)

# -----------------------------
# Main
# -----------------------------
def main():
    pygame.init()
    pygame.display.set_caption("Echo Realms — Visual Prototype v0.8")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 18)
    small = pygame.font.SysFont("consolas", 16)
    tiny = pygame.font.SysFont("consolas", 14)
    big = pygame.font.SysFont("consolas", 28, bold=True)

    # New game? Clear old journal for fresh run (optional)
    if not SAVE_FILE.exists():
        try:
            JOURNAL_FILE.write_text("", encoding="utf-8")
        except Exception:
            pass

    grid = make_grid(seed=7)

    realm = RealmState()
    player = pygame.Vector2(6 * TILE, 6 * TILE)

    # NPCs placed near paths on grass
    npcs: List[NPC] = []
    rnd = random.Random(11)
    tries = 0
    while len(npcs) < 8 and tries < 2000:
        tries += 1
        tx = rnd.randint(2, MAP_W - 3)
        ty = rnd.randint(2, MAP_H - 3)
        if grid[ty][tx] != T_GRASS:
            continue
        # prefer near path
        near_path = any(grid[ny][nx] == T_PATH for ny in range(ty-1, ty+2) for nx in range(tx-1, tx+2))
        if not near_path and rnd.random() < 0.80:
            continue
        name = NPC_NAMES[len(npcs) % len(NPC_NAMES)]
        pos = tile_center(tx, ty)
        npcs.append(NPC(name=name, x=float(pos.x), y=float(pos.y), home_tx=tx, home_ty=ty))

    # Load if exists
    codex: List[str] = ["The Witness", "Forest Haven", "Proximity"]
    journal: List[str] = []
    data = load_state(SAVE_FILE)
    if data:
        try:
            r = data.get("realm", {})
            realm.year = int(r.get("year", 1))
            realm.day = int(r.get("day", 1))
            realm.slice_idx = int(r.get("slice_idx", 0)) % len(SLICES)
            realm.pulse.update(r.get("pulse", {}))
            realm.resonance = int(r.get("resonance", 3))
            realm.minor_cast = int(r.get("minor_cast", 0))
            realm.major_cast = int(r.get("major_cast", 0))
            p = data.get("player", {})
            player.update(float(p.get("x", player.x)), float(p.get("y", player.y)))
            codex = list(data.get("codex", codex))
            # npcs restore
            loaded_npcs = data.get("npcs", None)
            if loaded_npcs:
                npcs = []
                for nd in loaded_npcs:
                    npcs.append(NPC(**nd))
            journal_append(journal, "[SYSTEM] Save loaded.")
        except Exception:
            journal_append(journal, "[SYSTEM] Save load failed; starting fresh.")
    else:
        journal_append(journal, "[SYSTEM] New realm started.")

    # UI state
    overlay: Optional[str] = None  # None, "glyph", "dream", "ritual", "journal", "codex"
    selected: Optional[NPC] = None

    slice_timer = SLICE_SECONDS

    # journal scroll (newest-first)
    journal_scroll = 0

    # codex list selection
    codex_selected = 0

    # ritual telegraph
    ritual_warning_timer = 0.0
    ritual_warning_text = ""
    pending_ritual: Optional[str] = None

    # flash feedback
    flash_timer = 0.0
    flash_color = (255, 255, 255)

    def trigger_flash(color: Tuple[int, int, int], duration: float = 0.35):
        nonlocal flash_timer, flash_color
        flash_timer = duration
        flash_color = color

    def blit(txt: str, x: int, y: int, fnt=font, col=COL["ui_text"]):
        surf = fnt.render(txt, True, col)
        screen.blit(surf, (x, y))
        return surf.get_rect(topleft=(x, y))

    def start_slice_checks():
        """Runs when a new slice begins (telegraph ritual if due)."""
        nonlocal ritual_warning_timer, ritual_warning_text, pending_ritual
        if overlay is not None:
            return
        pending_ritual = None
        for name, info in RITUALS.items():
            if (realm.season_name() == info["season"] and
                realm.day_in_season() in info["days"] and
                realm.slice_name() == info["slice"]):
                pending_ritual = name
                ritual_warning_timer = 3.0
                ritual_warning_text = f"The air shifts. {name} approaches..."
                break

    # initial slice check
    start_slice_checks()

    # -----------------------------
    # Main loop
    # -----------------------------
    running = True
    cam = pygame.Vector2(0, 0)

    while running:
        dt = clock.tick(FPS) / 1000.0

        # --- events
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False

            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if overlay is None:
                    mx, my = e.pos
                    # convert to world
                    wpos = pygame.Vector2(mx, my) + cam
                    selected = None
                    for n in npcs:
                        if dist(wpos, n.pos()) < 18:
                            selected = n
                            break

                # codex click select (simple)
                if overlay == "codex":
                    mx, my = e.pos
                    left = pygame.Rect(UI_W + 18, 100, 280, 520)
                    if left.collidepoint(mx, my):
                        rel = my - (left.y + 14)
                        idx = rel // 20
                        if 0 <= idx < min(22, len(codex)):
                            codex_selected = int(idx)

            if e.type == pygame.KEYDOWN:
                # global hotkeys
                if e.key == pygame.K_ESCAPE:
                    overlay = None

                if e.key == pygame.K_F5:
                    save_state(SAVE_FILE, realm, player, npcs, codex)
                    journal_append(journal, "[SYSTEM] Saved.")
                    trigger_flash((200, 220, 255), 0.25)

                if e.key == pygame.K_F9:
                    data2 = load_state(SAVE_FILE)
                    if data2:
                        try:
                            r = data2.get("realm", {})
                            realm.year = int(r.get("year", 1))
                            realm.day = int(r.get("day", 1))
                            realm.slice_idx = int(r.get("slice_idx", 0)) % len(SLICES)
                            realm.pulse.update(r.get("pulse", {}))
                            realm.resonance = int(r.get("resonance", 3))
                            realm.minor_cast = int(r.get("minor_cast", 0))
                            realm.major_cast = int(r.get("major_cast", 0))
                            p = data2.get("player", {})
                            player.update(float(p.get("x", player.x)), float(p.get("y", player.y)))
                            codex = list(data2.get("codex", codex))
                            codex_selected = clamp(codex_selected, 0, max(0, len(codex) - 1))
                            loaded_npcs = data2.get("npcs", None)
                            if loaded_npcs:
                                npcs = [NPC(**nd) for nd in loaded_npcs]
                            journal_append(journal, "[SYSTEM] Loaded.")
                            trigger_flash((255, 240, 140), 0.25)
                        except Exception:
                            journal_append(journal, "[SYSTEM] Load failed.")
                    else:
                        journal_append(journal, "[SYSTEM] No save file found.")

                if e.key == pygame.K_q:
                    running = False

                # overlay open/close
                if overlay is None:
                    if e.key == pygame.K_g:
                        overlay = "glyph"
                    if e.key == pygame.K_r:
                        overlay = "ritual"
                    if e.key == pygame.K_j:
                        overlay = "journal"
                        journal_scroll = 0
                    if e.key == pygame.K_c:
                        overlay = "codex"
                        codex_selected = clamp(codex_selected, 0, max(0, len(codex) - 1))
                    if e.key == pygame.K_d and selected:
                        if realm.slice_name() != "Night":
                            journal_append(journal, "[DREAM] Can only seed dreams at Night.")
                        else:
                            overlay = "dream"

                    if e.key == pygame.K_e and selected:
                        if near(player, selected.pos()):
                            witness(realm, selected, codex, journal)
                            trigger_flash((200, 255, 200), 0.30)
                        else:
                            journal_append(journal, "[WITNESS] Too far. Move closer.")

                # overlay interactions
                if overlay == "glyph":
                    # 1-3 minor glyphs, 8 for major
                    if e.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        idx = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2}[e.key]
                        names = list(GLYPHS_MINOR.keys())
                        if idx < len(names):
                            cast_glyph(realm, journal, names[idx])
                            trigger_flash((140, 200, 255), 0.40)
                    if e.key == pygame.K_8:
                        names = list(GLYPHS_MAJOR.keys())
                        if names:
                            cast_glyph(realm, journal, names[0])
                            trigger_flash((140, 200, 255), 0.55)

                if overlay == "dream":
                    if e.key == pygame.K_SPACE:
                        seed_dream(realm, journal, selected)
                        trigger_flash((200, 180, 255), 0.50)

                if overlay == "ritual":
                    if e.key == pygame.K_RETURN:
                        # if a ritual is due now, apply it; otherwise "listen"
                        applied = False
                        for name, info in RITUALS.items():
                            if (realm.season_name() == info["season"] and
                                realm.day_in_season() in info["days"] and
                                realm.slice_name() == info["slice"]):
                                ritual_apply(realm, journal, name)
                                trigger_flash((255, 240, 140), 0.45)
                                applied = True
                                break
                        if not applied:
                            journal_append(journal, "[RITUAL] You listen. Nothing rises.")
                            trigger_flash((120, 120, 120), 0.20)

                if overlay == "journal":
                    if e.key == pygame.K_UP:
                        journal_scroll = clamp(journal_scroll - 1, 0, max(0, len(journal) - 1))
                    if e.key == pygame.K_DOWN:
                        journal_scroll = clamp(journal_scroll + 1, 0, max(0, len(journal) - 1))

                if overlay == "codex":
                    if e.key == pygame.K_UP:
                        codex_selected = clamp(codex_selected - 1, 0, max(0, len(codex) - 1))
                    if e.key == pygame.K_DOWN:
                        codex_selected = clamp(codex_selected + 1, 0, max(0, len(codex) - 1))

        # --- movement
        keys = pygame.key.get_pressed()
        if overlay is None:
            move = pygame.Vector2(0, 0)
            if keys[pygame.K_w]:
                move.y -= 1
            if keys[pygame.K_s]:
                move.y += 1
            if keys[pygame.K_a]:
                move.x -= 1
            if keys[pygame.K_d]:
                move.x += 1
            if move.length_squared() > 0:
                move = move.normalize()
            speed = 160.0
            nxt = player + move * speed * dt
            # simple collision (try x then y)
            if not is_blocked(grid, nxt.x, player.y):
                player.x = nxt.x
            if not is_blocked(grid, player.x, nxt.y):
                player.y = nxt.y

        # --- npc wander (bounded)
        for n in npcs:
            npos = n.pos()
            home = n.home_pos()
            if (npos - home).length() > 5 * TILE:
                toward = (home - npos)
                if toward.length_squared() > 0:
                    step = toward.normalize() * 30.0 * dt
                else:
                    step = pygame.Vector2(0, 0)
            else:
                ang = random.random() * math.tau
                step = pygame.Vector2(math.cos(ang), math.sin(ang)) * 18.0 * dt
            nxt = npos + step
            if not is_blocked(grid, nxt.x, nxt.y):
                n.x, n.y = float(nxt.x), float(nxt.y)

        # --- time progression
        slice_timer -= dt
        if slice_timer <= 0:
            slice_timer = SLICE_SECONDS
            realm.slice_idx = (realm.slice_idx + 1) % len(SLICES)
            if realm.slice_idx == 0:
                # new day
                realm.day += 1
                if realm.day > DAYS_PER_YEAR:
                    realm.day = 1
                    realm.year += 1
            journal_append(journal, f"[TIME] {realm.slice_name()} — Day {realm.day_in_season()}/{DAYS_PER_SEASON} ({realm.season_name()})")
            start_slice_checks()

        # ritual telegraph timer
        if ritual_warning_timer > 0:
            ritual_warning_timer -= dt
            if ritual_warning_timer <= 0 and pending_ritual and overlay is None:
                overlay = "ritual"

        # --- camera
        cam.x = clamp(int(player.x - (W - UI_W) * 0.5), 0, MAP_W * TILE - (W - UI_W))
        cam.y = clamp(int(player.y - H * 0.5), 0, MAP_H * TILE - H)

        # -----------------------------
        # Render
        # -----------------------------
        screen.fill(COL["bg"])

        # map draw (simple)
        view_x0 = int(cam.x // TILE) - 1
        view_y0 = int(cam.y // TILE) - 1
        view_x1 = int((cam.x + (W - UI_W)) // TILE) + 2
        view_y1 = int((cam.y + H) // TILE) + 2

        for ty in range(max(0, view_y0), min(MAP_H, view_y1)):
            for tx in range(max(0, view_x0), min(MAP_W, view_x1)):
                t = grid[ty][tx]
                x = tx * TILE - cam.x + UI_W
                y = ty * TILE - cam.y
                r = pygame.Rect(int(x), int(y), TILE, TILE)
                if t == T_GRASS:
                    pygame.draw.rect(screen, COL["grass"] if (tx + ty) % 2 == 0 else COL["grass2"], r)
                elif t == T_TREE:
                    pygame.draw.rect(screen, COL["grass"], r)
                    pygame.draw.rect(screen, COL["tree"], r.inflate(-10, -10), border_radius=6)
                elif t == T_WATER:
                    pygame.draw.rect(screen, COL["water"], r)
                elif t == T_PATH:
                    pygame.draw.rect(screen, COL["grass"], r)
                    pygame.draw.rect(screen, COL["path"], r.inflate(-8, -8), border_radius=8)
                elif t == T_ROCK:
                    pygame.draw.rect(screen, COL["grass"], r)
                    pygame.draw.rect(screen, COL["rock"], r.inflate(-12, -12), border_radius=8)

        # atmospheric pulse overlay (subtle)
        if realm.pulse["veil"] > 70:
            fog = pygame.Surface((W - UI_W, H), pygame.SRCALPHA)
            fog.fill((180, 180, 200, 40))
            screen.blit(fog, (UI_W, 0))

        if realm.pulse["turbulence"] > 60:
            for _ in range(int(realm.pulse["turbulence"] // 3)):
                x = random.randint(UI_W, W - 1)
                y = random.randint(0, H - 1)
                pygame.draw.circle(screen, (255, 255, 255), (x, y), 1)

        if realm.pulse["growth"] > 70:
            for _ in range(10):
                x = random.randint(UI_W, W - 1)
                y = random.randint(0, H - 1)
                pygame.draw.circle(screen, (140, 255, 140), (x, y), 2)

        # NPCs
        for n in npcs:
            p = n.pos() - cam + pygame.Vector2(UI_W, 0)
            pygame.draw.circle(screen, (245, 245, 245), (int(p.x), int(p.y)), 10)
            if n.witnessed:
                pygame.draw.circle(screen, (200, 255, 200), (int(p.x), int(p.y)), 14, 2)
            # name above head
            name_surf = tiny.render(n.name, True, (240, 240, 240))
            screen.blit(name_surf, (int(p.x - name_surf.get_width() // 2), int(p.y - 26)))

        # player
        pp = player - cam + pygame.Vector2(UI_W, 0)
        pygame.draw.circle(screen, (255, 240, 140), (int(pp.x), int(pp.y)), 9)
        pygame.draw.circle(screen, (0, 0, 0), (int(pp.x), int(pp.y)), 9, 2)

        # selection indicator
        if selected and overlay is None:
            sp = selected.pos()
            p = sp - cam + pygame.Vector2(UI_W, 0)
            ring_col = COL["good"] if near(player, sp) else COL["bad"]
            pygame.draw.circle(screen, ring_col, (int(p.x), int(p.y)), 44, 2)

            # selected NPC pointer if far
            if not near(player, sp):
                dvec = (sp - player)
                if dvec.length_squared() > 0:
                    dvec = dvec.normalize()
                    arrow = player + dvec * 22 - cam + pygame.Vector2(UI_W, 0)
                    pygame.draw.circle(screen, COL["accent"], (int(arrow.x), int(arrow.y)), 4)

        # ritual warning banner
        if ritual_warning_timer > 0 and ritual_warning_text:
            banner = big.render(ritual_warning_text, True, COL["accent"])
            bx = UI_W + ((W - UI_W) - banner.get_width()) // 2
            by = H // 2 - 60
            bg = pygame.Rect(bx - 20, by - 10, banner.get_width() + 40, banner.get_height() + 20)
            pygame.draw.rect(screen, (20, 20, 20), bg, border_radius=12)
            pygame.draw.rect(screen, COL["accent"], bg, 2, border_radius=12)
            screen.blit(banner, (bx, by))

        # flash feedback
        if flash_timer > 0:
            flash_timer -= dt
            alpha = int((flash_timer / 0.55) * 80)
            alpha = clamp(alpha, 0, 80)
            surf = pygame.Surface((W, H), pygame.SRCALPHA)
            surf.fill((*flash_color, alpha))
            screen.blit(surf, (0, 0))

        # --- UI panel
        ui = pygame.Rect(0, 0, UI_W, H)
        pygame.draw.rect(screen, COL["ui"], ui)
        pygame.draw.rect(screen, COL["ui_border"], ui, 2)

        # header
        blit("Echo Realms: The Witness", 18, 18, big, COL["accent"])
        blit(f"Year {realm.year} • {realm.season_name()} • Day {realm.day_in_season()}/{DAYS_PER_SEASON} • {realm.slice_name()}",
             18, 52, small, COL["ui_text"])

        # time bar
        bar_w = UI_W - 36
        bar_h = 8
        bar_x = 18
        bar_y = 78
        prog = clamp(int((slice_timer / SLICE_SECONDS) * bar_w), 0, bar_w)
        pygame.draw.rect(screen, (40, 40, 40), pygame.Rect(bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, COL["accent"], pygame.Rect(bar_x, bar_y, prog, bar_h))
        pygame.draw.rect(screen, COL["ui_border"], pygame.Rect(bar_x, bar_y, bar_w, bar_h), 1)

        # pulse stats
        y = 104
        blit(f"Resonance {realm.resonance}/9 • Glyphs minor {realm.minor_cast} / major {realm.major_cast}", 18, y, tiny, COL["muted"])
        y += 26
        for k in ["growth", "harmony", "remembrance", "dream", "veil", "turbulence"]:
            blit(f"{k.title():<12} {realm.pulse[k]:>3}", 18, y, small, COL["ui_text"])
            y += 22

        # footer hints
        hint = "WASD move • Click NPC select • E witness • G glyph • D dream • R ritual • J journal • C codex • F5 save • F9 load • Q quit"
        if selected and realm.slice_name() != "Night":
            hint = hint.replace("D dream", "[D dream - Night only]")
        hint_s = tiny.render(hint, True, (235, 235, 235))
        screen.blit(hint_s, (UI_W + 18, 10))

        # recent journal (last 6)
        blit("Recent Journal:", 18, H - 170, small, COL["accent"])
        recent = journal[-6:]
        y2 = H - 145
        for ln in recent:
            blit(ln[:48] + ("…" if len(ln) > 48 else ""), 18, y2, tiny, COL["ui_text"])
            y2 += 18

        # --- overlay panels
        if overlay is not None:
            # dim background on world side
            dim = pygame.Surface((W - UI_W, H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 120))
            screen.blit(dim, (UI_W, 0))

        if overlay == "glyph":
            panel = pygame.Rect(UI_W + 80, 110, 680, 500)
            pygame.draw.rect(screen, COL["ui2"], panel, border_radius=14)
            pygame.draw.rect(screen, COL["ui_border"], panel, 2, border_radius=14)
            blit("Glyph Casting (Esc to close)", panel.x + 16, panel.y + 14, big, COL["accent"])

            y3 = panel.y + 70
            blit("Minor Glyphs (1-3):", panel.x + 16, y3, small, COL["muted"])
            y3 += 26
            for i, (name, info) in enumerate(GLYPHS_MINOR.items(), start=1):
                blit(f"{i}. {name} — {info['desc']}", panel.x + 26, y3, small, COL["ui_text"])
                y3 += 22

            y3 += 22
            blit("Major Glyph (8):", panel.x + 16, y3, small, COL["muted"])
            y3 += 26
            for name, info in GLYPHS_MAJOR.items():
                blit(f"8. {name} — {info['desc']}", panel.x + 26, y3, small, COL["ui_text"])
                y3 += 22

        if overlay == "dream":
            panel = pygame.Rect(UI_W + 160, 160, 520, 360)
            pygame.draw.rect(screen, COL["ui2"], panel, border_radius=14)
            pygame.draw.rect(screen, COL["ui_border"], panel, 2, border_radius=14)
            blit("Dream Seeding", panel.x + 16, panel.y + 16, big, COL["accent"])
            who = selected.name if selected else "the realm"
            blit(f"Target: {who}", panel.x + 16, panel.y + 60, small, COL["ui_text"])
            blit("Press SPACE to seed a dream (Night only).", panel.x + 16, panel.y + 90, small, COL["muted"])
            blit("Esc to close.", panel.x + 16, panel.y + 120, small, COL["muted"])

        if overlay == "ritual":
            panel = pygame.Rect(UI_W + 120, 140, 600, 420)
            pygame.draw.rect(screen, COL["ui2"], panel, border_radius=14)
            pygame.draw.rect(screen, COL["ui_border"], panel, 2, border_radius=14)
            blit("Ritual", panel.x + 16, panel.y + 16, big, COL["accent"])

            due = None
            for name, info in RITUALS.items():
                if (realm.season_name() == info["season"] and
                    realm.day_in_season() in info["days"] and
                    realm.slice_name() == info["slice"]):
                    due = name
                    break
            if due:
                blit(f"Due now: {due}", panel.x + 16, panel.y + 66, small, COL["accent"])
                body = RITUALS[due]["text"]
                for i, ln in enumerate(wrap_text(small, body, panel.w - 32)):
                    blit(ln, panel.x + 16, panel.y + 98 + i * 20, small, COL["ui_text"])
                blit("Press ENTER to accept.", panel.x + 16, panel.y + panel.h - 70, small, COL["muted"])
            else:
                blit("Nothing is due. You may still listen.", panel.x + 16, panel.y + 66, small, COL["ui_text"])
                blit("Press ENTER to listen.", panel.x + 16, panel.y + 98, small, COL["muted"])

            blit("Esc to close.", panel.x + 16, panel.y + panel.h - 42, small, COL["muted"])

        if overlay == "journal":
            panel = pygame.Rect(UI_W + 60, 70, 740, 580)
            pygame.draw.rect(screen, COL["ui2"], panel, border_radius=14)
            pygame.draw.rect(screen, COL["ui_border"], panel, 2, border_radius=14)
            blit("Journal (Up/Down scroll, Esc close)", panel.x + 16, panel.y + 14, big, COL["accent"])
            y3 = panel.y + 60
            # newest-first
            jrev = list(reversed(journal))
            view = jrev[journal_scroll:journal_scroll + 24]
            for ln in view:
                txt = ln[:100] + ("…" if len(ln) > 100 else "")
                blit(txt, panel.x + 16, y3, tiny, COL["ui_text"])
                y3 += 22

        if overlay == "codex":
            panel = pygame.Rect(UI_W + 40, 70, 820, 580)
            pygame.draw.rect(screen, COL["ui2"], panel, border_radius=14)
            pygame.draw.rect(screen, COL["ui_border"], panel, 2, border_radius=14)
            blit("Codex (Up/Down select, Esc close)", panel.x + 16, panel.y + 14, big, COL["accent"])

            left = pygame.Rect(panel.x + 16, panel.y + 60, 280, 500)
            right = pygame.Rect(panel.x + 310, panel.y + 60, 490, 500)
            pygame.draw.rect(screen, (18, 20, 24), left, border_radius=12)
            pygame.draw.rect(screen, COL["ui_border"], left, 1, border_radius=12)
            pygame.draw.rect(screen, (18, 20, 24), right, border_radius=12)
            pygame.draw.rect(screen, COL["ui_border"], right, 1, border_radius=12)

            y3 = left.y + 14
            for i, p in enumerate(codex[:22]):
                col = COL["accent"] if i == codex_selected else COL["ui_text"]
                label = p[:30] + ("…" if len(p) > 30 else "")
                blit(label, left.x + 12, y3, tiny, col)
                y3 += 20

            if codex:
                page = codex[codex_selected]
                blit(page, right.x + 12, right.y + 12, small, COL["accent"])
                body = CODEX_TEXT.get(page, "(text missing)")
                # generate simple placeholder lore for NPC pages
                if body == "(text missing)" and "— Seen" in page:
                    npc_name = page.split("—")[0].strip()
                    body = f"You notice {npc_name} more clearly.\n\nThey move with ordinary purpose, yet the realm changes when you truly see them."
                y3 = right.y + 44
                for ln in wrap_text(small, body, right.w - 24):
                    blit(ln, right.x + 12, y3, small, COL["ui_text"])
                    y3 += 22

        pygame.display.flip()

    pygame.quit()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

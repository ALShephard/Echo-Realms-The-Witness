
# Echo Realms — Visual Prototype v0.8 (Route 2: Mythic Ink)
# Run:  python src/echo_realms_visual_proto_v0_8.py
#
# Controls: WASD/Arrows move • E witness • G glyph • D dream • R ritual
#           J journal • C codex • T tile browser (debug) • F5 save • F9 load • Q/Esc quit

from __future__ import annotations

import json, os, sys, random
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import pygame

# ------------------------- Config -------------------------
TITLE = "Echo Realms — Visual Prototype v0.8"
WIN_W, WIN_H = 1200, 700
FPS = 60

TILE_W = TILE_H = 16          # Kenney Roguelike tile size
SHEET_SPACING = 1             # Kenney Roguelike sheet spacing (per sample TMX)
SHEET_MARGIN = 0
SCALE = 3                     # 16px -> 48px
RENDER_TILE = TILE_W * SCALE

WORLD_W, WORLD_H = 80, 60

UI_W = 360
UI_PAD = 16

# ------------------------- Paths -------------------------
def repo_root() -> str:
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(here, os.pardir))

ROOT = repo_root()
ASSETS = os.path.join(ROOT, "Assets")
SAVES = os.path.join(ROOT, "saves")
SAVE_FILE = os.path.join(SAVES, "echo_realms_save.json")

# Recommended extraction layout:
# Assets/
#   Tiles/
#     Kenney_RoguelikeRPG/Spritesheet/roguelikeSheet_transparent.png
#   UI/
#     Kenney_FantasyUIBorders/PNG/Default/Border/panel-border-000.png
#
# If your UI folder is named "U.I", this script will still find it.

# ------------------------- State -------------------------
@dataclass
class GameState:
    year: int = 1
    realm: str = "Verdance"
    day: int = 1
    time_of_day: str = "Dawn"
    growth: int = 55
    harmony: int = 55
    remembrance: int = 35
    dream: int = 30
    veil: int = 60
    turbulence: int = 15
    resonance: Tuple[int, int] = (3, 3)
    glyphs_minor: Tuple[int, int] = (0, 3)
    glyphs_major: Tuple[int, int] = (0, 1)
    player_pos: Tuple[int, int] = (10, 10)
    journal: List[str] = None

    def __post_init__(self):
        if self.journal is None:
            self.journal = [
                "[SYSTEM] Echo Realms v0.8 started.",
                f"[TIME] {self.time_of_day} • Day {self.day}/7, {self.realm}"
            ]

# ------------------------- Helpers -------------------------
def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v

def try_load_image(path: str) -> Optional[pygame.Surface]:
    if not os.path.exists(path):
        return None
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception:
        return None

def scale_nearest(img: pygame.Surface, w: int, h: int) -> pygame.Surface:
    return pygame.transform.scale(img, (w, h))

# ------------------------- Kenney tiles (slice + auto-pick) -------------------------
def slice_kenney_sheet(sheet: pygame.Surface,
                       tile_w: int = TILE_W, tile_h: int = TILE_H,
                       spacing: int = SHEET_SPACING, margin: int = SHEET_MARGIN) -> List[pygame.Surface]:
    sw, sh = sheet.get_width(), sheet.get_height()
    step_x, step_y = tile_w + spacing, tile_h + spacing
    cols = (sw + spacing - margin) // step_x
    rows = (sh + spacing - margin) // step_y
    out: List[pygame.Surface] = []
    for r in range(rows):
        for c in range(cols):
            x = margin + c * step_x
            y = margin + r * step_y
            if x + tile_w <= sw and y + tile_h <= sh:
                out.append(sheet.subsurface(pygame.Rect(x, y, tile_w, tile_h)).copy())
    return out

def avg_rgba_fast(surf: pygame.Surface) -> Tuple[float, float, float, float]:
    """
    Mean RGB + alpha coverage (0..1). Uses surfarray if numpy is available; falls back otherwise.
    """
    try:
        import numpy as np  # optional
        rgb = pygame.surfarray.array3d(surf)          # (w,h,3)
        a = pygame.surfarray.array_alpha(surf)        # (w,h)
        mr, mg, mb = rgb.mean(axis=(0, 1))
        cov = float((a > 0).mean())
        return float(mr), float(mg), float(mb), cov
    except Exception:
        w, h = surf.get_size()
        total = w * h
        r = g = b = 0
        nonzero = 0
        surf.lock()
        for y in range(h):
            for x in range(w):
                pr, pg, pb, pa = surf.get_at((x, y))
                r += pr; g += pg; b += pb
                if pa > 0: nonzero += 1
        surf.unlock()
        return (r / total, g / total, b / total, nonzero / total)

def auto_pick_tile_ids(tiles: List[pygame.Surface]) -> Dict[str, int]:
    """
    Heuristic selection of grass/dirt/stone/water for Kenney roguelike sheet (no atlas file).
    """
    if not tiles:
        return {}

    scored = []
    # sample every 2nd tile to stay snappy on low-power machines
    for i in range(0, len(tiles), 2):
        mr, mg, mb, cov = avg_rgba_fast(tiles[i])
        if cov < 0.40:
            continue
        brightness = (mr + mg + mb) / 3.0
        greenish = mg - (mr + mb) / 2.0
        bluish = mb - (mr + mg) / 2.0
        reddish = mr - (mg + mb) / 2.0
        grayness = 1.0 - (abs(mr - mg) + abs(mg - mb) + abs(mr - mb)) / (3.0 * 255.0)
        scored.append((i, brightness, greenish, bluish, reddish, grayness))

    if not scored:
        return {"grass": 0, "dirt": 0, "stone": 0, "water": 0}

    def best(f):
        bi, bs = scored[0][0], -1e9
        for (i, br, gn, bl, rd, gr) in scored:
            s = f(br, gn, bl, rd, gr)
            if s > bs:
                bs, bi = s, i
        return bi

    grass = best(lambda br, gn, bl, rd, gr: (gn * 2.0 + gr * 60 - abs(bl) * 0.5) if 40 < br < 220 else -1e9)
    water = best(lambda br, gn, bl, rd, gr: (bl * 2.2 + gr * 30 - abs(gn) * 0.6) if 30 < br < 230 else -1e9)
    stone = best(lambda br, gn, bl, rd, gr: (gr * 120 - abs(gn) * 0.8 - abs(bl) * 0.8) if 30 < br < 240 else -1e9)
    dirt  = best(lambda br, gn, bl, rd, gr: (rd * 1.6 + br * 0.2 + (1 - gr) * 40) if 30 < br < 230 else -1e9)
    return {"grass": grass, "dirt": dirt, "stone": stone, "water": water}

# ------------------------- UI Panel (Mythic Ink) -------------------------
def make_panel(size: Tuple[int, int], border_img: Optional[pygame.Surface]) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    surf.fill((5, 6, 8, 220))  # ink wash
    if border_img:
        surf.blit(scale_nearest(border_img, w, h), (0, 0))
    else:
        pygame.draw.rect(surf, (8, 9, 12, 230), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(surf, (255, 255, 255, 35), (0, 0, w, h), 2, border_radius=16)
    return surf

# ------------------------- World generation -------------------------
def generate_world(seed: int = 7) -> List[List[str]]:
    rng = random.Random(seed)
    g = [["grass" for _ in range(WORLD_W)] for _ in range(WORLD_H)]

    # Winding path (left -> right)
    x, y = 0, WORLD_H // 2
    for _ in range(WORLD_W * 2):
        g[y][x] = "dirt"
        dx = 1 if rng.random() < 0.7 else rng.choice([-1, 0, 1])
        dy = rng.choice([-1, 0, 1])
        x = clamp(x + dx, 0, WORLD_W - 1)
        y = clamp(y + dy, 2, WORLD_H - 3)

    # Stones
    for _ in range(160):
        sx, sy = rng.randrange(WORLD_W), rng.randrange(WORLD_H)
        if g[sy][sx] == "grass" and rng.random() < 0.65:
            g[sy][sx] = "stone"

    # Water blobs
    for _ in range(8):
        cx, cy = rng.randrange(5, WORLD_W - 5), rng.randrange(5, WORLD_H - 5)
        r = rng.randrange(2, 5)
        for yy in range(cy - r, cy + r + 1):
            for xx in range(cx - r, cx + r + 1):
                if 0 <= xx < WORLD_W and 0 <= yy < WORLD_H and (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    if rng.random() < 0.85:
                        g[yy][xx] = "water"
    return g

# ------------------------- Save / Load -------------------------
def save_game(gs: GameState) -> None:
    ensure_dir(SAVES)
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(gs), f, indent=2)

def load_game() -> Optional[GameState]:
    if not os.path.exists(SAVE_FILE):
        return None
    try:
        data = json.load(open(SAVE_FILE, "r", encoding="utf-8"))
        # lists -> tuples
        for k in ("resonance", "glyphs_minor", "glyphs_major", "player_pos"):
            if k in data and isinstance(data[k], list):
                data[k] = tuple(data[k])
        return GameState(**data)
    except Exception:
        return None

# ------------------------- Tile Browser (Debug) -------------------------
class TileBrowser:
    def __init__(self, tiles_scaled: List[pygame.Surface]):
        self.tiles = tiles_scaled
        self.enabled = False
        self.page = 0
        self.per_row = 14
        self.tile_px = RENDER_TILE
        self.margin = 10

    def toggle(self):
        self.enabled = not self.enabled
        self.page = 0

    def handle(self, ev: pygame.event.Event) -> Optional[int]:
        if not self.enabled:
            return None
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_PAGEUP:
                self.page = max(0, self.page - 1)
            elif ev.key == pygame.K_PAGEDOWN:
                self.page += 1
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            idx = self._index_at(*ev.pos)
            if idx is not None and idx < len(self.tiles):
                return idx
        return None

    def _index_at(self, mx: int, my: int) -> Optional[int]:
        start_x = UI_W + self.margin
        start_y = self.margin + 26
        cols = self.per_row
        rows = max(1, (WIN_H - 2 * self.margin) // (self.tile_px + 24))
        per_page = cols * rows
        lx, ly = mx - start_x, my - start_y
        if lx < 0 or ly < 0:
            return None
        c = lx // (self.tile_px + 8)
        r = ly // (self.tile_px + 24)
        if c < 0 or c >= cols or r < 0 or r >= rows:
            return None
        return self.page * per_page + (r * cols + c)

    def draw(self, screen: pygame.Surface, font_small: pygame.font.Font):
        if not self.enabled:
            return
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        screen.blit(overlay, (0, 0))

        start_x = UI_W + self.margin
        title = font_small.render("Tile Browser (T) • PgUp/PgDn • Click tile to copy index", True, (245, 245, 245))
        screen.blit(title, (start_x, self.margin))

        start_y = self.margin + 26
        cols = self.per_row
        rows = max(1, (WIN_H - 2 * self.margin) // (self.tile_px + 24))
        per_page = cols * rows
        base = self.page * per_page

        for r in range(rows):
            for c in range(cols):
                idx = base + r * cols + c
                if idx >= len(self.tiles):
                    continue
                x = start_x + c * (self.tile_px + 8)
                y = start_y + r * (self.tile_px + 24)
                screen.blit(self.tiles[idx], (x, y))
                screen.blit(font_small.render(str(idx), True, (230, 230, 230)), (x, y + self.tile_px + 2))

# ------------------------- Main -------------------------
def main():
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    clock = pygame.time.Clock()

    font = pygame.font.Font(None, 18)
    font_small = pygame.font.Font(None, 14)
    font_title = pygame.font.Font(None, 22)

    gs = GameState()

    # UI border (support Assets/UI or Assets/U.I)
    border_img = None
    for ui_dir in (os.path.join(ASSETS, "UI"), os.path.join(ASSETS, "U.I")):
        p = os.path.join(ui_dir, "Kenney_FantasyUIBorders", "PNG", "Default", "Border", "panel-border-000.png")
        border_img = try_load_image(p)
        if border_img:
            break
    ui_panel = make_panel((UI_W, WIN_H), border_img)

    # Tileset
    tiles_scaled: List[pygame.Surface] = []
    tile_ids: Dict[str, int] = {}
    sheet_path = os.path.join(ASSETS, "Tiles", "Kenney_RoguelikeRPG", "Spritesheet", "roguelikeSheet_transparent.png")
    sheet = try_load_image(sheet_path) if os.path.exists(sheet_path) else None
    if sheet:
        tiles = slice_kenney_sheet(sheet)
        tile_ids = auto_pick_tile_ids(tiles)
        tiles_scaled = [scale_nearest(t, RENDER_TILE, RENDER_TILE) for t in tiles]

    fallback = {"grass": (28, 120, 60), "dirt": (140, 115, 70), "stone": (70, 70, 70), "water": (35, 95, 140)}

    # World + camera
    world = generate_world(7)
    px, py = gs.player_pos
    cam_x = px * RENDER_TILE - (WIN_W - UI_W) // 2
    cam_y = py * RENDER_TILE - WIN_H // 2

    show_journal = False
    show_codex = False

    browser = TileBrowser(tiles_scaled)
    copied_idx: Optional[int] = None

    def log(msg: str):
        gs.journal.append(msg)
        if len(gs.journal) > 24:
            gs.journal = gs.journal[-24:]

    log("[SYSTEM] " + ("Kenney tiles loaded." if tiles_scaled else "Using fallback tiles."))

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key == pygame.K_j:
                    show_journal = not show_journal; show_codex = False
                elif ev.key == pygame.K_c:
                    show_codex = not show_codex; show_journal = False
                elif ev.key == pygame.K_f5:
                    save_game(gs); log("[SAVE] Game saved.")
                elif ev.key == pygame.K_f9:
                    loaded = load_game()
                    if loaded: gs = loaded; px, py = gs.player_pos; log("[LOAD] Save loaded.")
                    else: log("[LOAD] No save found.")
                elif ev.key == pygame.K_t:
                    if tiles_scaled: browser.toggle(); log("[DEBUG] Tile browser " + ("opened." if browser.enabled else "closed."))
                    else: log("[DEBUG] No tile sheet found.")
                elif ev.key == pygame.K_e:
                    log("[WITNESS] You pause… and the world stares back.")
                elif ev.key == pygame.K_g:
                    log("[GLYPH] A minor glyph hums in your palm.")
                elif ev.key == pygame.K_d:
                    log("[DREAM] A soft veil shifts at the edge of perception.")
                elif ev.key == pygame.K_r:
                    log("[RITUAL] You mark the moment. The field remembers.")

            picked = browser.handle(ev)
            if picked is not None:
                copied_idx = picked
                log(f"[DEBUG] Copied tile index: {picked}")

        # Movement (disabled while browsing)
        if not browser.enabled:
            keys = pygame.key.get_pressed()
            dx = dy = 0
            if keys[pygame.K_w] or keys[pygame.K_UP]: dy -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]: dy += 1
            if keys[pygame.K_a] or keys[pygame.K_LEFT]: dx -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += 1
            if dx and dy:
                if random.random() < 0.5: dx = 0
                else: dy = 0
            if dx or dy:
                nx, ny = clamp(px + dx, 0, WORLD_W - 1), clamp(py + dy, 0, WORLD_H - 1)
                if world[ny][nx] != "water":
                    px, py = nx, ny
                    gs.player_pos = (px, py)

        # Smooth camera
        target_x = px * RENDER_TILE - (WIN_W - UI_W) // 2
        target_y = py * RENDER_TILE - WIN_H // 2
        cam_x += (target_x - cam_x) * min(1.0, dt * 8.0)
        cam_y += (target_y - cam_y) * min(1.0, dt * 8.0)

        # -------- Render --------
        screen.fill((25, 80, 55))

        view_w = WIN_W - UI_W
        start_tx = int(cam_x // RENDER_TILE) - 2
        start_ty = int(cam_y // RENDER_TILE) - 2
        end_tx = start_tx + int(view_w // RENDER_TILE) + 6
        end_ty = start_ty + int(WIN_H // RENDER_TILE) + 6

        for ty in range(start_ty, end_ty):
            if ty < 0 or ty >= WORLD_H: continue
            for tx in range(start_tx, end_tx):
                if tx < 0 or tx >= WORLD_W: continue
                kind = world[ty][tx]
                sx = UI_W + int(tx * RENDER_TILE - cam_x)
                sy = int(ty * RENDER_TILE - cam_y)

                if tiles_scaled and tile_ids:
                    tid = tile_ids.get(kind, tile_ids.get("grass", 0))
                    if 0 <= tid < len(tiles_scaled):
                        screen.blit(tiles_scaled[tid], (sx, sy))
                    else:
                        pygame.draw.rect(screen, fallback[kind], (sx, sy, RENDER_TILE, RENDER_TILE))
                else:
                    pygame.draw.rect(screen, fallback[kind], (sx, sy, RENDER_TILE, RENDER_TILE))

        # Player + NPC dots (placeholder)
        p_sx = UI_W + int(px * RENDER_TILE - cam_x + RENDER_TILE * 0.5)
        p_sy = int(py * RENDER_TILE - cam_y + RENDER_TILE * 0.5)
        pygame.draw.circle(screen, (240, 240, 240), (p_sx, p_sy), max(6, RENDER_TILE // 6))
        pygame.draw.circle(screen, (0, 0, 0), (p_sx, p_sy), max(6, RENDER_TILE // 6), 2)

        for (nx, ny) in [(18, 12), (30, 22), (40, 10), (22, 34), (55, 28)]:
            if world[ny][nx] == "water": continue
            nsx = UI_W + int(nx * RENDER_TILE - cam_x + RENDER_TILE * 0.5)
            nsy = int(ny * RENDER_TILE - cam_y + RENDER_TILE * 0.5)
            pygame.draw.circle(screen, (255, 255, 255), (nsx, nsy), max(5, RENDER_TILE // 7))

        hint = "Move WASD • E witness • G glyph • D dream • R ritual • J journal • C codex • T tiles • F5 save • F9 load • Q quit"
        screen.blit(font_small.render(hint, True, (240, 240, 240)), (UI_W + 16, 10))

        # Left panel
        screen.blit(ui_panel, (0, 0))
        x0, y = UI_PAD, UI_PAD
        screen.blit(font_title.render("Echo Realms: The Witness", True, (255, 214, 90)), (x0, y)); y += 34
        screen.blit(font.render(f"Year {gs.year} • {gs.realm} • Day {gs.day}/7 • {gs.time_of_day}", True, (235, 235, 235)), (x0, y)); y += 26
        screen.blit(font_small.render(f"Resonance {gs.resonance[0]}/{gs.resonance[1]} • Glyphs {gs.glyphs_minor[0]}/{gs.glyphs_minor[1]} + {gs.glyphs_major[0]}/{gs.glyphs_major[1]}",
                                      True, (190, 190, 190)), (x0, y)); y += 26

        def stat(label: str, val: int):
            nonlocal y
            screen.blit(font_small.render(f"{label:>11}   {val}", True, (220, 220, 220)), (x0, y)); y += 18

        stat("Growth", gs.growth)
        stat("Harmony", gs.harmony)
        stat("Remembrance", gs.remembrance)
        stat("Dream", gs.dream)
        stat("Veil", gs.veil)
        stat("Turbulence", gs.turbulence)

        y = WIN_H - 140
        screen.blit(font_small.render("Recent Journal:", True, (210, 210, 210)), (x0, y)); y += 18
        for line in gs.journal[-3:]:
            screen.blit(font_small.render(line, True, (200, 200, 200)), (x0, y)); y += 18

        # Overlays
        if show_journal or show_codex:
            ov_w, ov_h = WIN_W - UI_W - 80, WIN_H - 120
            ov_x, ov_y = UI_W + 40, 70
            ov = pygame.Surface((ov_w, ov_h), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 170))
            pygame.draw.rect(ov, (255, 255, 255, 40), ov.get_rect(), 2, border_radius=12)
            screen.blit(ov, (ov_x, ov_y))
            header = "Journal" if show_journal else "Codex"
            screen.blit(font_title.render(header, True, (255, 214, 90)), (ov_x + 16, ov_y + 14))
            body_y = ov_y + 56
            lines = gs.journal[-12:] if show_journal else [
                "Codex (stub):",
                "• Verdance — realm of growth and gentle remembrance.",
                "• The Witness — you, moving through a world that watches back.",
                "• Ritual/Glyph/Dream are placeholders for upcoming systems.",
                "",
                "Tip: Press T for the tile browser (once Kenney tiles are installed).",
            ]
            for line in lines:
                screen.blit(font_small.render(line, True, (235, 235, 235)), (ov_x + 16, body_y))
                body_y += 20

        browser.draw(screen, font_small)

        if copied_idx is not None:
            screen.blit(font_small.render(f"Copied tile idx: {copied_idx}", True, (255, 255, 255)), (UI_W + 16, WIN_H - 28))

        pygame.display.flip()

    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()

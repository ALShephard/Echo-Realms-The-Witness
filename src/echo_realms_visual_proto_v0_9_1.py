# Echo Realms — Visual Prototype v0.9.1 (Asset Integration + Debug Calibration)
# Drop into: src/echo_realms_visual_proto_v0_9_1.py
# Run: python src/echo_realms_visual_proto_v0_9_1.py

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

# -----------------------------
# Paths / files (repo-relative)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # repo root (assuming file is in /src)
ASSETS_DIR = BASE_DIR / "assets"
SAVES_DIR = BASE_DIR / "saves"
SAVES_DIR.mkdir(parents=True, exist_ok=True)

SAVE_FILE = SAVES_DIR / "save_echo_realms.json"
JOURNAL_FILE = SAVES_DIR / "journal.txt"

# -----------------------------
# Game constants
# -----------------------------
SCREEN_W, SCREEN_H = 1100, 650
FPS = 60

WORLD_W, WORLD_H = 64, 40  # tiles

# Tile render size on screen (scaled up from sheet tile size)
TILE_SCALE = 3  # 16px -> 48px

# -----------------------------
# Helpers
# -----------------------------
def clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v

def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")

def try_load_image(path: Path) -> Optional[pygame.Surface]:
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except Exception:
        return None

def find_any_file(root: Path, patterns: List[str]) -> Optional[Path]:
    if not root.exists():
        return None
    for pat in patterns:
        hits = sorted(root.rglob(pat))
        if hits:
            return hits[0]
    return None

# -----------------------------
# 9-slice UI
# -----------------------------
def draw_nineslice(
    surf: pygame.Surface,
    img: pygame.Surface,
    rect: pygame.Rect,
    corner: int = 16,
) -> None:
    """
    Draw a 9-slice panel. Assumes source image is square-ish (Kenney panels often 48x48).
    corner is in SOURCE pixels.
    """
    iw, ih = img.get_width(), img.get_height()
    c = corner

    # Source rects
    TL = pygame.Rect(0, 0, c, c)
    TR = pygame.Rect(iw - c, 0, c, c)
    BL = pygame.Rect(0, ih - c, c, c)
    BR = pygame.Rect(iw - c, ih - c, c, c)

    TOP = pygame.Rect(c, 0, iw - 2 * c, c)
    BOT = pygame.Rect(c, ih - c, iw - 2 * c, c)
    LFT = pygame.Rect(0, c, c, ih - 2 * c)
    RGT = pygame.Rect(iw - c, c, c, ih - 2 * c)
    CTR = pygame.Rect(c, c, iw - 2 * c, ih - 2 * c)

    # Dest rects
    dx, dy, dw, dh = rect.x, rect.y, rect.w, rect.h
    dw = max(dw, 2)
    dh = max(dh, 2)

    dTL = pygame.Rect(dx, dy, c, c)
    dTR = pygame.Rect(dx + dw - c, dy, c, c)
    dBL = pygame.Rect(dx, dy + dh - c, c, c)
    dBR = pygame.Rect(dx + dw - c, dy + dh - c, c, c)

    dTOP = pygame.Rect(dx + c, dy, dw - 2 * c, c)
    dBOT = pygame.Rect(dx + c, dy + dh - c, dw - 2 * c, c)
    dLFT = pygame.Rect(dx, dy + c, c, dh - 2 * c)
    dRGT = pygame.Rect(dx + dw - c, dy + c, c, dh - 2 * c)
    dCTR = pygame.Rect(dx + c, dy + c, dw - 2 * c, dh - 2 * c)

    # If rect is too small, fallback to a simple scaled blit
    if dTOP.w < 1 or dLFT.h < 1 or dCTR.w < 1 or dCTR.h < 1:
        scaled = pygame.transform.smoothscale(img, (dw, dh))
        surf.blit(scaled, (dx, dy))
        return

    # Blit corners
    surf.blit(img, dTL, TL)
    surf.blit(img, dTR, TR)
    surf.blit(img, dBL, BL)
    surf.blit(img, dBR, BR)

    def blit_scaled(src_rect: pygame.Rect, dst_rect: pygame.Rect):
        patch = img.subsurface(src_rect)
        patch_s = pygame.transform.smoothscale(patch, (dst_rect.w, dst_rect.h))
        surf.blit(patch_s, dst_rect.topleft)

    blit_scaled(TOP, dTOP)
    blit_scaled(BOT, dBOT)
    blit_scaled(LFT, dLFT)
    blit_scaled(RGT, dRGT)
    blit_scaled(CTR, dCTR)

# -----------------------------
# Tilesheet loading
# -----------------------------
def infer_tile_size(sheet: pygame.Surface) -> int:
    w, h = sheet.get_width(), sheet.get_height()
    candidates = [16, 18, 24, 32, 48]
    best = 16
    best_tiles = 0
    for ts in candidates:
        if w % ts == 0 and h % ts == 0:
            tiles = (w // ts) * (h // ts)
            if tiles > best_tiles:
                best_tiles = tiles
                best = ts
    return best

def slice_tiles(sheet: pygame.Surface, tile_size: int) -> List[pygame.Surface]:
    w, h = sheet.get_width(), sheet.get_height()
    cols = w // tile_size
    rows = h // tile_size
    out: List[pygame.Surface] = []
    for r in range(rows):
        for c in range(cols):
            rect = pygame.Rect(c * tile_size, r * tile_size, tile_size, tile_size)
            out.append(sheet.subsurface(rect).copy())
    return out

def save_tile_index_debug(tiles: List[pygame.Surface], tile_size: int, out_path: Path, cols: int = 24) -> None:
    """
    Exports an atlas-like image of all tiles in index order.
    Note: this does NOT draw numbers (keeps it simple + fast).
    """
    if not tiles:
        return
    rows = (len(tiles) + cols - 1) // cols
    surf = pygame.Surface((cols * tile_size, rows * tile_size), pygame.SRCALPHA)
    for i, t in enumerate(tiles):
        x = (i % cols) * tile_size
        y = (i // cols) * tile_size
        surf.blit(t, (x, y))
    pygame.image.save(surf, str(out_path))

# -----------------------------
# Data
# -----------------------------
@dataclass
class Player:
    x: int = WORLD_W // 2
    y: int = WORLD_H // 2
    hp: int = 7
    witness: int = 0

@dataclass
class GameState:
    seed: int = 1337
    player: Player = field(default_factory=Player)
    steps: int = 0
    last_tip: str = "Press [J] to write to the Journal."
    discovered: int = 0

# -----------------------------
# World generation
# -----------------------------
T_VOID = 0
T_FLOOR = 1
T_WALL = 2
T_WATER = 3
T_SIGIL = 4

def gen_world(seed: int) -> List[List[int]]:
    rnd = random.Random(seed)
    world = [[T_FLOOR for _ in range(WORLD_W)] for _ in range(WORLD_H)]

    # Border walls
    for y in range(WORLD_H):
        for x in range(WORLD_W):
            if x == 0 or y == 0 or x == WORLD_W - 1 or y == WORLD_H - 1:
                world[y][x] = T_WALL

    # Random water pools
    for _ in range(8):
        cx = rnd.randint(6, WORLD_W - 7)
        cy = rnd.randint(6, WORLD_H - 7)
        radius = rnd.randint(2, 5)
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if 0 <= x < WORLD_W and 0 <= y < WORLD_H:
                    if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= radius * radius:
                        if world[y][x] != T_WALL:
                            world[y][x] = T_WATER

    # Random wall clusters
    for _ in range(18):
        cx = rnd.randint(4, WORLD_W - 5)
        cy = rnd.randint(4, WORLD_H - 5)
        w = rnd.randint(3, 9)
        h = rnd.randint(2, 6)
        for y in range(cy, min(WORLD_H - 1, cy + h)):
            for x in range(cx, min(WORLD_W - 1, cx + w)):
                if rnd.random() < 0.7:
                    if world[y][x] == T_FLOOR:
                        world[y][x] = T_WALL

    # Place sigils
    for _ in range(14):
        x = rnd.randint(2, WORLD_W - 3)
        y = rnd.randint(2, WORLD_H - 3)
        if world[y][x] == T_FLOOR:
            world[y][x] = T_SIGIL

    return world

def is_blocking(t: int) -> bool:
    return t in (T_WALL, T_WATER)

# -----------------------------
# Save/Load/Journal
# -----------------------------
def save_state(gs: GameState) -> None:
    payload = asdict(gs)
    payload["player"] = asdict(gs.player)
    SAVE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def load_state() -> GameState:
    if not SAVE_FILE.exists():
        return GameState()
    try:
        data = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
        gs = GameState()
        gs.seed = int(data.get("seed", gs.seed))
        gs.steps = int(data.get("steps", 0))
        gs.last_tip = str(data.get("last_tip", gs.last_tip))
        gs.discovered = int(data.get("discovered", 0))
        p = data.get("player", {})
        gs.player = Player(
            x=int(p.get("x", gs.player.x)),
            y=int(p.get("y", gs.player.y)),
            hp=int(p.get("hp", gs.player.hp)),
            witness=int(p.get("witness", gs.player.witness)),
        )
        return gs
    except Exception:
        return GameState()

def append_journal(line: str) -> None:
    JOURNAL_FILE.write_text(
        (JOURNAL_FILE.read_text(encoding="utf-8") if JOURNAL_FILE.exists() else "")
        + f"[{now_ts()}] {line}\n",
        encoding="utf-8",
    )

# -----------------------------
# Main
# -----------------------------
def main() -> None:
    pygame.init()
    pygame.display.set_caption("Echo Realms: The Witness — Prototype v0.9.1")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("consolas", 18)
    font_small = pygame.font.SysFont("consolas", 14)
    font_big = pygame.font.SysFont("consolas", 22, bold=True)

    gs = load_state()
    world = gen_world(gs.seed)

    if is_blocking(world[gs.player.y][gs.player.x]):
        gs.player.x, gs.player.y = WORLD_W // 2, WORLD_H // 2

    # -----------------------------
    # Asset discovery (improved + safe)
    # -----------------------------
    # Tilesheet: search within assets/tiles for the actual Kenney roguelike sheet.
    tilesheet_path = find_any_file(
        ASSETS_DIR / "tiles",
        patterns=[
            "*/roguelikeSheet_transparent.png",
            "*Sheet_transparent.png",
            "*sheet_transparent.png",
            "*/Spritesheet/*transparent*.png",
            "*roguelike*transparent*.png",
        ],
    )

    # UI Border: hard-lock based on YOUR confirmed structure
    panel_border_path = (
        ASSETS_DIR
        / "ui"
        / "Kenney_FantasyUIBorders"
        / "kenney_fantasy-ui-borders"
        / "PNG"
        / "Default"
        / "Border"
        / "panel-border-000.png"
    )
    if not panel_border_path.exists():
        # fallback search (just in case)
        panel_border_path = find_any_file(
            ASSETS_DIR / "ui",
            patterns=[
                "*/panel-border-000.png",
                "panel-border-000.png",
                "panel-border-00*.png",
            ],
        )

    tilesheet = try_load_image(tilesheet_path) if tilesheet_path else None
    panel_border = try_load_image(panel_border_path) if panel_border_path else None

    tiles: List[pygame.Surface] = []
    sheet_tile_size = 16
    if tilesheet:
        sheet_tile_size = infer_tile_size(tilesheet)
        tiles = slice_tiles(tilesheet, sheet_tile_size)

    # Startup debug prints (helpful while integrating assets)
    print(f"[DEBUG] BASE_DIR: {BASE_DIR}")
    print(f"[DEBUG] ASSETS_DIR: {ASSETS_DIR}")
    print(f"[DEBUG] Tilesheet found: {tilesheet_path}")
    print(f"[DEBUG] UI border found: {panel_border_path if panel_border else None}")
    if tilesheet:
        print(f"[DEBUG] Tilesheet size: {tilesheet.get_size()}")
        print(f"[DEBUG] Inferred tile size: {sheet_tile_size}px")
        print(f"[DEBUG] Total tiles sliced: {len(tiles)}")

    # -----------------------------
    # Tile mapping defaults (adjust in-game)
    # -----------------------------
    # Start with safer “likely” defaults for Kenney roguelike sheets.
    TILE_FLOOR_IDX = 57
    TILE_WALL_IDX = 114
    TILE_WATER_IDX = 627
    TILE_SIGIL_IDX = 450

    # Debug calibration controls
    show_tile_debug = False
    selected_mapping = 1  # 1=floor,2=wall,3=water,4=sigil

    # -----------------------------
    # Scaled tile cache
    # -----------------------------
    def safe_tile(i: int) -> Optional[pygame.Surface]:
        if not tiles:
            return None
        if 0 <= i < len(tiles):
            return tiles[i]
        return None

    tile_px = sheet_tile_size * TILE_SCALE
    scaled_cache: Dict[int, pygame.Surface] = {}

    def get_scaled(i: int) -> Optional[pygame.Surface]:
        if not tiles:
            return None
        if i < 0 or i >= len(tiles):
            return None
        if i not in scaled_cache:
            base = safe_tile(i)
            if base is None:
                return None
            scaled_cache[i] = pygame.transform.scale(base, (tile_px, tile_px))
        return scaled_cache[i]

    # Layout
    map_view = pygame.Rect(16, 16, SCREEN_W - 16 - 360, SCREEN_H - 32)
    ui_view = pygame.Rect(SCREEN_W - 332, 16, 316, SCREEN_H - 32)

    def world_to_screen(tx: int, ty: int, camx: int, camy: int) -> Tuple[int, int]:
        sx = map_view.x + (tx - camx) * tile_px
        sy = map_view.y + (ty - camy) * tile_px
        return sx, sy

    running = True
    message_flash = 0.0
    last_message = ""

    while running:
        dt = clock.tick(FPS) / 1000.0
        message_flash = max(0.0, message_flash - dt)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_state(gs)
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    save_state(gs)
                    running = False

                if event.key == pygame.K_F5:
                    save_state(gs)
                    last_message = "Saved."
                    message_flash = 1.2

                if event.key == pygame.K_F9:
                    gs = load_state()
                    world = gen_world(gs.seed)
                    last_message = "Loaded."
                    message_flash = 1.2

                if event.key == pygame.K_r:
                    gs.seed = random.randint(0, 999999)
                    world = gen_world(gs.seed)
                    scaled_cache.clear()  # recommended cleanup
                    gs.player.x, gs.player.y = WORLD_W // 2, WORLD_H // 2
                    gs.steps = 0
                    gs.discovered = 0
                    last_message = f"World re-seeded: {gs.seed}"
                    message_flash = 1.6

                if event.key == pygame.K_j:
                    line = f"Witness log — steps={gs.steps}, witness={gs.player.witness}, seed={gs.seed}"
                    append_journal(line)
                    gs.last_tip = "Journal entry written."
                    last_message = "Journal entry written."
                    message_flash = 1.6

                # Debug: toggle tile overlay
                if event.key == pygame.K_t:
                    show_tile_debug = not show_tile_debug
                    last_message = f"Tile debug: {'ON' if show_tile_debug else 'OFF'}"
                    message_flash = 1.2

                # Debug: choose mapping (1-4)
                if event.key == pygame.K_1:
                    selected_mapping = 1
                if event.key == pygame.K_2:
                    selected_mapping = 2
                if event.key == pygame.K_3:
                    selected_mapping = 3
                if event.key == pygame.K_4:
                    selected_mapping = 4

                # Debug: adjust selected index
                if event.key == pygame.K_LEFTBRACKET:
                    if selected_mapping == 1: TILE_FLOOR_IDX -= 1
                    if selected_mapping == 2: TILE_WALL_IDX -= 1
                    if selected_mapping == 3: TILE_WATER_IDX -= 1
                    if selected_mapping == 4: TILE_SIGIL_IDX -= 1
                    scaled_cache.clear()

                if event.key == pygame.K_RIGHTBRACKET:
                    if selected_mapping == 1: TILE_FLOOR_IDX += 1
                    if selected_mapping == 2: TILE_WALL_IDX += 1
                    if selected_mapping == 3: TILE_WATER_IDX += 1
                    if selected_mapping == 4: TILE_SIGIL_IDX += 1
                    scaled_cache.clear()

                # Debug: export tile atlas
                if event.key == pygame.K_p and tiles:
                    out_path = ASSETS_DIR / "debug_tiles_index_sheet.png"
                    save_tile_index_debug(tiles, sheet_tile_size, out_path, cols=24)
                    last_message = f"Exported: {out_path.name}"
                    message_flash = 1.8

        # Movement
        keys = pygame.key.get_pressed()
        dx = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
        dy = (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0) - (1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0)

        if dx != 0 or dy != 0:
            nx = clamp(gs.player.x + dx, 0, WORLD_W - 1)
            ny = clamp(gs.player.y + dy, 0, WORLD_H - 1)
            if not is_blocking(world[ny][nx]):
                gs.player.x, gs.player.y = nx, ny
                gs.steps += 1

                if world[ny][nx] == T_SIGIL:
                    world[ny][nx] = T_FLOOR
                    gs.player.witness += 1
                    gs.discovered += 1
                    last_message = "You touched a sigil. The world remembers."
                    message_flash = 2.0

        # Camera (fixed bounds logic)
        view_cols = max(1, map_view.w // tile_px)
        view_rows = max(1, map_view.h // tile_px)

        camx = clamp(gs.player.x - view_cols // 2, 0, max(0, WORLD_W - view_cols))
        camy = clamp(gs.player.y - view_rows // 2, 0, max(0, WORLD_H - view_rows))

        # -----------------------------
        # Render
        # -----------------------------
        screen.fill((14, 14, 18))

        # UI panels
        if panel_border:
            draw_nineslice(screen, panel_border, map_view.inflate(12, 12), corner=16)
            draw_nineslice(screen, panel_border, ui_view.inflate(12, 12), corner=16)
        else:
            pygame.draw.rect(screen, (35, 35, 45), map_view.inflate(12, 12), border_radius=10)
            pygame.draw.rect(screen, (35, 35, 45), ui_view.inflate(12, 12), border_radius=10)

        pygame.draw.rect(screen, (18, 18, 22), map_view)

        # Draw world
        for y in range(max(0, camy), min(WORLD_H, camy + view_rows)):
            for x in range(max(0, camx), min(WORLD_W, camx + view_cols)):
                t = world[y][x]
                sx, sy = world_to_screen(x, y, camx, camy)

                if tilesheet and tiles:
                    if t == T_FLOOR:
                        img = get_scaled(TILE_FLOOR_IDX)
                        if img: screen.blit(img, (sx, sy))
                    elif t == T_WALL:
                        img = get_scaled(TILE_WALL_IDX)
                        if img: screen.blit(img, (sx, sy))
                    elif t == T_WATER:
                        img = get_scaled(TILE_WATER_IDX)
                        if img: screen.blit(img, (sx, sy))
                    elif t == T_SIGIL:
                        base = get_scaled(TILE_FLOOR_IDX)
                        if base: screen.blit(base, (sx, sy))
                        sig = get_scaled(TILE_SIGIL_IDX)
                        if sig: screen.blit(sig, (sx, sy))
                    else:
                        base = get_scaled(TILE_FLOOR_IDX)
                        if base: screen.blit(base, (sx, sy))

                    # Missing-tile fallback marker
                    if not pygame.Rect(sx, sy, tile_px, tile_px).collidelistall([]):
                        pass
                else:
                    col = (55, 55, 65)
                    if t == T_WALL:
                        col = (90, 90, 105)
                    elif t == T_WATER:
                        col = (25, 45, 85)
                    elif t == T_SIGIL:
                        col = (120, 110, 170)
                    pygame.draw.rect(screen, col, (sx, sy, tile_px, tile_px))

                # Tile debug overlay
                if show_tile_debug and tilesheet and tiles:
                    idx = TILE_FLOOR_IDX
                    if t == T_WALL: idx = TILE_WALL_IDX
                    if t == T_WATER: idx = TILE_WATER_IDX
                    if t == T_SIGIL: idx = TILE_SIGIL_IDX
                    txt = font_small.render(str(idx), True, (255, 255, 0))
                    screen.blit(txt, (sx + 2, sy + 2))

        # Player marker
        px, py = world_to_screen(gs.player.x, gs.player.y, camx, camy)
        pygame.draw.circle(screen, (240, 240, 255), (px + tile_px // 2, py + tile_px // 2), max(6, tile_px // 6))
        pygame.draw.circle(screen, (130, 120, 200), (px + tile_px // 2, py + tile_px // 2), max(10, tile_px // 4), 2)

        # UI content
        title = font_big.render("THE WITNESS", True, (235, 235, 245))
        screen.blit(title, (ui_view.x + 18, ui_view.y + 18))

        # Asset status
        asset_lines = []
        if tilesheet and tiles:
            asset_lines.append(f"Tiles: loaded ({len(tiles)} @ {sheet_tile_size}px)")
        else:
            asset_lines.append("Tiles: MISSING (fallback)")

        if panel_border:
            asset_lines.append("UI Border: loaded")
        else:
            asset_lines.append("UI Border: MISSING (fallback)")

        yy = ui_view.y + 54
        for s in asset_lines:
            col = (120, 255, 120) if "loaded" in s.lower() else (255, 120, 120)
            screen.blit(font_small.render(s, True, col), (ui_view.x + 18, yy))
            yy += 18

        lines = [
            f"Seed: {gs.seed}",
            f"Steps: {gs.steps}",
            f"Sigils: {gs.player.witness}",
            f"Discovered: {gs.discovered}",
            "",
            "Controls:",
            "WASD / Arrows — Move",
            "J — Journal",
            "F5 — Save",
            "F9 — Load",
            "R — Reseed world",
            "ESC — Quit",
            "",
            "Debug:",
            "T — Toggle tile indices",
            "1/2/3/4 — Select: floor/wall/water/sigil",
            "[ / ] — Adjust selected index",
            "P — Export tile atlas",
        ]
        yy = ui_view.y + 110
        for ln in lines:
            screen.blit(font.render(ln, True, (220, 220, 235)), (ui_view.x + 18, yy))
            yy += 22

        # Debug current mapping line
        if tilesheet and tiles:
            sel_name = {1: "FLOOR", 2: "WALL", 3: "WATER", 4: "SIGIL"}[selected_mapping]
            sel_idx = {1: TILE_FLOOR_IDX, 2: TILE_WALL_IDX, 3: TILE_WATER_IDX, 4: TILE_SIGIL_IDX}[selected_mapping]
            mapping_line = f"Selected: {sel_name} = {sel_idx}"
            screen.blit(font_small.render(mapping_line, True, (200, 200, 255)), (ui_view.x + 18, ui_view.bottom - 34))

        # Toast
        if message_flash > 0.0 and last_message:
            txt = font.render(last_message, True, (245, 245, 255))
            bg = pygame.Surface((txt.get_width() + 20, txt.get_height() + 12), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 180))
            x = map_view.x + 14
            y = map_view.y + 14
            screen.blit(bg, (x, y))
            screen.blit(txt, (x + 10, y + 6))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()

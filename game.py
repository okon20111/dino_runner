# game.py
import pygame
import sys
import platform
import math
import os
import json
from typing import Optional

from render import ObstacleManager

# Lepsza inicjalizacja audio (mniejsze opóźnienie skoku)
try:
    pygame.mixer.pre_init(44100, -16, 2, 512)
except Exception:
    pass

pygame.init()

# Lepsza jakość skalowania (jeśli backend dostępny)
try:
    pygame.transform.set_smoothscale_backend("SSE2")
except Exception:
    try:
        pygame.transform.set_smoothscale_backend("GENERIC")
    except Exception:
        pass

# =====================
# USTAWIENIA
# =====================
TOP_PADDING = 10
LOCK_WINDOW_POS = True

INTRO_DURATION_MS = 5000

FADE_INTRO_TO_MENU_MS = 1200
FADE_MENU_TO_LOAD_MS = 900
LOAD_DURATION_MS = 4000
FADE_LOAD_TO_BG_MS = 900
FADE_BG_TO_MENU_MS = 700  # po kolizji
FADE_BG_TO_COUNTDOWN_MS = 700

COUNTDOWN_DURATION_MS = 3000
COUNTDOWN_SECONDS = max(1, COUNTDOWN_DURATION_MS // 1000)

FADE_MENU_TO_SETTINGS_MS = 650
FADE_SETTINGS_TO_MENU_MS = 450

TARGET_FPS_NO_VSYNC = 90
ESC_EXIT_PRESS_COUNT = 3
ESC_EXIT_PRESS_WINDOW_MS = 1200

# =====================
# WŁASNY KURSOR (skalowany)
# =====================
CURSOR_PATH = "assets/cursor/cursor.png"
CURSOR_HOTSPOT_RAW = (0, 0)

CURSOR_TARGET_H_PX = None
CURSOR_TARGET_H_FRAC = 0.06
CURSOR_MIN_H_PX = 18
CURSOR_MAX_H_PX = 64

# =====================
# TŁA PO ŁADOWANIU (bg1->bg6)
# =====================
BG_SWITCH_EVERY_MS = 20000

# Bazowa prędkość gry (scroll + przeszkody)
BG_SCROLL_PX_PER_SEC = 230.0

MAX_DT_MS_FOR_SCROLL = 40

# =====================
# LEVEL SPEED
# Speed per level: +15%, cap 2.50x.
# =====================
# Co level (czyli co zmianę tła) przyspieszamy o +4.2%, max do 1.40x.
LEVEL_SPEED_INCREASE = 0.15
LEVEL_SPEED_CAP_MULT = 2.50

# =====================
# DINO - PARAMETRY
# =====================
DINO_PATH = "assets/skin/dino.png"

GROUND_Y_FRAC_BY_BG = [
    0.86,  # bg1
    0.86,  # bg2
    0.90,  # bg3
    0.86,  # bg4
    0.90,  # bg5
    0.86,  # bg6
    0.86,  # bg7
    0.906, # bg8
]

GROUND_Y_PX_OFFSET_BY_BG = [
    0,      # bg1
    0,      # bg2
    -16,    # bg3
    +5,     # bg4
    -16,    # bg5
    0,      # bg6
    0,      # bg7
    0,      # bg8
]

DINO_X_FRAC = 0.18

# Dino mniejsze
DINO_HEIGHT_FRAC = 0.125

# Skok ~3% dalej
DINO_GRAVITY_PX_PER_S2 = 2800.0 / 1.03
DINO_JUMP_VEL_PX_PER_S = 1120.0

# =====================
# KOLIZJE - maska
# =====================
MASK_ALPHA_THRESHOLD = 50     # ignoruje bardzo "miękkie" piksele na krawędziach
MIN_OVERLAP_PIXELS = 4        # minimalna liczba pikseli overlap aby uznać kolizję

# =====================
# DŹWIĘK SKOKU
# =====================
JUMP_SOUND_PATH = "assets/sounds/jump.mp3"
jump_sound = None
try:
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    jump_sound = pygame.mixer.Sound(JUMP_SOUND_PATH)
except Exception:
    jump_sound = None

# >>> USTAWIENIA: dźwięk skoku (domyślnie WŁ.)
jump_sound_enabled = True

# >>> USTAWIENIA: sterowanie skokiem (domyślnie SPACJA)
# wartości: "space", "up", "w"
jump_key_mode = "space"

# >>> USTAWIENIA: odliczanie do nastepnego tla (domyslnie WL.)
bg_timer_enabled = True

def current_jump_key() -> int:
    if jump_key_mode == "up":
        return pygame.K_UP
    if jump_key_mode == "w":
        return pygame.K_w
    return pygame.K_SPACE


# =====================
# USTAWIENIA - zapis/odczyt (USER)
# =====================
SETTINGS_FOLDER_NAME = "Dino Runner"
SETTINGS_FILENAME = "setting.json"

def _get_settings_path():
    # "lokalizacja użytkownika": na Windows bierzemy APPDATA jeśli jest,
    # w innych systemach katalog domowy.
    base = None
    try:
        if platform.system() == "Windows":
            base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    except Exception:
        base = None

    if not base:
        base = os.path.expanduser("~")

    folder = os.path.join(base, SETTINGS_FOLDER_NAME)
    path = os.path.join(folder, SETTINGS_FILENAME)
    return folder, path

def load_user_settings():
    global jump_sound_enabled, jump_key_mode, bg_timer_enabled
    folder, path = _get_settings_path()
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        return

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            if "jump_sound_enabled" in data:
                jump_sound_enabled = bool(data["jump_sound_enabled"])

            if "bg_timer_enabled" in data:
                bg_timer_enabled = bool(data["bg_timer_enabled"])

            if "jump_key" in data:
                v = str(data["jump_key"]).lower().strip()
                if v in ("space", "up", "w"):
                    jump_key_mode = v
    except FileNotFoundError:
        # pierwszy start: utwórz plik z domyślnymi ustawieniami
        save_user_settings()
    except Exception:
        # uszkodzony plik / brak uprawnień: zostaw domyślne
        pass

def save_user_settings():
    folder, path = _get_settings_path()
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        return

    data = {
        "jump_sound_enabled": bool(jump_sound_enabled),
        "bg_timer_enabled": bool(bg_timer_enabled),
        "jump_key": str(jump_key_mode),
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# wczytaj na starcie
load_user_settings()


# =====================
# MENU: styl
# =====================
MENU_TEXT_FILL = (204, 166, 61)
MENU_TEXT_OUTLINE = (72, 82, 51)
MENU_TEXT_SHADOW = (40, 28, 18)
MENU_OUTLINE_PX = 6
MENU_SHADOW_OFFSET = (6, 6)

MENU_HOVER_FILL = (255, 225, 120)
MENU_HOVER_OUTLINE = (90, 105, 60)
MENU_HOVER_SHADOW = (55, 40, 25)
MENU_HOVER_SCALE = 0.10
MENU_HOVER_RISE_PX = 6
MENU_HOVER_ANIM_MS = 140

MENU_MAX_WIDTH_FRAC = 0.72
MENU_MAX_HEIGHT_FRAC = 0.68
MENU_Y_OFFSET_FRAC = 0.01
MENU_SPACING_FRAC = 0.26

# =====================
# HUD / PAUSE / GAME OVER
# =====================
HUD_MARGIN_FRAC = 0.02
PAUSE_BTN_RADIUS_FRAC = 0.035

PAUSE_BTN_FILL = (30, 30, 30)
PAUSE_BTN_FILL_HOVER = (45, 45, 45)
PAUSE_BTN_ICON = (245, 245, 245)
PAUSE_BTN_OUTLINE = (210, 210, 210)

OVERLAY_DIM_ALPHA = 140
OVERLAY_TITLE_Y_FRAC = 0.30
OVERLAY_OPTIONS_GAP_FRAC = 0.06
OVERLAY_OPTIONS_SPACING_FRAC = 0.28
OVERLAY_OPTIONS_MAX_WIDTH_FRAC = 0.82
OVERLAY_OPTIONS_MAX_HEIGHT_FRAC = 0.26
OVERLAY_OPTION_START_SIZE_FRAC = 0.07
OVERLAY_OPTION_MIN_SIZE_PX = 22

# =====================
# USTAWIENIA: design (piękny "glass" UI)
# =====================
SET_TITLE_FILL = (255, 225, 120)
SET_TITLE_OUTLINE = (72, 82, 51)
SET_TITLE_SHADOW = (40, 28, 18)

SET_PANEL_FILL = (16, 18, 24, 165)
SET_PANEL_STROKE = (255, 255, 255, 38)

SET_MUTED = (210, 210, 220)
SET_DIM = (140, 140, 155)

SET_ACCENT = (255, 225, 120)
SET_ACCENT2 = (204, 166, 61)

SET_TOGGLE_ON = (44, 220, 140)
SET_TOGGLE_OFF = (130, 130, 145)

SET_ROW_FILL = (255, 255, 255, 18)
SET_ROW_HOVER_FILL = (255, 255, 255, 28)

SET_RADIUS = 18

# =====================
# PASEK ŁADOWANIA - PARAMETRY
# =====================
BAR_W_FRAC   = 0.43
BAR_H_FRAC   = 0.060
BAR_CX_FRAC  = 0.275
BAR_CY_FRAC  = 0.740
BAR_OFFSET_X = -12

# =====================
# POMOCNICZE FUNKCJE
# =====================
def load_raw(path: str) -> pygame.Surface:
    return pygame.image.load(path)

def convert_best(img: pygame.Surface) -> pygame.Surface:
    """Konwersja do formatu ekranu z zachowaniem kanału alfa (jeśli występuje)."""
    try:
        if (img.get_flags() & pygame.SRCALPHA) or (img.get_alpha() is not None):
            return img.convert_alpha()
        return img.convert()
    except Exception:
        return img

def convert_img_alpha(img: pygame.Surface) -> pygame.Surface:
    return img.convert_alpha()

def get_work_area_rect():
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            SPI_GETWORKAREA = 48

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", wintypes.LONG),
                    ("top", wintypes.LONG),
                    ("right", wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            rect = RECT()
            ok = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
            )
            if ok:
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass

    info = pygame.display.Info()
    return 0, 0, info.current_w, info.current_h

def _set_window_position_win32(x: int, y: int) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        hwnd = pygame.display.get_wm_info().get("window")
        if not hwnd:
            return False
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            hwnd, None, int(x), int(y), 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        )
        return True
    except Exception:
        return False

def _set_window_position_safe(x: int, y: int) -> bool:
    try:
        pygame.display.set_window_position(int(x), int(y))
        return True
    except Exception:
        return _set_window_position_win32(x, y)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def smoothstep(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def scale_to_window(surf: pygame.Surface, w: int, h: int) -> pygame.Surface:
    """Skaluje z jak najwyższą jakością (smoothscale) i konwertuje do formatu ekranu."""
    if surf.get_width() != w or surf.get_height() != h:
        surf = pygame.transform.smoothscale(surf, (w, h))
    return convert_best(surf)

def render_text_styled(font: pygame.font.Font, text: str,
                       fill, outline, outline_px: int,
                       shadow=None, shadow_offset=(0, 0)) -> pygame.Surface:
    base = font.render(text, True, fill).convert_alpha()
    outline_surf = font.render(text, True, outline).convert_alpha()

    w = base.get_width() + outline_px * 2 + abs(shadow_offset[0])
    h = base.get_height() + outline_px * 2 + abs(shadow_offset[1])
    out = pygame.Surface((w, h), pygame.SRCALPHA)

    if shadow is not None and (shadow_offset[0] != 0 or shadow_offset[1] != 0):
        shadow_surf = font.render(text, True, shadow).convert_alpha()
        out.blit(shadow_surf, (outline_px + shadow_offset[0], outline_px + shadow_offset[1]))

    for dx in range(-outline_px, outline_px + 1):
        for dy in range(-outline_px, outline_px + 1):
            if dx == 0 and dy == 0:
                continue
            if dx * dx + dy * dy > outline_px * outline_px:
                continue
            out.blit(outline_surf, (outline_px + dx, outline_px + dy))

    out.blit(base, (outline_px, outline_px))
    return out

# =====================
# HUD / Pause / Game over helpers
# =====================
def _build_option_surfaces(labels, font_size: int):
    font = pygame.font.Font(FONT_PATH, font_size)
    surfs_normal = [
        render_text_styled(
            font, txt,
            fill=MENU_TEXT_FILL,
            outline=MENU_TEXT_OUTLINE,
            outline_px=MENU_OUTLINE_PX,
            shadow=MENU_TEXT_SHADOW,
            shadow_offset=MENU_SHADOW_OFFSET
        )
        for txt in labels
    ]
    surfs_hover = [
        render_text_styled(
            font, txt,
            fill=MENU_HOVER_FILL,
            outline=MENU_HOVER_OUTLINE,
            outline_px=MENU_OUTLINE_PX,
            shadow=MENU_HOVER_SHADOW,
            shadow_offset=MENU_SHADOW_OFFSET
        )
        for txt in labels
    ]

    spacing = int(font_size * OVERLAY_OPTIONS_SPACING_FRAC)
    total_h = sum(s.get_height() for s in surfs_normal) + spacing * (len(surfs_normal) - 1)
    max_w = max(s.get_width() for s in surfs_normal) if surfs_normal else 0
    return surfs_normal, surfs_hover, spacing, total_h, max_w

def _fit_option_surfaces(labels):
    start_size = max(30, int(HEIGHT * OVERLAY_OPTION_START_SIZE_FRAC))
    font_size = start_size
    while font_size > OVERLAY_OPTION_MIN_SIZE_PX:
        surfs_normal, surfs_hover, spacing, total_h, max_w = _build_option_surfaces(labels, font_size)
        if max_w <= int(WIDTH * OVERLAY_OPTIONS_MAX_WIDTH_FRAC) and total_h <= int(HEIGHT * OVERLAY_OPTIONS_MAX_HEIGHT_FRAC):
            break
        font_size -= 2
    return surfs_normal, surfs_hover, spacing

def build_overlay_cache(title_text: str, option_labels):
    title_surf = render_text_styled(
        font_overlay_title, title_text,
        fill=MENU_HOVER_FILL,
        outline=MENU_TEXT_OUTLINE,
        outline_px=MENU_OUTLINE_PX,
        shadow=MENU_TEXT_SHADOW,
        shadow_offset=MENU_SHADOW_OFFSET
    )
    title_rect = title_surf.get_rect(center=(WIDTH // 2, int(HEIGHT * OVERLAY_TITLE_Y_FRAC)))

    option_normal, option_hover, spacing = _fit_option_surfaces(option_labels)
    option_rects = []
    y = title_rect.bottom + int(HEIGHT * OVERLAY_OPTIONS_GAP_FRAC)
    for surf in option_normal:
        r = surf.get_rect(centerx=WIDTH // 2)
        r.top = y
        option_rects.append(r)
        y += surf.get_height() + spacing

    return {
        "title_surf": title_surf,
        "title_rect": title_rect,
        "option_normal": option_normal,
        "option_hover": option_hover,
        "option_rects": option_rects,
    }

def draw_overlay_menu(dst: pygame.Surface, cache: dict, mouse_pos):
    dst.blit(dim_overlay, (0, 0))
    dst.blit(cache["title_surf"], cache["title_rect"].topleft)

    mx, my = mouse_pos
    hovered = -1
    for i, rect in enumerate(cache["option_rects"]):
        if rect.collidepoint(mx, my):
            hovered = i
        surf = cache["option_hover"][i] if i == hovered else cache["option_normal"][i]
        dst.blit(surf, rect.topleft)

    return hovered

def draw_overlay_menu_animated(dst: pygame.Surface, cache: dict, mouse_pos, dt_ms: int, hover_t):
    dst.blit(dim_overlay, (0, 0))
    dst.blit(cache["title_surf"], cache["title_rect"].topleft)

    mx, my = mouse_pos
    hovered = -1
    for i, rect in enumerate(cache["option_rects"]):
        if rect.collidepoint(mx, my):
            hovered = i
            break

    step = dt_ms / max(1, MENU_HOVER_ANIM_MS)
    for i in range(len(hover_t)):
        if i == hovered:
            hover_t[i] = min(1.0, hover_t[i] + step)
        else:
            hover_t[i] = max(0.0, hover_t[i] - step)

    for i in range(len(cache["option_rects"])):
        t = smoothstep(hover_t[i])
        scale = 1.0 + MENU_HOVER_SCALE * t
        rise = int(MENU_HOVER_RISE_PX * t)

        n0 = cache["option_normal"][i]
        h0 = cache["option_hover"][i]

        nw = max(1, int(n0.get_width() * scale))
        nh = max(1, int(n0.get_height() * scale))

        n = pygame.transform.smoothscale(n0, (nw, nh))
        h = pygame.transform.smoothscale(h0, (nw, nh))

        n.set_alpha(int(255 * (1.0 - t)))
        h.set_alpha(int(255 * t))

        cx, cy = cache["option_rects"][i].center
        r = n.get_rect(center=(cx, cy - rise))

        dst.blit(n, r.topleft)
        dst.blit(h, r.topleft)

    return hovered

def draw_pause_button(dst: pygame.Surface, hovered: bool):
    rect = pause_button_rect
    cx, cy = rect.center
    radius = rect.width // 2

    fill = PAUSE_BTN_FILL_HOVER if hovered else PAUSE_BTN_FILL
    pygame.draw.circle(dst, fill, (cx, cy), radius)
    pygame.draw.circle(dst, PAUSE_BTN_OUTLINE, (cx, cy), radius, width=2)

    bar_w = max(4, int(radius * 0.28))
    bar_h = max(12, int(radius * 1.2))
    gap = max(5, int(radius * 0.35))
    bar_y = cy - bar_h // 2
    left_x = cx - gap // 2 - bar_w
    right_x = cx + gap // 2

    pygame.draw.rect(
        dst, PAUSE_BTN_ICON,
        pygame.Rect(left_x, bar_y, bar_w, bar_h),
        border_radius=max(1, bar_w // 2)
    )
    pygame.draw.rect(
        dst, PAUSE_BTN_ICON,
        pygame.Rect(right_x, bar_y, bar_w, bar_h),
        border_radius=max(1, bar_w // 2)
    )

timer_cache_seconds = None
timer_cache_surf = None

def draw_bg_timer(dst: pygame.Surface, now_ms: int):
    global timer_cache_seconds, timer_cache_surf
    if not bg_timer_enabled:
        return
    if bg_switch_start_ms is None:
        remaining_ms = BG_SWITCH_EVERY_MS
    else:
        remaining_ms = max(0, BG_SWITCH_EVERY_MS - (now_ms - bg_switch_start_ms))

    seconds_left = int(math.ceil(remaining_ms / 1000.0))
    if seconds_left != timer_cache_seconds or timer_cache_surf is None:
        timer_cache_seconds = seconds_left
        label = f"TLO ZA: {seconds_left}s"
        timer_cache_surf = render_text_styled(
            font_hud, label,
            fill=MENU_TEXT_FILL,
            outline=MENU_TEXT_OUTLINE,
            outline_px=4,
            shadow=MENU_TEXT_SHADOW,
            shadow_offset=(3, 3)
        )

    dst.blit(timer_cache_surf, (HUD_MARGIN_PX, HUD_MARGIN_PX))

def draw_game_world(dst: pygame.Surface):
    bg_scroll_x = int(bg_scroll_num // PIX_DEN)
    draw_scrolling_bg(dst, bg_sequence[bg_index], bg_scroll_x)
    obstacles.draw(dst)
    dx, dy = dino_draw_pos()
    dst.blit(dino_img, (dx, dy))

def capture_game_frame(now_ms: int, include_hud: bool = True) -> pygame.Surface:
    frame = pygame.Surface((WIDTH, HEIGHT)).convert()
    draw_game_world(frame)
    if include_hud:
        draw_bg_timer(frame, now_ms)
        draw_pause_button(frame, hovered=False)
    return frame

def make_countdown_base_frame(bg_idx: int = 0) -> pygame.Surface:
    frame = make_scrolling_bg_frame(bg_sequence[bg_idx], 0)
    gy = get_ground_y_for_bg(bg_idx)
    dx = int(dino_x - dino_img.get_width() // 2)
    dy = int(gy - dino_img.get_height())
    frame.blit(dino_img, (dx, dy))
    return frame

def resume_from_pause(now_ms: int):
    global pause_started_ms, bg_switch_start_ms
    if pause_started_ms is None:
        return

    pause_ms = max(0, now_ms - pause_started_ms)
    if bg_switch_start_ms is not None:
        bg_switch_start_ms += pause_ms

    try:
        obstacles.next_spawn_ms += pause_ms
    except Exception:
        pass

    pause_started_ms = None

def reset_exit_confirm_presses():
    global esc_exit_press_count, esc_exit_last_press_ms
    esc_exit_press_count = 0
    esc_exit_last_press_ms = None

def register_exit_confirm_press(now_ms: int) -> bool:
    global esc_exit_press_count, esc_exit_last_press_ms
    if esc_exit_last_press_ms is None or now_ms - esc_exit_last_press_ms > ESC_EXIT_PRESS_WINDOW_MS:
        esc_exit_press_count = 1
    else:
        esc_exit_press_count += 1
    esc_exit_last_press_ms = now_ms
    if esc_exit_press_count >= ESC_EXIT_PRESS_COUNT:
        reset_exit_confirm_presses()
        return True
    return False

def enter_exit_confirm(now_ms: int):
    global state, exit_confirm_prev_state, exit_confirm_frame, exit_confirm_started_ms
    if state == STATE_EXIT_CONFIRM:
        return
    exit_confirm_prev_state = state
    exit_confirm_frame = screen.copy()
    exit_confirm_started_ms = now_ms
    state = STATE_EXIT_CONFIRM

def resume_from_exit_confirm(now_ms: int):
    global state, exit_confirm_prev_state, exit_confirm_frame, exit_confirm_started_ms
    global fade_start_ms, load_start_ms, countdown_start_ms, intro_start_ms
    if exit_confirm_prev_state is None:
        state = STATE_MENU
        exit_confirm_started_ms = None
        return

    pause_ms = max(0, now_ms - (exit_confirm_started_ms or now_ms))
    prev_state = exit_confirm_prev_state

    if prev_state.startswith("fade_"):
        fade_start_ms += pause_ms
    elif prev_state == STATE_INTRO:
        intro_start_ms += pause_ms
    elif prev_state == STATE_LOAD:
        if load_start_ms is not None:
            load_start_ms += pause_ms
    elif prev_state == STATE_COUNTDOWN:
        if countdown_start_ms is not None:
            countdown_start_ms += pause_ms

    state = prev_state
    exit_confirm_prev_state = None
    exit_confirm_started_ms = None
    exit_confirm_frame = None
    reset_exit_confirm_presses()

def load_scale_cursor(path: str, win_h: int):
    raw = convert_img_alpha(load_raw(path))
    raw_w, raw_h = raw.get_size()

    if CURSOR_TARGET_H_PX is not None:
        target_h = int(CURSOR_TARGET_H_PX)
    else:
        target_h = int(win_h * CURSOR_TARGET_H_FRAC)

    target_h = clamp(target_h, CURSOR_MIN_H_PX, CURSOR_MAX_H_PX)
    if raw_h <= 0:
        return raw, CURSOR_HOTSPOT_RAW

    scale = target_h / float(raw_h)
    target_w = max(1, int(raw_w * scale))

    surf = pygame.transform.smoothscale(raw, (target_w, target_h)).convert_alpha()

    hx_raw, hy_raw = CURSOR_HOTSPOT_RAW
    hx = int(hx_raw * scale)
    hy = int(hy_raw * scale)
    return surf, (hx, hy)

def union_rects(rects):
    if not rects:
        return None
    u = rects[0].copy()
    for r in rects[1:]:
        u.union_ip(r)
    return u

# =====================
# USTAWIENIA - UI helpers
# =====================
def _draw_rounded_rect_alpha(dst: pygame.Surface, rect: pygame.Rect, color_rgba, radius: int):
    tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(tmp, color_rgba, tmp.get_rect(), border_radius=radius)
    dst.blit(tmp, rect.topleft)

def draw_glass_panel(dst: pygame.Surface, rect: pygame.Rect, radius: int = 18,
                     fill_rgba=(16, 18, 24, 165), stroke_rgba=(255, 255, 255, 38), stroke_w: int = 2):
    _draw_rounded_rect_alpha(dst, rect, fill_rgba, radius)
    tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(tmp, stroke_rgba, tmp.get_rect(), width=stroke_w, border_radius=radius)
    dst.blit(tmp, rect.topleft)

def draw_divider(dst: pygame.Surface, x1: int, x2: int, y: int, rgba=(255, 255, 255, 40)):
    tmp = pygame.Surface((max(1, x2 - x1), 2), pygame.SRCALPHA)
    tmp.fill(rgba)
    dst.blit(tmp, (x1, y))

# =====================
# PASEK ŁADOWANIA - FUNKCJE
# =====================
def _bar_rect(screen: pygame.Surface) -> pygame.Rect:
    sw, sh = screen.get_size()
    w = int(sw * BAR_W_FRAC)
    h = max(14, int(sh * BAR_H_FRAC))
    cx = int(sw * BAR_CX_FRAC)
    cy = int(sw * 0 + sh * BAR_CY_FRAC)

    r = pygame.Rect(0, 0, w, h)
    r.center = (cx + BAR_OFFSET_X, cy)
    return r

def draw_progress_bar(screen: pygame.Surface, progress: float, now_ms: int,
                      track_rect: Optional[pygame.Rect] = None):
    """Półprzezroczysty pasek ładowania: tło przezroczyste, delikatny obrys, zielone wypełnienie."""
    if track_rect is None:
        track_rect = _bar_rect(screen)

    screen_rect = screen.get_rect()
    track_rect = track_rect.copy()
    track_rect.clamp_ip(screen_rect)

    track_rect.width = max(80, track_rect.width)
    track_rect.height = max(14, track_rect.height)
    track_rect.clamp_ip(screen_rect)

    progress = max(0.0, min(1.0, float(progress)))
    radius = track_rect.height // 2

    # Delikatny cień (też półprzezroczysty)
    shadow = pygame.Surface((track_rect.width, track_rect.height), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (0, 0, 0, 70), shadow.get_rect(), border_radius=radius)
    screen.blit(shadow, (track_rect.left + 2, track_rect.top + 2))

    # Właściwy pasek (alpha overlay)
    bar = pygame.Surface((track_rect.width, track_rect.height), pygame.SRCALPHA)

    # Tor: bardzo lekki "glass"
    pygame.draw.rect(bar, (255, 255, 255, 22), bar.get_rect(), border_radius=radius)
    pygame.draw.rect(bar, (255, 255, 255, 60), bar.get_rect(), width=2, border_radius=radius)

    pad = 5
    inner = pygame.Rect(pad, pad, track_rect.width - pad * 2, track_rect.height - pad * 2)
    if inner.width <= 2 or inner.height <= 2:
        screen.blit(bar, track_rect.topleft)
        return

    fill_w = int(inner.width * progress)
    if fill_w > 0:
        fill_rect = inner.copy()
        fill_rect.width = fill_w
        fill_radius = min(inner.height // 2, max(0, fill_w // 2))
        pygame.draw.rect(bar, (44, 220, 140, 180), fill_rect, border_radius=fill_radius)

    screen.blit(bar, track_rect.topleft)

# =====================
# SCROLL TŁA - FUNKCJE
# =====================
def make_scrolling_bg_frame(bg: pygame.Surface, offset_px: int) -> pygame.Surface:
    w, h = bg.get_size()
    out = pygame.Surface((w, h)).convert()
    x = -offset_px
    out.blit(bg, (x, 0))
    out.blit(bg, (x + w, 0))
    return out

def draw_scrolling_bg(screen: pygame.Surface, bg: pygame.Surface, offset_px: int):
    w, _ = bg.get_size()
    x = -offset_px
    screen.blit(bg, (x, 0))
    screen.blit(bg, (x + w, 0))

# =====================
# ROZMIAR OKNA Z TŁA
# =====================
bg1_raw = load_raw("assets/game_bg/bg1.png")
WIDTH, HEIGHT = bg1_raw.get_size()

# =====================
# OKNO (bez ramki) + próba VSYNC + DOUBLEBUF
# =====================
flags = pygame.NOFRAME | pygame.DOUBLEBUF
vsync_enabled = False
try:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags, vsync=1)
    vsync_enabled = True
except TypeError:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
except Exception:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)

pygame.display.set_caption("Dino Runner")
clock = pygame.time.Clock()

# =====================
# USTAW POZYCJĘ OKNA
# =====================
left, top, right, bottom = get_work_area_rect()
work_w = right - left

target_x = left + (work_w - WIDTH) // 2
target_y = top + TOP_PADDING

target_x = clamp(target_x, left, right - WIDTH)
target_y = clamp(target_y, top, bottom - HEIGHT)

fixed_pos = None

if _set_window_position_safe(target_x, target_y):
    fixed_pos = (target_x, target_y)
else:
    fixed_pos = None

# =====================
# IKONA
# =====================
icon = pygame.image.load("assets/icon/icon.ico")
pygame.display.set_icon(icon)

# =====================
# CZCIONKI
# =====================
FONT_PATH = "assets/fonts/Bangers-Regular.ttf"
font_big = pygame.font.Font(FONT_PATH, 64)
font_small = pygame.font.Font(FONT_PATH, 32)
font_hud = pygame.font.Font(FONT_PATH, max(22, int(HEIGHT * 0.040)))
font_overlay_title = pygame.font.Font(FONT_PATH, max(56, int(HEIGHT * 0.115)))

# Fonts dla ustawień (ładniejsze skalowanie)
font_set_title = pygame.font.Font(FONT_PATH, max(72, int(HEIGHT * 0.12)))
font_set_h1 = pygame.font.Font(FONT_PATH, max(48, int(HEIGHT * 0.075)))
font_set_label = pygame.font.Font(FONT_PATH, max(30, int(HEIGHT * 0.045)))
font_set_hint = pygame.font.Font(FONT_PATH, max(22, int(HEIGHT * 0.032)))

font_countdown = pygame.font.Font(FONT_PATH, max(140, int(HEIGHT * 0.35)))
countdown_outline_px = max(6, int(font_countdown.get_height() * 0.08))
countdown_shadow_offset = (
    max(4, int(countdown_outline_px * 0.6)),
    max(4, int(countdown_outline_px * 0.6)),
)
countdown_surfs = {
    i: render_text_styled(
        font_countdown, str(i),
        fill=MENU_HOVER_FILL,
        outline=MENU_TEXT_OUTLINE,
        outline_px=countdown_outline_px,
        shadow=MENU_TEXT_SHADOW,
        shadow_offset=countdown_shadow_offset
    )
    for i in range(COUNTDOWN_SECONDS, 0, -1)
}

# =====================
# GRAFIKI
# =====================
intro_bg = scale_to_window(load_raw("assets/intro_screen/intro.png"), WIDTH, HEIGHT)
menu_bg = scale_to_window(load_raw("assets/menu/menu.png"), WIDTH, HEIGHT)
load_level_bg = scale_to_window(load_raw("assets/load_level/load_level.png"), WIDTH, HEIGHT)

bg1 = scale_to_window(bg1_raw, WIDTH, HEIGHT)
bg2 = scale_to_window(load_raw("assets/game_bg/bg2.png"), WIDTH, HEIGHT)
bg3 = scale_to_window(load_raw("assets/game_bg/bg3.png"), WIDTH, HEIGHT)
bg4 = scale_to_window(load_raw("assets/game_bg/bg4.png"), WIDTH, HEIGHT)
bg5 = scale_to_window(load_raw("assets/game_bg/bg5.png"), WIDTH, HEIGHT)
bg6 = scale_to_window(load_raw("assets/game_bg/bg6.png"), WIDTH, HEIGHT)
bg7 = scale_to_window(load_raw("assets/game_bg/bg7.png"), WIDTH, HEIGHT)
bg8 = scale_to_window(load_raw("assets/game_bg/bg8.png"), WIDTH, HEIGHT)

bg_sequence = [bg1, bg2, bg3, bg4, bg5, bg6, bg7, bg8]

# =====================
# WŁASNY KURSOR
# =====================
cursor_img = None
cursor_hotspot = (0, 0)
try:
    cursor_img, cursor_hotspot = load_scale_cursor(CURSOR_PATH, HEIGHT)
    pygame.mouse.set_visible(False)
except Exception:
    cursor_img = None
    pygame.mouse.set_visible(True)

# =====================
# DINO - wczytanie + skalowanie
# =====================
dino_raw = convert_img_alpha(load_raw(DINO_PATH))

target_h = max(24, int(HEIGHT * DINO_HEIGHT_FRAC))
scale = target_h / float(max(1, dino_raw.get_height()))
target_w = max(24, int(dino_raw.get_width() * scale))
dino_img = pygame.transform.smoothscale(dino_raw, (target_w, target_h)).convert_alpha()

dino_mask = pygame.mask.from_surface(dino_img, MASK_ALPHA_THRESHOLD)

dino_bounds_list = dino_mask.get_bounding_rects()
dino_bounds = union_rects(dino_bounds_list) or dino_img.get_rect()

DINO_BOTTOM_PAD_PX = int(dino_img.get_height() - dino_bounds.bottom)
if DINO_BOTTOM_PAD_PX < 0:
    DINO_BOTTOM_PAD_PX = 0
if len(GROUND_Y_PX_OFFSET_BY_BG) > 7:
    # bg8: push ground down to match the white base using dino bottom padding
    GROUND_Y_PX_OFFSET_BY_BG[7] += DINO_BOTTOM_PAD_PX

dino_x = int(WIDTH * 0.18)
dino_y = 0.0
dino_vy = 0.0
dino_on_ground = True

def get_ground_y_for_bg(bg_idx: int) -> int:
    i = bg_idx % len(GROUND_Y_FRAC_BY_BG)
    frac = GROUND_Y_FRAC_BY_BG[i]
    px_off = GROUND_Y_PX_OFFSET_BY_BG[i] if i < len(GROUND_Y_PX_OFFSET_BY_BG) else 0
    return int(HEIGHT * frac) + int(px_off)

def snap_dino_to_ground(bg_idx: int):
    global dino_y, dino_vy, dino_on_ground
    gy = get_ground_y_for_bg(bg_idx)
    dino_y = float(gy - dino_img.get_height())
    dino_vy = 0.0
    dino_on_ground = True

def resolve_dino_vs_ground(bg_idx: int):
    global dino_y, dino_vy, dino_on_ground
    gy = get_ground_y_for_bg(bg_idx)
    if dino_y + dino_img.get_height() >= gy:
        dino_y = float(gy - dino_img.get_height())
        dino_vy = 0.0
        dino_on_ground = True

def dino_safe_right_px() -> int:
    return int(dino_x + dino_img.get_width() // 2)

def dino_draw_pos() -> tuple[int, int]:
    dx = int(dino_x - dino_img.get_width() // 2)
    dy = int(dino_y)
    return dx, dy

def dino_hit_rect_world() -> pygame.Rect:
    dx, dy = dino_draw_pos()
    return pygame.Rect(dx + dino_bounds.left, dy + dino_bounds.top, dino_bounds.width, dino_bounds.height)

# =====================
# PRZESZKODY - manager
# =====================
obstacles = ObstacleManager(
    screen_size=(WIDTH, HEIGHT),
    dino_height_px=dino_img.get_height(),
    obstacle_dir="assets/obstacles",
    base_speed_px_per_sec=BG_SCROLL_PX_PER_SEC,
    mask_alpha_threshold=MASK_ALPHA_THRESHOLD,
    jump_vel_px_per_s=DINO_JUMP_VEL_PX_PER_S,
    gravity_px_per_s2=DINO_GRAVITY_PX_PER_S2,
)

# =====================
# SPEED MULT
# =====================
speed_mult = 1.0

def current_game_speed_px_per_sec() -> float:
    return BG_SCROLL_PX_PER_SEC * float(speed_mult)

def apply_speed_to_systems(rescale_existing: bool = True):
    global bg_speed_micro_per_sec
    spd = current_game_speed_px_per_sec()
    bg_speed_micro_per_sec = int(spd * 1_000_000)
    try:
        obstacles.set_base_speed(spd, rescale_existing=rescale_existing)
    except Exception:
        obstacles.base_speed = float(spd)

apply_speed_to_systems(rescale_existing=False)

# =====================
# MENU - AUTO-FIT + CACHE + HOVER ANIM
# =====================
menu_labels = ["GRAJ", "USTAWIENIA", "WYJDŹ"]

def build_menu_surfaces(font_size: int):
    font = pygame.font.Font(FONT_PATH, font_size)

    surfs_normal = [
        render_text_styled(
            font, txt,
            fill=MENU_TEXT_FILL,
            outline=MENU_TEXT_OUTLINE,
            outline_px=MENU_OUTLINE_PX,
            shadow=MENU_TEXT_SHADOW,
            shadow_offset=MENU_SHADOW_OFFSET
        )
        for txt in menu_labels
    ]

    surfs_hover = [
        render_text_styled(
            font, txt,
            fill=MENU_HOVER_FILL,
            outline=MENU_HOVER_OUTLINE,
            outline_px=MENU_OUTLINE_PX,
            shadow=MENU_HOVER_SHADOW,
            shadow_offset=MENU_SHADOW_OFFSET
        )
        for txt in menu_labels
    ]

    spacing = int(font_size * MENU_SPACING_FRAC)
    total_h = sum(s.get_height() for s in surfs_normal) + spacing * (len(surfs_normal) - 1)
    max_w = max(s.get_width() for s in surfs_normal)
    return surfs_normal, surfs_hover, spacing, total_h, max_w

start_size = max(58, int(HEIGHT * 0.145))
font_size = start_size
while font_size > 30:
    tmp_normal, tmp_hover, tmp_spacing, tmp_total_h, tmp_max_w = build_menu_surfaces(font_size)
    if tmp_max_w <= int(WIDTH * MENU_MAX_WIDTH_FRAC) and tmp_total_h <= int(HEIGHT * MENU_MAX_HEIGHT_FRAC):
        break
    font_size -= 2

menu_surfs_normal, menu_surfs_hover, menu_spacing, menu_total_h, menu_max_w = build_menu_surfaces(font_size)

def build_menu_layout_and_static_surface():
    surf = pygame.Surface((WIDTH, HEIGHT)).convert()
    surf.blit(menu_bg, (0, 0))

    x_center = WIDTH // 2
    y_offset = int(HEIGHT * MENU_Y_OFFSET_FRAC)
    start_y = (HEIGHT - menu_total_h) // 2 + y_offset

    centers = []
    rects = []
    y = start_y
    for s in menu_surfs_normal:
        r = s.get_rect()
        r.centerx = x_center
        r.top = y
        surf.blit(s, r.topleft)
        rects.append(r)
        centers.append(r.center)
        y += s.get_height() + menu_spacing

    return centers, surf, rects

menu_item_centers, menu_surface_static, menu_item_rects_static = build_menu_layout_and_static_surface()

menu_hover_t = [0.0 for _ in menu_labels]

def compose_menu_frame(mouse_pos, dt_ms: int):
    mx, my = mouse_pos
    hovered_index = -1

    for i, base_rect in enumerate(menu_item_rects_static):
        if base_rect.collidepoint(mx, my):
            hovered_index = i
            break

    step = dt_ms / max(1, MENU_HOVER_ANIM_MS)
    for i in range(len(menu_hover_t)):
        if i == hovered_index:
            menu_hover_t[i] = min(1.0, menu_hover_t[i] + step)
        else:
            menu_hover_t[i] = max(0.0, menu_hover_t[i] - step)

    surf = pygame.Surface((WIDTH, HEIGHT)).convert()
    surf.blit(menu_bg, (0, 0))

    rects = []
    for i in range(len(menu_labels)):
        t = smoothstep(menu_hover_t[i])
        scale = 1.0 + MENU_HOVER_SCALE * t
        rise = int(MENU_HOVER_RISE_PX * t)

        n0 = menu_surfs_normal[i]
        h0 = menu_surfs_hover[i]

        nw = max(1, int(n0.get_width() * scale))
        nh = max(1, int(n0.get_height() * scale))

        n = pygame.transform.smoothscale(n0, (nw, nh))
        h = pygame.transform.smoothscale(h0, (nw, nh))

        n.set_alpha(int(255 * (1.0 - t)))
        h.set_alpha(int(255 * t))

        cx, cy = menu_item_centers[i]
        r = n.get_rect(center=(cx, cy - rise))

        surf.blit(n, r.topleft)
        surf.blit(h, r.topleft)

        rects.append(r)

    return surf, rects, hovered_index

load_surface = pygame.Surface((WIDTH, HEIGHT)).convert()
load_surface.blit(load_level_bg, (0, 0))
countdown_bg_frame = None

# =====================
# HUD / PAUSE / GAME OVER - INIT
# =====================
HUD_MARGIN_PX = max(10, int(HEIGHT * HUD_MARGIN_FRAC))
pause_btn_radius = max(16, int(HEIGHT * PAUSE_BTN_RADIUS_FRAC))
pause_button_rect = pygame.Rect(0, 0, pause_btn_radius * 2, pause_btn_radius * 2)
pause_button_rect.topright = (WIDTH - HUD_MARGIN_PX, HUD_MARGIN_PX)

dim_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
dim_overlay.fill((0, 0, 0, OVERLAY_DIM_ALPHA))

pause_menu_cache = build_overlay_cache(
    "PAUZA",
    ["KONTYNUUJ GRE", "ROZPOCZNIJ NOWA GRE", "WROC DO MENU"],
)
pause_menu_hover_t = [0.0 for _ in pause_menu_cache["option_rects"]]
game_over_menu_cache = build_overlay_cache(
    "PRZEGRALES",
    ["ROZPOCZNIJ NOWA GRE", "WROC DO MENU"],
)
game_over_hover_t = [0.0 for _ in game_over_menu_cache["option_rects"]]
exit_confirm_cache = build_overlay_cache(
    "CZY NA PEWNO WYJSC?",
    ["WYJDZ", "ZOSTAN"],
)

# =====================
# USTAWIENIA - NOWY DESIGN
# =====================

# Globalny stan zakładek: 0 = Audio, 1 = Sterowanie
settings_active_tab = 2  # 0: AUDIO, 1: STEROWANIE, 2: OGOLNE

# Recty interaktywne (updateowane w _build_settings_cache)
settings_sidebar_audio_rect = pygame.Rect(0, 0, 0, 0)
settings_sidebar_controls_rect = pygame.Rect(0, 0, 0, 0)
settings_sidebar_general_rect = pygame.Rect(0, 0, 0, 0)

settings_toggle_rect = pygame.Rect(0, 0, 0, 0)
settings_sound_row_rect = pygame.Rect(0, 0, 0, 0)
settings_timer_toggle_rect = pygame.Rect(0, 0, 0, 0)
settings_timer_row_rect = pygame.Rect(0, 0, 0, 0)

settings_control_btn_rects = [pygame.Rect(0, 0, 0, 0) for _ in range(3)]
SET_CONTROL_OPTIONS = [
    ("space", "SPACJA"),
    ("up", "GÓRA"),
    ("w", "W"),
]
settings_back_rect = pygame.Rect(0, 0, 0, 0)

# Animacja suwaka audio
toggle_anim = 1.0 if jump_sound_enabled else 0.0
bg_timer_toggle_anim = 1.0 if bg_timer_enabled else 0.0

# Cache elementów graficznych
_settings_cache = {
    "bg_base": None,          # Tło + Title + Pusty layout paneli
    "sidebar_rect": None,
    "main_rect": None,

    "tab_audio_sel": None,    # Surface aktywnej zakładki Audio
    "tab_audio_unsel": None,  # Surface nieaktywnej zakładki Audio
    "tab_ctrl_sel": None,
    "tab_ctrl_unsel": None,
    "tab_gen_sel": None,
    "tab_gen_unsel": None,

    "hdr_audio": None,        # Tytuł sekcji (prawy panel)
    "hdr_ctrl": None,
    "hdr_general": None,

    "sound_label": None,
    "sound_status_on": None,
    "sound_status_off": None,
    "timer_label": None,
    "timer_status_on": None,
    "timer_status_off": None,

    "btn_text_sel": None,     # dict: key -> surface
    "btn_text_unsel": None,   # dict: key -> surface

    "hint_rect": None,
}
_settings_frame = None
_settings_just_entered = True

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def _build_settings_cache():
    global settings_sidebar_audio_rect, settings_sidebar_controls_rect, settings_sidebar_general_rect
    global settings_toggle_rect, settings_sound_row_rect, settings_timer_toggle_rect, settings_timer_row_rect, settings_back_rect
    global settings_control_btn_rects
    global _settings_cache

    base = pygame.Surface((WIDTH, HEIGHT)).convert()
    base.blit(menu_bg, (0, 0))

    # Przyciemnienie
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 92))
    base.blit(overlay, (0, 0))

    # Główny Tytuł
    title = render_text_styled(
        font_set_title, "USTAWIENIA",
        fill=SET_TITLE_FILL,
        outline=SET_TITLE_OUTLINE,
        outline_px=6,
        shadow=SET_TITLE_SHADOW,
        shadow_offset=(6, 6)
    )
    tr = title.get_rect(center=(WIDTH // 2, int(HEIGHT * 0.11)))
    base.blit(title, tr.topleft)

    # Podkreślenie
    line_y = tr.bottom - int(HEIGHT * 0.01)
    draw_divider(base, int(WIDTH * 0.35), int(WIDTH * 0.65), line_y, rgba=(255, 255, 255, 45))

    # Layout: Sidebar (L) + Main (P)
    sidebar_rect = pygame.Rect(int(WIDTH * 0.055), int(HEIGHT * 0.20), int(WIDTH * 0.245), int(HEIGHT * 0.70))
    main_rect = pygame.Rect(int(WIDTH * 0.325), int(HEIGHT * 0.20), int(WIDTH * 0.62), int(HEIGHT * 0.70))

    # Rysujemy puste szklane panele na "base"
    draw_glass_panel(base, sidebar_rect, radius=SET_RADIUS, fill_rgba=SET_PANEL_FILL, stroke_rgba=SET_PANEL_STROKE, stroke_w=2)
    draw_glass_panel(base, main_rect, radius=SET_RADIUS, fill_rgba=SET_PANEL_FILL, stroke_rgba=SET_PANEL_STROKE, stroke_w=2)

    # --- SIDEBAR CONTENT ---
    cat_hdr = font_set_hint.render("KATEGORIE", True, SET_DIM).convert_alpha()
    base.blit(cat_hdr, (sidebar_rect.left + int(sidebar_rect.width * 0.08), sidebar_rect.top + int(sidebar_rect.height * 0.08)))

    # Pozycje zakładek
    tab_h = int(sidebar_rect.height * 0.12)
    tab_gap = int(sidebar_rect.height * 0.02)

    r_gen = pygame.Rect(
        sidebar_rect.left + int(sidebar_rect.width * 0.06),
        sidebar_rect.top + int(sidebar_rect.height * 0.18),
        int(sidebar_rect.width * 0.88),
        tab_h
    )
    r_audio = r_gen.copy()
    r_audio.top = r_gen.bottom + tab_gap
    r_ctrl = r_audio.copy()
    r_ctrl.top = r_audio.bottom + tab_gap

    settings_sidebar_general_rect = r_gen
    settings_sidebar_audio_rect = r_audio
    settings_sidebar_controls_rect = r_ctrl

    # Funkcja do generowania tekstu zakładki (aktywna / nieaktywna)
    def make_tab_label(text, active: bool):
        fill = SET_ACCENT if active else SET_DIM
        # Jeśli aktywna, dodajemy styl outline
        if active:
            return render_text_styled(
                font_set_label, text,
                fill=fill,
                outline=(50, 55, 40),
                outline_px=3,
                shadow=(25, 18, 12),
                shadow_offset=(3, 3)
            )
        else:
            return font_set_label.render(text, True, fill).convert_alpha()

    tab_audio_sel = make_tab_label("AUDIO", True)
    tab_audio_unsel = make_tab_label("AUDIO", False)
    tab_ctrl_sel = make_tab_label("STEROWANIE", True)
    tab_ctrl_unsel = make_tab_label("STEROWANIE", False)
    tab_gen_sel = make_tab_label("OGOLNE", True)
    tab_gen_unsel = make_tab_label("OGOLNE", False)

    # --- MAIN CONTENT HEADERS ---
    def make_header(text):
        h1 = render_text_styled(
            font_set_h1, text,
            fill=SET_ACCENT2,
            outline=(60, 64, 44),
            outline_px=5,
            shadow=(25, 18, 12),
            shadow_offset=(5, 5)
        )
        return h1

    hdr_general = make_header("USTAWIENIA OGOLNE")

    hdr_audio = make_header("USTAWIENIA DŹWIĘKU")
    hdr_ctrl = make_header("STEROWANIE POSTACIĄ")

    # --- AUDIO ELEMENTS ---
    # Suwak będzie wycentrowany w Main Panelu
    # Label
    sound_label = font_set_label.render("DŹWIĘK SKOKU", True, SET_MUTED).convert_alpha()

    # Toggle Rect (mniejszy)
    tog_w = int(main_rect.width * 0.34)
    tog_h = int(main_rect.height * 0.055)
    tog_w = max(210, tog_w)
    tog_h = max(26, tog_h)

    tog = pygame.Rect(0, 0, tog_w, tog_h)
    tog.centerx = main_rect.centerx
    tog.centery = main_rect.centery + int(main_rect.height * 0.05)

    settings_toggle_rect = tog
    # Cały wiersz dla hit boxa (opcjonalnie)
    settings_sound_row_rect = tog.inflate(16, 16)

    sound_status_on = font_set_hint.render("WŁĄCZONY", True, SET_TOGGLE_ON).convert_alpha()
    sound_status_off = font_set_hint.render("WYŁĄCZONY", True, SET_TOGGLE_OFF).convert_alpha()

    timer_label = font_set_label.render("ODLICZANIE DO NASTEPNEGO TLA", True, SET_MUTED).convert_alpha()

    timer_tog = pygame.Rect(0, 0, tog_w, tog_h)
    timer_tog.centerx = main_rect.centerx
    timer_tog.centery = main_rect.centery + int(main_rect.height * 0.05)

    settings_timer_toggle_rect = timer_tog
    settings_timer_row_rect = timer_tog.inflate(16, 16)

    timer_status_on = font_set_hint.render("WLACZONY", True, SET_TOGGLE_ON).convert_alpha()
    timer_status_off = font_set_hint.render("WYLACZONY", True, SET_TOGGLE_OFF).convert_alpha()

    # --- CONTROLS ELEMENTS ---
    # Grupa przycisków
    grp_w = int(main_rect.width * 0.80)
    grp_h = int(main_rect.height * 0.12)
    grp_w = max(320, grp_w)
    grp_h = max(50, grp_h)

    grp = pygame.Rect(0, 0, grp_w, grp_h)
    grp.centerx = main_rect.centerx
    grp.centery = main_rect.centery

    # 3 przyciski w grupie
    gap = 15
    btn_w = (grp.width - gap * 2) // 3
    btns = []
    x = grp.left
    for i in range(3):
        r = pygame.Rect(x, grp.top, btn_w, grp.height)
        btns.append(r)
        x += btn_w + gap

    settings_control_btn_rects = btns

    btn_text_sel = {}
    btn_text_unsel = {}
    for key, label in SET_CONTROL_OPTIONS:
        btn_text_sel[key] = font_set_hint.render(label, True, (255, 255, 255)).convert_alpha()
        btn_text_unsel[key] = font_set_hint.render(label, True, (220, 220, 235)).convert_alpha()

    # --- BOTTOM HINT ---
    hint = font_set_hint.render("WROC DO MENU", True, (220, 220, 235)).convert_alpha()
    hint_pos = (int(WIDTH * 0.06), int(HEIGHT * 0.93))
    base.blit(hint, hint_pos)
    hint_rect = pygame.Rect(hint_pos[0], hint_pos[1], hint.get_width(), hint.get_height())
    settings_back_rect = hint_rect

    _settings_cache.update({
        "bg_base": base,
        "sidebar_rect": sidebar_rect,
        "main_rect": main_rect,

        "tab_audio_sel": tab_audio_sel,
        "tab_audio_unsel": tab_audio_unsel,
        "tab_ctrl_sel": tab_ctrl_sel,
        "tab_ctrl_unsel": tab_ctrl_unsel,
        "tab_gen_sel": tab_gen_sel,
        "tab_gen_unsel": tab_gen_unsel,

        "hdr_audio": hdr_audio,
        "hdr_ctrl": hdr_ctrl,
        "hdr_general": hdr_general,

        "sound_label": sound_label,
        "sound_status_on": sound_status_on,
        "sound_status_off": sound_status_off,
        "timer_label": timer_label,
        "timer_status_on": timer_status_on,
        "timer_status_off": timer_status_off,

        "btn_text_sel": btn_text_sel,
        "btn_text_unsel": btn_text_unsel,
        "hint_rect": hint_rect
    })

def _draw_pretty_slider(dst: pygame.Surface, rect: pygame.Rect, t: float, hovered: bool):
    t = clamp(t, 0.0, 1.0)
    r = rect.height // 2

    # Baza
    track = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(track, (255, 255, 255, 50), track.get_rect(), border_radius=r)
    pygame.draw.rect(track, (0, 0, 0, 60), track.get_rect(), width=2, border_radius=r)
    dst.blit(track, rect.topleft)

    # Fill
    fill_w = int(rect.width * t)
    if fill_w > r:
        fill_rect = rect.copy()
        fill_rect.width = fill_w
        tmp_fill = pygame.Surface((fill_w, rect.height), pygame.SRCALPHA)
        col = (44, 220, 140, 160 if hovered else 140)
        pygame.draw.rect(tmp_fill, col, tmp_fill.get_rect(), border_radius=r)
        dst.blit(tmp_fill, rect.topleft)

    # Gałka
    cx = int(_lerp(rect.left + r, rect.right - r, t))
    cy = rect.centery
    knob_r = max(6, int(rect.height * 0.42))

    # Glow gałki
    if hovered:
        pygame.draw.circle(dst, (44, 220, 140, 60), (cx, cy), knob_r + 5)

    # Cień
    pygame.draw.circle(dst, (0,0,0,80), (cx+2, cy+2), knob_r)
    # Ring
    pygame.draw.circle(dst, (255,255,255,255), (cx, cy), knob_r)
    # Środek
    pygame.draw.circle(dst, (44, 220, 140) if t > 0.1 else (200,200,200), (cx, cy), knob_r - 3)

def _draw_segment_button(dst: pygame.Surface, rect: pygame.Rect, selected: bool, hovered: bool):
    radius = 12
    if selected:
        fill = (44, 220, 140, 130 if not hovered else 155)
        stroke = (44, 220, 140, 200 if not hovered else 255)
    else:
        fill = (255, 255, 255, 18 if not hovered else 30)
        stroke = (0, 0, 0, 70 if not hovered else 90)

    tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(tmp, fill, tmp.get_rect(), border_radius=radius)
    pygame.draw.rect(tmp, stroke, tmp.get_rect(), width=2, border_radius=radius)
    dst.blit(tmp, rect.topleft)

def _draw_sidebar_tab(dst: pygame.Surface, rect: pygame.Rect, label_surf: pygame.Surface, active: bool, hovered: bool):
    # Tło zakładki
    if active:
        _draw_rounded_rect_alpha(dst, rect, (255, 255, 255, 25), radius=14)
        # Glow
        glow = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 225, 120, 20), glow.get_rect(), border_radius=14)
        dst.blit(glow, rect.topleft)
    elif hovered:
        _draw_rounded_rect_alpha(dst, rect, (255, 255, 255, 12), radius=14)

    # Tekst
    lr = label_surf.get_rect(midleft=(rect.left + int(rect.width * 0.12), rect.centery))
    dst.blit(label_surf, lr.topleft)

def compose_settings_frame(mouse_pos, dt_ms: int):
    global toggle_anim, jump_sound_enabled, jump_key_mode, bg_timer_toggle_anim, bg_timer_enabled
    global _settings_frame, _settings_just_entered
    global settings_active_tab

    if _settings_cache["bg_base"] is None:
        _build_settings_cache()

    if _settings_frame is None:
        _settings_frame = pygame.Surface((WIDTH, HEIGHT)).convert()

    mx, my = mouse_pos
    surf = _settings_frame
    surf.blit(_settings_cache["bg_base"], (0, 0))

    main_rect = _settings_cache["main_rect"]

    # --- SIDEBAR LOGIC ---
    # Rysujemy przyciski zakładek
    hov_gen = settings_sidebar_general_rect.collidepoint(mx, my)
    hov_audio = settings_sidebar_audio_rect.collidepoint(mx, my)
    hov_ctrl = settings_sidebar_controls_rect.collidepoint(mx, my)

    # General Tab Button
    _draw_sidebar_tab(
        surf, settings_sidebar_general_rect,
        _settings_cache["tab_gen_sel"] if settings_active_tab == 2 else _settings_cache["tab_gen_unsel"],
        active=(settings_active_tab == 2), hovered=hov_gen
    )

    # Audio Tab Button
    _draw_sidebar_tab(
        surf, settings_sidebar_audio_rect,
        _settings_cache["tab_audio_sel"] if settings_active_tab == 0 else _settings_cache["tab_audio_unsel"],
        active=(settings_active_tab == 0), hovered=hov_audio
    )

    # Controls Tab Button
    _draw_sidebar_tab(
        surf, settings_sidebar_controls_rect,
        _settings_cache["tab_ctrl_sel"] if settings_active_tab == 1 else _settings_cache["tab_ctrl_unsel"],
        active=(settings_active_tab == 1), hovered=hov_ctrl
    )
    # --- MAIN CONTENT LOGIC ---
    if settings_active_tab == 0:
        # === AUDIO TAB ===
        # Header
        h = _settings_cache["hdr_audio"]
        hr = h.get_rect(topleft=(main_rect.left + int(main_rect.width * 0.07), main_rect.top + int(main_rect.height * 0.08)))
        surf.blit(h, hr.topleft)
        draw_divider(surf, main_rect.left + 30, main_rect.right - 30, hr.bottom + 20)

        # Content: Slider
        label = _settings_cache["sound_label"]

        tog = settings_toggle_rect
        label_gap = max(18, int(main_rect.height * 0.06))
        lr = label.get_rect(center=(main_rect.centerx, tog.top - label_gap))
        surf.blit(label, lr.topleft)

        hov_tog = tog.collidepoint(mx, my)

        # Animacja suwaka
        target = 1.0 if jump_sound_enabled else 0.0
        if _settings_just_entered:
            toggle_anim = target
        else:
            step = clamp(dt_ms / 120.0, 0.0, 1.0)
            toggle_anim = toggle_anim + (target - toggle_anim) * step

        t = smoothstep(toggle_anim)
        _draw_pretty_slider(surf, tog, t, hov_tog)

        # Status text
        st = _settings_cache["sound_status_on"] if jump_sound_enabled else _settings_cache["sound_status_off"]
        status_gap = max(16, int(main_rect.height * 0.05))
        sr = st.get_rect(center=(tog.centerx, tog.bottom + status_gap))
        surf.blit(st, sr.topleft)

    elif settings_active_tab == 1:
        # === CONTROLS TAB ===
        # Header
        h = _settings_cache["hdr_ctrl"]
        hr = h.get_rect(topleft=(main_rect.left + int(main_rect.width * 0.07), main_rect.top + int(main_rect.height * 0.08)))
        surf.blit(h, hr.topleft)
        draw_divider(surf, main_rect.left + 30, main_rect.right - 30, hr.bottom + 20)

        # Content: Buttons
        for i, (key, label) in enumerate(SET_CONTROL_OPTIONS):
            br = settings_control_btn_rects[i]
            hov = br.collidepoint(mx, my)
            sel = (jump_key_mode == key)

            _draw_segment_button(surf, br, selected=sel, hovered=hov)

            txt = _settings_cache["btn_text_sel"][key] if sel else _settings_cache["btn_text_unsel"][key]
            tr = txt.get_rect(center=br.center)
            surf.blit(txt, tr.topleft)

    else:
        # === GENERAL TAB ===
        # Header
        h = _settings_cache["hdr_general"]
        hr = h.get_rect(topleft=(main_rect.left + int(main_rect.width * 0.07), main_rect.top + int(main_rect.height * 0.08)))
        surf.blit(h, hr.topleft)
        draw_divider(surf, main_rect.left + 30, main_rect.right - 30, hr.bottom + 20)

        # Content: Slider
        label = _settings_cache["timer_label"]

        tog = settings_timer_toggle_rect
        label_gap = max(18, int(main_rect.height * 0.06))
        lr = label.get_rect(center=(main_rect.centerx, tog.top - label_gap))
        surf.blit(label, lr.topleft)

        hov_tog = tog.collidepoint(mx, my)

        # Animacja suwaka
        target = 1.0 if bg_timer_enabled else 0.0
        if _settings_just_entered:
            bg_timer_toggle_anim = target
        else:
            step = clamp(dt_ms / 120.0, 0.0, 1.0)
            bg_timer_toggle_anim = bg_timer_toggle_anim + (target - bg_timer_toggle_anim) * step

        t = smoothstep(bg_timer_toggle_anim)
        _draw_pretty_slider(surf, tog, t, hov_tog)

        # Status text
        st = _settings_cache["timer_status_on"] if bg_timer_enabled else _settings_cache["timer_status_off"]
        status_gap = max(16, int(main_rect.height * 0.05))
        sr = st.get_rect(center=(tog.centerx, tog.bottom + status_gap))
        surf.blit(st, sr.topleft)

    if _settings_just_entered:
        _settings_just_entered = False

    return surf


# =====================
# SYSTEM FADE
# =====================
fade_from = None
fade_to = None
fade_start_ms = 0
fade_duration_ms = 0
fade_next_state = None

def start_fade(now_ms: int, from_surf: pygame.Surface, to_surf: pygame.Surface,
               duration_ms: int, next_state: str):
    global fade_from, fade_to, fade_start_ms, fade_duration_ms, fade_next_state
    fade_from = from_surf.convert_alpha()
    fade_to = to_surf.convert_alpha()
    fade_start_ms = now_ms
    fade_duration_ms = max(1, duration_ms)
    fade_next_state = next_state

def begin_countdown(now_ms: int, from_surf: pygame.Surface):
    global state, countdown_start_ms, countdown_bg_frame
    countdown_start_ms = None
    countdown_bg_frame = make_countdown_base_frame(0)
    start_fade(now_ms, from_surf, countdown_bg_frame, FADE_BG_TO_COUNTDOWN_MS, STATE_COUNTDOWN)
    state = STATE_FADE_BG_COUNTDOWN

def draw_fade(now_ms: int):
    elapsed = now_ms - fade_start_ms
    t = smoothstep(elapsed / fade_duration_ms)

    a_to = int(255 * t)
    a_from = int(255 * (1.0 - t))

    fade_from.set_alpha(a_from)
    fade_to.set_alpha(a_to)

    screen.fill((0, 0, 0))
    screen.blit(fade_from, (0, 0))
    screen.blit(fade_to, (0, 0))

    return elapsed >= fade_duration_ms

# =====================
# STANY
# =====================
STATE_INTRO = "intro"
STATE_FADE_INTRO_MENU = "fade_intro_menu"
STATE_MENU = "menu"
STATE_SETTINGS = "settings"   # <<< ustawienia
STATE_FADE_MENU_SETTINGS = "fade_menu_settings"
STATE_FADE_SETTINGS_MENU = "fade_settings_menu"
STATE_FADE_MENU_LOAD = "fade_menu_load"
STATE_LOAD = "load"
STATE_FADE_LOAD_BG = "fade_load_bg"
STATE_COUNTDOWN = "countdown"
STATE_BG = "bg_cycle"
STATE_PAUSED = "paused"
STATE_GAME_OVER = "game_over"
STATE_EXIT_CONFIRM = "exit_confirm"
STATE_FADE_BG_COUNTDOWN = "fade_bg_countdown"
STATE_FADE_BG_MENU = "fade_bg_menu"

state = STATE_INTRO
intro_start_ms = pygame.time.get_ticks()
load_start_ms = None
pause_started_ms = None
countdown_start_ms = None
exit_confirm_prev_state = None
exit_confirm_frame = None
exit_confirm_started_ms = None
esc_exit_press_count = 0
esc_exit_last_press_ms = None

menu_frame_surface = menu_surface_static
menu_item_rects_dynamic = menu_item_rects_static
menu_hovered_index = -1

# ustawienia: cache ostatniej klatki
settings_frame_surface = None

def set_hand_cursor(is_hand: bool):
    return

# =====================
# BG (bg1->bg8) - zmienne stanu
# =====================
bg_index = 0
bg_switch_start_ms = None

bg_scroll_num = 0
bg_speed_micro_per_sec = int(BG_SCROLL_PX_PER_SEC * 1_000_000)
PIX_DEN = 1_000_000_000

# =====================
# PĘTLA GŁÓWNA
# =====================
running = True
while running:
    if vsync_enabled:
        dt = clock.tick()
    else:
        dt = clock.tick_busy_loop(TARGET_FPS_NO_VSYNC)

    now = pygame.time.get_ticks()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            save_user_settings()
            running = False

        # ESC: w grze pauza, poza gra 3x aby pokazac wyjscie
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if state == STATE_BG:
                reset_exit_confirm_presses()
                pause_started_ms = now
                state = STATE_PAUSED
                pause_menu_hover_t = [0.0 for _ in pause_menu_cache["option_rects"]]
            elif state == STATE_SETTINGS:
                reset_exit_confirm_presses()
                save_user_settings()
                from_s = settings_frame_surface
                if from_s is None:
                    _settings_just_entered = True
                    from_s = compose_settings_frame(pygame.mouse.get_pos(), 0)
                start_fade(now, from_s, menu_surface_static, FADE_SETTINGS_TO_MENU_MS, STATE_MENU)
                state = STATE_FADE_SETTINGS_MENU
            elif state in (STATE_FADE_MENU_SETTINGS, STATE_FADE_SETTINGS_MENU):
                reset_exit_confirm_presses()
                pass
            elif state == STATE_EXIT_CONFIRM:
                resume_from_exit_confirm(now)
            else:
                if register_exit_confirm_press(now):
                    enter_exit_confirm(now)

        if state == STATE_BG and event.type == pygame.KEYDOWN and event.key == current_jump_key():
            if dino_on_ground:
                dino_vy = -DINO_JUMP_VEL_PX_PER_S
                dino_on_ground = False
                if jump_sound is not None and jump_sound_enabled:
                    try:
                        jump_sound.play()
                    except Exception:
                        pass

        if state == STATE_BG and event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            pause_started_ms = now
            state = STATE_PAUSED
            pause_menu_hover_t = [0.0 for _ in pause_menu_cache["option_rects"]]

        if state == STATE_BG and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if pause_button_rect.collidepoint(event.pos):
                pause_started_ms = now
                state = STATE_PAUSED
                pause_menu_hover_t = [0.0 for _ in pause_menu_cache["option_rects"]]

        if state == STATE_PAUSED and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if pause_menu_cache["option_rects"][0].collidepoint(mx, my):
                resume_from_pause(now)
                state = STATE_BG
            elif pause_menu_cache["option_rects"][1].collidepoint(mx, my):
                pause_started_ms = None
                frame = capture_game_frame(now, include_hud=False)
                begin_countdown(now, frame)
            elif pause_menu_cache["option_rects"][2].collidepoint(mx, my):
                pause_started_ms = None
                frame = capture_game_frame(now, include_hud=False)
                start_fade(now, frame, menu_surface_static, FADE_BG_TO_MENU_MS, STATE_MENU)
                state = STATE_FADE_BG_MENU

        if state == STATE_GAME_OVER and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if game_over_menu_cache["option_rects"][0].collidepoint(mx, my):
                frame = capture_game_frame(now, include_hud=False)
                begin_countdown(now, frame)
            elif game_over_menu_cache["option_rects"][1].collidepoint(mx, my):
                frame = capture_game_frame(now, include_hud=False)
                start_fade(now, frame, menu_surface_static, FADE_BG_TO_MENU_MS, STATE_MENU)
                state = STATE_FADE_BG_MENU

        if state == STATE_EXIT_CONFIRM and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if exit_confirm_cache["option_rects"][0].collidepoint(mx, my):
                save_user_settings()
                running = False
            elif exit_confirm_cache["option_rects"][1].collidepoint(mx, my):
                resume_from_exit_confirm(now)
            continue

        if state == STATE_MENU and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            if menu_item_rects_dynamic[2].collidepoint(mx, my):
                save_user_settings()
                running = False

            elif menu_item_rects_dynamic[0].collidepoint(mx, my):
                start_fade(now, menu_frame_surface, load_surface, FADE_MENU_TO_LOAD_MS, STATE_LOAD)
                state = STATE_FADE_MENU_LOAD
                load_start_ms = None

            elif menu_item_rects_dynamic[1].collidepoint(mx, my):
                # >>> ładne przejście do ustawień
                _settings_just_entered = True
                settings_active_tab = 2 # reset na Ogolne
                preview = compose_settings_frame(pygame.mouse.get_pos(), dt)
                start_fade(now, menu_frame_surface, preview, FADE_MENU_TO_SETTINGS_MS, STATE_SETTINGS)
                state = STATE_FADE_MENU_SETTINGS

        if state == STATE_SETTINGS and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # 1. Obsługa paska bocznego (zakładki)
            if settings_sidebar_general_rect.collidepoint(mx, my):
                settings_active_tab = 2
            elif settings_sidebar_audio_rect.collidepoint(mx, my):
                settings_active_tab = 0
            elif settings_sidebar_controls_rect.collidepoint(mx, my):
                settings_active_tab = 1

            # 2. Obsługa zawartości w zależności od zakładki
            elif settings_active_tab == 0:
                # AUDIO TAB - tylko suwak
                if settings_toggle_rect.collidepoint(mx, my) or settings_sound_row_rect.collidepoint(mx, my):
                    jump_sound_enabled = not jump_sound_enabled
                    save_user_settings()

            elif settings_active_tab == 1:
                # CONTROLS TAB - tylko przyciski wyboru
                for i, (key, _label) in enumerate(SET_CONTROL_OPTIONS):
                    if settings_control_btn_rects[i].collidepoint(mx, my):
                        jump_key_mode = key
                        save_user_settings()
                        break

            # 3. Powrót (Hint na dole)
            elif settings_active_tab == 2:
                # GENERAL TAB - tylko suwak
                if settings_timer_toggle_rect.collidepoint(mx, my) or settings_timer_row_rect.collidepoint(mx, my):
                    bg_timer_enabled = not bg_timer_enabled
                    save_user_settings()

            if settings_back_rect.collidepoint(mx, my):
                save_user_settings()
                from_s = settings_frame_surface
                if from_s is None:
                    _settings_just_entered = True
                    from_s = compose_settings_frame(pygame.mouse.get_pos(), 0)
                start_fade(now, from_s, menu_surface_static, FADE_SETTINGS_TO_MENU_MS, STATE_MENU)
                state = STATE_FADE_SETTINGS_MENU

    if LOCK_WINDOW_POS and fixed_pos is not None:
        try:
            if pygame.display.get_window_position() != fixed_pos:
                pygame.display.set_window_position(*fixed_pos)
        except Exception:
            _set_window_position_win32(*fixed_pos)

    # =====================
    # LOGIKA STANÓW
    # =====================
    if state == STATE_INTRO:
        if now - intro_start_ms >= INTRO_DURATION_MS:
            start_fade(now, intro_bg, menu_surface_static, FADE_INTRO_TO_MENU_MS, STATE_MENU)
            state = STATE_FADE_INTRO_MENU

    elif state == STATE_LOAD:
        if load_start_ms is None:
            load_start_ms = now
        if now - load_start_ms >= LOAD_DURATION_MS:
            speed_mult = 1.0
            apply_speed_to_systems(rescale_existing=False)

            bg_index = 0
            bg_switch_start_ms = None
            bg_scroll_num = 0
            snap_dino_to_ground(bg_index)

            obstacles.reset(bg_index, now, dino_safe_right_px=dino_safe_right_px(), start_visible=True)

            first_bg_frame = make_scrolling_bg_frame(bg_sequence[0], 0)
            start_fade(now, load_surface, first_bg_frame, FADE_LOAD_TO_BG_MS, STATE_BG)
            state = STATE_FADE_LOAD_BG

    elif state == STATE_COUNTDOWN:
        if countdown_start_ms is None:
            countdown_start_ms = now
        if countdown_bg_frame is None:
            countdown_bg_frame = make_countdown_base_frame(0)
        if now - countdown_start_ms >= COUNTDOWN_DURATION_MS:
            speed_mult = 1.0
            apply_speed_to_systems(rescale_existing=False)

            bg_index = 0
            bg_switch_start_ms = now
            bg_scroll_num = 0
            snap_dino_to_ground(bg_index)

            obstacles.reset(bg_index, now, dino_safe_right_px=dino_safe_right_px(), start_visible=True)

            countdown_start_ms = None
            state = STATE_BG

    elif state == STATE_BG:
        if bg_switch_start_ms is None:
            bg_switch_start_ms = now

        if now - bg_switch_start_ms >= BG_SWITCH_EVERY_MS:
            speed_mult = min(LEVEL_SPEED_CAP_MULT, speed_mult * (1.0 + LEVEL_SPEED_INCREASE))
            apply_speed_to_systems(rescale_existing=True)

            bg_index = (bg_index + 1) % len(bg_sequence)
            bg_switch_start_ms = now
            bg_scroll_num = 0

            obstacles.on_bg_change(bg_index, now, dino_safe_right_px=dino_safe_right_px())

            if dino_on_ground:
                snap_dino_to_ground(bg_index)
            else:
                resolve_dino_vs_ground(bg_index)

        dt_ms = min(dt, MAX_DT_MS_FOR_SCROLL)
        dt_s = dt_ms / 1000.0

        gy = get_ground_y_for_bg(bg_index)

        dino_vy += DINO_GRAVITY_PX_PER_S2 * dt_s
        dino_y += dino_vy * dt_s

        if dino_y + dino_img.get_height() >= gy:
            dino_y = float(gy - dino_img.get_height())
            dino_vy = 0.0
            dino_on_ground = True
        else:
            dino_on_ground = False

        w = bg_sequence[bg_index].get_width()
        if w > 0:
            mod = w * PIX_DEN
            bg_scroll_num = (bg_scroll_num + bg_speed_micro_per_sec * dt_ms) % mod

        obstacles.update(
            dt_ms=dt_ms,
            ground_y=gy,
            bg_idx=bg_index,
            now_ms=now,
            dino_safe_right_px=dino_safe_right_px(),
            baseline_offset_px=DINO_BOTTOM_PAD_PX
        )

        dx, dy = dino_draw_pos()
        dino_hit = dino_hit_rect_world()
        if obstacles.collides_mask(
            dino_mask=dino_mask,
            dino_topleft=(dx, dy),
            dino_hit_rect=dino_hit,
            min_overlap_pixels=MIN_OVERLAP_PIXELS
        ):
            state = STATE_GAME_OVER
            game_over_hover_t = [0.0 for _ in game_over_menu_cache["option_rects"]]

    # =====================
    # RYSOWANIE
    # =====================
    if state == STATE_INTRO:
        screen.blit(intro_bg, (0, 0))
        set_hand_cursor(False)

    elif state == STATE_MENU:
        menu_frame_surface, menu_item_rects_dynamic, menu_hovered_index = compose_menu_frame(
            pygame.mouse.get_pos(), dt
        )
        screen.blit(menu_frame_surface, (0, 0))
        set_hand_cursor(menu_hovered_index != -1)

    elif state == STATE_SETTINGS:
        settings_frame_surface = compose_settings_frame(pygame.mouse.get_pos(), dt)
        screen.blit(settings_frame_surface, (0, 0))

    elif state == STATE_COUNTDOWN:
        set_hand_cursor(False)
        if countdown_bg_frame is None:
            countdown_bg_frame = make_countdown_base_frame(0)
        screen.blit(countdown_bg_frame, (0, 0))
        if countdown_start_ms is None:
            seconds_left = COUNTDOWN_SECONDS
        else:
            elapsed_ms = max(0, now - countdown_start_ms)
            seconds_left = COUNTDOWN_SECONDS - (elapsed_ms // 1000)
            seconds_left = max(1, min(COUNTDOWN_SECONDS, int(seconds_left)))
        surf = countdown_surfs.get(int(seconds_left))
        if surf is not None:
            rect = surf.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(surf, rect.topleft)

    elif state == STATE_PAUSED:
        set_hand_cursor(False)
        draw_game_world(screen)
        draw_overlay_menu_animated(screen, pause_menu_cache, pygame.mouse.get_pos(), dt, pause_menu_hover_t)

    elif state == STATE_GAME_OVER:
        set_hand_cursor(False)
        draw_game_world(screen)
        draw_overlay_menu_animated(screen, game_over_menu_cache, pygame.mouse.get_pos(), dt, game_over_hover_t)

    elif state == STATE_EXIT_CONFIRM:
        set_hand_cursor(False)
        if exit_confirm_frame is not None:
            screen.blit(exit_confirm_frame, (0, 0))
        else:
            screen.fill((0, 0, 0))
        draw_overlay_menu(screen, exit_confirm_cache, pygame.mouse.get_pos())

    elif state in (
        STATE_FADE_INTRO_MENU,
        STATE_FADE_MENU_LOAD,
        STATE_FADE_MENU_SETTINGS,
        STATE_FADE_SETTINGS_MENU,
        STATE_FADE_LOAD_BG,
        STATE_FADE_BG_COUNTDOWN,
        STATE_FADE_BG_MENU,
    ):
        set_hand_cursor(False)
        done = draw_fade(now)
        if done:
            state = fade_next_state
            if state == STATE_LOAD:
                load_start_ms = now
            if state == STATE_SETTINGS:
                _settings_just_entered = True
            if state == STATE_COUNTDOWN:
                countdown_start_ms = now
            if state == STATE_BG:
                bg_switch_start_ms = now
                bg_scroll_num = 0
                snap_dino_to_ground(bg_index)
                obstacles.reset(bg_index, now, dino_safe_right_px=dino_safe_right_px(), start_visible=True)

    elif state == STATE_LOAD:
        set_hand_cursor(False)
        screen.blit(load_surface, (0, 0))

        if load_start_ms is None:
            progress = 0.0
        else:
            progress = (now - load_start_ms) / float(LOAD_DURATION_MS)
            progress = max(0.0, min(1.0, progress))

        draw_progress_bar(screen, progress, now_ms=now)

    elif state == STATE_BG:
        set_hand_cursor(False)
        draw_game_world(screen)
        draw_bg_timer(screen, now)
        pause_hovered = pause_button_rect.collidepoint(pygame.mouse.get_pos())
        draw_pause_button(screen, hovered=pause_hovered)

    # =====================
    # RYSUJ WŁASNY KURSOR NA WIERZCHU
    # =====================
    if cursor_img is not None:
        mx, my = pygame.mouse.get_pos()
        hx, hy = cursor_hotspot
        screen.blit(cursor_img, (mx - hx, my - hy))

    pygame.display.flip()

# utrwal ustawienia przy zamykaniu gry
save_user_settings()
pygame.quit()
sys.exit()

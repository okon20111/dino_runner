# render.py
import os
import glob
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import pygame


@dataclass
class Variant:
    img: pygame.Surface
    mask: pygame.mask.Mask
    bounds: pygame.Rect
    foot_bottom: int

    # warstwy renderu
    ground_shadow_img: Optional[pygame.Surface]
    ground_shadow_offset: Tuple[int, int]

    soft_shadow_img: Optional[pygame.Surface]
    soft_shadow_offset: Tuple[int, int]

    rim_img: Optional[pygame.Surface]

    highlight_img: Optional[pygame.Surface]
    highlight_offset: Tuple[int, int]


@dataclass
class Obstacle:
    img: pygame.Surface
    mask: pygame.mask.Mask

    ground_shadow_img: Optional[pygame.Surface]
    ground_shadow_offset: Tuple[int, int]

    soft_shadow_img: Optional[pygame.Surface]
    soft_shadow_offset: Tuple[int, int]

    rim_img: Optional[pygame.Surface]

    highlight_img: Optional[pygame.Surface]
    highlight_offset: Tuple[int, int]

    x: float
    y: float
    speed: float

    draw_rect: pygame.Rect
    hit_rect: pygame.Rect

    bounds: pygame.Rect
    foot_bottom: int

    pinned: bool = True


@dataclass
class SpawnSpec:
    gap_scale: float = 1.0
    size_bias: float = 1.0
    speed_scale: float = 1.0
    prefer_narrow: bool = False


class ObstacleManager:
    # --- bezpieczniki układania (fix na ogromne odstępy na starcie poziomu) ---
    START_FIRST_SPAWN_MIN_MS = 300
    START_FIRST_SPAWN_MAX_MS = 520

    # anti-catchup: maksymalny horyzont liczenia (sekundy)
    CATCHUP_HORIZON_S = 1.25

    # maksymalny gap (żeby nigdy nie było „pustyni” na pół ekranu)
    MAX_GAP_FRAC_OF_SCREEN = 0.34
    EXTRA_GAP_FRAC = 0.22
    # Per level difficulty bump (background change).
    LEVEL_DIFFICULTY_BONUS_STEP = 0.09
    LEVEL_DIFFICULTY_BONUS_CAP = 0.40
    MAX_DIFFICULTY = 1.35

    def __init__(
        self,
        screen_size: Tuple[int, int],
        dino_height_px: int,
        obstacle_dir: str = "assets/obstacles",
        base_speed_px_per_sec: float = 230.0,
        seed: Optional[int] = None,
        mask_alpha_threshold: int = 50,
        jump_vel_px_per_s: Optional[float] = None,
        gravity_px_per_s2: Optional[float] = None,
    ):
        self.sw, self.sh = int(screen_size[0]), int(screen_size[1])
        self.dino_h = max(1, int(dino_height_px))
        self.obstacle_dir = obstacle_dir
        self.base_speed = float(base_speed_px_per_sec)

        # Powiększ przeszkody trochę bardziej
        self.obstacle_scale = 1.16
        # Per-obstacle scale tweaks (filename -> multiplier).
        self.obstacle_scale_overrides = {
            "bg3_obs1.png": 1.10,
            "bg4_obs1.png": 1.15,
            "bg5_obs1.png": 1.20,
            "bg6_obs1.png": 1.25,
        }
        self.raw_paths: Dict[int, List[str]] = {}

        self.rng = random.Random(seed)
        self.alpha_thr = int(mask_alpha_threshold)
        self.jump_vel = None if jump_vel_px_per_s is None else float(jump_vel_px_per_s)
        self.gravity = None if gravity_px_per_s2 is None else float(gravity_px_per_s2)

        self.raw_bank: Dict[int, List[pygame.Surface]] = self._load_raw_bank()
        self.base_bank: Dict[int, List[pygame.Surface]] = self._build_base_bank()
        self._variant_cache: Dict[Tuple[int, int, int], Variant] = {}

        self.bg_idx = 0
        self.obstacles: List[Obstacle] = []
        self.recent_img_idx: List[int] = []

        self.elapsed_ms = 0
        self.difficulty = 0.0
        self.level_bonus = 0.0
        self.next_spawn_ms = 0
        self.pattern_cooldown_ms = 0
        self.last_pattern_name = ""

    # ---------- public: speed update ----------
    def set_base_speed(self, new_base_speed: float, rescale_existing: bool = True):
        new_base_speed = float(new_base_speed)
        old = float(self.base_speed) if self.base_speed > 0 else new_base_speed
        self.base_speed = new_base_speed

        if rescale_existing and old > 0:
            ratio = new_base_speed / old
            for ob in self.obstacles:
                ob.speed *= ratio

    # ---------- helpers ----------
    @staticmethod
    def _union_rects(rects: List[pygame.Rect], fallback: pygame.Rect) -> pygame.Rect:
        if not rects:
            return fallback
        u = rects[0].copy()
        for r in rects[1:]:
            u.union_ip(r)
        return u

    def _make_hit_rect(self, x: float, y: float, bounds: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(int(x + bounds.left), int(y + bounds.top), int(bounds.width), int(bounds.height))

    def _pin_y_to_baseline(self, baseline_y: int, foot_bottom: int) -> float:
        return float(int(baseline_y - foot_bottom))

    # ---------- tiny blur helper ----------
    @staticmethod
    def _cheap_blur(surf: pygame.Surface, scale: float = 0.45) -> pygame.Surface:
        w, h = surf.get_size()
        if w < 2 or h < 2:
            return surf
        w2 = max(1, int(w * scale))
        h2 = max(1, int(h * scale))
        small = pygame.transform.smoothscale(surf, (w2, h2))
        return pygame.transform.smoothscale(small, (w, h))

    # ---------- render layers ----------
    def _build_ground_shadow(
        self, img: pygame.Surface, bounds: pygame.Rect, foot_bottom: int
    ) -> Tuple[Optional[pygame.Surface], Tuple[int, int]]:
        """Subtelny cień kontaktu z ziemią (bez krzykliwych kółek)."""
        w = max(10, int(bounds.width * 0.88))
        h = max(6, int(bounds.height * 0.16))

        # jeśli sprite jest bardzo wąski – nie rób cienia
        if w < 12 or h < 6:
            return None, (0, 0)

        shadow = pygame.Surface((w, h), pygame.SRCALPHA)

        # elipsa, ale spłaszczona + mocno miękka
        pygame.draw.ellipse(shadow, (0, 0, 0, 65), shadow.get_rect())
        shadow = self._cheap_blur(shadow, scale=0.38)

        # offset względem (x,y) przeszkody
        # centrowanie pod bounds
        ox = int(bounds.left + (bounds.width - w) * 0.5)
        # cień leży na baseline -> foot_bottom
        oy = int(foot_bottom - (h // 2))

        return shadow, (ox, oy)

    def _build_soft_shadow(
        self, img: pygame.Surface, mask: pygame.mask.Mask
    ) -> Tuple[Optional[pygame.Surface], Tuple[int, int]]:
        """Miękki cień sylwetki ZA przeszkodą."""
        w, h = img.get_size()
        if w <= 2 or h <= 2:
            return None, (0, 0)

        base = mask.to_surface(
            setcolor=(0, 0, 0, 120),
            unsetcolor=(0, 0, 0, 0)
        ).convert_alpha()

        blur = self._cheap_blur(base, scale=0.35)

        pad = 6
        out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
        out.blit(blur, (pad, pad))

        desired_off = (3, 4)
        return out, (desired_off[0] - pad, desired_off[1] - pad)

    def _build_rim(self, img: pygame.Surface, mask: pygame.mask.Mask) -> Optional[pygame.Surface]:
        outline = mask.outline()
        if len(outline) < 2:
            return None

        rim = pygame.Surface(img.get_size(), pygame.SRCALPHA)
        pygame.draw.lines(rim, (255, 248, 220, 26), True, outline, 3)
        pygame.draw.lines(rim, (255, 248, 220, 55), True, outline, 1)
        return rim

    def _build_highlight(
        self, img: pygame.Surface, mask: pygame.mask.Mask
    ) -> Tuple[Optional[pygame.Surface], Tuple[int, int]]:
        outline = mask.outline()
        if len(outline) < 2:
            return None, (0, 0)

        w, h = img.get_size()
        pad = 4
        out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)

        tmp = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.lines(tmp, (255, 255, 255, 30), True, outline, 2)
        out.blit(tmp, (pad, pad))

        return out, (-pad - 1, -pad - 1)

    def _jump_air_time_s(self) -> Optional[float]:
        if self.jump_vel is None or self.gravity is None or self.gravity <= 0:
            return None
        return (2.0 * self.jump_vel) / self.gravity

    # ---------- scaling ----------
    def _base_target_h(self) -> int:
        target = int(self.dino_h * 0.80 * self.obstacle_scale)
        target = max(18, target)
        target = min(int(self.sh * 0.28), target)
        return target

    def _scale_to_h(self, surf: pygame.Surface, target_h: int) -> pygame.Surface:
        target_h = max(8, int(target_h))
        src_h = max(1, surf.get_height())
        scale = target_h / float(src_h)
        target_w = max(1, int(surf.get_width() * scale))
        return pygame.transform.smoothscale(surf, (target_w, target_h)).convert_alpha()

    # ---------- loading ----------
    def _load_raw_bank(self) -> Dict[int, List[pygame.Surface]]:
        bank: Dict[int, List[pygame.Surface]] = {}
        path_bank: Dict[int, List[str]] = {}
        for i in range(6):
            pat = os.path.join(self.obstacle_dir, f"bg{i+1}_*.png")
            paths = sorted(glob.glob(pat))
            imgs: List[pygame.Surface] = []
            ok_paths: List[str] = []
            for p in paths:
                try:
                    raw = pygame.image.load(p).convert_alpha()
                    imgs.append(raw)
                    ok_paths.append(p)
                except Exception:
                    pass
            bank[i] = imgs
            path_bank[i] = ok_paths
        self.raw_paths = path_bank
        return bank

    def _build_base_bank(self) -> Dict[int, List[pygame.Surface]]:
        base_h = self._base_target_h()
        out: Dict[int, List[pygame.Surface]] = {}
        for bg_idx, raws in self.raw_bank.items():
            out[bg_idx] = [self._scale_to_h(r, base_h) for r in raws]
        return out

    def _get_variant(self, bg_idx: int, img_index: int, target_h: int) -> Variant:
        key = (bg_idx, img_index, int(target_h))
        if key in self._variant_cache:
            return self._variant_cache[key]

        raws = self.raw_bank.get(bg_idx, [])
        if not raws:
            dummy = pygame.Surface((1, 1), pygame.SRCALPHA)
            mask = pygame.mask.from_surface(dummy, self.alpha_thr)
            bounds = dummy.get_rect()
            v = Variant(
                img=dummy,
                mask=mask,
                bounds=bounds,
                foot_bottom=bounds.bottom,
                ground_shadow_img=None,
                ground_shadow_offset=(0, 0),
                soft_shadow_img=None,
                soft_shadow_offset=(0, 0),
                rim_img=None,
                highlight_img=None,
                highlight_offset=(0, 0),
            )
            self._variant_cache[key] = v
            return v

        src = raws[img_index]
        img = self._scale_to_h(src, target_h)

        mask = pygame.mask.from_surface(img, self.alpha_thr)
        rects = mask.get_bounding_rects()
        bounds = self._union_rects(rects, img.get_rect())
        foot_bottom = int(bounds.bottom)

        ground_shadow_img, ground_shadow_offset = None, (0, 0)
        soft_shadow_img, soft_shadow_offset = None, (0, 0)
        rim_img = self._build_rim(img, mask)
        highlight_img, highlight_offset = self._build_highlight(img, mask)

        v = Variant(
            img=img,
            mask=mask,
            bounds=bounds,
            foot_bottom=foot_bottom,
            ground_shadow_img=ground_shadow_img,
            ground_shadow_offset=ground_shadow_offset,
            soft_shadow_img=soft_shadow_img,
            soft_shadow_offset=soft_shadow_offset,
            rim_img=rim_img,
            highlight_img=highlight_img,
            highlight_offset=highlight_offset,
        )
        self._variant_cache[key] = v
        return v

    # ---------- difficulty / speed ----------
    def _update_difficulty(self, dt_ms: int):
        self.elapsed_ms += max(0, int(dt_ms))
        base = min(1.0, self.elapsed_ms / 50000.0)
        bonus = min(self.LEVEL_DIFFICULTY_BONUS_CAP, self.level_bonus)
        self.difficulty = min(self.MAX_DIFFICULTY, base + bonus)

    def _speed_now(self) -> float:
        return self.base_speed * (1.0 + 0.20 * self.difficulty)

    def _spawn_interval_ms(self) -> int:
        t = self.difficulty
        lo = int(900 - 200 * t)
        hi = int(1400 - 300 * t)
        lo = max(600, lo)
        hi = max(lo + 120, hi)
        return self.rng.randint(lo, hi)

    def _gap_px(self, speed: float, tight: bool = False, gap_scale: float = 1.0) -> int:
        base = int(speed * 0.62 + self.dino_h * 0.85)
        t = self.difficulty
        lo = int(base * (0.85 - 0.08 * t))
        hi = int(base * (1.20 - 0.10 * t))
        lo = max(160, lo)
        hi = max(lo + 90, hi)

        gap = self.rng.randint(lo, hi)
        if tight:
            gap = max(140, int(gap * 0.78))
        gap = int(gap * max(0.65, float(gap_scale)))

        min_gap = max(120, int(self.dino_h * 0.90))
        air_time = self._jump_air_time_s()
        if air_time is not None:
            factor = 0.75 if not tight else 0.62
            min_gap = max(min_gap, int(speed * air_time * factor))
        gap = max(min_gap, gap)
        return gap

    # ---------- selection ----------
    def _pick_img_index(self, prefer_narrow: bool = False) -> int:
        pool = self.base_bank.get(self.bg_idx, [])
        if not pool:
            return 0

        widths = [img.get_width() for img in pool]
        w_max = max(1, max(widths))
        w_min = max(1, min(widths))
        weights = []
        for idx, img in enumerate(pool):
            w = img.get_width()
            if w_max == w_min:
                narrow_bias = 0.0
            else:
                narrow_bias = (w_max - w) / float(w_max - w_min)
            weight = 1.0 + 0.6 * narrow_bias
            if prefer_narrow:
                weight *= 1.2 + 0.7 * narrow_bias
            if len(pool) > 1 and idx in self.recent_img_idx:
                weight *= 0.55
            weights.append(weight)

        idx = self.rng.choices(range(len(pool)), weights=weights, k=1)[0]
        if len(pool) > 1:
            self.recent_img_idx.append(idx)
            self.recent_img_idx = self.recent_img_idx[-2:]
        return idx

    def _pick_variant_h(self, size_bias: float = 1.0) -> int:
        base_h = self._base_target_h()
        spread = 0.10 + 0.06 * self.difficulty
        lo = base_h * (1.0 - spread)
        hi = base_h * (1.0 + spread)
        target = self.rng.uniform(lo, hi) * max(0.85, min(1.15, float(size_bias)))
        target = max(int(base_h * 0.84), min(int(base_h * 1.18), int(target)))
        return int(target)

    def _obstacle_scale_for(self, bg_idx: int, img_idx: int) -> float:
        paths = self.raw_paths.get(bg_idx, [])
        if 0 <= int(img_idx) < len(paths):
            name = os.path.basename(paths[int(img_idx)]).lower()
            return float(self.obstacle_scale_overrides.get(name, 1.0))
        return 1.0

    def _pick_pattern(self) -> Tuple[str, List[SpawnSpec]]:
        if self.pattern_cooldown_ms > 0:
            return "single", [SpawnSpec()]

        t = self.difficulty
        roll = self.rng.random()

        name = "single"
        specs = [SpawnSpec()]

        if t < 0.20:
            name, specs = "single", [SpawnSpec()]
        elif t < 0.45:
            if roll < 0.25:
                name = "double"
                specs = [
                    SpawnSpec(),
                    SpawnSpec(gap_scale=0.82, size_bias=0.96, prefer_narrow=True),
                ]
        elif t < 0.75:
            if roll < 0.20:
                name = "double_tight"
                specs = [
                    SpawnSpec(),
                    SpawnSpec(gap_scale=0.74, size_bias=0.94, prefer_narrow=True),
                ]
            elif roll < 0.32:
                name = "stagger"
                specs = [
                    SpawnSpec(size_bias=0.92),
                    SpawnSpec(gap_scale=0.88, size_bias=1.08),
                ]
        else:
            if roll < 0.18:
                name = "triple"
                specs = [
                    SpawnSpec(size_bias=0.92),
                    SpawnSpec(gap_scale=0.76, size_bias=0.98, prefer_narrow=True),
                    SpawnSpec(gap_scale=0.86, size_bias=1.05),
                ]
            elif roll < 0.34:
                name = "double_tight"
                specs = [
                    SpawnSpec(),
                    SpawnSpec(gap_scale=0.74, size_bias=0.95, prefer_narrow=True),
                ]
            elif roll < 0.46:
                name = "stagger"
                specs = [
                    SpawnSpec(size_bias=0.92),
                    SpawnSpec(gap_scale=0.90, size_bias=1.08),
                ]

        if name == self.last_pattern_name and name != "single" and self.rng.random() < 0.60:
            return "single", [SpawnSpec()]

        return name, specs

    # ---------- API ----------
    def reset(self, bg_idx: int, now_ms: int, dino_safe_right_px: int, start_visible: bool = True):
        """Reset na start gry (tu difficulty wraca do 0)."""
        self.bg_idx = int(bg_idx)
        self.obstacles.clear()
        self.elapsed_ms = 0
        self.difficulty = 0.0
        self.level_bonus = 0.0
        self.recent_img_idx.clear()
        self.pattern_cooldown_ms = 0
        self.last_pattern_name = ""

        if start_visible:
            self._spawn_one(
                baseline_y=0,  # przypniemy w pierwszym update
                base_speed=self.base_speed,
                dino_safe_right_px=dino_safe_right_px,
                start_x=self._initial_visible_x(dino_safe_right_px),
                start_baseline_override=True,
            )

        # szybciej pierwszy spawn, żeby nie było pustki
        early = self.rng.randint(self.START_FIRST_SPAWN_MIN_MS, self.START_FIRST_SPAWN_MAX_MS)
        self.next_spawn_ms = int(now_ms + min(self._spawn_interval_ms(), early))

    def on_bg_change(self, bg_idx: int, now_ms: int, dino_safe_right_px: int):
        """Zmiana levela: NIE zerujemy difficulty (to usuwa efekt wielkiej pustki na początku levela)."""
        self.bg_idx = int(bg_idx)
        self.obstacles.clear()
        self.recent_img_idx.clear()

        # mały cooldown żeby nie robić triple od razu po zmianie tła
        self.pattern_cooldown_ms = min(self.pattern_cooldown_ms, 450)
        self.last_pattern_name = ""
        self.level_bonus = min(
            self.LEVEL_DIFFICULTY_BONUS_CAP,
            self.level_bonus + self.LEVEL_DIFFICULTY_BONUS_STEP,
        )
        self._update_difficulty(0)

        self._spawn_one(
            baseline_y=0,
            base_speed=self.base_speed,
            dino_safe_right_px=dino_safe_right_px,
            start_x=self._initial_visible_x(dino_safe_right_px),
            start_baseline_override=True,
        )

        early = self.rng.randint(self.START_FIRST_SPAWN_MIN_MS, self.START_FIRST_SPAWN_MAX_MS)
        self.next_spawn_ms = int(now_ms + min(self._spawn_interval_ms(), early))

    def update(
        self,
        dt_ms: int,
        ground_y: int,
        bg_idx: int,
        now_ms: int,
        dino_safe_right_px: int,
        baseline_offset_px: int = 0,
    ):
        if int(bg_idx) != self.bg_idx:
            self.on_bg_change(bg_idx, now_ms, dino_safe_right_px)
            return

        if not self.raw_bank.get(self.bg_idx, []):
            return

        baseline_y = int(ground_y - max(0, int(baseline_offset_px)))

        for ob in self.obstacles:
            if not ob.pinned:
                ob.y = self._pin_y_to_baseline(baseline_y, ob.foot_bottom)
                ob.draw_rect.topleft = (int(ob.x), int(ob.y))
                ob.hit_rect = self._make_hit_rect(ob.x, ob.y, ob.bounds)
                ob.pinned = True

        self._update_difficulty(dt_ms)
        if self.pattern_cooldown_ms > 0:
            self.pattern_cooldown_ms = max(0, self.pattern_cooldown_ms - int(dt_ms))
        base_speed = self._speed_now()

        dt_s = max(0.0, dt_ms / 1000.0)

        alive: List[Obstacle] = []
        for ob in self.obstacles:
            ob.x -= ob.speed * dt_s
            ob.draw_rect.topleft = (int(ob.x), int(ob.y))
            ob.hit_rect = self._make_hit_rect(ob.x, ob.y, ob.bounds)
            if ob.draw_rect.right >= -30:
                alive.append(ob)

        # ważne: sort po X (bardziej inteligentny porządek + poprawne "last obstacle")
        alive.sort(key=lambda o: o.x)
        self.obstacles = alive

        if now_ms >= self.next_spawn_ms:
            pattern_name, specs = self._pick_pattern()
            spawned = 0
            for spec in specs:
                ob = self._spawn_one(
                    baseline_y=baseline_y,
                    base_speed=base_speed,
                    dino_safe_right_px=dino_safe_right_px,
                    start_x=None,
                    start_baseline_override=False,
                    tight=False,
                    gap_scale=spec.gap_scale,
                    size_bias=spec.size_bias,
                    speed_scale=spec.speed_scale,
                    prefer_narrow=spec.prefer_narrow,
                )
                if ob is not None:
                    spawned += 1

            interval = self._spawn_interval_ms()
            if spawned > 1:
                interval = int(interval * (1.0 + 0.35 * (spawned - 1)))
                self.pattern_cooldown_ms = int(600 + 260 * spawned + 200 * self.difficulty)
            self.next_spawn_ms = int(now_ms + interval)
            if spawned > 0:
                self.last_pattern_name = pattern_name

    def draw(self, screen: pygame.Surface):
        """Render: ground shadow, soft silhouette, img, highlight (ADD), rim.
        Sortowanie po X poprawia warstwy (bardziej "z przodu" = bardziej na prawo)."""
        if not self.obstacles:
            return

        obs_sorted = sorted(self.obstacles, key=lambda o: o.draw_rect.left)

        ground_shadow_blits = []
        soft_shadow_blits = []
        img_blits = []
        highlight_blits = []
        rim_blits = []

        for ob in obs_sorted:
            if ob.ground_shadow_img is not None:
                gx = int(ob.x + ob.ground_shadow_offset[0])
                gy = int(ob.y + ob.ground_shadow_offset[1])
                ground_shadow_blits.append((ob.ground_shadow_img, (gx, gy)))

            if ob.soft_shadow_img is not None:
                sx = int(ob.x + ob.soft_shadow_offset[0])
                sy = int(ob.y + ob.soft_shadow_offset[1])
                soft_shadow_blits.append((ob.soft_shadow_img, (sx, sy)))

            img_blits.append((ob.img, ob.draw_rect.topleft))

            if ob.highlight_img is not None:
                hx = int(ob.x + ob.highlight_offset[0])
                hy = int(ob.y + ob.highlight_offset[1])
                highlight_blits.append((ob.highlight_img, (hx, hy), None, pygame.BLEND_RGBA_ADD))

            if ob.rim_img is not None:
                rim_blits.append((ob.rim_img, ob.draw_rect.topleft))

        try:
            if ground_shadow_blits:
                screen.blits(ground_shadow_blits)
            if soft_shadow_blits:
                screen.blits(soft_shadow_blits)
            if img_blits:
                screen.blits(img_blits)
            if highlight_blits:
                screen.blits(highlight_blits)
            if rim_blits:
                screen.blits(rim_blits)
        except Exception:
            for s, pos in ground_shadow_blits:
                screen.blit(s, pos)
            for s, pos in soft_shadow_blits:
                screen.blit(s, pos)
            for s, pos in img_blits:
                screen.blit(s, pos)
            for item in highlight_blits:
                s, pos, _area, flags = item
                screen.blit(s, pos, special_flags=flags)
            for s, pos in rim_blits:
                screen.blit(s, pos)

    def collides_mask(
        self,
        dino_mask: pygame.mask.Mask,
        dino_topleft: Tuple[int, int],
        dino_hit_rect: pygame.Rect,
        min_overlap_pixels: int = 1,
    ) -> bool:
        dx, dy = int(dino_topleft[0]), int(dino_topleft[1])

        for ob in self.obstacles:
            if not ob.hit_rect.colliderect(dino_hit_rect):
                continue

            off = (int(ob.draw_rect.left - dx), int(ob.draw_rect.top - dy))
            area = dino_mask.overlap_area(ob.mask, off)
            if area >= int(min_overlap_pixels):
                return True

        return False

    # ---------- internal spawn ----------
    def _initial_visible_x(self, dino_safe_right_px: int) -> int:
        # start bliżej (mniej pustego ekranu), ale nadal bezpiecznie dla dino
        x = int(self.sw * self.rng.uniform(0.50, 0.66))
        min_x = dino_safe_right_px + int(self.sw * 0.26)
        return max(x, min_x)

    def _spawn_one(
        self,
        baseline_y: int,
        base_speed: float,
        dino_safe_right_px: int,
        start_x: Optional[int],
        start_baseline_override: bool,
        tight: bool = False,
        gap_scale: float = 1.0,
        size_bias: float = 1.0,
        speed_scale: float = 1.0,
        prefer_narrow: bool = False,
    ) -> Optional[Obstacle]:
        raws = self.raw_bank.get(self.bg_idx, [])
        if not raws:
            return None

        img_idx = self._pick_img_index(prefer_narrow=prefer_narrow)
        img_idx = max(0, min(img_idx, len(raws) - 1))

        target_h = self._pick_variant_h(size_bias=size_bias)
        scale_mult = self._obstacle_scale_for(self.bg_idx, img_idx)
        if scale_mult != 1.0:
            target_h = max(8, int(target_h * scale_mult))
        v = self._get_variant(self.bg_idx, img_idx, target_h)

        if start_baseline_override:
            y = float(-v.foot_bottom)
            pinned = False
        else:
            y = self._pin_y_to_baseline(baseline_y, v.foot_bottom)
            pinned = True

        # najpierw ustal prędkość (do mądrzejszego gapu)
        speed_scale = max(0.92, min(1.08, float(speed_scale)))
        speed = float(base_speed) * self.rng.uniform(0.98, 1.06) * speed_scale

        if start_x is not None:
            x = float(start_x)
        else:
            pad_hi = max(36, int(self.sw * 0.12))
            x = float(self.sw + self.rng.randint(24, pad_hi))

        if self.obstacles:
            # po sortowaniu w update - ostatni = najbardziej na prawo
            last = self.obstacles[-1]

            # gap bazowy pod skok / czytelność
            ref_speed = max(float(base_speed), float(speed), float(last.speed))
            gap = self._gap_px(ref_speed, tight=tight, gap_scale=gap_scale)

            # dopasuj gap do szerokości przeszkód (bardziej "inteligentne" układanie)
            width_pad = int(0.12 * (last.draw_rect.width + v.img.get_width()))
            gap += max(0, width_pad)

            # anti-catchup (NAPRAWIONE: limit czasu + limit gapu, żeby nie robić pustyni)
            if speed > last.speed + 1e-6 and last.speed > 1e-6:
                time_to_off = (float(last.draw_rect.right) + 30.0) / float(last.speed)
                horizon = min(self.CATCHUP_HORIZON_S, max(0.0, time_to_off))
                catchup = (speed - last.speed) * horizon
                gap = max(gap, 32 + int(catchup))

            # twardy limit gapu
            max_gap_cap = int(self.sw * self.MAX_GAP_FRAC_OF_SCREEN) + int(self.dino_h * 0.45)
            gap = min(gap, max_gap_cap)
            max_gap = min(max_gap_cap, gap + int(gap * self.EXTRA_GAP_FRAC))

            min_x = float(last.draw_rect.right + gap)
            max_x = float(last.draw_rect.right + max_gap)
            if x < min_x:
                x = min_x
            elif x > max_x:
                x = max_x

        if start_x is None:
            min_x_from_dino = float(dino_safe_right_px + int(self.sw * 0.26))
            if x < min_x_from_dino:
                x = min_x_from_dino

        draw_rect = v.img.get_rect(topleft=(int(x), int(y)))
        hit_rect = self._make_hit_rect(x, y, v.bounds)

        ob = Obstacle(
            img=v.img,
            mask=v.mask,
            ground_shadow_img=v.ground_shadow_img,
            ground_shadow_offset=v.ground_shadow_offset,
            soft_shadow_img=v.soft_shadow_img,
            soft_shadow_offset=v.soft_shadow_offset,
            rim_img=v.rim_img,
            highlight_img=v.highlight_img,
            highlight_offset=v.highlight_offset,
            x=float(x),
            y=float(y),
            speed=float(speed),
            draw_rect=draw_rect,
            hit_rect=hit_rect,
            bounds=v.bounds,
            foot_bottom=v.foot_bottom,
            pinned=pinned,
        )
        self.obstacles.append(ob)
        return ob

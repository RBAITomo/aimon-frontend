"""Sprite manager for frame-based character assets.

Loads individual PNG frames from assets/{stage}/animations/{anim}/{direction}/ dirs.
Scales frames to CHAR_SPRITE_SIZE. Supports stage transitions by loading/unloading.
For movable stages (child/adult), loads all 8 directions. Others load south only.
Falls back to code-generated placeholder shapes for missing stages.
"""

import os
import logging

import pygame

import config

log = logging.getLogger(__name__)

# Placeholder colors for stages without art assets
_PLACEHOLDER_COLORS = {
    "egg": (200, 180, 120),
    "baby": (220, 160, 80),
    "child": (100, 180, 220),
    "adult": (180, 100, 200),
}

# All supported direction subdirectory names
_ALL_DIRECTIONS = [
    "south", "south-east", "east", "north-east",
    "north", "north-west", "west", "south-west",
]


class SpriteSheetManager:
    """Loads per-stage frame animations, returns frame by tick."""

    def __init__(self):
        # {(stage, animation, direction): [Surface, ...]}
        self._frames = {}
        # {(stage, animation): {"fps": int, "loop": bool}}
        self._meta = {}
        self._loaded_stages = set()

    def load_stage(self, stage, variant_code=None):
        """Load all animations for a given evolution stage.

        For variant stage, variant_code must be provided to resolve asset folder.
        """
        if stage in self._loaded_stages:
            return
        self._loaded_stages.add(stage)

        asset_folder = config.STAGE_ASSET_MAP.get(stage)

        # Variant stage: resolve folder from VARIANT_SPRITE_MAP
        if asset_folder is None and variant_code:
            asset_folder = config.VARIANT_SPRITE_MAP.get(variant_code)

        if asset_folder:
            asset_path = os.path.join(config.ASSET_DIR, asset_folder)
            self._load_from_assets(stage, asset_path, variant_code=variant_code)
        else:
            self._generate_placeholder(stage)

        # Ensure at least an idle animation exists (south direction)
        if (stage, "idle", "south") not in self._frames:
            self._load_static_rotation(stage)

        loaded = set(a for s, a, d in self._frames if s == stage)
        log.info("Stage '%s' (variant=%s) loaded animations: %s", stage, variant_code, sorted(loaded))

        is_movable_variant = variant_code and variant_code in config.MOVABLE_VARIANTS
        if stage in config.MOVABLE_STAGES or is_movable_variant:
            if (stage, "walking", "south") not in self._frames:
                log.warning("Stage '%s' (variant=%s) is movable but has no walking animation", stage, variant_code)

    def _load_from_assets(self, stage, asset_path, variant_code=None):
        """Load animations from assets/{stage}/animations/{name}/{direction}/ dirs."""
        anim_dir = os.path.join(asset_path, "animations")
        if not os.path.isdir(anim_dir):
            return

        # Variant stages check MOVABLE_VARIANTS; normal stages check MOVABLE_STAGES
        if variant_code:
            is_movable = variant_code in config.MOVABLE_VARIANTS
        else:
            is_movable = stage in config.MOVABLE_STAGES

        for folder_name in os.listdir(anim_dir):
            folder_path = os.path.join(anim_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue

            internal_name = config.ANIMATION_MAP.get(folder_name, folder_name)
            is_loop = internal_name in ("idle", "listening", "speaking", "walking")
            fps = 8 if internal_name == "idle" else 10

            # Determine which directions to load
            if is_movable:
                dirs_to_load = _ALL_DIRECTIONS
            else:
                dirs_to_load = ["south"]

            loaded_any = False
            for direction in dirs_to_load:
                dir_path = os.path.join(folder_path, direction)
                if not os.path.isdir(dir_path):
                    continue
                frames = self._load_frames_from_dir(dir_path)
                if frames:
                    self._frames[(stage, internal_name, direction)] = frames
                    loaded_any = True

            if loaded_any:
                self._meta[(stage, internal_name)] = {"fps": fps, "loop": is_loop}

    def _load_static_rotation(self, stage):
        """Load all rotation PNGs as idle animation (gentle rocking motion).

        Sequences: south -> south-east -> south -> south-west -> south (loop).
        Falls back to south.png single frame if others missing.
        """
        asset_folder = config.STAGE_ASSET_MAP.get(stage)
        if not asset_folder:
            return
        rot_dir = os.path.join(config.ASSET_DIR, asset_folder, "rotations")
        if not os.path.isdir(rot_dir):
            return

        rock_sequence = [
            "south.png", "south-east.png", "east.png", "south-east.png",
            "south.png", "south-west.png", "west.png", "south-west.png",
        ]
        frames = []
        for fname in rock_sequence:
            fpath = os.path.join(rot_dir, fname)
            if os.path.isfile(fpath):
                frame = self._load_and_scale(fpath)
                if frame:
                    frames.append(frame)

        if not frames:
            return
        self._frames[(stage, "idle", "south")] = frames
        self._meta[(stage, "idle")] = {"fps": 4, "loop": True}

    def _load_frames_from_dir(self, directory):
        """Load sorted PNG frames from a directory, scale to CHAR_SPRITE_SIZE."""
        files = sorted(
            f for f in os.listdir(directory) if f.lower().endswith(".png")
        )
        frames = []
        for fname in files:
            frame = self._load_and_scale(os.path.join(directory, fname))
            if frame:
                frames.append(frame)
        return frames

    def _load_and_scale(self, path):
        """Load a PNG and scale to CHAR_SPRITE_SIZE with alpha."""
        try:
            surf = pygame.image.load(path)
            if surf.get_size() != config.CHAR_SPRITE_SIZE:
                surf = pygame.transform.smoothscale(surf, config.CHAR_SPRITE_SIZE)
            return surf.convert_alpha()
        except pygame.error as e:
            log.warning("Failed to load sprite %s: %s", path, e)
            return None

    def _generate_placeholder(self, stage):
        """Generate colored rectangle placeholder for missing stages."""
        w, h = config.CHAR_SPRITE_SIZE
        color = _PLACEHOLDER_COLORS.get(stage, (150, 150, 150))
        font = pygame.font.SysFont("dejavusans", 14)

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(surf, color, (10, 10, w - 20, h - 20), border_radius=12)
        pygame.draw.rect(surf, (0, 0, 0), (10, 10, w - 20, h - 20), 2, border_radius=12)
        label = font.render(stage.upper(), True, (255, 255, 255))
        lx = (w - label.get_width()) // 2
        ly = (h - label.get_height()) // 2
        surf.blit(label, (lx, ly))

        self._frames[(stage, "idle", "south")] = [surf]
        self._meta[(stage, "idle")] = {"fps": 1, "loop": True}

    def get_frame(self, stage, animation, tick, direction="south"):
        """Return (Surface, bool_done) for animation at tick.

        Args:
            stage: Evolution stage name.
            animation: Animation name (idle, walking, etc.).
            tick: Current animation tick counter.
            direction: Facing direction (south, north, east, etc.).

        Falls back: requested direction -> south -> idle south.
        """
        key = (stage, animation, direction)
        if key not in self._frames:
            key = (stage, animation, "south")
        if key not in self._frames:
            key = (stage, "idle", direction)
        if key not in self._frames:
            key = (stage, "idle", "south")
        frames = self._frames.get(key)
        if not frames:
            return None, True

        resolved_anim = key[1]
        meta = self._meta.get((stage, resolved_anim), {"fps": 10, "loop": True})
        anim_fps = meta["fps"]
        loops = meta["loop"]

        frame_idx = int(tick * anim_fps / config.LCD_FPS)

        if loops:
            return frames[frame_idx % len(frames)], False
        else:
            if frame_idx >= len(frames):
                return frames[-1], True
            return frames[frame_idx], False

    def unload_stage(self, stage):
        """Free memory for a stage no longer needed."""
        keys_to_remove = [k for k in self._frames if k[0] == stage]
        for k in keys_to_remove:
            del self._frames[k]
            self._meta.pop((k[0], k[1]), None)
        self._loaded_stages.discard(stage)
        log.info("Unloaded stage '%s'", stage)

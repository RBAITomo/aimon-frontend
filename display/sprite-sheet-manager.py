"""Sprite manager for frame-based character assets.

Loads individual PNG frames from assets/{stage}/animations/{anim}/south/ dirs.
Scales frames to CHAR_SPRITE_SIZE. Supports stage transitions by loading/unloading.
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


class SpriteSheetManager:
    """Loads per-stage frame animations, returns frame by tick."""

    def __init__(self):
        self._frames = {}       # {(stage, animation): [Surface, ...]}
        self._meta = {}         # {(stage, animation): {"fps": int, "loop": bool}}
        self._loaded_stages = set()

    def load_stage(self, stage):
        """Load all animations for a given evolution stage.

        Looks up asset folder from STAGE_ASSET_MAP in config. If no assets
        exist, generates colored placeholder frames.
        """
        if stage in self._loaded_stages:
            return
        self._loaded_stages.add(stage)

        asset_folder = config.STAGE_ASSET_MAP.get(stage)
        if asset_folder:
            asset_path = os.path.join(config.ASSET_DIR, asset_folder)
            self._load_from_assets(stage, asset_path)
        else:
            self._generate_placeholder(stage)

        # Ensure at least an idle animation exists
        if (stage, "idle") not in self._frames:
            self._load_static_rotation(stage)

        loaded = [a for s, a in self._frames if s == stage]
        log.info("Stage '%s' loaded: %s", stage, loaded)

    def _load_from_assets(self, stage, asset_path):
        """Load animations from assets/{stage}/animations/{name}/south/ dirs."""
        anim_dir = os.path.join(asset_path, "animations")
        if not os.path.isdir(anim_dir):
            return

        for folder_name in os.listdir(anim_dir):
            south_dir = os.path.join(anim_dir, folder_name, "south")
            if not os.path.isdir(south_dir):
                continue

            # Map folder name to internal animation name
            internal_name = config.ANIMATION_MAP.get(folder_name, folder_name)
            frames = self._load_frames_from_dir(south_dir)
            if frames:
                self._frames[(stage, internal_name)] = frames
                # Default metadata: looping idle, one-shot for others
                is_loop = internal_name in ("idle", "listening", "speaking")
                fps = 8 if internal_name == "idle" else 10
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

        # Define rocking sequence for a gentle wobble animation
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
        self._frames[(stage, "idle")] = frames
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
        # Rounded rectangle body
        pygame.draw.rect(surf, color, (10, 10, w - 20, h - 20), border_radius=12)
        pygame.draw.rect(surf, (0, 0, 0), (10, 10, w - 20, h - 20), 2, border_radius=12)
        # Stage label
        label = font.render(stage.upper(), True, (255, 255, 255))
        lx = (w - label.get_width()) // 2
        ly = (h - label.get_height()) // 2
        surf.blit(label, (lx, ly))

        self._frames[(stage, "idle")] = [surf]
        self._meta[(stage, "idle")] = {"fps": 1, "loop": True}

    def get_frame(self, stage, animation, tick):
        """Return (Surface, bool_done) for animation at tick.

        Falls back to idle if requested animation not found.
        """
        key = (stage, animation)
        if key not in self._frames or not self._frames[key]:
            key = (stage, "idle")
        frames = self._frames.get(key)
        if not frames:
            return None, True

        meta = self._meta.get(key, {"fps": 10, "loop": True})
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
            self._meta.pop(k, None)
        self._loaded_stages.discard(stage)
        log.info("Unloaded stage '%s'", stage)

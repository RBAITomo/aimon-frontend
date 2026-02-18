# AI-MON Sprite Asset Guide

## Directory Structure

Each evolution stage has its own folder mapped in `config.py → STAGE_ASSET_MAP`.

```
assets/
├── Coneko-egg-form/
│   ├── rotations/                    ← Static rotation PNGs (wobble idle)
│   │   ├── south.png
│   │   ├── south-east.png
│   │   ├── east.png
│   │   ├── south-west.png
│   │   └── west.png
│   └── animations/                   ← Frame-by-frame animations
│       └── evolution/south/          ← Egg hatching (one-shot)
│           ├── 001.png
│           ├── 002.png
│           └── ...
│
├── Coneko-baby-Form/
│   ├── rotations/                    ← Fallback idle if no animations/idle
│   └── animations/
│       ├── idle/south/               ← Idle loop (breathing, blinking)
│       │   ├── 001.png ... N.png
│       ├── listening/south/          ← Ear perked up, attentive
│       │   ├── 001.png ... N.png
│       ├── speaking/south/           ← Mouth moving, animated
│       │   ├── 001.png ... N.png
│       ├── happy/south/              ← Hearts, bouncing
│       │   ├── 001.png ... N.png
│       ├── eating/south/             ← Munching animation
│       │   ├── 001.png ... N.png
│       ├── jump/south/               ← Jump/bounce
│       │   ├── 001.png ... N.png
│       ├── evolution/south/          ← Growing to child (one-shot)
│       │   ├── 001.png ... N.png
│       ├── warning/south/            ← Shaking, sad eyes (one-shot)
│       │   ├── 001.png ... N.png
│       └── regression/south/         ← Shrinking, crying (one-shot)
│           ├── 001.png ... N.png
│
├── Coneko-child-Form/                ← (future) same structure as baby
│   └── animations/
│       ├── idle/south/
│       ├── listening/south/
│       ├── speaking/south/
│       ├── happy/south/
│       ├── eating/south/
│       ├── evolution/south/          ← Growing to adult
│       ├── warning/south/
│       └── regression/south/
│
└── Coneko-adult-Form/                ← (future) same structure
    └── animations/
        ├── idle/south/
        ├── listening/south/
        ├── speaking/south/
        ├── happy/south/
        ├── eating/south/
        ├── warning/south/
        └── regression/south/
```

## Animation Types

### Looping (play forever)
| Name | When | Notes |
|------|------|-------|
| `idle` | Default state, no interaction | Breathing, blinking, subtle motion |
| `listening` | Child is talking (mic on) | Ear perked, attentive pose |
| `speaking` | Pet is responding (TTS playing) | Mouth moving, expressive |

### One-shot (play once, then stop)
| Name | When | Notes |
|------|------|-------|
| `happy` | After conversation turn ends | Hearts, bouncing, ~3s |
| `eating` | After feeding via camera | Munching, ~2s |
| `jump` | Level up or special event | Bounce, ~1s |
| `evolution` | Stage upgrade triggered | Glow/grow/transform, ~3s |
| `warning` | Stats critically low | Shaking, sad eyes, ~2s |
| `regression` | Pet regresses to egg | Shrinking, crying, ~4s |

## Frame Specs

- **Size**: 156x156 px (auto-scaled from any size, but native is best)
- **Format**: PNG with transparency (alpha channel)
- **Naming**: Sequential numbers (`001.png`, `002.png`, ...) — loaded sorted
- **FPS**: idle=8, listening/speaking=10, others=10 (configurable in code)
- **Frame count guide**:
  - idle: 8-16 frames (looping)
  - listening: 6-12 frames (looping)
  - speaking: 8-12 frames (looping)
  - happy: 10-15 frames (one-shot, ~1-2s)
  - eating: 8-12 frames (one-shot, ~1s)
  - evolution: 20-30 frames (one-shot, ~3s)
  - warning: 12-20 frames (one-shot, ~2s)
  - regression: 30-40 frames (one-shot, ~4s)

## Adding a New Stage

1. Create folder: `assets/Coneko-{stage}-Form/`
2. Add to `config.py → STAGE_ASSET_MAP`:
   ```python
   STAGE_ASSET_MAP = {
       "egg": "Coneko-egg-form",
       "baby": "Coneko-baby-Form",
       "child": "Coneko-child-Form",   # add this
       "adult": "Coneko-adult-Form",   # add this
   }
   ```
3. Create `animations/{name}/south/` dirs with PNGs
4. Minimum required: `idle` animation (fallback to rotations/ wobble if missing)

## Rotations (Optional Fallback)

If a stage has no `animations/idle/`, the system loads `rotations/` PNGs as a gentle rocking idle:

```
rotations/
├── south.png         ← center
├── south-east.png    ← tilt right
├── east.png          ← full right
├── south-west.png    ← tilt left
└── west.png          ← full left
```

Sequence: S → SE → E → SE → S → SW → W → SW (loop at 4 FPS)

## State → Animation Mapping

| App State | Animation Played |
|-----------|-----------------|
| IDLE | `idle` |
| LISTENING | `listening` |
| ASR (thinking) | `idle` |
| ANSWER (TTS) | `speaking` |
| EMOTION (post-turn) | `happy` (or current emotion) |
| Feeding | `eating` |
| Warning | `warning` |
| Evolution | `evolution` |
| Regression | `regression` |
| OFFLINE | `idle` |

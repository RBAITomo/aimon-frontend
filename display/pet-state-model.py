"""Pet state dataclass for display rendering.

Holds all pet data needed by the layer compositor: evolution stage,
current animation, vital stats, level/XP, and mood.
"""

from dataclasses import dataclass, field


@dataclass
class PetState:
    """Mutable pet data for rendering. Mutate from main loop only."""

    stage: str = "egg"            # egg, baby, child, adult
    variant: str = None           # variant code if transformed
    animation: str = "idle"       # current animation name
    hunger: int = 50              # 0-100, high = hungry (bad)
    energy: int = 100             # 0-100, low = tired (bad)
    happiness: int = 80           # 0-100, low = sad (bad)
    level: int = 1
    xp: int = 0
    xp_for_next: int = 50        # XP needed for next level
    mood: str = "neutral"

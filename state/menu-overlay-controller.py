"""Menu overlay state machine: navigate 4 items, enter/back screens."""

import enum
import logging

log = logging.getLogger(__name__)


class MenuItem(enum.Enum):
    PET_STATUS = 0
    FOOD_INVENTORY = 1
    BADGES = 2
    MAP = 3
    VOLUME = 4
    MINI_GAME = 5
    COOKBOOK = 6


class MenuState(enum.Enum):
    CLOSED = "closed"
    ITEM_SELECT = "item_select"
    SCREEN_VIEW = "screen_view"


class MenuOverlayController:
    """Controls menu navigation: open/close, item cycling, screen entry."""

    ITEMS = list(MenuItem)

    def __init__(self):
        self._state = MenuState.CLOSED
        self._index = 0

    @property
    def is_open(self) -> bool:
        return self._state != MenuState.CLOSED

    @property
    def current_item(self) -> MenuItem:
        return self.ITEMS[self._index]

    @property
    def in_screen(self) -> bool:
        return self._state == MenuState.SCREEN_VIEW

    @property
    def state(self) -> MenuState:
        return self._state

    def toggle(self):
        """Main button: open menu or close from any state."""
        if self._state == MenuState.CLOSED:
            self._state = MenuState.ITEM_SELECT
            self._index = 0
            log.info("Menu opened")
        else:
            self._state = MenuState.CLOSED
            log.info("Menu closed")

    def next_item(self):
        """Button A in item select: cycle to next menu item."""
        if self._state == MenuState.ITEM_SELECT:
            self._index = (self._index + 1) % len(self.ITEMS)
            log.debug("Menu item: %s", self.current_item.name)

    def prev_item(self):
        """Button D in item select: cycle to previous menu item."""
        if self._state == MenuState.ITEM_SELECT:
            self._index = (self._index - 1) % len(self.ITEMS)
            log.debug("Menu item: %s", self.current_item.name)

    def enter(self):
        """Button B: enter screen view for current item."""
        if self._state == MenuState.ITEM_SELECT:
            self._state = MenuState.SCREEN_VIEW
            log.info("Entered screen: %s", self.current_item.name)

    def back(self):
        """Button C: back from screen to item select, or close menu from item select."""
        if self._state == MenuState.SCREEN_VIEW:
            self._state = MenuState.ITEM_SELECT
            log.debug("Back to item select")
        elif self._state == MenuState.ITEM_SELECT:
            self._state = MenuState.CLOSED
            log.info("Menu closed via back")

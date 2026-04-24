from enum import Enum


class ElementType(Enum):
    WOOD = "wood"
    WATER = "water"
    METAL = "metal"
    FIRE = "fire"
    EARTH = "earth"


PRODUCTIVE_CYCLE: dict["ElementType", "ElementType"] = {
    ElementType.WATER: ElementType.WOOD,
    ElementType.WOOD: ElementType.FIRE,
    ElementType.FIRE: ElementType.EARTH,
    ElementType.EARTH: ElementType.METAL,
    ElementType.METAL: ElementType.WATER,
}

DESTRUCTIVE_CYCLE: dict["ElementType", "ElementType"] = {
    ElementType.FIRE: ElementType.METAL,
    ElementType.METAL: ElementType.WOOD,
    ElementType.WOOD: ElementType.EARTH,
    ElementType.EARTH: ElementType.WATER,
    ElementType.WATER: ElementType.FIRE,
}

ELEMENT_LIST: list[ElementType] = list(ElementType)

# World dimensions (virtual units)
WORLD_WIDTH: int = 80
WORLD_HEIGHT: int = 60

# Display dimensions (pixels)
WINDOW_W: int = 800
WINDOW_H: int = 600
PANEL_W: int = 240
SCALE_X: float = WINDOW_W / WORLD_WIDTH    # 10.0 px per virtual unit
SCALE_Y: float = WINDOW_H / WORLD_HEIGHT   # 10.0 px per virtual unit

# Colors
BACKGROUND_COLOR: tuple[int, int, int] = (5, 20, 20)
GRID_COLOR: tuple[int, int, int] = (30, 40, 40)
PANEL_COLOR: tuple[int, int, int] = (20, 30, 30)
WHITE: tuple[int, int, int] = (255, 255, 255)
DIM_WHITE: tuple[int, int, int] = (180, 180, 180)

ELEMENT_COLOR: dict[ElementType, tuple[int, int, int]] = {
    ElementType.WOOD:  (60,  160,  40),
    ElementType.WATER: (30,   80, 220),
    ElementType.METAL: (192, 192, 192),
    ElementType.FIRE:  (255,  80,  10),
    ElementType.EARTH: (210, 180,  30),
}

TAOBOT_COLOR: tuple[int, int, int] = (0, 220, 120)
TAOBOT_FLEE_COLOR: tuple[int, int, int] = (220, 220, 0)

ELEMENT_RESOURCE_NAME: dict[ElementType, str] = {
    ElementType.WOOD:  "Wood",
    ElementType.WATER: "Water",
    ElementType.METAL: "Metal",
    ElementType.FIRE:  "Fire",
    ElementType.EARTH: "Earth",
}

ELEMENT_HAZARD_NAME: dict[ElementType, str] = {
    ElementType.WOOD:  "Thornwall",
    ElementType.WATER: "Sinkhole",
    ElementType.METAL: "Shardfield",
    ElementType.FIRE:  "Pyre",
    ElementType.EARTH: "Mudpit",
}

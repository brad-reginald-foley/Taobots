import math


def torus_delta(a: float, b: float, size: float) -> float:
    """Signed shortest displacement from a to b on a torus of given size."""
    d = b - a
    if d > size / 2:
        d -= size
    elif d < -size / 2:
        d += size
    return d


def torus_distance(
    x1: float, y1: float, x2: float, y2: float, world_w: float, world_h: float
) -> float:
    """Euclidean distance between two float positions on a torus."""
    dx = torus_delta(x1, x2, world_w)
    dy = torus_delta(y1, y2, world_h)
    return math.sqrt(dx * dx + dy * dy)


def torus_direction(
    x1: float, y1: float, x2: float, y2: float, world_w: float, world_h: float
) -> tuple[float, float]:
    """Unit vector from (x1,y1) toward (x2,y2) on a torus.
    Returns (0.0, 0.0) if positions are identical."""
    dx = torus_delta(x1, x2, world_w)
    dy = torus_delta(y1, y2, world_h)
    dist = math.sqrt(dx * dx + dy * dy)
    if dist == 0.0:
        return (0.0, 0.0)
    return (dx / dist, dy / dist)


def wrap_position(x: float, y: float, world_w: float, world_h: float) -> tuple[float, float]:
    """Apply torus wrap to a position."""
    return (x % world_w, y % world_h)


def polar_to_cartesian(r: float, theta: float) -> tuple[float, float]:
    """Convert polar (r, theta radians) to (x, y)."""
    return (r * math.cos(theta), r * math.sin(theta))


def world_to_screen(x: float, y: float, scale_x: float, scale_y: float) -> tuple[int, int]:
    """Convert virtual-unit position to pixel position for rendering."""
    return (int(x * scale_x), int(y * scale_y))

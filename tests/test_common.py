from common import DESTRUCTIVE_CYCLE, ELEMENT_LIST, PRODUCTIVE_CYCLE, ElementType


def test_productive_cycle_is_complete():
    assert set(PRODUCTIVE_CYCLE.keys()) == set(ElementType)
    assert set(PRODUCTIVE_CYCLE.values()) == set(ElementType)


def test_productive_cycle_length():
    # Following the cycle from any element should return to start after 5 steps
    start = ElementType.WOOD
    current = start
    for _ in range(5):
        current = PRODUCTIVE_CYCLE[current]
    assert current == start


def test_destructive_cycle_is_complete():
    assert set(DESTRUCTIVE_CYCLE.keys()) == set(ElementType)
    assert set(DESTRUCTIVE_CYCLE.values()) == set(ElementType)


def test_destructive_cycle_length():
    start = ElementType.FIRE
    current = start
    for _ in range(5):
        current = DESTRUCTIVE_CYCLE[current]
    assert current == start


def test_no_self_loops():
    for k, v in PRODUCTIVE_CYCLE.items():
        assert k != v, f"Productive cycle self-loop at {k}"
    for k, v in DESTRUCTIVE_CYCLE.items():
        assert k != v, f"Destructive cycle self-loop at {k}"


def test_element_list_has_all_types():
    assert set(ELEMENT_LIST) == set(ElementType)
    assert len(ELEMENT_LIST) == 5

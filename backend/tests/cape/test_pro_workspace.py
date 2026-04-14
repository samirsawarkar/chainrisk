from cape.visuals.pro_workspace import parse_tick_range


def test_parse_tick_range_string():
    assert parse_tick_range("T5-T8", None, None, 20) == (5, 8)
    assert parse_tick_range("T8–T5", None, None, 20) == (5, 8)


def test_parse_tick_range_fallback():
    assert parse_tick_range(None, 2, 7, 10) == (2, 7)

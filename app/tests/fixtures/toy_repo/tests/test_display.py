from app.display import format_display_name


def test_format_display_name_basic() -> None:
    assert format_display_name(" alice ") == "Alice"


def test_format_display_name_none() -> None:
    assert format_display_name(None) == ""

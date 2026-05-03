from bs4 import BeautifulSoup

from app.skills.website import (
    check_headings,
    check_meta_description,
    check_robots,
    check_title,
    check_viewport,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_title_missing_is_high_severity() -> None:
    finding = check_title(_soup("<html><body>nothing</body></html>"))
    assert finding["present"] is False
    assert finding["severity"] == "high"


def test_title_short_is_medium_severity() -> None:
    finding = check_title(_soup("<title>Hi</title>"))
    assert finding["severity"] == "medium"


def test_title_in_range_is_ok() -> None:
    finding = check_title(_soup("<title>AdVanta AI — Growth Command Center for Modern SaaS</title>"))
    assert finding["severity"] == "ok"
    assert 30 <= finding["length"] <= 65


def test_meta_description_missing_is_high() -> None:
    finding = check_meta_description(_soup("<html></html>"))
    assert finding["severity"] == "high"


def test_meta_description_in_range_is_ok() -> None:
    desc = "AdVanta AI is the growth command center for SaaS marketers, deploying AI skill agents across paid, SEO, and conversion to remove busywork." * 1
    finding = check_meta_description(
        _soup(f'<meta name="description" content="{desc}">')
    )
    assert finding["severity"] == "ok"


def test_headings_no_h1_is_high() -> None:
    finding = check_headings(_soup("<h2>Subhead</h2>"))
    assert finding["severity"] == "high"
    assert finding["h1_count"] == 0


def test_headings_multiple_h1_is_medium() -> None:
    finding = check_headings(_soup("<h1>One</h1><h1>Two</h1>"))
    assert finding["severity"] == "medium"
    assert finding["h1_count"] == 2


def test_headings_single_h1_is_ok() -> None:
    finding = check_headings(_soup("<h1>Turn ad chaos into intelligent growth</h1>"))
    assert finding["severity"] == "ok"


def test_viewport_missing_is_high() -> None:
    finding = check_viewport(_soup("<html></html>"))
    assert finding["severity"] == "high"


def test_viewport_with_device_width_is_ok() -> None:
    finding = check_viewport(_soup('<meta name="viewport" content="width=device-width, initial-scale=1">'))
    assert finding["severity"] == "ok"


def test_robots_noindex_is_high() -> None:
    finding = check_robots(_soup('<meta name="robots" content="noindex, nofollow">'))
    assert finding["severity"] == "high"


def test_robots_no_directive_is_ok() -> None:
    finding = check_robots(_soup("<html></html>"))
    assert finding["severity"] == "ok"

from clipfactory.discover.service import _duration


def test_rss_duration_parsing():
    assert _duration("1:02:03") == 3723
    assert _duration("bad") is None
    assert _duration(90) == 90.0

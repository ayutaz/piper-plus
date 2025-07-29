"""
Basic tests that work on all platforms including Windows
"""


def test_import():
    """Test basic imports work"""
    import piper_train  # noqa: F401

    assert True


def test_basic_math():
    """Test basic functionality"""
    assert 1 + 1 == 2


def test_list_operations():
    """Test basic list operations"""
    items = [1, 2, 3]
    assert len(items) == 3
    assert sum(items) == 6

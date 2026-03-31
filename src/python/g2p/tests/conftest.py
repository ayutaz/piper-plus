import pytest


def _has_pyopenjtalk():
    try:
        import pyopenjtalk_plus  # noqa: F401

        return True
    except ImportError:
        try:
            import pyopenjtalk  # noqa: F401

            return True
        except ImportError:
            return False


def _has_g2p_en():
    try:
        from g2p_en import G2p  # noqa: F401

        return True
    except ImportError:
        return False


requires_ja = pytest.mark.skipif(
    not _has_pyopenjtalk(), reason="pyopenjtalk not installed"
)
requires_en = pytest.mark.skipif(
    not _has_g2p_en(), reason="g2p-en not installed"
)

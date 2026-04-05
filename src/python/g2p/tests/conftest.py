import pytest


@pytest.fixture(autouse=True)
def _clear_phonemize_cache():
    """各テスト前後に音素化キャッシュをクリア."""
    try:
        from piper_plus_g2p.japanese import clear_phonemize_cache

        clear_phonemize_cache()
    except ImportError:
        pass
    yield
    try:
        from piper_plus_g2p.japanese import clear_phonemize_cache

        clear_phonemize_cache()
    except ImportError:
        pass


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


def _has_pypinyin():
    try:
        import pypinyin  # noqa: F401

        return True
    except ImportError:
        return False


def _has_g2pk2():
    try:
        from g2pk2 import G2p  # noqa: F401

        G2p()("test")
        return True
    except Exception:  # noqa: BLE001
        return False


requires_ja = pytest.mark.skipif(
    not _has_pyopenjtalk(), reason="pyopenjtalk not installed"
)
requires_en = pytest.mark.skipif(not _has_g2p_en(), reason="g2p-en not installed")
requires_zh = pytest.mark.skipif(not _has_pypinyin(), reason="pypinyin not installed")
requires_ko = pytest.mark.skipif(not _has_g2pk2(), reason="g2pk2 not installed")


def _has_piper_train():
    try:
        import piper_train  # noqa: F401

        return True
    except ImportError:
        return False


requires_piper_train = pytest.mark.skipif(
    not _has_piper_train(), reason="piper_train not installed"
)


@pytest.fixture(scope="session")
def ja_phonemizer():
    if not _has_pyopenjtalk():
        pytest.skip("pyopenjtalk not installed")
    from piper_plus_g2p import get_phonemizer

    return get_phonemizer("ja")


@pytest.fixture(scope="session")
def en_phonemizer():
    if not _has_g2p_en():
        pytest.skip("g2p-en not installed")
    from piper_plus_g2p import get_phonemizer

    return get_phonemizer("en")

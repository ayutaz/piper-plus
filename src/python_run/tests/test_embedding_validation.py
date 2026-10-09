"""Single speaker contract shared by runtime, extraction and training."""

import numpy as np
import pytest

from piper_plus.embedding import embedding_dimension, validate_embedding


@pytest.mark.parametrize("dimension", [192, 256])
@pytest.mark.parametrize("batched", [False, True])
def test_single_speaker_is_normalized_without_mutating_caller(dimension, batched):
    values = np.arange(1, dimension + 1, dtype=np.float64)
    if batched:
        values = values[None, :]
    before = values.copy()
    result = validate_embedding(values, dimension)
    assert result.shape == (dimension,)
    assert result.dtype == np.float32
    assert np.linalg.norm(result) == pytest.approx(1.0)
    np.testing.assert_array_equal(values, before)


@pytest.mark.parametrize(
    "values",
    [
        np.zeros(192),
        np.full(192, np.nan),
        np.full(192, np.inf),
        np.ones(256),
        np.ones((2, 96)),
        np.ones((1, 1, 192)),
        ["x"] * 192,
    ],
)
def test_invalid_explicit_embedding_is_rejected(values):
    with pytest.raises(ValueError, match="speaker_embedding"):
        validate_embedding(values, 192)


def test_large_finite_values_do_not_overflow_norm():
    result = validate_embedding(np.full(192, 1e38), 192)
    assert np.isfinite(result).all()
    assert np.linalg.norm(result) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "shape,expected", [([1, 256], 256), (["batch", 192], 192), ([1, "dim"], 192)]
)
def test_graph_fixed_dimension_takes_precedence(shape, expected):
    from types import SimpleNamespace

    assert (
        embedding_dimension([SimpleNamespace(name="speaker_embedding", shape=shape)])
        == expected
    )

import numpy as np
import pytest

from src.embeddings.similarity import cosine_similarity_matrix


def test_identical_vectors_have_similarity_one():
    result = cosine_similarity_matrix([[1.0, 0.0]], [[1.0, 0.0]])

    assert result.shape == (1, 1)
    assert result[0, 0] == pytest.approx(1.0)


def test_orthogonal_vectors_have_similarity_zero():
    result = cosine_similarity_matrix([[1.0, 0.0]], [[0.0, 1.0]])

    assert result[0, 0] == pytest.approx(0.0)


def test_opposite_vectors_have_similarity_negative_one():
    result = cosine_similarity_matrix([[1.0, 0.0]], [[-1.0, 0.0]])

    assert result[0, 0] == pytest.approx(-1.0)


def test_matrix_shape_matches_input_sizes():
    embeddings_a = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    embeddings_b = [[1.0, 0.0], [0.0, 1.0]]

    result = cosine_similarity_matrix(embeddings_a, embeddings_b)

    assert result.shape == (3, 2)
    assert np.allclose(result[0], [1.0, 0.0])
    assert np.allclose(result[1], [0.0, 1.0])

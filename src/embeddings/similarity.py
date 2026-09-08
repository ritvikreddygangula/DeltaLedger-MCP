import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


def cosine_similarity_matrix(
    embeddings_a: list[list[float]], embeddings_b: list[list[float]]
) -> np.ndarray:
    """Returns a len(embeddings_a) x len(embeddings_b) matrix where entry
    [i, j] is the cosine similarity between embeddings_a[i] and embeddings_b[j].
    """
    return cosine_similarity(np.array(embeddings_a), np.array(embeddings_b))

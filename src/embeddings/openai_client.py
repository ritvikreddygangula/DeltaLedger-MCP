import tiktoken
from openai import OpenAI

DEFAULT_MODEL = "text-embedding-3-small"

# OpenAI's stated limit is 8192 tokens per embedding input; stay one under
# as a safety margin rather than sitting exactly on the boundary.
MAX_INPUT_TOKENS = 8191


def _truncate_to_token_limit(text: str, model: str) -> str:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    if len(tokens) <= MAX_INPUT_TOKENS:
        return text
    return encoding.decode(tokens[:MAX_INPUT_TOKENS])


def get_embeddings(
    texts: list[str], client: OpenAI | None = None, model: str = DEFAULT_MODEL
) -> list[list[float]]:
    """Section bodies (e.g. a full Risk Factors section) can easily exceed
    the embedding model's 8192-token input limit, so each text is truncated
    to a safe token count before being sent -- losing the tail of very long
    sections is an acceptable trade-off for this similarity-preview pipeline,
    not for the LLM-based classifier agents (a later Part), which will read
    full section text directly rather than through an embedding.
    """
    client = client or OpenAI()
    truncated = [_truncate_to_token_limit(t, model) for t in texts]
    response = client.embeddings.create(model=model, input=truncated)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]

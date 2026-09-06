from openai import OpenAI

DEFAULT_MODEL = "text-embedding-3-small"


def get_embeddings(
    texts: list[str], client: OpenAI | None = None, model: str = DEFAULT_MODEL
) -> list[list[float]]:
    client = client or OpenAI()
    response = client.embeddings.create(model=model, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]

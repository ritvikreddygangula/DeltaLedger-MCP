import logging
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..observability import log_event


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
def call_responses_parse(client: OpenAI, **kwargs: Any):
    """Retries transient failures (rate limits, network blips, occasional
    truncated/malformed JSON) up to 3 attempts before giving up. A
    transient failure that isn't retried gets silently swallowed by the
    caller's broad `except Exception: return []` fallback, turning a
    recoverable hiccup into a false "nothing material happened." Callers
    should still catch the final re-raised exception and degrade
    gracefully -- this only prevents discarding a call that would have
    succeeded on a second try.
    """
    return client.responses.parse(**kwargs)


def log_usage(logger: logging.Logger, event: str, response: Any, **fields: Any) -> None:
    """Logs token usage from a Responses API result, tolerating its absence
    -- `response.usage` is present on real API responses but callers may
    pass a test double that doesn't set it, so every field is optional.
    """
    usage = getattr(response, "usage", None)
    log_event(
        logger,
        event,
        input_tokens=getattr(usage, "input_tokens", None) if usage else None,
        output_tokens=getattr(usage, "output_tokens", None) if usage else None,
        total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        **fields,
    )

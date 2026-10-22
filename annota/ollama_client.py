"""Small dependency-free client for an optional local Ollama instance."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import OLLAMA_BASE_URL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Raised when Ollama cannot service a local preprocessing request."""


def _request(path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{OLLAMA_BASE_URL}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise OllamaError(f"Ollama request failed ({path}): {exc}") from exc


def status() -> dict[str, Any]:
    """Return availability and installed model names without raising."""
    try:
        result = _request("/api/tags")
        models = [m.get("name") for m in result.get("models", []) if m.get("name")]
        return {"available": True, "base_url": OLLAMA_BASE_URL, "models": models}
    except OllamaError as exc:
        return {"available": False, "base_url": OLLAMA_BASE_URL, "error": str(exc)}


def generate_json(
    model: str,
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.0,
) -> Any:
    """Generate and parse a JSON response from Ollama."""
    if not model:
        raise OllamaError("OLLAMA_LLM_MODEL is not configured")

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system
    result = _request("/api/generate", payload)
    text = str(result.get("response", "")).strip()
    if not text:
        raise OllamaError("Ollama returned an empty response")

    # Reasoning models may emit a private thought block before the JSON.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    # A few models still wrap JSON in a markdown fence despite format=json.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Ollama returned invalid JSON: {text[:240]}") from exc


def embed(model: str, inputs: list[str]) -> list[list[float]]:
    """Create embeddings, supporting both current and legacy Ollama endpoints."""
    if not model:
        raise OllamaError("OLLAMA_EMBED_MODEL is not configured")
    try:
        result = _request("/api/embed", {"model": model, "input": inputs})
        embeddings = result.get("embeddings")
        if embeddings:
            return embeddings
    except OllamaError:
        logger.debug("Current Ollama embedding endpoint failed; trying legacy endpoint")

    embeddings = []
    for value in inputs:
        result = _request("/api/embeddings", {"model": model, "prompt": value})
        vector = result.get("embedding")
        if not vector:
            raise OllamaError("Ollama returned no embedding")
        embeddings.append(vector)
    return embeddings

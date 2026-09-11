"""Minimal, safe client for a local Ollama server."""

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class LLMClient:
    """Call a configured local Ollama model without raising network errors."""

    base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    timeout_seconds: float = 90.0

    def check_available(self) -> bool:
        """Return whether Ollama is reachable and contains configured model."""
        try:
            payload = self._request("/api/tags", None, method="GET")
        except (HTTPError, OSError, URLError, ValueError):
            return False

        models = payload.get("models") if isinstance(payload, dict) else None
        return isinstance(models, list) and any(model.get("name") == self.model for model in models if isinstance(model, dict))

    def generate(self, prompt: str) -> str | None:
        """Generate text, returning None when local Ollama cannot serve request."""
        try:
            payload = self._request(
                "/api/generate",
                {"model": self.model, "prompt": prompt, "stream": False},
            )
        except (HTTPError, OSError, URLError, ValueError):
            return None

        response = payload.get("response") if isinstance(payload, dict) else None
        return response.strip() if isinstance(response, str) and response.strip() else None

    def _request(self, path: str, body: dict | None, method: str = "POST") -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            decoded = response.read().decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            raise ValueError("Ollama response must be a JSON object")
        return payload

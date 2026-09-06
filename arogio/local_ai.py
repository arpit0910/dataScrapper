"""Optional local Ollama integration for constrained extraction.

The model is an extraction aid only. Source fetching, validation, provenance,
and verification remain deterministic application responsibilities.
"""

import json
from urllib.error import URLError
from urllib.request import Request, urlopen


class LocalModelUnavailable(RuntimeError):
    pass


class OllamaExtractor:
    def __init__(self, model: str = "qwen2.5:3b", endpoint: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.endpoint = endpoint.rstrip("/")

    def is_available(self) -> bool:
        try:
            with urlopen(f"{self.endpoint}/api/tags", timeout=2) as response:
                return response.status == 200
        except (URLError, OSError):
            return False

    def model_available(self) -> bool:
        """Return whether Ollama is reachable and the configured model is installed."""
        try:
            with urlopen(f"{self.endpoint}/api/tags", timeout=2) as response:
                if response.status != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8"))
            return any(item.get("name") == self.model for item in payload.get("models", []))
        except (URLError, OSError, json.JSONDecodeError, AttributeError):
            return False

    def smoke_test(self) -> dict:
        """Run a tiny real extraction to prove the configured model can be used."""
        return self.extract("<h1>Example Hospital</h1><p>Phone: 0141-1234567</p>", ["name", "phone"])

    def extract(self, html: str, fields: list[str]) -> dict:
        if not self.is_available():
            raise LocalModelUnavailable("Ollama is not running at " + self.endpoint)
        prompt = (
            "Extract only explicitly stated values from this public webpage. "
            "Return one JSON object with exactly these keys: " + json.dumps(fields) + ". "
            "Use null when a value is absent or ambiguous. Never infer, translate, or fabricate values.\n\n"
            "HTML:\n" + html[:120000]
        )
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False, "format": "json"}).encode()
        request = Request(f"{self.endpoint}/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise LocalModelUnavailable(f"Local model request failed: {exc}") from exc
        try:
            result = json.loads(payload["response"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LocalModelUnavailable("Local model returned invalid JSON") from exc
        return {field: result.get(field) for field in fields}

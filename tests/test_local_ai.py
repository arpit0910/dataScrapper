import json

import pytest

from arogio.local_ai import LocalModelUnavailable, OllamaExtractor


def test_candidates_reject_invented_and_non_string_values(monkeypatch):
    model = OllamaExtractor()
    monkeypatch.setattr(model, "extract", lambda *args, **kwargs: {
        "name": "Example Hospital", "phone": "123456", "email": "invented@example.org",
        "website": {"url": "example.org"}, "address": "",
    })
    result = model.extract_tags({"name": "Example Hospital", "description": "Phone: 123456"})
    assert result == {"name": "Example Hospital", "phone": "123456", "email": None,
                      "website": None, "address": None}


def test_tag_extraction_constrains_model_to_source_values(monkeypatch):
    model = OllamaExtractor()
    captured = {}

    def extract(*args, **kwargs):
        captured.update(kwargs)
        return {"name": "Hospital"}

    monkeypatch.setattr(model, "extract", extract)
    model.extract_tags({"name": "Hospital", "official_name": "Hospital", "beds": 20})
    assert captured["allowed_values"] == ["Hospital"]


@pytest.mark.parametrize("value", [[], None, 42, "text"])
def test_extract_rejects_non_object_json(monkeypatch, value):
    model = OllamaExtractor()
    monkeypatch.setattr(model, "is_available", lambda: True)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({"response": json.dumps(value)}).encode()

    monkeypatch.setattr("arogio.local_ai.urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(LocalModelUnavailable, match="non-object"):
        model.extract("page", ["name"])

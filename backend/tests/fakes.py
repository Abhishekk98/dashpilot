"""Test doubles for the LLM layer (no network, no waiting)."""

from llm.base import LLMProvider


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, replies=None, errors=None, max_retries=2):
        super().__init__("fake-model", max_retries=max_retries, sleep=lambda s: self.sleeps.append(s))
        self.replies = list(replies or [])
        self.errors = list(errors or [])
        self.calls: list[dict] = []
        self.sleeps: list[float] = []

    def _next(self, **call):
        self.calls.append(call)
        if self.errors:
            raise self.errors.pop(0)
        return self.replies.pop(0)

    def _generate(self, prompt, system, json_schema):
        return self._next(prompt=prompt, system=system, json_schema=json_schema)

    def _analyze_image(self, image, prompt, mime_type, json_schema):
        return self._next(prompt=prompt, image=image, mime_type=mime_type, json_schema=json_schema)

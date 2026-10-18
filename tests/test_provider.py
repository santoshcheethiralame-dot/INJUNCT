"""Providers disagree about what a message's `content` is, and the model-driven
path had never been run against a real one - so a dict reached a regex three
frames away and took the whole benchmark down."""
import json

import pytest

from injunct import provider


def test_a_plain_string_is_left_alone():
    assert provider._text("hello") == "hello"


def test_cloudflare_returns_parsed_json_not_a_string():
    """The actual failure: Cloudflare hands back a dict when the model emits
    JSON, where OpenAI hands back a string."""
    assert provider._text({"tool": "done"}) == '{"tool": "done"}'
    assert json.loads(provider._text({"tool": "write_file", "path": "a.py"}))["tool"] == "write_file"


def test_a_list_of_parts_is_joined():
    assert provider._text([{"text": "ab"}, {"text": "cd"}]) == "abcd"


def test_nothing_becomes_empty_text_not_none():
    assert provider._text(None) == ""


@pytest.mark.parametrize("shape", ["str", {"tool": "done"}, [{"text": "x"}], None, 42])
def test_every_shape_comes_back_as_text(shape):
    assert isinstance(provider._text(shape), str)


def test_gemma_gets_its_instructions_in_the_user_turn(monkeypatch):
    """Gemma on the Gemini API rejects a system turn, so it must never be sent one."""
    monkeypatch.setattr(provider, "MODEL", "gemma-4-31b-it")
    msgs = provider._messages("the task", "the rules")
    assert [m["role"] for m in msgs] == ["user"]
    assert msgs[0]["content"].startswith("the rules") and msgs[0]["content"].endswith("the task")


def test_other_models_keep_the_system_role(monkeypatch):
    monkeypatch.setattr(provider, "MODEL", "qwen2.5-coder:7b")
    assert [m["role"] for m in provider._messages("t", "s")] == ["system", "user"]
    assert [m["role"] for m in provider._messages("t", "")] == ["user"]


def test_gemma_reasoning_is_stripped_before_anyone_parses_json():
    raw = '<thought>maybe {"template": "wrong"}?</thought>{"template": "co_change"}'
    assert provider._unthink(raw) == '{"template": "co_change"}'
    assert provider._unthink("plain") == "plain"


def test_a_server_error_is_retried_like_a_rate_limit(monkeypatch):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) < 2:
            raise provider.Unavailable("HTTP Error 500: Internal Server Error")
        return "ok"

    monkeypatch.setattr(provider, "_once", flaky)
    monkeypatch.setattr(provider.time, "sleep", lambda s: None)
    assert provider.chat("x") == "ok" and len(calls) == 2

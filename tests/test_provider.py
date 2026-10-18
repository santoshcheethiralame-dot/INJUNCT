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

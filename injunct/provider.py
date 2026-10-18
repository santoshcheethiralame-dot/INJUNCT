"""One OpenAI-compatible client. Ollama by default; any free tier by env var.

INJUNCT_BASE_URL  default http://localhost:11434/v1
INJUNCT_MODEL     default qwen2.5-coder:7b
INJUNCT_API_KEY   optional (Groq / Cerebras / OpenRouter / Gemini-compat)
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("INJUNCT_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL = os.environ.get("INJUNCT_MODEL", "qwen2.5-coder:7b")
KEY = os.environ.get("INJUNCT_API_KEY", "")

# Plenty of OpenAI-compatible endpoints sit behind Cloudflare, and Cloudflare
# rejects urllib's default "Python-urllib/3.12" on browser fingerprint alone -
# error 1010, a 403 that never reaches the API and looks exactly like a bad
# key. Sending an ordinary browser agent is the difference between "your
# credentials are wrong" and a working provider.
USER_AGENT = os.environ.get(
    "INJUNCT_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class Unavailable(RuntimeError):
    pass


def _text(content) -> str:
    """Every provider disagrees about what `content` is.

    OpenAI sends a string. Cloudflare sends a parsed dict when the model emits
    JSON. Others send a list of parts. Callers want text, so give them text
    rather than letting a dict reach a regex three frames later.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content)
    if content is None:
        return ""
    return json.dumps(content)


def chat(prompt: str, system: str = "", timeout: float = 30.0, temperature: float = 0.0,
         attempts: int = 4) -> str:
    """One completion, with backoff on a rate limit.

    Every free tier throttles, and a 429 that propagates as Unavailable makes
    the harness record a run in which the model was never asked anything. Those
    runs then score a pass, because an untouched repository passes its own
    oracle. Waiting is the honest response to being told to wait.
    """
    last: Exception | None = None
    for n in range(attempts):
        try:
            return _once(prompt, system, timeout, temperature)
        except Unavailable as e:
            last = e
            if "429" not in str(e) or n == attempts - 1:
                raise
            time.sleep(min(30.0, 3.0 * (2 ** n)))
    raise last if last else Unavailable("no attempt was made")


def _once(prompt: str, system: str = "", timeout: float = 30.0, temperature: float = 0.0) -> str:
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    body = json.dumps({"model": MODEL, "messages": msgs, "temperature": temperature}).encode()
    req = urllib.request.Request(f"{BASE}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json",
                                          "User-Agent": USER_AGENT,
                                          **({"Authorization": f"Bearer {KEY}"} if KEY else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _text(json.loads(r.read())["choices"][0]["message"]["content"])
    except (urllib.error.URLError, OSError, KeyError, json.JSONDecodeError) as e:
        raise Unavailable(str(e)) from e


def available(timeout: float = 25.0) -> bool:
    """Is there a model at the other end?

    The probe used to allow four seconds, which is under the cold-start time of
    every hosted provider - so a model that answers perfectly well was reported
    unreachable and `--live` refused to start. Refusing to run is the safe
    failure here, but only if it refuses for a true reason.
    """
    try:
        chat("ping", timeout=timeout)
        return True
    except Unavailable:
        return False

"""
llm_client.py
Single place for all model calls, with provider fallback.

Provider chain (tried in order, skipping any without a key set):
  1. GEMINI_API_KEY     -> Google AI Studio, gemini-2.5-flash
                           (free tier, key never expires, ~1500 req/day)
  2. OPENROUTER_API_KEY -> OpenRouter :free vision models
                           (50 req/day without credits - fallback only)
  3. GROQ_API_KEY       -> Groq (TEXT ONLY - Groq's free vision models were
                           deprecated in 2026; used for description parsing only)

Why this design: a single call site with automatic fallback means one bad
provider never takes the demo down, and keys are read fresh from env on every
call so a key set on Railway "just works" without code changes.

Models are overridable via env:
  GEMINI_MODEL             (default: gemini-2.5-flash)
  OPENROUTER_VISION_MODEL  (default: tries the candidate list below)
  GROQ_TEXT_MODEL          (default: llama-3.3-70b-versatile)
"""

from __future__ import annotations
import base64
import os

# OpenRouter free vision-capable candidates, tried in order.
# All handle plain text too, so the same list serves both call types.
_OPENROUTER_CANDIDATES = [
    "qwen/qwen2.5-vl-72b-instruct:free",
    "meta-llama/llama-4-maverick:free",
    "google/gemma-3-27b-it:free",
]


class AllProvidersFailed(RuntimeError):
    """Raised when every configured provider errored (or none is configured)."""


def _detect_mime_type(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


# -- Gemini ------------------------------------------------------------------

def _gemini_call(prompt: str, image_bytes: bytes | None) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    if image_bytes is not None:
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=_detect_mime_type(image_bytes)),
            prompt,
        ]
    else:
        contents = prompt

    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(temperature=0, max_output_tokens=4096),
    )
    if not resp.text:
        raise RuntimeError(f"Gemini returned empty response (model={model})")
    return resp.text


# -- OpenRouter ---------------------------------------------------------------

def _openrouter_call(prompt: str, image_bytes: bytes | None) -> str:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )

    if image_bytes is not None:
        data_uri = (
            f"data:{_detect_mime_type(image_bytes)};base64,"
            f"{base64.b64encode(image_bytes).decode()}"
        )
        content = [
            {"type": "image_url", "image_url": {"url": data_uri}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = prompt

    override = os.environ.get("OPENROUTER_VISION_MODEL")
    candidates = [override] if override else _OPENROUTER_CANDIDATES

    last_err: Exception | None = None
    for model in candidates:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=0,
                max_tokens=4096,
            )
            text = resp.choices[0].message.content
            if text:
                return text
            last_err = RuntimeError(f"empty response from {model}")
        except Exception as e:  # model gone / rate-limited -> try next candidate
            last_err = e
    raise RuntimeError(f"All OpenRouter models failed; last error: {last_err}")


# -- Groq (text only) ---------------------------------------------------------

def _groq_call(prompt: str, image_bytes: bytes | None) -> str:
    if image_bytes is not None:
        raise RuntimeError("Groq free tier no longer has a vision model (deprecated 2026)")
    from openai import OpenAI

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )
    resp = client.chat.completions.create(
        model=os.environ.get("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=4096,
    )
    return resp.choices[0].message.content


# -- Public API ----------------------------------------------------------------

_CHAIN = [
    ("gemini", "GEMINI_API_KEY", _gemini_call),
    ("openrouter", "OPENROUTER_API_KEY", _openrouter_call),
    ("groq", "GROQ_API_KEY", _groq_call),
]


def configured_providers() -> list[str]:
    return [name for name, key, _ in _CHAIN if os.environ.get(key)]


def _call(prompt: str, image_bytes: bytes | None) -> str:
    available = [(n, fn) for n, key, fn in _CHAIN if os.environ.get(key)]
    if not available:
        raise AllProvidersFailed(
            "No API key configured. Set GEMINI_API_KEY (recommended, free at "
            "https://aistudio.google.com/apikey) or OPENROUTER_API_KEY in .env / Railway variables."
        )

    errors: list[str] = []
    for name, fn in available:
        try:
            return fn(prompt, image_bytes)
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise AllProvidersFailed(
        "Every configured provider failed -> " + " | ".join(errors)
    )


def call_vision(image_bytes: bytes, prompt: str) -> str:
    """Send an image + prompt; returns raw model text."""
    return _call(prompt, image_bytes)


def call_text(prompt: str) -> str:
    """Send a text-only prompt; returns raw model text."""
    return _call(prompt, None)

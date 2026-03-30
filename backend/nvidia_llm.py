from __future__ import annotations

import os
from typing import Iterable

from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "tiiuae/falcon3-7b-instruct").strip()
NVIDIA_DEFAULT_TEMPERATURE = float(os.getenv("NVIDIA_TEMPERATURE", "0.2"))
NVIDIA_DEFAULT_TOP_P = float(os.getenv("NVIDIA_TOP_P", "0.7"))
NVIDIA_TIMEOUT_SECONDS = int(os.getenv("NVIDIA_TIMEOUT_SECONDS", "45"))

NVIDIA_API_KEYS = [
    "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",
    "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",
    "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",
    "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",
    "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",
    "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",
]


def _key_pool(extra_keys: Iterable[str] | None = None) -> list[str]:
    env_keys = [
        os.getenv("NVIDIA_API_KEY", "").strip(),
        os.getenv("NVIDIA_API_KEY_ALT_1", "").strip(),
        os.getenv("NVIDIA_API_KEY_ALT_2", "").strip(),
        os.getenv("NVIDIA_API_KEY_ALT_3", "").strip(),
        os.getenv("NVIDIA_API_KEY_ALT_4", "").strip(),
        os.getenv("NVIDIA_API_KEY_ALT_5", "").strip(),
    ]
    ordered = [*(extra_keys or []), *env_keys, *NVIDIA_API_KEYS]
    deduped: list[str] = []
    for key in ordered:
        if key and key not in deduped:
            deduped.append(key)
    return deduped


def request_nvidia_chat(
    *,
    prompt: str,
    system_prompt: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    top_p: float | None = None,
    timeout_seconds: int | None = None,
    extra_keys: Iterable[str] | None = None,
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_error = "NVIDIA API request failed"
    for api_key in _key_pool(extra_keys):
        client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=api_key,
            timeout=timeout_seconds or NVIDIA_TIMEOUT_SECONDS,
        )
        try:
            completion = client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=messages,
                temperature=NVIDIA_DEFAULT_TEMPERATURE if temperature is None else temperature,
                top_p=NVIDIA_DEFAULT_TOP_P if top_p is None else top_p,
                max_tokens=max_tokens,
                stream=False,
            )
            content = completion.choices[0].message.content or ""
            if content:
                return content
            last_error = "NVIDIA API response was empty"
        except Exception as exc:
            last_error = str(exc)
            continue
    raise ValueError(last_error)

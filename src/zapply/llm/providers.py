"""Provider adapters — the swappable half of the seam.

`CLAUDE.md` says the LLM must be wrapped "so the provider is swappable — I want to learn the
seam, not hardcode a vendor." This module is that seam made real. Each provider knows how to
talk to one vendor's API and returns the *same* normalised `LLMResponse`, so the rest of the
app (and the tracing) never sees a vendor-specific detail.

Two adapters cover almost everything:

* ``AnthropicProvider``        — the native Anthropic Messages API (Claude).
* ``OpenAICompatibleProvider`` — any endpoint that speaks the OpenAI chat protocol. That's
  Google Gemini (via its OpenAI-compatible endpoint), Groq, Ollama, OpenRouter, OpenAI
  itself — all one adapter, distinguished only by base URL + key + model.

The choice of which provider to build is data, resolved from config (see
``Settings.resolve_provider``). Adding a new vendor is: add a row to that resolver, maybe a
new adapter here — nothing in the business logic changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class LLMResponse:
    """Vendor-neutral result of one model call."""

    text: str | None = None
    tool_input: dict[str, Any] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None  # "stop"/"end_turn" = complete; "length"/"max_tokens" = truncated


@dataclass
class ProviderConfig:
    """Everything needed to construct a provider, resolved from settings."""

    kind: str  # "anthropic" | "openai_compatible"
    name: str  # human label, e.g. "gemini"
    api_key: str | None
    base_url: str | None
    model: str
    env_var: str  # which env var holds the key (for error messages)


class Provider(Protocol):
    """The contract every adapter satisfies."""

    name: str
    model: str

    def complete(
        self, prompt: str, *, system: str | None, max_tokens: int, temperature: float, model: str
    ) -> LLMResponse: ...

    def complete_structured(
        self,
        prompt: str,
        *,
        system: str | None,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> LLMResponse: ...


class AnthropicProvider:
    """Adapter for the native Anthropic Messages API (Claude)."""

    def __init__(self, config: ProviderConfig) -> None:
        from anthropic import Anthropic

        self.name = config.name
        self.model = config.model
        self._client = Anthropic(api_key=config.api_key)

    def complete(
        self, prompt: str, *, system: str | None, max_tokens: int, temperature: float, model: str
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
            **({"system": system} if system else {}),
        )
        text = "".join(
            getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
        ).strip()
        return LLMResponse(
            text=text,
            input_tokens=getattr(response.usage, "input_tokens", None),
            output_tokens=getattr(response.usage, "output_tokens", None),
            finish_reason=getattr(response, "stop_reason", None),
        )

    def complete_structured(
        self,
        prompt: str,
        *,
        system: str | None,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"name": tool_name, "description": tool_description, "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
            **({"system": system} if system else {}),
        )
        tool_input: dict[str, Any] | None = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                tool_input = dict(getattr(block, "input", {}))
                break
        return LLMResponse(
            tool_input=tool_input,
            input_tokens=getattr(response.usage, "input_tokens", None),
            output_tokens=getattr(response.usage, "output_tokens", None),
        )


class OpenAICompatibleProvider:
    """Adapter for any OpenAI-chat-compatible endpoint (Gemini, Groq, Ollama, OpenAI, ...)."""

    def __init__(self, config: ProviderConfig) -> None:
        from openai import OpenAI

        self.name = config.name
        self.model = config.model
        # A key is always passed; local servers (Ollama) accept any placeholder.
        self._client = OpenAI(api_key=config.api_key or "not-needed", base_url=config.base_url)

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _usage(response: Any) -> tuple[int | None, int | None]:
        usage = getattr(response, "usage", None)
        return (
            getattr(usage, "prompt_tokens", None) if usage else None,
            getattr(usage, "completion_tokens", None) if usage else None,
        )

    def complete(
        self, prompt: str, *, system: str | None, max_tokens: int, temperature: float, model: str
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=self._messages(prompt, system),
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        in_tok, out_tok = self._usage(response)
        return LLMResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            finish_reason=getattr(choice, "finish_reason", None),
        )

    def complete_structured(
        self,
        prompt: str,
        *,
        system: str | None,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=self._messages(prompt, system),
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool_description,
                        "parameters": schema,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            in_tok, out_tok = self._usage(response)
            return LLMResponse(
                tool_input=json.loads(tool_calls[0].function.arguments or "{}"),
                input_tokens=in_tok,
                output_tokens=out_tok,
            )

        # Some OpenAI-compatible endpoints (notably Gemini) intermittently ignore a forced
        # tool_choice and return prose instead — reliably so on longer inputs. Fall back to JSON
        # mode with the schema injected into the prompt, which is dependable across these APIs.
        return self._json_mode(prompt, system, schema, max_tokens, temperature, model)

    def _json_mode(
        self,
        prompt: str,
        system: str | None,
        schema: dict[str, Any],
        max_tokens: int,
        temperature: float,
        model: str,
    ) -> LLMResponse:
        instruction = (
            f"{prompt}\n\nReturn ONLY a single JSON object conforming to this JSON Schema "
            f"(no prose, no markdown fences):\n{json.dumps(schema)}"
        )
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=self._messages(instruction, system),
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        in_tok, out_tok = self._usage(response)
        return LLMResponse(
            tool_input=_loads_lenient(content), input_tokens=in_tok, output_tokens=out_tok
        )


def _loads_lenient(content: str) -> dict[str, Any] | None:
    """Parse a JSON object from model output, tolerating stray prose or ```json fences."""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def build_provider(config: ProviderConfig) -> Provider:
    """Factory: construct the right adapter for a resolved provider config."""
    if config.kind == "anthropic":
        return AnthropicProvider(config)
    if config.kind == "openai_compatible":
        return OpenAICompatibleProvider(config)
    raise ValueError(f"Unknown provider kind: {config.kind!r}")

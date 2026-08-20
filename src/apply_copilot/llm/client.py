"""Provider-agnostic LLM client.

This is the *seam*: every part of apply-copilot talks to the model through this class, never
through a vendor SDK directly. The client owns two responsibilities and delegates the third:

* **What to call** — two entry points cover everything downstream needs:
  ``complete(...)`` for free text, ``complete_structured(...)`` for a validated Pydantic
  object.
* **Observability** — every call is wrapped in a Langfuse generation span, uniformly.
* **Which vendor** — delegated to a `Provider` adapter (see `providers.py`), chosen from
  config. The client never knows whether it's talking to Gemini, Claude, or a local Ollama.

The structured path is a deliberately *minimal* seam using native tool/function calling —
Phase 2 is where structured extraction gets the full treatment (native vs. `instructor`,
retries, field-level evals). We build the entry point now and deepen it then.
"""

from __future__ import annotations

import warnings
from typing import TypeVar

from pydantic import BaseModel

from ..config import Settings, get_settings
from .providers import Provider, build_provider
from .tracing import Tracer, build_tracer

TModel = TypeVar("TModel", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when the model call fails or returns something unusable."""


# finish_reason values that mean "I ran out of token budget", across providers.
_TRUNCATED_REASONS = {"length", "max_tokens", "MAX_TOKENS"}


class LLMClient:
    """A thin, traced, provider-agnostic wrapper around a chat/completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        config = self.settings.resolve_provider()

        if not config.api_key and config.kind != "openai_compatible":
            raise LLMError(_missing_key_message(config.name, config.env_var))
        # OpenAI-compatible local servers (Ollama) don't need a real key, but hosted ones do.
        if not config.api_key and config.base_url and "localhost" not in config.base_url:
            raise LLMError(_missing_key_message(config.name, config.env_var))

        try:
            self.provider: Provider = build_provider(config)
        except Exception as exc:  # e.g. SDK not installed / bad config
            raise LLMError(f"Could not initialise provider {config.name!r}: {exc}") from exc

        self.provider_name = config.name
        self.model = config.model
        self.tracer: Tracer = build_tracer(self.settings)

    # -- free-text -------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> str:
        """Send a single-turn prompt and return the model's text response."""
        model = model or self.model
        with self.tracer.generation(
            name="llm.complete",
            model=model,
            input={"system": system, "prompt": prompt},
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
            metadata={"provider": self.provider_name},
        ) as span:
            try:
                result = self.provider.complete(
                    prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=model,
                )
            except Exception as exc:
                raise LLMError(f"{self.provider_name} call failed: {exc}") from exc

            span.record(
                output=result.text,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            if result.finish_reason in _TRUNCATED_REASONS:
                warnings.warn(
                    f"Response was truncated (finish_reason={result.finish_reason!r}); "
                    f"raise max_tokens. Note: 'thinking' models spend budget on hidden "
                    f"reasoning before the visible answer.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            return result.text or ""

    # -- structured ------------------------------------------------------------

    def complete_structured(
        self,
        prompt: str,
        response_model: type[TModel],
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> TModel:
        """Send a prompt and return output validated against a Pydantic model.

        Uses native tool/function calling: the model is handed the target schema as a single
        tool and forced to call it, so the arguments it produces *are* the structured output.
        We then validate them with Pydantic — the program, not the model, decides it's good.
        """
        model = model or self.model
        tool_name = _tool_name_for(response_model)
        with self.tracer.generation(
            name="llm.complete_structured",
            model=model,
            input={"system": system, "prompt": prompt, "schema": response_model.__name__},
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
            metadata={"provider": self.provider_name},
        ) as span:
            try:
                result = self.provider.complete_structured(
                    prompt,
                    system=system,
                    schema=response_model.model_json_schema(),
                    tool_name=tool_name,
                    tool_description=(response_model.__doc__ or "Return the extracted data.").strip(),
                    max_tokens=max_tokens,
                    temperature=temperature,
                    model=model,
                )
            except Exception as exc:
                raise LLMError(f"{self.provider_name} structured call failed: {exc}") from exc

            span.record(
                output=result.tool_input,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            if result.tool_input is None:
                raise LLMError(
                    f"{self.provider_name} returned no structured tool call for "
                    f"{response_model.__name__}."
                )
            try:
                return response_model.model_validate(result.tool_input)
            except Exception as exc:
                raise LLMError(
                    f"Model output did not validate against {response_model.__name__}: {exc}"
                ) from exc

    def flush(self) -> None:
        """Flush pending traces. Call before a short-lived process exits."""
        self.tracer.flush()


# -- helpers -------------------------------------------------------------------


def _tool_name_for(model: type[BaseModel]) -> str:
    """A stable tool name derived from the model class name."""
    return f"return_{model.__name__.lower()}"


def _missing_key_message(provider: str, env_var: str) -> str:
    return (
        f"No API key for provider {provider!r}. Set {env_var} in your .env "
        f"(copy .env.example to .env first)."
    )

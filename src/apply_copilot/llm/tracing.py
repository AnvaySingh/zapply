"""Langfuse tracing seam for the LLM client.

The whole point of Phase 0 is that *every* LLM call is observable from line one — so the
tracing lives here, wrapped around the client, rather than being sprinkled through business
logic later. Two design choices make this painless:

1. **Graceful no-op.** If Langfuse isn't configured (no keys) or fails to import, the tracer
   becomes a null object. Call sites don't branch on "is tracing on?" — they always open a
   generation span; it just does nothing when disabled. The app never breaks for lack of a
   telescope.
2. **A tiny uniform handle.** Whether tracing is on or off, the client gets back an object
   with the same `.record(...)` method, so there's exactly one code path.

Built against the Langfuse v3 (OpenTelemetry-based) Python SDK.
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterator

from ..config import Settings


class _NullSpan:
    """Stand-in generation handle used when tracing is disabled."""

    def record(self, **_: Any) -> None:  # noqa: D401 - trivial no-op
        return None

    @property
    def trace_id(self) -> str | None:
        return None


class _LangfuseSpan:
    """Adapter over a live Langfuse generation, exposing our uniform `.record()`."""

    def __init__(self, client: Any, generation: Any) -> None:
        self._client = client
        self._generation = generation

    def record(
        self,
        *,
        output: Any = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        usage: dict[str, int] = {}
        if input_tokens is not None:
            usage["input"] = input_tokens
        if output_tokens is not None:
            usage["output"] = output_tokens
        self._generation.update(output=output, usage_details=usage or None)

    @property
    def trace_id(self) -> str | None:
        # Valid only while the span is the current context.
        try:
            return self._client.get_current_trace_id()
        except Exception:  # pragma: no cover - defensive
            return None


class Tracer:
    """Thin wrapper over a Langfuse client (or nothing at all)."""

    def __init__(self, client: Any | None, host: str) -> None:
        self._client = client
        self._host = host

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @contextlib.contextmanager
    def generation(
        self,
        *,
        name: str,
        model: str,
        input: Any,
        model_parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[_NullSpan | _LangfuseSpan]:
        """Open a traced 'generation' span around one model call."""
        if self._client is None:
            yield _NullSpan()
            return
        kwargs = {
            "name": name,
            "model": model,
            "input": input,
            "model_parameters": model_parameters or {},
            "metadata": metadata or {},
        }
        # Langfuse v3 renamed the API; prefer the new one, fall back for older SDKs.
        if hasattr(self._client, "start_as_current_observation"):
            cm = self._client.start_as_current_observation(as_type="generation", **kwargs)
        else:  # pragma: no cover - older langfuse
            cm = self._client.start_as_current_generation(**kwargs)
        with cm as generation:
            yield _LangfuseSpan(self._client, generation)

    def flush(self) -> None:
        """Force pending events to Langfuse. Essential for short-lived CLI runs."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.flush()

    def trace_url(self, trace_id: str | None) -> str | None:
        if self._client is None or trace_id is None:
            return None
        with contextlib.suppress(Exception):
            return self._client.get_trace_url(trace_id=trace_id)
        return None


def build_tracer(settings: Settings) -> Tracer:
    """Construct a Tracer from settings, degrading to a no-op on any problem."""
    if not settings.tracing_enabled:
        return Tracer(None, settings.langfuse_host)
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return Tracer(client, settings.langfuse_host)
    except Exception as exc:  # pragma: no cover - defensive
        # A missing/broken telescope must never stop the work.
        import warnings

        warnings.warn(f"Langfuse tracing disabled: {exc!r}", RuntimeWarning, stacklevel=2)
        return Tracer(None, settings.langfuse_host)

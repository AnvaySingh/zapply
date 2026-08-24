"""Central configuration, loaded from the environment / a local `.env` file.

Everything the app needs to know about *where things live* and *which keys to use* lives
here, in one typed object. Nothing else in the codebase should read `os.environ` directly —
that keeps secrets in one place and makes the LLM client trivially testable.

The `LLM_PROVIDER` switch is the heart of the swappable seam: change one env var and the whole
app talks to a different vendor, with no code change. Default is Gemini's free tier.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from .llm.providers import ProviderConfig


class Settings(BaseSettings):
    """Typed view of the environment. Reads `.env` automatically (see `.env.example`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Which provider drives the LLM seam ---
    # One of: "gemini" (default, free), "anthropic", "openai" (any OpenAI-compatible endpoint).
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")

    # --- Google Gemini (free tier, via its OpenAI-compatible endpoint) ---
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.6-flash", alias="GEMINI_MODEL")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        alias="GEMINI_BASE_URL",
    )

    # --- Anthropic (Claude) ---
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-5", alias="ANTHROPIC_MODEL")

    # --- Generic OpenAI-compatible (OpenAI, Groq, Ollama, OpenRouter, ...) ---
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")

    # --- Langfuse (observability) ---
    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com", alias="LANGFUSE_HOST"
    )

    @property
    def tracing_enabled(self) -> bool:
        """Tracing turns on only when *both* Langfuse keys are present."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def resolve_provider(self) -> ProviderConfig:
        """Turn the `LLM_PROVIDER` switch into a concrete provider config.

        This is the single place that maps a provider name → (kind, key, base_url, model).
        Adding a vendor is a new branch here plus, if it speaks a new protocol, an adapter in
        `llm/providers.py`. Nothing else in the app changes.
        """
        from .llm.providers import ProviderConfig  # lazy: avoids an import cycle

        provider = self.llm_provider.strip().lower()
        if provider == "anthropic":
            return ProviderConfig(
                kind="anthropic",
                name="anthropic",
                api_key=self.anthropic_api_key,
                base_url=None,
                model=self.anthropic_model,
                env_var="ANTHROPIC_API_KEY",
            )
        if provider == "gemini":
            return ProviderConfig(
                kind="openai_compatible",
                name="gemini",
                api_key=self.gemini_api_key,
                base_url=self.gemini_base_url,
                model=self.gemini_model,
                env_var="GEMINI_API_KEY",
            )
        if provider == "openai":
            return ProviderConfig(
                kind="openai_compatible",
                name="openai",
                api_key=self.openai_api_key,
                base_url=self.openai_base_url,
                model=self.openai_model,
                env_var="OPENAI_API_KEY",
            )
        raise ValueError(
            f"Unknown LLM_PROVIDER {self.llm_provider!r}. "
            "Use one of: 'gemini', 'anthropic', 'openai'."
        )


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide singleton of the settings."""
    return Settings()

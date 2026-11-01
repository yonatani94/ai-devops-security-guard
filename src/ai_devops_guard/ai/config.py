"""Explicit provider selection. No secrets, dynamic imports, or automatic fallback."""

import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ai_devops_guard.ai.base import ExplanationProvider
from ai_devops_guard.models import Contract
from ai_devops_guard.storage import read_regular


class AISettings(Contract):
    provider: Literal["fake", "ollama", "openai-compatible"] = "fake"
    model: str | None = Field(default=None, max_length=120)
    timeout_seconds: float = Field(default=60, gt=0, le=180)
    endpoint: str | None = Field(default=None, max_length=500, repr=False)
    auth_mode: Literal["none", "bearer", "api-key"] = "none"
    schema_mode: Literal["json_schema", "json_object"] = "json_schema"
    token_parameter: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"
    max_output_tokens: int = Field(default=384, ge=64, le=4096)

    @field_validator("model")
    @classmethod
    def valid_model(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,120}", value):
            raise ValueError("invalid model or deployment identifier")
        return value

    @model_validator(mode="after")
    def provider_fields(self) -> "AISettings":
        if self.provider == "openai-compatible":
            if not self.endpoint or not self.model:
                raise ValueError("gateway provider requires an endpoint and explicit model")
        elif self.endpoint is not None or self.auth_mode != "none":
            raise ValueError("endpoint and authentication apply only to the gateway adapter")
        if self.provider == "fake" and self.model is not None:
            raise ValueError("fake provider has no model")
        if self.provider != "openai-compatible" and (
            self.schema_mode != "json_schema" or self.token_parameter != "max_completion_tokens"
        ):
            raise ValueError("gateway-only protocol options cannot configure a different adapter")
        return self


class GuardSettings(Contract):
    ai: AISettings


def load_settings(path: Path | None) -> AISettings:
    if path is None:
        return AISettings()
    data = tomllib.loads(read_regular(path, 16_384).decode("utf-8"))
    return GuardSettings.model_validate(data).ai


def create_provider(settings: AISettings) -> ExplanationProvider:
    # Registry changes are reviewed code changes, never an arbitrary import from config.
    from ai_devops_guard.ai.compatible import CompatibleProvider
    from ai_devops_guard.ai.fake import FakeProvider
    from ai_devops_guard.ai.ollama import OllamaProvider

    factories = {
        "fake": lambda: FakeProvider(),
        "ollama": lambda: OllamaProvider(
            settings.model or "qwen2.5:1.5b", settings.timeout_seconds, settings.max_output_tokens
        ),
        "openai-compatible": lambda: CompatibleProvider(settings),
    }
    provider = factories[settings.provider]()
    if not isinstance(provider, ExplanationProvider):
        raise ValueError("adapter does not implement the provider contract")
    if not provider.capabilities.structured_json:
        raise ValueError("adapter does not support validated structured output")
    if provider.status != "simulated" and not provider.capabilities.bounded_rule_lookup:
        raise ValueError("real adapter lacks bounded rule lookup")
    return provider

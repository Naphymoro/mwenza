from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelGatewayStatus:
    provider: str
    model: str
    configured: bool
    mode: str
    note: str


class ModelGateway:
    """Provider-neutral boundary for future model calls.

    The evidence engine remains usable without credentials. A later adapter
    can implement streaming/tool calls here while preserving the same policy
    and provenance contract.
    """

    def status(self) -> ModelGatewayStatus:
        provider = os.getenv("MWENZA_MODEL_PROVIDER", "none")
        model = os.getenv("MWENZA_MODEL_NAME", "grounded-deterministic")
        configured = provider not in {"", "none", "offline"}
        return ModelGatewayStatus(provider, model, configured, "provider-ready" if configured else "deterministic", "Model output must remain subordinate to retrieved evidence and citation validation.")

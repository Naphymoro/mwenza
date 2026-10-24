"""Model fallback for the mwenza agent: when the hosted model cannot answer, the turn continues on a local one.

Load it from DeerFlow's ``extensions_config.json`` after the constitution middleware, so it sits inside it and the
constitution's hidden revision prompt reaches whichever model answers::

    {"class": "mwenza_deerflow.routing:MwenzaModelFallbackMiddleware", "kwargs": {"fallback": "mwenza-local-14b"}}

A model call that fails because the provider is unreachable, over its limit (the mwenza-ai Worker's daily cap is a
429) or erroring is repeated once on the fallback model, and every later call in the same run goes straight to it.
Replies from the fallback carry ``additional_kwargs["mwenza_model"]`` so Mwenza can tell the student. It only ever
falls back from hosted to local: a run that already uses the fallback (a private thread) is left alone, so a failing
local model can never push a private conversation to a hosted one. This sits inside DeerFlow's
LLMErrorHandlingMiddleware, so it sees provider errors before DeerFlow retries them.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import openai
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

ROUTE_KEY = "mwenza_model"
UNAVAILABLE = (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError)


def model_id(model: Any) -> str | None:
    return getattr(model, "model_name", None) or getattr(model, "model", None)


def unavailable(exc: BaseException) -> bool:
    if isinstance(exc, UNAVAILABLE):
        return True
    return isinstance(exc, openai.APIStatusError) and (exc.status_code == 429 or exc.status_code >= 500)


class MwenzaModelFallbackMiddleware(AgentMiddleware):
    def __init__(self, fallback: str = "mwenza-local-14b", agents: list[str] | None = None) -> None:
        super().__init__()
        self.fallback = fallback
        self.agents = set(agents or ["mwenza"])
        self._model: Any = None
        self._lock = threading.Lock()
        self._fallen_back: dict[tuple[str, str], str] = {}

    def _fallback_model(self) -> Any:
        with self._lock:
            if self._model is None:
                from deerflow.models import create_chat_model  # the Gateway's own factory, so config and tracing match

                self._model = create_chat_model(self.fallback)
            return self._model

    def _usable_fallback(self, exc: BaseException) -> Any:
        """The fallback model, or the provider's original error if the fallback cannot be built."""
        try:
            return self._fallback_model()
        except Exception as build_error:
            raise exc from build_error

    @staticmethod
    def _key(request: ModelRequest) -> tuple[str, str]:
        context = getattr(request.runtime, "context", None) or {}
        return str(context.get("thread_id") or "default"), str(context.get("run_id") or "default")

    def _applies(self, request: ModelRequest) -> bool:
        context = getattr(request.runtime, "context", None) or {}
        if context.get("agent_name") not in self.agents:
            return False
        try:
            return model_id(request.model) != model_id(self._fallback_model())
        except Exception:  # fallback not buildable: use the run's model as usual; a failure then raises the original error
            return True

    def _mark(self, response: ModelResponse, reason: str) -> ModelResponse:
        marked = []
        for message in response.result:
            if isinstance(message, AIMessage):
                extra = dict(message.additional_kwargs or {})
                extra[ROUTE_KEY] = {"route": "local-fallback", "model": self.fallback, "reason": reason}
                message = message.model_copy(update={"additional_kwargs": extra})
            marked.append(message)
        return ModelResponse(result=marked, structured_response=response.structured_response)

    def _remember(self, request: ModelRequest, exc: BaseException) -> str:
        reason = type(exc).__name__
        with self._lock:
            self._fallen_back[self._key(request)] = reason
        logger.warning("Mwenza: hosted model unavailable (%s); continuing this run on %s", reason, self.fallback)
        return reason

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelCallResult:
        if not self._applies(request):
            return handler(request)
        reason = self._fallen_back.get(self._key(request))
        if reason is None:
            try:
                return handler(request)
            except Exception as exc:
                if not unavailable(exc):
                    raise
                reason = self._remember(request, exc)
                fallback = self._usable_fallback(exc)
        else:
            fallback = self._fallback_model()
        return self._mark(handler(request.override(model=fallback)), reason)

    async def awrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]) -> ModelCallResult:
        if not self._applies(request):
            return await handler(request)
        reason = self._fallen_back.get(self._key(request))
        if reason is None:
            try:
                return await handler(request)
            except Exception as exc:
                if not unavailable(exc):
                    raise
                reason = self._remember(request, exc)
                fallback = self._usable_fallback(exc)
        else:
            fallback = self._fallback_model()
        return self._mark(await handler(request.override(model=fallback)), reason)

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        context = getattr(runtime, "context", None) or {}
        with self._lock:
            self._fallen_back.pop((str(context.get("thread_id") or "default"), str(context.get("run_id") or "default")), None)
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self.after_agent(state, runtime)

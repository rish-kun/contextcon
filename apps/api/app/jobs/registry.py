"""Step handlers, registered by name.

    from app.jobs import StepContext, step_handler

    @step_handler("verify.identity")
    async def identify(ctx: StepContext) -> dict:
        ...
        return {"crustdata_company_id": "123"}

A handler must be idempotent: the worker may run it again after a crash or a lost
lease. Route paid calls through `ctx.cache` / `ctx.recorder` so a re-run replays
cached responses instead of paying twice, and write rows with natural keys
(e.g. `evidence.origin_key`) so a re-run upserts instead of duplicating.
"""

import importlib
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.jobs.engine import StepContext

Handler = Callable[["StepContext"], Awaitable[dict[str, Any] | None]]

log = logging.getLogger(__name__)

# Modules imported by `load_handlers()` so their decorators run. Pipeline packages
# that do not exist yet are skipped.
HANDLER_MODULES = ("app.pipelines.registry",)


async def noop(ctx: "StepContext") -> dict[str, Any]:
    """Does nothing. Useful as a barrier step other steps depend on."""
    return {}


class StepRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {"noop": noop}

    def register(self, name: str, handler: Handler, *, replace: bool = False) -> Handler:
        if name in self._handlers and not replace and self._handlers[name] is not handler:
            raise ValueError(f"step handler {name!r} is already registered")
        self._handlers[name] = handler
        return handler

    def handler(self, name: str, *, replace: bool = False) -> Callable[[Handler], Handler]:
        def decorate(fn: Handler) -> Handler:
            return self.register(name, fn, replace=replace)

        return decorate

    def get(self, name: str) -> Handler | None:
        return self._handlers.get(name)

    def names(self) -> list[str]:
        return sorted(self._handlers)


registry = StepRegistry()


def step_handler(name: str, *, replace: bool = False) -> Callable[[Handler], Handler]:
    """Register a handler in the default registry."""
    return registry.handler(name, replace=replace)


def load_handlers(modules: tuple[str, ...] = HANDLER_MODULES) -> StepRegistry:
    for module in modules:
        try:
            importlib.import_module(module)
        except ModuleNotFoundError as exc:
            if exc.name is None or not module.startswith(exc.name):
                raise
            log.info("handler module %s not present; skipping", module)
    return registry

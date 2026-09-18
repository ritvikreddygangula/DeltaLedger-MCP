import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mangum import Mangum
from mcp.server.transport_security import TransportSecuritySettings

from .mcp_server import mcp
from .rest import app as rest_app

# Must be created before the lifespan runs -- mcp.session_manager is only
# accessible after streamable_http_app() has been called at least once.
#
# transport_security disables DNS-rebinding protection, which defaults (via
# streamable_http_app's host="127.0.0.1" default) to only accepting Host
# headers matching localhost/127.0.0.1/::1 -- fine for local dev, but it
# rejects every real request once deployed, since API Gateway's hostname is
# never one of those. Confirmed live: a real mcp.Client against the
# deployed URL failed entirely (both server/discover and the initialize
# fallback got rejected) until this was added. DNS-rebinding protection is a
# browser-focused mitigation against a page tricking a victim's browser into
# reaching an otherwise-unreachable internal service; it protects nothing
# extra here, since this server is deliberately public and read-only (same
# reasoning already applied to opening the RDS security group -- see
# PROGRESS.md, Part 7), and the alternative (hardcoding today's
# CloudFormation-generated API Gateway hostname into allowed_hosts) would
# just break on the next stack recreation.
mcp_app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A mounted sub-app's own lifespan never runs automatically -- the
    # session manager has to be driven explicitly from the parent app. Used
    # for local uvicorn testing (`uvicorn src.api.lambda_handler:app`) --
    # uvicorn owns one event loop for the whole process and runs this
    # exactly once, which is exactly what StreamableHTTPSessionManager.run()
    # requires. NOT used by the real Lambda `handler` below -- see its
    # docstring for why.
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
# mcp_app already registers its own route at "/mcp" internally (confirmed by
# inspecting mcp_app.routes), so it mounts at "/" -- mounting it at "/mcp"
# would double it up into "/mcp/mcp". "/api" is registered first so it's
# matched before the catch-all root mount.
app.mount("/api", rest_app)
app.mount("/", mcp_app)

_mangum_handler: Mangum | None = None
_session_manager_cm: Any = None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Real Lambda entry point -- deliberately not `Mangum(app, lifespan="auto")`.

    Mangum's "auto"/"on" modes re-run the ASGI lifespan protocol on every
    single invocation (a fresh LifespanCycle is built inside its __call__),
    but StreamableHTTPSessionManager.run() can only be entered once per
    instance, ever. Confirmed live via CloudWatch logs after deploying with
    lifespan="auto": the first request on a warm container succeeded, and
    every request after it on that same container crashed with
    "StreamableHTTPSessionManager .run() can only be called once per
    instance."

    Mangum does reuse a single event loop across warm invocations (set up
    once in its __init__, not per __call__ -- confirmed by reading
    mangum/adapter.py), so the fix is to enter the session manager exactly
    once ourselves on that same loop, the first time this function actually
    runs, and tell Mangum not to touch lifespan at all. This has to be lazy
    (not run at module import time) because this same module is also
    imported directly by uvicorn for local testing, which needs the
    `lifespan` callback above instead -- uvicorn owns its own event loop,
    separate from whatever loop exists at plain import time, so eagerly
    entering the session manager here would either bind it to the wrong
    loop under uvicorn or double-enter it when uvicorn's own lifespan
    protocol then tries to run the callback above too.

    The context manager returned by mcp.session_manager.run() must be kept
    alive in a module-level variable, not just __aenter__'d inline -- it
    wraps a suspended async generator holding the live task group, and
    without a reference to it, it gets garbage collected right after
    __aenter__ returns, which tears the task group down again (confirmed by
    hitting "Task group is not initialized. Make sure to use run()." on the
    very next request when this was first written without storing it).
    """
    global _mangum_handler, _session_manager_cm
    if _mangum_handler is None:
        loop = asyncio.get_event_loop()
        _session_manager_cm = mcp.session_manager.run()
        loop.run_until_complete(_session_manager_cm.__aenter__())
        _mangum_handler = Mangum(app, lifespan="off")
    return _mangum_handler(event, context)

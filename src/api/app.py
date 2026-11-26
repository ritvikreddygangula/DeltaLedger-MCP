"""The deployed ASGI app: REST under /api, MCP (streamable HTTP) at /mcp.

Run locally:  uv run uvicorn src.api.app:app --port 8000
On Render:    see render.yaml (same command, with --host 0.0.0.0 --port $PORT)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from .db_pool import close_pool
from .mcp_server import mcp
from .rest import app as rest_app

# Must be created before the lifespan runs: mcp.session_manager only exists
# after streamable_http_app() has been called at least once.
#
# DNS-rebinding protection is off on purpose. Its default only accepts
# localhost Host headers, which rejects every real request once deployed
# behind Render's hostname. It's a browser-focused mitigation against a page
# reaching an otherwise-unreachable internal service, and protects nothing
# here: this server is deliberately public and read-only.
mcp_app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A mounted sub-app's own lifespan never runs automatically, so the MCP
    # session manager has to be driven from the parent app. uvicorn runs this
    # exactly once per process, which is exactly what
    # StreamableHTTPSessionManager.run() requires.
    async with mcp.session_manager.run():
        yield
    close_pool()


app = FastAPI(lifespan=lifespan)
# mcp_app registers its own "/mcp" route internally, so it mounts at "/".
# Mounting it at "/mcp" too would double it up into "/mcp/mcp". "/api" is
# registered first so it's matched before the catch-all root mount.
app.mount("/api", rest_app)
app.mount("/", mcp_app)

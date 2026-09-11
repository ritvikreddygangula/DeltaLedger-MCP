from contextlib import asynccontextmanager

from fastapi import FastAPI
from mangum import Mangum

from .mcp_server import mcp
from .rest import app as rest_app

# Must be created before the lifespan runs -- mcp.session_manager is only
# accessible after streamable_http_app() has been called at least once.
mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A mounted sub-app's own lifespan never runs automatically -- the
    # session manager has to be driven explicitly from the parent app.
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
# mcp_app already registers its own route at "/mcp" internally (confirmed by
# inspecting mcp_app.routes), so it mounts at "/" -- mounting it at "/mcp"
# would double it up into "/mcp/mcp". "/api" is registered first so it's
# matched before the catch-all root mount.
app.mount("/api", rest_app)
app.mount("/", mcp_app)

handler = Mangum(app, lifespan="auto")

"""Agent-side HTTP endpoint executing allowlisted actions dispatched by server."""

import time

from fastapi import Depends, FastAPI

from infraops.common.logging import setup_logger
from infraops.common.schemas import ActionRequest, ActionResponse
from infraops.server.security import verify_api_key
from infraops.server.sop.actions import execute_action

logger = setup_logger("infraops.agent.action_api")

app = FastAPI(title="InfraOps Agent Action API", version="0.1.0")


@app.post("/agent/action", response_model=ActionResponse, dependencies=[Depends(verify_api_key)])
def run_action(req: ActionRequest):
    """Execute an allowlisted remediation or diagnostic action locally on the agent host."""
    start = time.time()
    logger.info("Executing local agent action '%s'", req.action)
    try:
        output = execute_action(req.action, req.params)
        duration_ms = round((time.time() - start) * 1000.0, 2)
        return ActionResponse(ok=True, output=output, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = round((time.time() - start) * 1000.0, 2)
        logger.warning("Agent action '%s' failed: %s", req.action, e)
        return ActionResponse(ok=False, output=None, error=str(e), duration_ms=duration_ms)


def start_action_server(host: str = "127.0.0.1", port: int = 8099):
    """Start the action API server."""
    import uvicorn

    uvicorn.run("infraops.agent.action_api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    start_action_server()

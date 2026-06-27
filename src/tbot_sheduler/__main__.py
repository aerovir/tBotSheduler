"""Entry point: python -m tbot_sheduler"""
from __future__ import annotations

import uvicorn

from tbot_sheduler.app import create_app
from tbot_sheduler.core.config import LOG_LEVEL

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "tbot_sheduler.__main__:app",
        host="0.0.0.0",
        port=8000,
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )

from __future__ import annotations

import os

import uvicorn

from .app import create_app


def run() -> None:
    uvicorn.run(
        create_app(),
        host=os.getenv("COLDTH_HOST", "0.0.0.0"),
        port=int(os.getenv("COLDTH_PORT", "8080")),
    )


if __name__ == "__main__":
    run()

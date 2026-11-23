"""Entry point used by the launchers: python -m app.server"""
from __future__ import annotations

import logging

import uvicorn

from .config import get_settings
from .main import create_app


def main() -> None:
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(), host=s.host, port=s.port, log_level="info", proxy_headers=False)


if __name__ == "__main__":
    main()

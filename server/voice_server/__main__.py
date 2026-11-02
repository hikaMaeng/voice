"""`uv run voice-server [--host 127.0.0.1] [--port 8765]` — 기본은 이 기계에서만 열린다."""
from __future__ import annotations

import argparse
import os


def main() -> None:
    ap = argparse.ArgumentParser(prog="voice-server")
    ap.add_argument("--host", default=os.environ.get("VOICE_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("VOICE_PORT", "8765")))
    a = ap.parse_args()
    import uvicorn
    uvicorn.run("voice_server.app:app", host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()

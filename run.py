"""Start the Hospital Finder web app:   python run.py   [--config other.yaml] [--port 8000] [--no-browser]"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser


def main() -> int:
    ap = argparse.ArgumentParser(description="Hospital Finder")
    ap.add_argument("--config", help="path to a config yaml (default: config.yaml)")
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    try:
        import uvicorn
        from app.config import ConfigError, load_settings
        from app.main import create_app
    except ModuleNotFoundError as exc:
        print(f"\nMissing Python package: {exc.name}\nRun:  pip install -r requirements.txt\n")
        return 1

    try:
        settings = load_settings(args.config)
        app = create_app(args.config)
    except ConfigError as exc:
        print(f"\nConfiguration problem: {exc}\n")
        return 1

    host = args.host or settings.server.get("host", "127.0.0.1")
    port = args.port or int(settings.server.get("port", 8000))
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    print(f"\n  Hospital Finder  ->  {url}\n  (first start builds the road graph and can take a few minutes)\n")
    if settings.server.get("open_browser", True) and not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())

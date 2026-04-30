import os
import socket
import threading
import webbrowser
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.request import urlopen
from wsgiref.simple_server import WSGIServer, make_server

from app import DATA_DIR, UPLOAD_FOLDER, app


HOST = os.environ.get("SRC_PORTAL_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("SRC_PORTAL_PORT", "5050")))
AUTO_OPEN = os.environ.get("SRC_PORTAL_OPEN_BROWSER", "1") == "1"


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def ensure_runtime_folders():
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def app_is_healthy(host: str, port: int) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def open_browser_later(url: str):
    if not AUTO_OPEN:
        return

    def _open():
        webbrowser.open(url, new=2)

    timer = threading.Timer(1.2, _open)
    timer.daemon = True
    timer.start()


def main():
    ensure_runtime_folders()
    url = f"http://127.0.0.1:{PORT}/"

    if is_port_in_use(HOST, PORT):
        if app_is_healthy(HOST, PORT):
            open_browser_later(url)
            print("SRC Portal is already running. Opening it in your browser.")
            return
        print(f"Port {PORT} is already in use by another application.")
        return

    open_browser_later(url)

    with make_server(HOST, PORT, app, server_class=ThreadedWSGIServer) as server:
        app.config["SERVER_SHUTDOWN"] = server.shutdown
        print("SRC Portal is running.")
        print(f"Open: {url}")
        print("Press Ctrl+C to stop the portal.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping SRC Portal...")
        finally:
            app.config.pop("SERVER_SHUTDOWN", None)


if __name__ == "__main__":
    main()

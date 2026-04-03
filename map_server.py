import threading
import http.server
import socketserver
import os

MAP_PORT = 7870
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def init():
    os.makedirs(os.path.join(BASE_DIR, "map_output"), exist_ok=True)

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=BASE_DIR, **kwargs)
        def log_message(self, format, *args):
            pass

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    def serve():
        with ReusableTCPServer(("", MAP_PORT), QuietHandler) as httpd:
            httpd.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    print(f"Map server running on http://localhost:{MAP_PORT}")
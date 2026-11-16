#!/usr/bin/env python3
"""Raspberry Pi camera MJPEG stream. Open http://<pi>:8000/ in a browser.

GET /snap.jpg returns the latest frame immediately (for taking photos).
Also shows the camera on the Pi's own monitor when a desktop session is running.
"""
import io
import logging
import os
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2, Preview
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput

PORT = 8000
SIZE = (1280, 720)

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Pi Camera</title>
<style>body{margin:0;background:#111;display:flex;justify-content:center;align-items:center;height:100vh}
img{max-width:100%;max-height:100vh}</style></head>
<body><img src="stream.mjpg"></body></html>
"""


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            content = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/snap.jpg":
            with output.condition:
                frame = output.frame
            if frame is None:
                self.send_error(503, "No frame yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", len(frame))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(frame)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", 0)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception as e:
                logging.info("Client %s disconnected: %s", self.client_address, e)
        else:
            self.send_error(404)


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": SIZE}))

# Show on the Pi's monitor if the desktop (Wayland) is available.
runtime_dir = f"/run/user/{os.getuid()}"
if os.path.exists(f"{runtime_dir}/wayland-0"):
    os.environ.setdefault("XDG_RUNTIME_DIR", runtime_dir)
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    try:
        picam2.start_preview(Preview.QTGL, width=SIZE[0], height=SIZE[1])
    except Exception as e:
        logging.warning("Monitor preview unavailable: %s", e)

output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))
if "AfMode" in picam2.camera_controls:
    picam2.set_controls({"AfMode": 2})  # continuous autofocus (Camera Module 3)

try:
    print(f"Streaming on port {PORT}")
    StreamingServer(("", PORT), StreamingHandler).serve_forever()
finally:
    picam2.stop_recording()

"""HTTP server supporting RFC 7233 Range Requests for CheerpJ web artifacts."""

from __future__ import annotations

import http.server
import os
import re
from pathlib import Path
from typing import Optional, Tuple, Union


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler supporting HTTP Range Requests (206 Partial Content)."""

    protocol_version = "HTTP/1.1"

    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def parse_byte_range(self, range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
        """Parse 'Range: bytes=start-end' into inclusive (start, end) offsets."""
        match = re.match(r"^bytes=(\d*)-(\d*)$", range_header.strip())
        if not match:
            return None

        start_str, end_str = match.groups()
        if not start_str and not end_str:
            return None

        if start_str:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
        else:
            length = int(end_str)
            if length <= 0:
                return None
            start = max(0, file_size - length)
            end = file_size - 1

        if start >= file_size or start > end:
            return None

        return start, min(end, file_size - 1)

    def send_head(self):
        """Handle GET/HEAD, including directory index resolution and Range requests."""
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            parts = self.path.split("?")
            if not parts[0].endswith("/"):
                self.send_response(301)
                new_parts = (parts[0] + "/",) + parts[1:]
                self.send_header("Location", "?".join(new_parts))
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            for index in ("index.html", "index.htm"):
                index_path = os.path.join(path, index)
                if os.path.exists(index_path):
                    path = index_path
                    break
            else:
                return self.list_directory(path)

        ctype = self.guess_type(path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            file_size = fs.st_size
            range_header = self.headers.get("Range")

            if range_header:
                byte_range = self.parse_byte_range(range_header, file_size)
                if byte_range is None:
                    self.send_response(416, "Range Not Satisfiable")
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    f.close()
                    return None

                start, end = byte_range
                content_length = (end - start) + 1
                self.send_response(206, "Partial Content")
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.end_headers()
                f.seek(start)
                return RangeFileWrapper(f, content_length)

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except Exception:
            f.close()
            raise

    def log_message(self, format: str, *args) -> None:
        if os.environ.get("PROVIKOM_HTTP_LOG") == "1":
            super().log_message(format, *args)


class RangeFileWrapper:
    """Wrap an open binary file and read exactly `length` bytes."""

    def __init__(self, file_obj, length: int):
        self.file_obj = file_obj
        self.remaining = length

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        if size < 0 or size > self.remaining:
            size = self.remaining
        chunk = self.file_obj.read(size)
        self.remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self.file_obj.close()


def run_server(directory: Union[str, Path], port: int = 8080, host: str = "0.0.0.0") -> None:
    """Run a standalone HTTP server with Range Request support."""
    directory = str(Path(directory).resolve())

    class DirectoryHandler(RangeRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

    server = http.server.ThreadingHTTPServer((host, port), DirectoryHandler)
    print(f"Serving '{directory}' at http://localhost:{port} (Range Requests enabled)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server.server_close()

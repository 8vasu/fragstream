#!/usr/bin/python3
# fragstream - Run a Shadertoy style fragment shader: serve it live to a browser, or render it without a display to an image, a video or timings
# Copyright (C) 2026 Soumendra Ganguly

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Run a Shadertoy style fragment shader: serve it live to a browser, or render it without a display to an image, a video or timings."""

import argparse
import http.server
import inspect
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, get_args
from urllib.parse import urlsplit

import numpy as np
from PIL import Image
from wgpu_shadertoy import Shadertoy

# --- names and paths -------------------------------------------------------
PROG = os.path.basename(sys.argv[0])  # invoked name, tracks renames
HERE = Path(__file__).resolve().parent
PAGE = HERE / "index.html"

# --- frames ----------------------------------------------------------------
SIZE = (256, 144)
SIZE_SEP = "x"
SIZE_TEXT = SIZE_SEP.join(map(str, SIZE))  # SIZE as text, which argparse parses like any value typed on the command line
FPS = 30
SECONDS = 5.0
START = 0.0
FIRST_FRAME = 0
RGB_CHANNELS = 3
RGBA_CHANNELS = 4
MS = 1000

# --- finding out which order the GPU hands the channels back in ------------
PROBE_RGBA = (0.9, 0.6, 0.3, 1.0)  # alpha, red, green, blue in falling order, so ranking a pixel names its channels
PROBE_SHADER = f"void mainImage(out vec4 c, in vec2 p) {{ c = vec4{PROBE_RGBA}; }}"
PROBE_SIZE = (16, 16)
PROBE_PIXEL = (0, 0)
ALPHA_RANK = 1  # alpha is the largest value, so the colour channels follow it

# --- the video encoder -----------------------------------------------------
ENCODER = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "{size}",
           "-r", "{fps}", "-i", "-", "-pix_fmt", "yuv420p", "{out}"]

# --- serving the live page -------------------------------------------------
HOST = "127.0.0.1"
PORT = 8000
PAGE_ROUTE = "/"
SHADER_ROUTE = "/shader"  # what the page fetches, whichever file is served
SIZE_ROUTE = "/size"      # the frame size the page starts with
HTML = "text/html; charset=utf-8"
TEXT = "text/plain; charset=utf-8"
CONTENT_TYPE = "Content-Type"
CONTENT_LENGTH = "Content-Length"
CACHE_CONTROL = ("Cache-Control", "no-store")  # an edited shader shows on the next load
STATUS_OK = 200
STATUS_MISSING = 404

# --- command line ----------------------------------------------------------
FLAG = "--{}"
UNDERSCORE = "_"
DASH = "-"

# --- messages --------------------------------------------------------------
ERR_PREFIX = "error: "
SAVED_PREFIX = "saved: "
BENCH_LINE = "{count} frames at {width}x{height}: {ms:.2f} ms per frame, {fps:.1f} frames per second"
ADDRESS = "http://{host}:{port}/"  # the only thing serving prints, for a person or a script to pick up


# --- helpers ---------------------------------------------------------------
class RenderError(Exception):
    """A user-facing error."""


def fail(msg):
    """Raise a RenderError carrying msg."""
    raise RenderError(msg)


def ensure(ok, msg):
    """Raise a RenderError carrying msg unless ok."""
    ok or fail(msg)


def flag(name):
    """Return the option that a parameter name gives: underscores become dashes."""
    return FLAG.format(name.replace(UNDERSCORE, DASH))


def dimensions(text):
    """Return the width and height that a text of sizes joined by the separator names."""
    try:
        size = tuple(int(part) for part in text.split(SIZE_SEP))
    except ValueError:
        fail(f"size must be {len(SIZE)} whole numbers joined by {SIZE_SEP!r}, got {text}")
    ensure(len(size) == len(SIZE) and min(size) > 0, f"size must be {len(SIZE)} positive numbers, got {text}")

    return size


Size = Annotated[dimensions, f"frame size as WIDTH{SIZE_SEP}HEIGHT"]


# --- drawing ---------------------------------------------------------------
def read_shader(path):
    """Return the source of the shader file at path."""
    ensure(path.is_file(), f"shader not found: {path}")

    return path.read_text()


def raw_frame(shadertoy, size, seconds=START, number=FIRST_FRAME):
    """Return one frame as the GPU hands it back, channels in the GPU's own order."""
    data = shadertoy.snapshot(time_float=seconds, frame=number)

    return np.asarray(data, dtype=np.uint8).reshape(*size[::-1], RGBA_CHANNELS)


def channel_order():
    """Return the positions of red, green and blue among the channels the GPU hands back."""
    # draw a colour whose channels differ, then read its ranking off one pixel
    probe = Shadertoy(PROBE_SHADER, resolution=PROBE_SIZE, offscreen=True)
    pixel = raw_frame(probe, PROBE_SIZE)[PROBE_PIXEL].astype(int)

    return np.argsort(-pixel)[ALPHA_RANK:ALPHA_RANK + RGB_CHANNELS]


def renderer(path, size):
    """Return a function drawing the shader's frame at a time and frame number as RGB pixels."""
    shadertoy = Shadertoy(read_shader(path), resolution=size, offscreen=True)
    order = channel_order()

    def draw(seconds, number):
        """Return the frame at this time and frame number."""
        return raw_frame(shadertoy, size, seconds, number)[..., order]

    return draw


def sequence(draw, count, fps):
    """Yield the first count frames of a video at fps."""
    for number in range(count):
        yield draw(number / fps, number)


def encode(pictures, out, size, fps):
    """Write the pictures as a video file at out."""
    command_line = [part.format(size=SIZE_SEP.join(map(str, size)), fps=fps, out=out) for part in ENCODER]

    # a missing encoder is a clean user error, not a traceback
    try:
        encoder = subprocess.Popen(command_line, stdin=subprocess.PIPE)
    except FileNotFoundError:
        fail(f"command not found: {command_line[0]}")

    # feed the pictures; an encoder that stops early is reported through its exit status
    try:
        with encoder.stdin:
            for picture in pictures:
                encoder.stdin.write(picture.tobytes())
    except BrokenPipeError:
        pass
    ensure(encoder.wait() == 0, f"{command_line[0]} failed")


# --- outputs ---------------------------------------------------------------
def write(shader, out, size, at, seconds, fps):
    """Write the shader to out: one frame if the suffix is one of an image, otherwise a video."""
    draw = renderer(shader, size)
    out.parent.mkdir(parents=True, exist_ok=True)

    # an image takes the frame at one time, a video takes every frame of its length
    if out.suffix.lower() in Image.registered_extensions():
        Image.fromarray(draw(at, round(at * fps))).save(out)
    else:
        encode(sequence(draw, round(seconds * fps), fps), out, size, fps)
    print(f"{SAVED_PREFIX}{out}")


def time_frames(shader, count, size, fps):
    """Print how long drawing a frame takes, reading each one back."""
    draw = renderer(shader, size)

    # the first frame pays for setting up, so it stays out of the timing
    draw(START, FIRST_FRAME)
    began = time.perf_counter()
    for _ in sequence(draw, count, fps):
        pass
    elapsed = time.perf_counter() - began

    print(BENCH_LINE.format(count=count, width=size[0], height=size[1],
                            ms=MS * elapsed / count, fps=count / elapsed))


def handler_for(shader, size):
    """Return a request handler class that answers with the page, the frame size and the shader as it is on disk at that moment."""
    routes = {PAGE_ROUTE: (PAGE.read_bytes, HTML),
              SHADER_ROUTE: (shader.read_bytes, TEXT),
              SIZE_ROUTE: (lambda: SIZE_SEP.join(map(str, size)).encode(), TEXT)}

    class Handler(http.server.BaseHTTPRequestHandler):
        """Answers each request from the source of its route."""

        def do_GET(self):
            """Answer one request, or report that its route is unknown or its file has gone."""
            try:
                read, kind = routes[urlsplit(self.path).path]
                body = read()
            except (KeyError, OSError):
                self.send_error(STATUS_MISSING)

                return

            self.send_response(STATUS_OK)
            self.send_header(CONTENT_TYPE, kind)
            self.send_header(CONTENT_LENGTH, str(len(body)))
            self.send_header(*CACHE_CONTROL)
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(shader, host, port, size):
    """Serve the page that runs the shader live in a browser, until interrupted."""
    # a port that is taken is a clean user error, not a traceback
    try:
        server = http.server.ThreadingHTTPServer((host, port), handler_for(shader, size))
    except OSError as error:
        fail(f"cannot listen on {host}:{port}: {error}")

    # the address is read back from the server, since a port left to the system is only known now
    print(ADDRESS.format(host=host, port=server.server_address[1]), flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# --- driving ---------------------------------------------------------------
def run(in_file: Annotated[Path, "Shadertoy style fragment shader file"],
        out_host: Annotated[str, "address to serve the live page on"] = HOST,
        out_port: Annotated[int, "port to serve the live page on, or 0 to let the system pick a free one"] = PORT,
        out_res: Size = SIZE_TEXT,
        out_file: Annotated[Path, "file to write instead of serving: an image suffix gives one frame, any other a video"] = None,
        at: Annotated[float, "seconds into the shader at which the image is taken"] = START,
        seconds: Annotated[float, "length of the video in seconds"] = SECONDS,
        fps: Annotated[int, "frames per second of the video"] = FPS,
        bench: Annotated[int, "time this many frames instead of serving"] = None):
    """Serve the shader live, write it to a file, or time it, depending on the options given."""
    ensure(in_file.is_file(), f"shader not found: {in_file}")
    ensure(out_file is None or bench is None, "choose either a file to write or frames to time, not both")

    # the output follows from the options given
    if out_file is not None:
        write(in_file, out_file, out_res, at, seconds, fps)
    elif bench is not None:
        time_frames(in_file, bench, out_res, fps)
    else:
        serve(in_file, out_host, out_port, out_res)


def add_arguments(parser, func):
    """Add the parameters of func to parser: those without a default as positional arguments, the others as options."""
    for p in inspect.signature(func).parameters.values():
        tp, help_text = get_args(p.annotation)
        positional = p.default is p.empty
        names = [p.name] if positional else [flag(p.name)]
        extra = {} if positional else dict(default=p.default)
        parser.add_argument(*names, **dict(type=tp, help=help_text), **extra)


def main(argv):
    """Build the command line from the parameters of run, then run it with what was given."""
    parser = argparse.ArgumentParser(prog=PROG, description=__doc__,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    add_arguments(parser, run)
    run(**vars(parser.parse_args(argv)))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except RenderError as error:
        sys.exit(f"{ERR_PREFIX}{error}")

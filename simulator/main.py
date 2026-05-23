"""Simulator entrypoint.

Builds the FastAPI app, runs the asyncio render loop, and pipes frames
into ffmpeg for HLS delivery. Render reads and API writes share a single
asyncio.Lock on Scene.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import build_router
from .render import render_frame
from .scene import FIELD_H, FIELD_W, Scene
from .stream import HLSStreamer


FPS = 25
HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
HLS_DIR = HERE / "hls"


async def render_loop(scene: Scene, streamer: HLSStreamer) -> None:
    frame_interval = 1.0 / FPS
    last = time.perf_counter()
    while True:
        await asyncio.sleep(frame_interval)
        now = time.perf_counter()
        dt = now - last
        last = now
        try:
            async with scene.lock:
                scene.step(dt)
                frame = render_frame(scene)
            await streamer.push_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # don't kill the loop on a single bad frame
            print(f"[render_loop] {type(e).__name__}: {e}")


def create_app() -> FastAPI:
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    scene = Scene()
    streamer = HLSStreamer(FIELD_W, FIELD_H, FPS, HLS_DIR)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        streamer.start()
        task = asyncio.create_task(render_loop(scene, streamer))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            streamer.stop()

    app = FastAPI(title="HHBot Simulator", lifespan=lifespan)
    app.include_router(build_router(scene))
    app.mount("/hls", StaticFiles(directory=str(HLS_DIR)), name="hls")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app


app = create_app()


def run() -> None:
    host = os.environ.get("SIMULATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("SIMULATOR_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()

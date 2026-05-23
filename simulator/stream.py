"""HLS (H.264) streamer: raw BGR frames → ffmpeg → playlist.m3u8 + .ts.

The ffmpeg subprocess does the H.264 encoding and HLS segmenting; we just
pipe BGR bytes in. Frame writes are pushed to a thread executor so the
asyncio loop never blocks on pipe back-pressure.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import numpy as np


class HLSStreamer:
    def __init__(self, width: int, height: int, fps: int, out_dir: Path) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.out_dir = out_dir
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "ffmpeg not found on PATH. Install it (macOS: `brew install ffmpeg`) and retry."
            )
        self.out_dir.mkdir(parents=True, exist_ok=True)
        # Clean stale segments so the playlist starts fresh
        for p in self.out_dir.glob("*.ts"):
            p.unlink(missing_ok=True)
        playlist = self.out_dir / "playlist.m3u8"
        playlist.unlink(missing_ok=True)

        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning",
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-g", str(self.fps),
            "-keyint_min", str(self.fps),
            "-sc_threshold", "0",
            "-hls_time", "1",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments+independent_segments+omit_endlist",
            "-hls_segment_filename", str(self.out_dir / "seg_%05d.ts"),
            "-f", "hls",
            str(playlist),
        ]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    async def push_frame(self, frame: np.ndarray) -> None:
        if self.proc is None or self.proc.stdin is None:
            return
        data = frame.tobytes()
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self.proc.stdin.write, data)
        except (BrokenPipeError, ValueError):
            # ffmpeg exited under us — stop trying; lifespan will clean up
            self.proc = None

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None

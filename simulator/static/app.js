// Test page wiring: HLS player + mode-driven clicks + state polling.

const FIELD_W = 1280;
const FIELD_H = 720;
const STREAM_URL = "/hls/playlist.m3u8";

const video = document.getElementById("video");
const modeButtons = document.querySelectorAll("#modes button");
const cmdButtons = document.querySelectorAll(".controls button");
const modeLabel = document.getElementById("mode-label");
const timerEl = document.getElementById("timer");
const stateEl = document.getElementById("state-json");
const tagValueInput = document.getElementById("tag-value");

let mode = "move1";

function setMode(m, labelText) {
  mode = m;
  modeButtons.forEach((b) => b.classList.toggle("active", b.dataset.mode === m));
  modeLabel.textContent = labelText || m;
}

modeButtons.forEach((b) => {
  b.addEventListener("click", () => setMode(b.dataset.mode, b.textContent));
});

async function fire(path) {
  try {
    const r = await fetch(path);
    const j = await r.json().catch(() => ({}));
    console.log(path, j);
  } catch (e) {
    console.error(path, e);
  }
}

cmdButtons.forEach((b) => {
  b.addEventListener("click", () => fire(b.dataset.cmd));
});

video.addEventListener("click", (e) => {
  const rect = video.getBoundingClientRect();
  // Video wrap is locked to 16:9 and source is 16:9, so the rect maps
  // 1:1 to the canvas — no letterboxing math needed.
  const sx = FIELD_W / rect.width;
  const sy = FIELD_H / rect.height;
  const x = Math.round((e.clientX - rect.left) * sx);
  const y = Math.round((e.clientY - rect.top) * sy);
  if (x < 0 || y < 0 || x > FIELD_W || y > FIELD_H) return;

  if (mode === "move1") fire(`/robot/1/move?x=${x}&y=${y}`);
  else if (mode === "move2") fire(`/robot/2/move?x=${x}&y=${y}`);
  else if (mode === "tag") {
    const v = parseInt(tagValueInput.value, 10) || 1;
    fire(`/tag/add?x=${x}&y=${y}&value=${v}`);
  }
});

// HLS setup — Safari plays natively; everyone else needs hls.js.
function attachHls() {
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = STREAM_URL;
    return;
  }
  if (window.Hls && window.Hls.isSupported()) {
    const hls = new window.Hls({ liveSyncDuration: 2, lowLatencyMode: true });
    hls.loadSource(STREAM_URL);
    hls.attachMedia(video);
    hls.on(window.Hls.Events.ERROR, (_, data) => {
      // Retry on fatal errors while ffmpeg warms up on first load
      if (data.fatal) {
        setTimeout(() => { hls.destroy(); attachHls(); }, 1500);
      }
    });
  }
}
attachHls();

// Live state panel: poll /state at 2 Hz
async function poll() {
  try {
    const r = await fetch("/state");
    const j = await r.json();
    timerEl.textContent = j.game.running
      ? `${j.game.time_left.toFixed(1)}s`
      : `${j.game.time_left.toFixed(1)}s (paused)`;
    stateEl.textContent = JSON.stringify(j, null, 2);
  } catch (e) {
    // tolerate transient errors silently
  }
}
setInterval(poll, 500);
poll();

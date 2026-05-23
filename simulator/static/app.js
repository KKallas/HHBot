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
// We surface every failure on the page itself so a black <video> never
// leaves us guessing whether the stream, the player, or autoplay is at fault.
const statusEl = document.getElementById("stream-status");

function setStatus(text, kind) {
  if (!statusEl) return;
  if (!text) { statusEl.classList.add("hidden"); return; }
  statusEl.classList.remove("hidden");
  statusEl.classList.toggle("error", kind === "error");
  statusEl.textContent = text;
}

function tryPlay() {
  // Some Chromium contexts (cross-origin iframe, fresh tab, no user
  // interaction yet) reject muted autoplay. The native controls give a
  // fallback button if this rejects.
  const p = video.play();
  if (p && typeof p.catch === "function") {
    p.catch((err) => setStatus(`Autoplay blocked — click ▶ on the video. (${err.message || err.name})`, "error"));
  }
}

let retries = 0;
function attachHls() {
  setStatus("Connecting to stream…");
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = STREAM_URL;
    video.addEventListener("playing", () => setStatus(""), { once: true });
    tryPlay();
    return;
  }
  if (!window.Hls) {
    setStatus("hls.js failed to load (CDN blocked?). Hard-refresh, or bundle hls.js locally.", "error");
    return;
  }
  if (!window.Hls.isSupported()) {
    setStatus("This browser can't play HLS (no MSE support).", "error");
    return;
  }
  const hls = new window.Hls({ liveSyncDuration: 2, lowLatencyMode: false });
  hls.loadSource(STREAM_URL);
  hls.attachMedia(video);
  hls.on(window.Hls.Events.MANIFEST_PARSED, () => tryPlay());
  hls.on(window.Hls.Events.FRAG_LOADED, () => setStatus(""));
  hls.on(window.Hls.Events.ERROR, (_, data) => {
    if (!data.fatal) return;
    retries += 1;
    if (retries > 8) {
      setStatus(`Stream error after ${retries} retries: ${data.type}/${data.details}`, "error");
      return;
    }
    setStatus(`Stream warming up (${data.details})… retry ${retries}`);
    setTimeout(() => { hls.destroy(); attachHls(); }, 1200);
  });
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

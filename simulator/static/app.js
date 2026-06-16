// Test page wiring: HLS player + mode-driven clicks + state polling.
//
// Canvas math: the rendered stream is CANVAS_W x CANVAS_H pixels. The top
// FIELD_H pixels are the top-down field (1 px = 1 mm); the bottom strip is
// the Z viz panel. Clicks inside the top-down map directly to world mm.
// Clicks inside the side strip are ignored.

const FIELD_W_MM = 700;
const FIELD_H_MM = 394;
const CANVAS_W = FIELD_W_MM;
const CANVAS_H = FIELD_H_MM;

// Default Z for click-driven move commands. The test page is a primitives
// tester — descend/ascend cycles are scripted in Python by the player.
let CLICK_Z = 55.25;                   // Z_safe in mm (overridden by /state at boot)

const STREAM_URL = "/hls/playlist.m3u8";

const video = document.getElementById("video");
const clickPad = document.getElementById("click-pad");
const playOverlay = document.getElementById("play-overlay");
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

// Clicks land on #click-pad (transparent overlay), not on <video>, so the
// browser's built-in play/pause toggle never sees them.
clickPad.addEventListener("click", (e) => {
  const rect = clickPad.getBoundingClientRect();
  // Pad spans the whole canvas (top-down + side strip). Translate from
  // display pixels to canvas pixels (1 px = 1 mm in the top-down panel).
  const sx = CANVAS_W / rect.width;
  const sy = CANVAS_H / rect.height;
  const px_x = (e.clientX - rect.left) * sx;
  const px_y = (e.clientY - rect.top) * sy;

  if (px_x < 0 || px_y < 0 || px_x > FIELD_W_MM || px_y > FIELD_H_MM) return;

  const x_mm = Math.round(px_x * 10) / 10;
  const y_mm = Math.round(px_y * 10) / 10;
  const z_mm = CLICK_Z.toFixed(2);

  if (mode === "move1") fire(`/robot/1/move?x=${x_mm}&y=${y_mm}&z=${z_mm}`);
  else if (mode === "move2") fire(`/robot/2/move?x=${x_mm}&y=${y_mm}&z=${z_mm}`);
  else if (mode === "tag") {
    const v = parseInt(tagValueInput.value, 10) || 1;
    fire(`/tag/add?x=${x_mm}&y=${y_mm}&value=${v}`);
  }
});

// Manual play fallback: shown only when autoplay is blocked. The click
// is a real user gesture so video.play() is guaranteed to succeed.
playOverlay.addEventListener("click", () => {
  video.play().then(() => {
    playOverlay.hidden = true;
    setStatus("");
  }).catch((err) => setStatus(`Play failed: ${err.message || err.name}`, "error"));
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
  // interaction yet) reject muted autoplay. If that happens, reveal the
  // big ▶ overlay so a single click resumes playback.
  const p = video.play();
  if (p && typeof p.catch === "function") {
    p.then(() => { playOverlay.hidden = true; })
     .catch(() => {
       playOverlay.hidden = false;
       setStatus("Autoplay blocked — click the ▶ overlay to start.", "error");
     });
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
  hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
    setStatus("Manifest parsed — waiting for playback…");
    tryPlay();
  });
  hls.on(window.Hls.Events.FRAG_LOADED, (_, data) => {
    setStatus(`Loaded ${data.frag && data.frag.sn !== undefined ? "seg " + data.frag.sn : "segment"} — waiting for decode…`);
  });
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

// Native <video> events independently confirm decode + display state.
// hls.js can happily report FRAG_LOADED while the video remains paused or
// stuck on the first frame — these listeners tell us the *element* state.
video.addEventListener("playing", () => { setStatus(""); playOverlay.hidden = true; });
video.addEventListener("waiting", () => setStatus("Buffering…"));
video.addEventListener("stalled", () => setStatus("Stalled — network or pipe paused"));
video.addEventListener("pause", () => {
  // <video> auto-pauses when the tab is hidden — don't nag in that case.
  if (!document.hidden) {
    playOverlay.hidden = false;
    setStatus("Paused — click the ▶ overlay to resume.", "error");
  }
});
video.addEventListener("error", () => {
  const e = video.error;
  setStatus(`Video element error: code ${e ? e.code : "?"}`, "error");
});

// Live state panel: poll /state at 2 Hz; pick up Z_safe from server so the
// click-default mirrors whatever the simulator currently configures.
async function poll() {
  try {
    const r = await fetch("/state");
    const j = await r.json();
    if (j.z && typeof j.z.safe === "number") CLICK_Z = j.z.safe;
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

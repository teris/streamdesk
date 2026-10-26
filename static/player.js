const video = document.querySelector('video');
const message = document.querySelector('#message');
let player;
let timer;
let parsingErrors = 0;
let progressAt = Date.now();
let lastTime = -1;
let unloading = false;
function retry() {
  if (unloading) return;
  message.hidden = false;
  message.textContent = 'Vorschau wird verbunden …';
  clearTimeout(timer);
  timer = setTimeout(() => { timer = null; load(); }, 4000);
}
function load() {
  if (unloading) return;
  if (player) player.destroy();
  progressAt = Date.now();
  parsingErrors = 0;
  lastTime = -1;
  if (window.Hls && Hls.isSupported()) {
    player = new Hls({ maxLiveSyncPlaybackRate: 1.2, lowLatencyMode: false, backBufferLength: 15 });
    player.loadSource('index.m3u8');
    player.attachMedia(video);
    player.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => { }));
    player.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) { retry(); return; }
      if (data.details === 'fragParsingError' && ++parsingErrors >= 3) retry();
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = 'index.m3u8';
    video.play().catch(() => { });
    video.onerror = retry;
  } else {
    message.textContent = 'Dieser Browser unterstützt die Vorschau nicht.';
  }
}
video.addEventListener('playing', () => { message.hidden = true; });
const watchdog = setInterval(() => {
  if (video.currentTime !== lastTime) { lastTime = video.currentTime; progressAt = Date.now(); }
  if (video.paused && video.readyState >= 2) return;
  if (Date.now() - progressAt > 20000 && !timer) retry();
}, 2000);
window.addEventListener('pagehide', () => { unloading = true; clearTimeout(timer); clearInterval(watchdog); if (player) player.destroy(); });
load();

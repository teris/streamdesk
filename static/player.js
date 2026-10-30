const video = document.querySelector('video');
const message = document.querySelector('#message');
const audioButton=document.querySelector('#player-audio-toggle'),volume=document.querySelector('#player-volume'),audioStatus=document.querySelector('#player-audio-status');
video.volume=.7;
function audioState(){return {muted:video.muted,volume:video.volume,playing:!video.paused};}
function updateAudio(){
  const audible=!video.muted&&video.volume>0;
  audioButton.textContent=audible?'Ton ausschalten':'Ton einschalten';audioButton.setAttribute('aria-pressed',String(audible));volume.value=Math.round(video.volume*100);
  audioStatus.textContent=audible?'Ton an · '+Math.round(video.volume*100)+' %':'Vorschau ist stumm.';
  if(window.parent!==window)window.parent.postMessage({type:'streamdesk:preview-audio',...audioState()},location.origin);
}
async function setAudio(settings){
  if(typeof settings.volume==='number'&&Number.isFinite(settings.volume))video.volume=Math.max(0,Math.min(1,settings.volume));
  if(typeof settings.muted==='boolean')video.muted=settings.muted;
  try{if(video.paused)await video.play();}
  catch(error){if(!video.muted&&error.name==='NotAllowedError'){video.muted=true;video.play().catch(()=>{});updateAudio();throw new Error('Bitte „Ton einschalten“ erneut anklicken. Der Browser benötigt die Freigabe per Klick.');}if(error.name!=='AbortError')throw new Error('Die Vorschau lädt noch. Bitte den Ton gleich erneut einschalten.');}
  updateAudio();return audioState();
}
function setEmbedded(embedded){document.body.classList.toggle('embedded-program',embedded);document.querySelector('#player-audio').hidden=embedded;}
window.StreamDeskPlayer={setAudio,audioState,setEmbedded};
audioButton.addEventListener('click',()=>setAudio({muted:!video.muted&&video.volume>0,volume:video.volume||.7}).catch(error=>{audioStatus.textContent=error.message;}));
volume.addEventListener('input',()=>setAudio({volume:Number(volume.value)/100,muted:Number(volume.value)===0}).catch(error=>{audioStatus.textContent=error.message;}));
for(const event of ['volumechange','play','pause'])video.addEventListener(event,updateAudio);
updateAudio();
let player;
let timer;
let parsingErrors = 0;
let progressAt = Date.now();
let lastTime = -1;
let unloading = false;
function retry() {
  if (unloading) return;
  message.hidden = false;
  message.textContent = document.body.dataset.switchText || 'Synchronisation';
  clearTimeout(timer);
  timer = setTimeout(() => { timer = null; load(); }, 4000);
}
async function resumePlayback(){
  try{await video.play();}
  catch(error){
    if(!video.muted&&error.name==='NotAllowedError'){
      video.muted=true;updateAudio();
      audioStatus.textContent='Der Browser hat den Ton pausiert. Bitte erneut einschalten.';
      try{await video.play();}catch(_){retry();}
    }
  }
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
    player.on(Hls.Events.MANIFEST_PARSED, resumePlayback);
    player.on(Hls.Events.ERROR, (_, data) => {
      if (data.fatal) { retry(); return; }
      if (data.details === 'fragParsingError' && ++parsingErrors >= 3) retry();
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = 'index.m3u8';
    resumePlayback();
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

'use strict';
const $ = (selector) => document.querySelector(selector);
const csrf = $('meta[name="csrf-token"]').content;
let busy = false;
let redirecting = false;
function redirectToLogin() { if (!redirecting) { redirecting=true;location.assign('/login'); } }
let state;
let failures = 0;
let toastTimer;
let transfer = null;
let programPreviewWanted = true;
let librarySignature = '';
let libraryLoading = false;
let recordingSignature = '';
let recordingLoading = false;
let renewalLoaded = false;
let currentView = 'dashboard';
let rateSampleAt = 0;
let statsSample = null;
let statsReceivedAt = 0;
let studioTab='chat';
let chatData=null;
let chatLoading=false;
let targetSignature='';
let widgetBase='';
const rateHistory = {receive:[], send:[]};
const viewInfo = {
  dashboard:['ÜBERSICHT','Dein Stream auf einen Blick.','Signal, Sendezeit und Medien – alles an einem Ort.','Dashboard'],
  sources:['LIVE-EINGÄNGE','Deine Quellen.','Live-Eingänge, Vorschau und aktuelle Quellensteuerung.','Quellen'],
  videos:['MEDIENBIBLIOTHEK','Deine Offline-Videos.','Videos auswählen, hochladen und mit Overlays gestalten.','Offline-Videos'],
  recordings:['AUFNAHMEBIBLIOTHEK','Aufnehmen & Wiederholen.','Deine Aufnahmen speichern, herunterladen und manuell als Source 1 zuschalten.','Aufnahmen'],
  chat:['GEMEINSAMER LIVE-CHAT','Deine Chats an einem Ort.','Twitch und YouTube lesen, gezielt schreiben und als Widget einbinden.','Chat & Widget'],
  settings:['EINSTELLUNGEN','Streaming-Auswahl.','Ziele für deinen nächsten Stream auswählen und einzeln einrichten.','Streaming-Auswahl'],
  'settings-twitch':['EINSTELLUNGEN','Twitch.','Twitch-Konto und Streamschlüssel an einem Ort verwalten.','Twitch'],
  'settings-youtube':['EINSTELLUNGEN','YouTube.','YouTube-Konto, Sendung und Streamschlüssel getrennt einrichten.','YouTube'],
  'settings-custom':['EINSTELLUNGEN','Eigener Anbieter.','Die Zieladresse deines eigenen Streaming-Anbieters verwalten.','Eigener Anbieter'],
  'settings-appearance':['EINSTELLUNGEN','Darstellung & Sprache.','Theme und Sprache deiner Oberfläche auswählen.','Darstellung & Sprache'],
  account:['MEIN KONTO','Dein Konto.','Dein eigenes Passwort und deine Anmeldung verwalten.','Mein Konto'],
  'expert-outputs':['EXPERTENMODUS','Ausgänge & Konten.','Weitere Konten und Anbieter hinzufügen, Ausgänge getrennt steuern.','Ausgänge & Konten'],
  expert:['TECHNISCHE VERWALTUNG','Expertenmodus.','MediaMTX-Einstellungen in einem eigenen Bereich.','Expertenmodus'],
  'expert-protocols':['EXPERTENMODUS','Protokolle & WebRTC.','Serverstatus, WebRTC-Einrichtung und Kamera-Verbindungen.','Protokolle & WebRTC'],
  'expert-routing':['EXPERTENMODUS','Quellen & Routing.','Quellen einzeln verwalten und ihren Ausgängen zuordnen.','Quellen & Routing'],
  'expert-playback':['EXPERTENMODUS','Playback.','Eigene Aufnahmesegmente geschützt abspielen.','Playback'],
  'expert-recording':['EXPERTENMODUS','Native Aufnahme.','MediaMTX-Aufnahme, Segmente und Aufbewahrung konfigurieren.','Native Aufnahme'],
  'expert-viewers':['EXPERTENMODUS','Zuschauerfreigabe.','Öffentlichen Player freigeben, erneuern oder widerrufen.','Zuschauerfreigabe'],
  'expert-renewal':['EXPERTENMODUS','Neuverbindung.','Verbindungsintervalle und manuelle Neuverbindung.','Neuverbindung'],
  'expert-automation':['EXPERTENMODUS','Automation & Export.','Hooks, Zeitpläne, Exporte und Benachrichtigungen verwalten.','Automation & Export'],
  'expert-discord':['EXPERTENMODUS','Discord-Bot.','Bot Schritt für Schritt erstellen und mit deinem Chat verbinden.','Discord-Bot'],
  'administration-services':['VERWALTUNG','Dienste & Freigaben.','Dienste zentral für alle Benutzer sperren oder wieder freigeben.','Dienste & Freigaben'],
  administration:['VERWALTUNG','Administration.','Benutzer und die gemeinsame Twitch-App verwalten.','Administration']
};
function showView(){
  const requested=location.hash.slice(1)||'dashboard';
  let next=Object.hasOwn(viewInfo,requested)&&document.querySelector(`[data-view="${requested}"]`)?requested:'dashboard';
  if(next.startsWith('expert-')&&document.documentElement.dataset.expert!=='true')next='expert';
  if(next!==requested)history.replaceState(null,'','#'+next);
  const previous=currentView;currentView=next;
  for(const view of document.querySelectorAll('.app-view'))view.hidden=view.dataset.view!==next;
  for(const link of document.querySelectorAll('.menu-link')){
    if(link.hash==='#'+next||link.hash==='#expert'&&next.startsWith('expert-')||link.hash==='#settings'&&next.startsWith('settings-')||link.hash==='#administration'&&next.startsWith('administration-'))link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  }
  if($('#admin-subnav')){$('#admin-subnav').hidden=!next.startsWith('administration');for(const link of $('#admin-subnav').querySelectorAll('a')){if(link.hash==='#'+next)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}}
  $('#expert-subnav').hidden=!next.startsWith('expert');
  $('#settings-subnav').hidden=next!=='settings'&&!next.startsWith('settings-');
  for(const link of document.querySelectorAll('#settings-subnav a')){
    if(link.hash==='#'+next)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  }
  for(const link of document.querySelectorAll('#expert-subnav a')){
    if(link.hash==='#'+next)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
  }
  const [eyebrow,title,description,label]=viewInfo[next];
  $('#view-eyebrow').textContent=eyebrow;$('#view-title').textContent=title;$('#view-description').textContent=description;$('#breadcrumb-title').textContent=label;document.title=label+' · MediaMTX - StreamDesk';
  if(previous!==next){
    for(const frame of document.querySelectorAll('.app-view iframe')){frame.src='about:blank';frame.hidden=true;}
    for(const player of document.querySelectorAll('.app-view video'))player.pause();
    for(const button of document.querySelectorAll('.preview-toggle:not([data-slot="3"])'))button.textContent='Vorschau öffnen';
    if(next!=='sources')document.querySelectorAll('.source-credentials').forEach(details=>{details.open=false;details.querySelector('.credential-fields').replaceChildren();});
    window.scrollTo(0,0);
  }
  if(state)render(state);
  if(next==='videos')loadLibrary().catch(error=>notify(error.message,true));
  if(next==='recordings')loadRecordings().catch(error=>notify(error.message,true));
  if(next==='chat'||next==='dashboard'&&studioTab==='chat')loadChat();
  if(next==='administration')loadAdmin().catch(error=>notify(error.message,true));
  window.StreamDeskServices?.apply();
}
window.addEventListener('hashchange',showView);
setInterval(()=>{
  if(state?.ok&&state.state==='forwarding'&&state.stats){
    const elapsed=Math.min(4,Math.max(0,(Date.now()-statsReceivedAt)/1000));
    $('#stat-session').textContent=duration(state.stats.stream_seconds+elapsed);
    $('#stat-total-time').textContent=duration(state.stats.total_stream_seconds+elapsed);
  }
},1000);
function duration(seconds){
  const value=Math.max(0,Math.floor(Number(seconds)||0));
  return [Math.floor(value/3600),Math.floor(value/60)%60,value%60].map(n=>String(n).padStart(2,'0')).join(':');
}
function bytes(value){
  const units=['B','KB','MB','GB','TB'];let index=0,n=Math.max(0,Number(value)||0);
  while(n>=1000&&index<units.length-1){n/=1000;index++;}
  return n.toLocaleString('de-DE',{maximumFractionDigits:index?1:0})+' '+units[index];
}
function renderDashboard(data){
  const stats=data.stats||{};
  if(stats!==statsSample){statsSample=stats;statsReceivedAt=Date.now();}
  $('#stat-receive').replaceChildren(document.createTextNode(data.ok?(data.receive_mbps||0).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' ':'— '));
  $('#stat-send').replaceChildren(document.createTextNode(data.ok?(data.send_mbps||0).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' ':'— '));
  for(const selector of ['#stat-receive','#stat-send']){const unit=document.createElement('small');unit.textContent='Mbit/s';$(selector).append(unit);}
  $('#stat-send-note').textContent=data.state==='forwarding'?(data.output.kind==='twitch'?'Zu Twitch':'Zum Streamingziel'):data.state==='renewing'?'Neuverbindung läuft':data.enabled?'Verbindungsaufbau':'Ausgang gestoppt';
  if(data.bandwidth_warning)$('#stat-send-note').textContent=`Upload-Warnung: ${data.send_mbps.toLocaleString('de-DE')} von ${data.bandwidth_limit_mbps.toLocaleString('de-DE')} Mbit/s · ${data.metrics?.readers||0} Leser`;
  $('#stat-storage').textContent=bytes(stats.used_bytes);
  $('#stat-storage-note').textContent=bytes(stats.free_bytes)+' auf dem Server frei';
  $('#storage-capacity').style.width=Math.min(100,100*(stats.server_used_bytes||0)/(stats.total_bytes||1))+'%';
  $('#session-label').textContent=data.enabled?'Aktuelle Streamdauer':'Letzte Streamdauer';
  $('#stat-session').textContent=duration(stats.stream_seconds);
  $('#stat-session-note').textContent=data.state==='forwarding'?'● Verbunden · Zeit wird erfasst':data.state==='renewing'?'Sitzung bleibt bei Neuverbindung erhalten':data.enabled?'Warte auf Verbindung zum Ziel':stats.stream_seconds?'Stream beendet':'Noch kein Stream erfasst';
  $('#stat-recordings').textContent=duration(stats.recording_seconds);
  $('#stat-recordings-note').textContent=(stats.recording_count||0)+' gespeicherte Aufnahme'+(stats.recording_count===1?'':'n');
  $('#stat-videos').textContent=duration(stats.video_seconds);
  $('#stat-videos-note').textContent=(stats.video_count||0)+' Video'+(stats.video_count===1?'':'s')+' · ausgewählt: '+duration(stats.selected_video_seconds);
  $('#stat-total-time').textContent=duration(stats.total_stream_seconds);
  $('#stat-total-note').textContent=stats.stats_since?'Erfasst seit '+new Date(stats.stats_since*1000).toLocaleDateString('de-DE'):'Wird ab diesem Update erfasst';
  $('#dash-recording').textContent=data.recording?.active?'● Aufnahme · '+duration(Date.now()/1000-data.recording.active.started):'Keine Aufnahme';
  $('#dash-recording').classList.toggle('online',!!data.recording?.active);
  if(data.ok&&performance.now()-rateSampleAt>=1500){
    rateSampleAt=performance.now();rateHistory.receive.push(data.receive_mbps||0);rateHistory.send.push(data.send_mbps||0);
    for(const [key,values] of Object.entries(rateHistory)){
      if(values.length>30)values.shift();const ceiling=Math.max(1,...values);
      $('#'+key+'-line').setAttribute('points',values.map((v,i)=>`${i*120/Math.max(1,values.length-1)},${22-v*20/ceiling}`).join(' '));
    }
  }
}

function notify(message, error = false) {
  const element = $(error ? '#alert' : '#toast');
  element.textContent = message;
  element.hidden = false;
  if (!error) { clearTimeout(toastTimer); toastTimer = setTimeout(() => element.hidden = true, 7000); }
}
async function api(path, body, method = 'POST') {
  const options = {method: body === undefined ? 'GET' : method, credentials: 'same-origin', cache: 'no-store'};
  if (body !== undefined) {
    options.headers = {'X-CSRF-Token': csrf};
    if (body instanceof FormData) options.body = body;
    else { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  }
  const response = await fetch(path, options);
  if (response.status === 401) { redirectToLogin(); throw new Error('Bitte erneut anmelden.'); }
  if (response.status === 204) return {};
  let data;
  try { data = await response.json(); }
  catch (_) {
    if (response.status === 413) throw new Error('Der Proxy hat den Upload abgewiesen. Das Upload-Limit in NPMplus muss mindestens 501 MB betragen.');
    throw new Error(`Die Anfrage wurde mit HTTP ${response.status} beantwortet. Verbindung und Proxy prüfen.`);
  }
  if (!response.ok) throw new Error(data.error || 'Die Aktion ist fehlgeschlagen.');
  return data;
}
function render(data) {
  state = data;
  window.dispatchEvent(new CustomEvent('streamdesk:status', {detail:data}));
  window.StreamDeskRouting?.render(data);
  const online = data.ok;
  renderDashboard(data);
  renderDestinations(data);
  $('#connection').textContent = online ? '● Server verbunden' : '● Server nicht erreichbar';
  $('#connection').classList.toggle('good', online);
  $('#start').disabled = busy || !online || data.enabled || !data.output.configured || ['queued','processing'].includes(data.upload.state);
  $('#stop').disabled = busy || !online || !data.enabled;
  $('#upload-button').disabled = busy || !online || ['queued','processing'].includes(data.upload.state);
  const metadataReady = window.StreamDeskServices.allowed('twitch') && !!data.twitch_edit_ready;
  $('#save-channel').disabled = busy || !online || !metadataReady;
  $('#load-channel').disabled = busy || !online || !metadataReady;
  $('#metadata-connect').hidden = metadataReady;
  $('#twitch-meta-note').textContent = metadataReady ? 'Titel und Kategorie werden direkt auf deinem verbundenen Twitch-Kanal geändert – auch während des Streams.' : 'Für Titel und Spiel musst du Twitch einmal erneut verbinden und die zusätzliche Berechtigung bestätigen. Dazu den Ausgang kurz stoppen.';
  if (!online) {
    $('#output-state').textContent = 'Status nicht verfügbar';
    $('#output-description').textContent = data.error || 'Verbindung wird erneut versucht.';
    $('#output-dot').className = 'dot error';

    return;
  }
  const states = {
    stopped: ['Stream gestoppt', 'Du sendest gerade nicht. Deine Quellen bleiben empfangsbereit.', ''],
    connecting: ['Verbindung wird aufgebaut', 'Der Server verbindet sich mit deinem Ausgang.', 'connecting'],
    forwarding: ['Ausgang verbunden', 'Dein Stream wird an den gewählten Ausgang übertragen.', 'good'],
    error: ['Verbindung fehlgeschlagen', 'Zieladresse, Streamschlüssel und Erreichbarkeit prüfen. Der Server versucht es erneut.', 'error'],
    renewing: ['Verbindung wird erneuert', 'Die Verbindung zum Ziel wird kurz getrennt und wieder aufgebaut. Lokale Quellen und Aufnahmen laufen weiter.', 'connecting']
  };
  const output = states[data.state] || states.connecting;
  $('#output-state').textContent = output[0];
  const configured=effectiveOutputs(data);
  const connected=configured.filter(x=>data.output_states?.[x.kind]==='forwarding').length;
  $('#output-description').textContent = (configured.length>1?`${connected} von ${configured.length} Ausgängen verbunden. `:'') + output[1] + ({waiting:' Die Browserquelle wartet auf einen freien Renderer dieses Servers.',starting:' Browserquelle wird gestartet …',error:' Browserquelle nicht erreichbar; erneuter Versuch folgt.',live:' Live-Browserquelle aktiv.'}[data.browser_status] || '');
  $('#output-dot').className = 'dot ' + output[2];
  const activeRecording=data.recording?.active;
  $('#record-indicator').textContent=activeRecording?(activeRecording.status==='finishing'?'Wird abgeschlossen …':'● Aufnahme läuft'):'Keine Aufnahme';
  $('#record-start').disabled=busy||!online||!!activeRecording;
  $('#record-stop').disabled=busy||!activeRecording||activeRecording.status!=='recording';
  $('#replay-stop').disabled=busy||!data.replay_id;
  $('#record-note').textContent=(activeRecording?`Laufzeit: ${Math.max(0,Math.floor(Date.now()/1000-activeRecording.started))} Sekunden. `:'')+`Freier Speicher: ${data.recording?.free_mb ?? '—'} MB. Bei weniger als 350 MB stoppt eine Aufnahme automatisch.`+(data.replay_id?' Wiederholung ist manuell eingeschaltet.':'');
  if(!renewalLoaded){$('#renew-interval').value=String(data.renewal.interval);$('#renew-gap').value=String(data.renewal.gap);renewalLoaded=true;}
  $('#renew-now').disabled=busy||!data.enabled||data.state==='renewing';
  $('#renew-note').textContent=data.renewal.resume?`Neuverbindung läuft. Wiederaufbau ab ${new Date(data.renewal.resume*1000).toLocaleTimeString('de-DE')}.`:data.renewal.next?`Nächste geplante Neuverbindung: ${new Date(data.renewal.next*1000).toLocaleString('de-DE')}.`:data.renewal.interval?'Automatik aktiviert; der Timer beginnt bei bestehender Verbindung.':'Automatische Neuverbindung ist ausgeschaltet.';
  window.StreamDeskRouting?.program(data);
  const destination = effectiveOutputs(data).map(x=>platformName(x.kind)).join(' + ')||'Keine Ziele ausgewählt';
  $('#output-kind').textContent = configured.length>1?configured.length+' Ausgänge':destination;
  $('#account').textContent = data.output.account ? `Twitch-Konto: ${data.output.account}` : data.output.configured ? 'Ausgang ist eingerichtet.' : 'Noch kein Ausgang eingerichtet.';
  $('#oauth-note').textContent = data.oauth_ready ? 'Verbinde deinen Account über Twitch. Der Stream startet erst auf deinen Klick.' : 'Die Twitch-App muss noch einmalig vom Administrator eingerichtet werden. Ein Streamschlüssel funktioniert bereits.';
  $('#oauth').setAttribute('aria-disabled', data.enabled ? 'true' : 'false');
  $('#upload-meter').hidden = !transfer;
  $('#upload-state').textContent = transfer ? `Datei wird hochgeladen: ${transfer.percent} %${transfer.percent === 100 ? ' – wird auf dem Server geprüft …' : ''}` : data.upload.message || 'Standard-Offline-Video ist eingerichtet.';
  $('#upload-state').classList.toggle('error', data.upload.state === 'error');
  $('#upload-progress').hidden = !!transfer || !['queued','processing'].includes(data.upload.state);
  $('#updated').textContent = 'Aktualisiert ' + new Date().toLocaleTimeString('de-DE');
}
async function refresh() {
  if (redirecting) return;
  try { const data = await api('/api/status'); failures = 0; render(data); await Promise.all([currentView==='videos'?loadLibrary():Promise.resolve(),currentView==='recordings'?loadRecordings():Promise.resolve(),currentView==='chat'||currentView==='dashboard'&&studioTab==='chat'?loadChat():Promise.resolve()]); }
  catch (error) {
    failures++;
    if (failures > 1 && state) render({...state,ok:false,error:'Verbindung zur Oberfläche unterbrochen. Status wird erneut geprüft.'});
  }
}
function formFeedback(element, message, error = false) {
  if (!element) return;
  let feedback = element.querySelector('.form-feedback');
  if (!feedback) {
    feedback = document.createElement('p');
    feedback.setAttribute('aria-live', 'polite');
    element.append(feedback);
  }
  feedback.className = 'form-feedback ' + (error ? 'error' : 'success');
  feedback.textContent = message;
  feedback.setAttribute('role', error ? 'alert' : 'status');
}
async function action(callback, message, target = null) {
  if (busy) return;
  busy = true;
  $('#alert').hidden = true;
  if (target) {
    formFeedback(target, 'Wird gespeichert …');
    for (const button of target.querySelectorAll('button[type=submit]')) button.disabled = true;
  }
  if (state) render(state);
  try {
    await callback();
    if (message) { notify(message); formFeedback(target, message); }
    if (!redirecting) await refresh();
  }
  catch(error) { notify(error.message,true); formFeedback(target, error.message, true); }
  finally {
    busy = false;
    if (target) for (const button of target.querySelectorAll('button[type=submit]')) button.disabled = false;
    if (state) render(state);
  }
}
$('#start').addEventListener('click', () => action(() => api('/api/start',{}), 'Start angefordert. Der Verbindungsstatus wird aktualisiert.'));
$('#stop').addEventListener('click', () => action(() => api('/api/stop',{}), 'Weiterleitung gestoppt.'));
$('#record-start').addEventListener('click',()=>action(()=>api('/api/recordings/start',{source:$('#record-source').value}),'Aufnahme manuell gestartet.',$('.recording-panel')));
$('#record-stop').addEventListener('click',()=>action(()=>api('/api/recordings/stop',{}),'Aufnahme wird abgeschlossen.',$('.recording-panel')));
$('#replay-stop').addEventListener('click',()=>action(()=>api('/api/replay/stop',{}),'Wiederholung beendet. Die normale Quellenwahl übernimmt.',$('.recording-panel')));
$('#renewal-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api('/api/renewal',{interval:Number($('#renew-interval').value),gap:Number($('#renew-gap').value)});renewalLoaded=false;},'Einstellungen gespeichert.',$('#renewal-form'));});
$('#renew-now').addEventListener('click',()=>action(()=>api('/api/renewal/now',{}),'Neuverbindung manuell angefordert.',$('#renewal-form')));
$('#logout').addEventListener('click', () => action(async () => { await api('/api/logout',{}); redirectToLogin(); }));
$('#disconnect').addEventListener('click', () => action(() => api('/api/disconnect',{}), 'Ausgänge gestoppt und Streamschlüssel entfernt. Kontofreigaben bleiben erhalten.'));
$('#oauth').addEventListener('click', event => { if (state?.enabled) { event.preventDefault(); notify('Bitte den Ausgang zuerst stoppen.',true); } });
$('#metadata-connect').addEventListener('click', event => {
  if (state?.enabled) { event.preventDefault();formFeedback($('#metadata-form'),'Bitte den Ausgang für die neue Twitch-Berechtigung einmal kurz stoppen.',true); }
});
$('#category-search').addEventListener('click', async () => {
  const query = $('#category-query').value.trim();
  if(query.length < 2) {$('#category-note').textContent='Bitte mindestens zwei Zeichen eingeben.';return;}
  const button=$('#category-search');button.disabled=true;$('#category-note').textContent='Suche bei Twitch …';
  try {
    const data=await api('/api/twitch/categories?q='+encodeURIComponent(query));
    const select=$('#category-results');select.replaceChildren(new Option('Kategorie unverändert lassen',''),new Option('Keine Kategorie','0'));
    for(const item of data.categories)select.append(new Option(item.name,item.id));
    $('#category-note').textContent=data.categories.length?`${data.categories.length} Treffer. Bitte die passende Kategorie auswählen.`:'Keine passende Kategorie gefunden.';
  } catch(error) {$('#category-note').textContent=error.message;}
  finally {button.disabled=false;}
});
$('#category-query').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();$('#category-search').click();}});
$('#load-channel').addEventListener('click',()=>action(async()=>{
  const data=await api('/api/twitch/channel');$('#stream-title').value=data.title;
  $('#category-results').replaceChildren(new Option('Kategorie unverändert lassen',''),new Option(data.game_name||'Keine Kategorie',data.game_id||'0'));
  $('#category-results').value=data.game_id||'0';$('#category-note').textContent='Aktuelle Daten von '+data.name+' geladen.';
},'Twitch-Daten geladen.',$('#metadata-form')));
$('#metadata-form').addEventListener('submit',event=>{
  event.preventDefault();const body={};const title=$('#stream-title').value.trim();if(title)body.title=title;
  const game=$('#category-results').value;if(game!=='')body.game_id=game;
  if(!Object.keys(body).length){formFeedback($('#metadata-form'),'Bitte einen Titel eingeben oder eine Kategorie auswählen.',true);return;}
  action(()=>api('/api/twitch/channel',body),'Titel und Kategorie wurden auf Twitch gespeichert.',$('#metadata-form'));
});
for (const button of document.querySelectorAll('.preview-toggle')) {
  button.addEventListener('click', () => {
    if (button.dataset.slot === '3') { programPreviewWanted = !programPreviewWanted; if (state) window.StreamDeskRouting?.program(state); return; }
    const frame = button.closest('article').querySelector('iframe');
    frame.hidden = !frame.hidden;
    if (!frame.hidden) frame.src = `/preview/${button.dataset.slot}/`;
    else frame.src = 'about:blank';
    button.textContent = frame.hidden ? 'Vorschau öffnen' : 'Vorschau schließen';
  });
}

async function loadLibrary(force = false) {
  if (libraryLoading) return;
  libraryLoading = true;
  try {
    const data = await api('/api/videos');
    const signature = JSON.stringify([data,!!state?.enabled,state?.upload?.state,state?.limits]);
    if (!force && signature === librarySignature) return;
    // Do not destroy an editor or a playing library preview during polling.
    if (!force && ($('#video-list').contains(document.activeElement) || [...document.querySelectorAll('#video-list video')].some(v => !v.paused))) return;
    librarySignature = signature;
    $('#library-count').textContent = `${data.videos.length} Video${data.videos.length === 1 ? '' : 's'}`;
    const container = $('#video-list');container.replaceChildren();
    for (const video of data.videos) {
      const selected = video.id === data.selected;
      const card = document.createElement('article');card.className = 'video-card' + (selected ? ' chosen' : '');card.dataset.videoId = video.id;
      const title = document.createElement('h3');title.textContent = video.name;card.append(title);
      const info = document.createElement('p');info.className = selected ? 'selected-label' : 'small muted';info.textContent = selected ? '✓ Für den Offline-Modus ausgewählt' : 'In deiner Bibliothek';card.append(info);
      const player = document.createElement('video');player.controls = true;player.preload = 'none';player.playsInline = true;player.src = `/media/video/${video.id}`;card.append(player);
      const metadata = document.createElement('p');metadata.className='small muted';metadata.textContent=`${(video.size/1048576).toFixed(1)} MB`+(video.duration?` · ${duration(video.duration)}`:'')+(video.overlay_text?' · Text-Overlay':'')+(video.browser_enabled?' · Browserquelle':'');card.append(metadata);
      const actions = document.createElement('div');actions.className = 'video-actions';
      const select = document.createElement('button');select.className = 'secondary';select.textContent = selected ? 'Ausgewählt' : 'Dieses Video verwenden';select.disabled = selected || !!state?.enabled || ['queued','processing'].includes(state?.upload?.state);
      select.addEventListener('click', () => action(async () => {await api(`/api/videos/${video.id}/select`,{});await loadLibrary(true);}, 'Offline-Video ausgewählt.', card));actions.append(select);
      const del = document.createElement('button');del.className = 'danger';del.textContent = 'Löschen';del.disabled = selected || ['queued','processing'].includes(state?.upload?.state);
      const confirm = document.createElement('div');confirm.className='delete-confirm';confirm.hidden=true;
      const question=document.createElement('p');question.className='small';question.textContent='Dieses Video endgültig aus deiner Bibliothek löschen?';confirm.append(question);
      const yes=document.createElement('button');yes.className='danger';yes.textContent='Endgültig löschen';yes.addEventListener('click',()=>action(async()=>{await api(`/api/videos/${video.id}/delete`,{});await loadLibrary(true);},'Video gelöscht.',card));confirm.append(yes);
      const cancel=document.createElement('button');cancel.className='ghost';cancel.textContent='Abbrechen';cancel.addEventListener('click',()=>confirm.hidden=true);confirm.append(cancel);
      del.addEventListener('click',()=>confirm.hidden=!confirm.hidden);actions.append(del);card.append(actions,confirm);
      const editor=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Text-Overlay bearbeiten';editor.append(summary);
      const form=document.createElement('form');
      const label=document.createElement('label');label.textContent='Dein Text';
      const text=document.createElement('textarea');text.name='text';text.maxLength=200;text.placeholder='Zum Beispiel: Gleich wieder da!\nMehr unter example.com';text.value=video.overlay_text;label.append(text);form.append(label);
      const style=video.overlay_style;
      const controls={};
      const grid=document.createElement('div');grid.className='text-controls';
      function addControl(key,title,type,min,max) {
        const label=document.createElement('label');label.textContent=title;
        const input=document.createElement('input');input.name=key;input.type=type;
        if(type==='checkbox') {input.checked=style[key];label.className='checkbox-label';}
        else input.value=style[key];
        if(min!==undefined) input.min=min;
        if(max!==undefined) input.max=max;
        const value=document.createElement('span');value.className='small muted';
        if(type==='range') {value.textContent=input.value;input.addEventListener('input',()=>value.textContent=input.value);}
        label.append(input,value);grid.append(label);controls[key]=input;
      }
      addControl('x','Horizontal: links → rechts','range',0,100);
      addControl('y','Vertikal: oben → unten','range',0,100);
      addControl('size','Schriftgröße in Pixeln','range',16,120);
      addControl('color','Textfarbe','color');
      addControl('background','Hintergrundfarbe','color');
      addControl('opacity','Hintergrund-Deckkraft in %','range',0,100);
      addControl('bold','Fettschrift','checkbox');
      addControl('box','Hintergrund anzeigen','checkbox');form.append(grid);
      const stage=document.createElement('div');stage.className='text-stage';
      const sample=document.createElement('video');sample.controls=true;sample.muted=true;sample.loop=true;sample.playsInline=true;sample.preload='none';stage.append(sample);
      const caption=document.createElement('div');caption.className='overlay-caption';stage.append(caption);form.append(stage);
      function readStyle(){const result={};for(const [key,input] of Object.entries(controls))result[key]=input.type==='checkbox'?input.checked:input.type==='range'?Number(input.value):input.value;return result;}
      function updateCaption(){const s=readStyle();caption.textContent=text.value;caption.style.left=s.x+'%';caption.style.top=s.y+'%';caption.style.transform=`translate(-${s.x}%,-${s.y}%)`;caption.style.fontSize=(s.size/19.2)+'cqw';caption.style.color=s.color;caption.style.fontWeight=s.bold?'700':'400';caption.style.background=s.box?s.background+Math.round(s.opacity*2.55).toString(16).padStart(2,'0'):'transparent';caption.style.padding=s.box?'.9375cqw':'0';}
      text.addEventListener('input',updateCaption);for(const input of Object.values(controls))input.addEventListener('input',updateCaption);updateCaption();
      editor.addEventListener('toggle',()=>{if(editor.open){sample.src=`/media/video/${video.id}?original=1`;sample.play().catch(()=>{});}else{sample.pause();sample.removeAttribute('src');sample.load();}});
      const hint=document.createElement('p');hint.className='small muted';hint.textContent='Vorschau deiner Einstellungen. Bis zu 3 Zeilen / 200 Zeichen. Speichern rechnet den Text einmalig ein; leerer Text entfernt ihn.';form.append(hint);
      const save=document.createElement('button');save.type='submit';save.className='secondary';save.textContent='Text-Version erstellen';save.disabled=['queued','processing'].includes(state?.upload?.state) || (selected&&!!state?.enabled);form.append(save);
      form.addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api(`/api/videos/${video.id}/overlay`,{text:text.value,style:readStyle()});},'Text wird verarbeitet. Den Status findest du beim Upload.',form);});editor.append(form);card.append(editor);
      const browserEditor=document.createElement('details');const browserSummary=document.createElement('summary');browserSummary.textContent='Live-Browserquelle (z. B. StreamElements)';browserEditor.append(browserSummary);
      const browserForm=document.createElement('form');browserForm.className='browser-form';browserForm.dataset.service='browser_overlays';browserForm.classList.toggle('service-disabled',!window.StreamDeskServices.allowed('browser_overlays'));const enableLabel=document.createElement('label');enableLabel.className='checkbox-label';enableLabel.textContent='Browser-Overlay beim Offline-Video einschalten';const enable=document.createElement('input');enable.type='checkbox';enable.checked=video.browser_enabled;enableLabel.append(enable);browserForm.append(enableLabel);
      const urlLabel=document.createElement('label');urlLabel.textContent='Öffentliche HTTPS-Overlay-Adresse';const url=document.createElement('input');url.type='text';url.spellcheck=false;url.autocomplete='off';url.placeholder=video.browser_enabled?`Gespeichert: ${video.browser_host} – leer lassen zum Beibehalten`:'https://streamelements.com/overlay/…';urlLabel.append(url);browserForm.append(urlLabel);
      const explanation=document.createElement('p');explanation.className='small muted';explanation.textContent=`Wird live transparent über das Video gemischt, inklusive Animationen und Alerts. Ton stammt vom Video. 1920 × 1080; Bildaktualisierung bis zu ${state?.limits?.browser_fps || 10} fps. Maximale Anzahl gleichzeitiger Browserquellen: ${state?.limits?.browser_limit || 1}.`;browserForm.append(explanation);
      const demo=document.createElement('button');demo.type='button';demo.className='ghost';demo.textContent='Test-Overlay-Adresse einsetzen';demo.addEventListener('click',()=>{const base=($('meta[name="public-url"]')?.content||state?.public_url||location.origin).replace(/\/$/,'');url.value=base+'/overlay-demo';enable.checked=true;});browserForm.append(demo);
      const browserSave=document.createElement('button');browserSave.type='submit';browserSave.className='secondary';browserSave.textContent='Browserquelle speichern';browserSave.disabled=selected&&!!state?.enabled;browserForm.append(browserSave);
      browserForm.addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api(`/api/videos/${video.id}/browser`,{enabled:enable.checked,url:url.value});url.value='';await loadLibrary(true);},'Browserquelle gespeichert. Sie startet erst bei verbundenem Ausgang im Offline-Modus.',browserForm);});browserEditor.append(browserForm);card.append(browserEditor);container.append(card);
    }
    $('#library-feedback').textContent=state?.enabled?'Zum Wechseln des ausgewählten Videos bitte den Ausgang stoppen. Uploads und Bibliotheksvorschauen sind unabhängig möglich.':'Nur das ausgewählte Video wird bei verbundenem Ausgang als Offline-Video gesendet.';
  } finally {libraryLoading = false;}
}

async function loadRecordings(force=false){
  if(recordingLoading)return;recordingLoading=true;
  try{
    const data=await api('/api/recordings');const signature=JSON.stringify(data);
    if(!force&&signature===recordingSignature)return;
    if(!force&&[...document.querySelectorAll('#recording-list video')].some(v=>!v.paused))return;
    recordingSignature=signature;const list=$('#recording-list');list.replaceChildren();
    if(!data.recordings.length){const empty=document.createElement('p');empty.className='small muted';empty.textContent='Noch keine manuellen Aufnahmen. Native MediaMTX-Segmente werden separat angezeigt.';list.append(empty);}
    for(const recording of data.recordings){
      const card=document.createElement('article');card.className='video-card';card.dataset.recordingId=recording.id;
      const title=document.createElement('h3');title.textContent=recording.name;card.append(title);
      const info=document.createElement('p');info.className='small muted';info.textContent=`${duration(recording.duration)} · ${(recording.size/1048576).toFixed(1)} MB · ${({recording:'Aufnahme läuft',finishing:'Wird abgeschlossen',ready:'Bereit',error:'Fehler'})[recording.status]||recording.status}`;card.append(info);
      if(recording.status==='ready'){
        const video=document.createElement('video');video.controls=true;video.playsInline=true;video.preload='none';video.src=`/media/recording/${recording.id}`;card.append(video);
        const actions=document.createElement('div');actions.className='video-actions';const download=document.createElement('a');download.className='secondary download-link';download.href=`/media/recording/${recording.id}?download=1`;download.textContent='MP4 herunterladen';actions.append(download);
        const replay=document.createElement('button');replay.className='secondary';replay.textContent=data.replay_id===recording.id?'Wiederholung läuft':'Als Source 1 wiederholen';replay.disabled=data.replay_id===recording.id;replay.addEventListener('click',()=>action(()=>api(`/api/recordings/${recording.id}/replay`,{}),'Wiederholung manuell angefordert.',$('.recording-panel')));actions.append(replay);card.append(actions);
      }
      const message=document.createElement('p');message.className='small muted';message.textContent=recording.message;card.append(message);
      if(!['recording','finishing'].includes(recording.status)){
        const remove=document.createElement('button');remove.className='ghost';remove.textContent='Aufnahme löschen';remove.disabled=data.replay_id===recording.id;
        const confirmation=document.createElement('div');confirmation.className='delete-confirm';confirmation.hidden=true;const text=document.createElement('p');text.className='small';text.textContent='Diese Aufnahme endgültig löschen?';confirmation.append(text);
        const yes=document.createElement('button');yes.className='danger';yes.textContent='Endgültig löschen';yes.addEventListener('click',()=>action(async()=>{await api(`/api/recordings/${recording.id}/delete`,{});await loadRecordings(true);},'Aufnahme gelöscht.',$('.recording-panel')));confirmation.append(yes);
        const cancel=document.createElement('button');cancel.className='ghost';cancel.textContent='Abbrechen';cancel.addEventListener('click',()=>confirmation.hidden=true);confirmation.append(cancel);remove.addEventListener('click',()=>confirmation.hidden=!confirmation.hidden);card.append(remove,confirmation);
      }
      list.append(card);
    }
  }finally{recordingLoading=false;}
}
function form(id, endpoint, message, done) {
  const element = $(id);
  if (!element) return;
  element.noValidate = true;
  element.addEventListener('submit', event => {
    event.preventDefault();
    for (const input of element.querySelectorAll('input,select')) {
      if (input.required && !input.value.trim()) {
        formFeedback(element, 'Bitte alle Pflichtfelder ausfüllen.', true);
        input.focus();
        return;
      }
      if (input.minLength > 0 && input.value.length < input.minLength) {
        const title = input.labels?.[0]?.textContent.trim() || 'Das Feld';
        formFeedback(element, `${title} benötigt mindestens ${input.minLength} Zeichen.`, true);
        input.focus();
        return;
      }
    }
    const values = Object.fromEntries(new FormData(element));
    action(async () => {
      await api(endpoint,values);
      for (const field of element.querySelectorAll('input[type=password]')) field.value='';
      if (done) await done();
    },message,element);
  });
}
form('#output-form','/api/output','Anbieter gespeichert. Unter Streaming-Auswahl für den nächsten Start auswählen.');
form('#twitch-output-form','/api/output','Twitch-Schlüssel gespeichert. Unter Streaming-Auswahl für den nächsten Start auswählen.');
form('#youtube-output-form','/api/output','YouTube-Schlüssel gespeichert. Unter Streaming-Auswahl für den nächsten Start auswählen.');
form('#password-form','/api/password','Dein Passwort wurde geändert.');
form('#user-form','/api/admin/users','Benutzer mit Live-Quellen angelegt.',loadAdmin);
form('#oauth-form','/api/admin/oauth','Twitch-App gespeichert.',loadAdmin);
form('#google-form','/api/admin/google','Google-App gespeichert.',loadAdmin);
function uploadVideo(file) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.setRequestHeader('X-CSRF-Token', csrf);
    xhr.responseType = 'json';
    xhr.timeout = 600000;
    transfer = {percent:0};
    if (state) render(state);
    xhr.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      transfer.percent = Math.min(100, Math.round(event.loaded / event.total * 100));
      $('#upload-meter').value = transfer.percent;
      if (state) render(state);
    };
    xhr.onload = () => {
      if (xhr.status === 401) { redirectToLogin(); reject(new Error('Bitte erneut anmelden.')); return; }
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response?.ok) { resolve(xhr.response); return; }
      reject(new Error(xhr.response?.error || (xhr.status === 413 ? 'NPMplus hat den Upload abgewiesen. Upload-Limit im Proxy auf mindestens 501 MB setzen.' : `Upload fehlgeschlagen (HTTP ${xhr.status}). Bitte Verbindung und Proxy prüfen.`)));
    };
    xhr.onerror = () => reject(new Error('Die Verbindung beim Upload wurde unterbrochen. Bitte erneut versuchen.'));
    xhr.ontimeout = () => reject(new Error('Der Upload hat zu lange gedauert. Bitte eine kleinere Datei oder eine schnellere Verbindung verwenden.'));
    xhr.onabort = () => reject(new Error('Upload abgebrochen.'));
    const body = new FormData();body.append('video',file);
    xhr.send(body);
  });
}
$('#upload-form').addEventListener('submit', event => {
  event.preventDefault();
  const file = $('#upload-form [name=video]').files[0];
  if (!file) { formFeedback($('#upload-form'),'Bitte zuerst eine MP4-Datei auswählen.',true); return; }
  if (file.size > 500 * 1024 * 1024) { formFeedback($('#upload-form'),'Die Datei ist zu groß. Maximal 500 MB.',true); return; }
  action(async () => {
    try { await uploadVideo(file); $('#upload-form').reset(); }
    finally { transfer = null; if (state) render(state); }
  }, 'Datei angekommen. Der Verarbeitungsstatus steht direkt darunter.', $('#upload-form'));
});
async function loadAdmin() {
  const data = await api('/api/admin');
  $('#client-id').value=data.client_id;
  $('#client-secret').placeholder=data.secret_set?'Bereits gespeichert; leer lassen zum Beibehalten':'Client-Secret eintragen';
  $('#callback').textContent=data.callback;
  $('#google-client-id').value=data.google_client_id||'';
  $('#google-client-secret').placeholder=data.google_secret_set?'Bereits gespeichert; leer lassen zum Beibehalten':'Client-Secret eintragen';
  $('#google-callback').textContent=data.google_callback;
  const list=$('#user-list');list.replaceChildren();
  for(const user of data.users) {
    const row=document.createElement('div');row.className='user-row';
    const label=document.createElement('span');label.textContent=user.username+' · '+({admin:'Admin',moderator:'Moderator',user:'Benutzer'}[user.role]||user.role)+(!user.active?' · deaktiviert':'');row.append(label);
    if(user.id!==data.current_user_id){
      const role=document.createElement('select');
      for(const value of ['user','moderator','admin'])role.append(new Option({user:'Benutzer',moderator:'Moderator',admin:'Admin'}[value],value,false,user.role===value));
      const owner=document.createElement('select');owner.title='Chat-Konto für Moderator';
      owner.append(new Option('Chat-Konto wählen',''));
      for(const candidate of data.users.filter(item=>item.id!==user.id&&item.role!=='moderator'&&item.active))owner.append(new Option(candidate.username,candidate.id,false,candidate.id===user.chat_owner_id));
      owner.hidden=user.role!=='moderator';role.onchange=()=>owner.hidden=role.value!=='moderator';
      const saveRole=document.createElement('button');saveRole.type='button';saveRole.className='ghost';saveRole.textContent='Rolle speichern';
      saveRole.addEventListener('click',()=>action(async()=>{await api(`/api/admin/users/${user.id}/role`,{role:role.value,chat_owner_id:owner.value||null});await loadAdmin();},'Rolle aktualisiert.',row));
      row.append(role,owner,saveRole);
      const toggle=document.createElement('button');toggle.type='button';toggle.className='ghost';toggle.textContent=user.active?'Deaktivieren':'Aktivieren';
      toggle.addEventListener('click',()=>action(async()=>{await api(`/api/admin/users/${user.id}/toggle`,{});await loadAdmin();},'Benutzer aktualisiert.'));row.append(toggle);
      if(!user.active){
        const remove=document.createElement('button');remove.type='button';remove.className='danger';remove.textContent='Benutzer löschen';
        const confirmation=document.createElement('div');confirmation.className='delete-confirm';confirmation.hidden=true;
        const note=document.createElement('p');note.textContent='Konto und Zugänge werden gelöscht. Vorhandene Mediendateien bleiben separat archiviert. Zur Bestätigung den Benutzernamen eingeben.';
        const input=document.createElement('input');input.placeholder=user.username;input.autocomplete='off';input.setAttribute('aria-label','Benutzernamen zum Löschen bestätigen');
        const yes=document.createElement('button');yes.type='button';yes.className='danger';yes.textContent='Konto löschen';
        yes.addEventListener('click',()=>action(async()=>{await api(`/api/admin/users/${user.id}/delete`,{confirm:input.value.trim()});await loadAdmin();},'Deaktivierter Benutzer gelöscht; Medien archiviert.',confirmation));
        const cancel=document.createElement('button');cancel.type='button';cancel.className='ghost';cancel.textContent='Abbrechen';cancel.addEventListener('click',()=>confirmation.hidden=true);
        confirmation.append(note,input,yes,cancel);remove.addEventListener('click',()=>{confirmation.hidden=!confirmation.hidden;if(!confirmation.hidden)input.focus();});row.append(remove,confirmation);
      }
    }
    list.append(row);
  }
}
$('#admin')?.addEventListener('toggle', () => { if($('#admin').open) loadAdmin().catch(error=>notify(error.message,true)); });
function platformName(kind){return state?.outputs?.find(row=>row.kind===kind)?.label||{twitch:'Twitch',youtube:'YouTube',custom:'Eigener Anbieter'}[kind]||kind;}
function effectiveOutputs(data){return (data.outputs||[]).filter(x=>x.allowed!==false&&(data.enabled?data.output_states?.[x.kind]&&data.output_states[x.kind]!=='stopped':x.selected));}
function renderDestinations(data){
  const destinations=data.outputs||[];const selected=effectiveOutputs(data);
  const signature=JSON.stringify(destinations);
  if(signature!==targetSignature){
    targetSignature=signature;const list=$('#target-list');list.replaceChildren();
    for(const kind of ['twitch','youtube','custom',...destinations.filter(row=>!['twitch','youtube','custom'].includes(row.kind)).map(row=>row.kind)]){
      const destination=destinations.find(x=>x.kind===kind);const row=document.createElement('div');row.className='target-item';
      const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.dataset.outputKind=kind;input.checked=!!destination?.selected;input.disabled=!destination||busy;
      label.append(input,document.createTextNode(platformName(kind)));row.append(label);
      const badge=document.createElement('span');badge.className='badge';badge.textContent=destination?.allowed===false?'Durch Admin gesperrt':destination?.configured!==false&&destination?'Eingerichtet':'Schlüssel fehlt';row.append(badge);
      const manage=document.createElement('a');manage.className='target-manage';manage.textContent=destination?.configured!==false&&destination?'Verwalten →':'Einrichten →';manage.href=['twitch','youtube','custom'].includes(kind)?'#settings-'+kind:'#expert-outputs';row.append(manage);
      list.append(row);
    }
  }
  for(const input of document.querySelectorAll('[data-output-kind]'))input.disabled=busy||!destinations.some(d=>d.kind===input.dataset.outputKind&&d.configured!==false&&d.allowed!==false);
  for(const remove of document.querySelectorAll('[data-remove-output]'))remove.disabled=data.enabled||busy||!destinations.some(row=>row.kind===remove.dataset.removeOutput&&row.configured!==false&&row.allowed!==false);
  for(const label of document.querySelectorAll('[data-platform-state]')){
    const ready=destinations.some(row=>row.kind===label.dataset.platformState&&row.configured!==false);
    label.textContent=ready?'Streaming eingerichtet':'Noch kein Streamschlüssel';label.classList.toggle('good',ready);
  }
  $('#save-targets').disabled=busy;
  const saved=destinations.filter(x=>x.selected&&x.allowed!==false).map(x=>platformName(x.kind)).join(' + ')||'Keine Plattform';
  if($('#target-summary'))$('#target-summary').textContent='Gespeichert für den nächsten Start: '+saved+(data.enabled?' · Aktueller Stream läuft unverändert weiter.':'');
  for(const preset of document.querySelectorAll('[data-target-preset]'))preset.disabled=busy||preset.dataset.targetPreset.split(',').filter(Boolean).some(kind=>!destinations.some(d=>d.kind===kind&&d.configured!==false&&d.allowed!==false));
  const health=$('#destination-health');health.replaceChildren();
  for(const destination of selected){const status=data.output_states?.[destination.kind]||'stopped';const badge=document.createElement('span');badge.className='destination-pill '+status;badge.textContent=platformName(destination.kind)+' · '+({forwarding:'Verbunden',stopped:'Gestoppt',error:'Fehler',connecting:'Verbinde …',renewing:'Neuverbindung'})[status];health.append(badge);}
  const connected=data.chat||{};
  $('#youtube-account').textContent=connected.youtube_connected?'YouTube-Kanal: '+connected.youtube_name:connected.google_ready?'YouTube-Konto für Chat und Sendungsauswahl verbinden.':'Für den Chat muss zuerst eine Google-App in der Administration hinterlegt werden. Ein Streamschlüssel funktioniert unabhängig davon.';
  $('#yt-load').disabled=!connected.youtube_connected||busy;$('#yt-select-chat').disabled=!connected.youtube_connected||busy;$('#yt-use-output').disabled=!connected.youtube_connected||data.enabled||busy;
  $('#youtube-disconnect').disabled=!connected.youtube_connected||busy;$('#twitch-disconnect').disabled=!data.twitch_edit_ready||busy;
}
for(const preset of document.querySelectorAll('[data-target-preset]'))preset.addEventListener('click',()=>{
  const chosen=preset.dataset.targetPreset.split(',').filter(Boolean);
  for(const checkbox of document.querySelectorAll('[data-output-kind]'))checkbox.checked=chosen.includes(checkbox.dataset.outputKind)&&!checkbox.disabled;
  formFeedback($('#targets-form'),'Auswahl geändert. Bitte mit „Streaming-Auswahl speichern“ übernehmen.');
});
$('#targets-form').addEventListener('submit',event=>{event.preventDefault();const kinds=[...document.querySelectorAll('[data-output-kind]:checked:not(:disabled)')].map(x=>x.dataset.outputKind);action(()=>api('/api/outputs/select',{kinds}),'Streaming-Auswahl gespeichert. Konten und gespeicherte Schlüssel bleiben verbunden.',$('#targets-form'));});
for(const [button,tab] of [['#studio-chat-tab','chat'],['#studio-meta-tab','metadata']]){
  $(button).addEventListener('click',()=>{studioTab=tab;$('#studio-chat').hidden=tab!=='chat';$('#twitch-metadata').hidden=tab!=='metadata';$('#studio-chat-tab').setAttribute('aria-selected',String(tab==='chat'));$('#studio-meta-tab').setAttribute('aria-selected',String(tab==='metadata'));if(tab==='chat')loadChat();});
}
function renderChat(){
  if(!chatData)return;
  for(const component of document.querySelectorAll('.chat-component')){
    component.querySelector('.chat-twitch-status').textContent='Twitch · '+chatData.connections.twitch;
    component.querySelector('.chat-youtube-status').textContent='YouTube · '+chatData.connections.youtube;
    component.querySelector('.chat-discord-status').textContent='Discord · '+chatData.connections.discord;
    ChatUI.draw(component.querySelector('.chat-messages'),chatData.messages,component.querySelector('.chat-filter').value);
    const select=component.querySelector('.chat-target');
    for(const option of select.options)option.disabled=option.value==='both'?!(chatData.twitch_ready&&chatData.youtube_chat_ready):option.value==='twitch'?!chatData.twitch_ready:option.value==='youtube'?!chatData.youtube_chat_ready:!chatData.discord_ready;
    if(select.selectedOptions[0]?.disabled){const available=[...select.options].find(x=>!x.disabled);if(available)select.value=available.value;}
    component.querySelector('.chat-message').maxLength=select.value==='twitch'?500:200;
    component.querySelector('.chat-send').disabled=component.dataset.sending==='1'||!select.selectedOptions[0]||select.selectedOptions[0].disabled;
  }
}
async function loadChat(){
  if(chatLoading)return;chatLoading=true;
  try{chatData=await api('/api/chat');renderChat();}
  catch(error){for(const status of document.querySelectorAll('.chat-connections span'))status.textContent='Chat nicht erreichbar · erneuter Versuch folgt';}
  finally{chatLoading=false;}
}
for(const component of document.querySelectorAll('.chat-component')){
  component.querySelector('.chat-filter').addEventListener('change',renderChat);
  component.querySelector('.chat-target').addEventListener('change',renderChat);
  const form=component.querySelector('.chat-compose');
  component.querySelector('.chat-message').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();form.requestSubmit();}});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(component.dataset.sending==='1')return;
    const input=component.querySelector('.chat-message'),target=component.querySelector('.chat-target').value,feedback=component.querySelector('.chat-feedback');
    const message=input.value.replace(/[\r\n]+/g,' ').trim();if(!message)return;
    const targets=target==='both'?['twitch','youtube']:[target];
    const fingerprint=JSON.stringify([message,targets]);
    if(component.dataset.pendingMessage!==fingerprint){component.dataset.pendingMessage=fingerprint;component.dataset.pendingNonce=crypto.randomUUID();}
    component.dataset.sending='1';renderChat();feedback.textContent='Wird gesendet …';
    try{
      const result=await api('/api/chat/send',{message,targets,nonce:component.dataset.pendingNonce});
      component.dataset.pendingMessage='';component.dataset.pendingNonce='';
      feedback.textContent=Object.entries(result.results).map(([platform,outcome])=>platformName(platform)+': '+(outcome.ok?'gesendet':outcome.error)).join(' · ');
      feedback.classList.toggle('error',!result.ok);
      if(result.ok)input.value='';
      else{const failed=Object.entries(result.results).filter(([,x])=>!x.ok).map(([k])=>k);if(failed.length===1){component.querySelector('.chat-target').value=failed[0];feedback.textContent+=' · Erneut senden gilt nur für '+platformName(failed[0])+'.';}}
      await loadChat();
    }catch(error){feedback.textContent=error.message;feedback.classList.add('error');}
    finally{component.dataset.sending='0';renderChat();}
  });
}
$('#yt-load').addEventListener('click',()=>action(async()=>{
  const data=await api('/api/youtube/broadcasts');const select=$('#yt-broadcasts');select.replaceChildren(new Option('Sendung auswählen',''));
  for(const broadcast of data.broadcasts)select.append(new Option(broadcast.title+' · '+broadcast.status,broadcast.id));
  if(state?.chat?.broadcast_id)select.value=state.chat.broadcast_id;
  $('#yt-note').textContent=data.broadcasts.length?'Für Chat auswählen oder den zugehörigen Streamschlüssel ausdrücklich übernehmen.':'Keine offenen Sendungen gefunden. Bitte im YouTube Studio eine Sendung anlegen.';
},null,$('.youtube-broadcast-controls')));
for(const [button,output] of [['#yt-select-chat',false],['#yt-use-output',true]])$(button).addEventListener('click',()=>action(async()=>{
  const id=$('#yt-broadcasts').value;if(!id)throw new Error('Bitte zuerst eine Sendung auswählen.');
  await api('/api/youtube/broadcast',{id,output});await loadChat();
},output?'YouTube-Ausgang und Chat übernommen.':'YouTube-Chat ausgewählt.',$('.youtube-broadcast-controls')));
$('#youtube-disconnect').addEventListener('click',()=>action(()=>api('/api/youtube/disconnect',{}),'YouTube-Konto getrennt. Der gespeicherte Streamschlüssel bleibt erhalten.'));
$('#twitch-disconnect').addEventListener('click',()=>action(()=>api('/api/twitch/disconnect',{}),'Twitch-Konto getrennt. Der gespeicherte Streamschlüssel bleibt erhalten.'));
for(const button of document.querySelectorAll('[data-remove-output]'))button.addEventListener('click',()=>action(()=>api(`/api/outputs/${button.dataset.removeOutput}/delete`,{}),'Streamschlüssel entfernt.',button.closest('.panel')));
function updateWidgetUrl(){
  if(!widgetBase)return;const url=new URL(widgetBase);url.searchParams.set('platform',$('#widget-platform').value);if($('#widget-transparent').checked)url.searchParams.set('transparent','1');$('#widget-url').value=url.href;$('#widget-copy').disabled=false;$('#widget-open').disabled=false;
}
// Also update pages rendered from the running server's template cache.
$('#widget-url').type='text';
$('#widget-load').addEventListener('click',()=>action(async()=>{widgetBase=(await api('/api/chat/widget')).url;updateWidgetUrl();},null,$('.widget-settings')));
$('#widget-rotate').addEventListener('click',()=>action(async()=>{widgetBase=(await api('/api/chat/widget',{})).url;updateWidgetUrl();},'Neuer Widget-Link erstellt. Der bisherige Link ist ungültig.',$('.widget-settings')));
$('#widget-platform').addEventListener('change',updateWidgetUrl);$('#widget-transparent').addEventListener('change',updateWidgetUrl);
$('#widget-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#widget-url').value);notify('Widget-Link kopiert.');}catch(error){notify('Link bitte manuell aus dem Feld kopieren.',true);}});
$('#widget-open').addEventListener('click',()=>{if(widgetBase)window.open($('#widget-url').value,'_blank','noopener');});
const notices={youtube_setup:'Für YouTube-Chat zuerst die Google-App in der Administration einrichten. Streaming per Streamschlüssel ist bereits möglich.',youtube_ok:'YouTube-Konto verbunden. Unter Einstellungen eine Sendung für den Chat auswählen.',youtube_failed:'YouTube-Verbindung fehlgeschlagen. Google-App, Testnutzer, Berechtigung und YouTube-Kanal prüfen.',youtube_cancelled:'YouTube-Verbindung abgebrochen.',oauth_setup:'Bitte die Twitch-App zuerst im Administrationsbereich einrichten.',use_domain:'Für die Kontofreigabe die in STREAMDESK_PUBLIC eingetragene HTTPS-Adresse im Browser öffnen.',oauth_failed:'Twitch-Verbindung fehlgeschlagen. App-Einstellungen prüfen und erneut versuchen.',oauth_cancelled:'Twitch-Verbindung abgebrochen.',oauth_ok:'Twitch-Konto verbunden. Du kannst deinen Stream jetzt starten.'};
const notice=new URLSearchParams(location.search).get('notice');
if(notices[notice]) {
  notify(notices[notice],!['oauth_ok','youtube_ok'].includes(notice));
  const hash=['oauth_setup','youtube_setup'].includes(notice)&&$('#admin')?'#administration':'#settings';
  history.replaceState(null,'',location.pathname+hash);
}
showView();
(async function poll(){await refresh();setTimeout(poll,2000);})();

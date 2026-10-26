'use strict';
(() => {
  const find = selector => document.querySelector(selector);
  let status, loading = false, loaded = false, customsSignature = '';
  const video = find('#playback-video');
  function stopPlayback() {
    video.pause();video.removeAttribute('src');video.load();video.hidden = true;
    find('#playback-download').hidden = true;
  }
  async function load(force=false){
    if(!status?.expert_mode||loading||!force&&loaded)return;
    loading=true;
    try{
      const playback=await api('/api/playback/status');if(!status?.expert_mode)return;
      find('#playback-status').textContent=playback.enabled?'Playback-Server aktiviert. Bitte Quelle und Zeitraum auswählen.':'Playback ist deaktiviert. Ein Administrator kann den Server hier aktivieren.';
      const select=find('#playback-source'),selected=select.value;
      select.replaceChildren(...playback.sources.map(source=>new Option(playback.labels?.[source]||window.StreamDeskRouting?.sourceName(source)||source,source)));
      select.value=playback.sources.includes(selected)?selected:'live';
      if(find('#playback-enabled')){find('#playback-enabled').checked=playback.enabled;find('#playback-address').value=playback.address;}
      loaded=true;
    }catch(error){notify(error.message,true);}finally{loading=false;}
  }
  window.addEventListener('streamdesk:status',event=>{
    const previous=status;status=event.detail;
    if(!status.expert_mode){loaded=false;stopPlayback();}
    if(location.hash==='#expert-playback')load(!previous||previous.expert_mode!==status.expert_mode);
  });
  window.addEventListener('hashchange',()=>{if(location.hash!=='#expert-playback')stopPlayback();else load(true);});
  function submit(selector,callback,message){const form=find(selector);form?.addEventListener('submit',event=>{event.preventDefault();action(callback,message,form);});}
  submit('#playback-server',async()=>{await api('/api/admin/playback',{enabled:find('#playback-enabled').checked,address:find('#playback-address').value.trim()});stopPlayback();await load(true);},'Playback-Konfiguration gespeichert.');
  function play(url, source, start, duration) {
    if (!status?.expert_mode) return;
    stopPlayback();video.src = url;video.hidden = false;
    const download = find('#playback-download');download.href = url;download.hidden = false;
    const local = new Date(start);local.setMinutes(local.getMinutes()-local.getTimezoneOffset());
    find('#playback-clip-start').value = local.toISOString().slice(0,-1);
    find('#playback-duration').value = Math.max(1,Math.min(3600,Math.floor(duration)));
    video.play().catch(() => {});
  }
  submit('#playback-search',async () => {
    stopPlayback();const source = find('#playback-source').value;
    const value = find('#playback-start').value;
    const query = value ? '?start='+encodeURIComponent(new Date(value).toISOString()) : '';
    const data = await api('/api/playback/'+source+'/spans'+query);
    const list = find('#playback-spans');list.replaceChildren();
    if (!data.spans.length) list.textContent = 'Keine Segmente für diesen Zeitraum vorhanden.';
    for (const row of data.spans) {
      const button = document.createElement('button');button.type = 'button';button.className = 'secondary';
      button.textContent = new Date(row.start).toLocaleString('de-DE')+' · '+Math.round(row.duration)+' s';
      button.addEventListener('click',() => play(row.url,source,row.start,Math.min(row.duration,3600)));list.append(button);
    }
  },'Segmentliste geladen.');
  submit('#playback-clip',async () => {
    const start = new Date(find('#playback-clip-start').value).toISOString();
    const duration = Number(find('#playback-duration').value), source = find('#playback-source').value;
    play('/api/playback/'+source+'/media?'+new URLSearchParams({start,duration,format:'fmp4'}),source,start,duration);
  },'Ausschnitt geöffnet.');
  find('#playback-source').addEventListener('change',() => {stopPlayback();find('#playback-spans').replaceChildren();});
  video.addEventListener('error',() => {if(video.getAttribute('src'))notify('Wiedergabe nicht verfügbar. Zeitraum, Aufnahmeformat und Serverstatus prüfen.',true);});
})();

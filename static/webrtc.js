'use strict';
(() => {
  const video = document.querySelector('#rtc-video'), message = document.querySelector('#rtc-status');
  const start = document.querySelector('#rtc-start'), stop = document.querySelector('#rtc-stop');
  const mode = document.body.dataset.mode, slot = document.body.dataset.slot, program = document.body.dataset.program || 'main';
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  let pc, media, resource, generation = 0;
  async function cleanup() {
    generation++;
    const target = resource;resource = null;
    if (pc) { pc.onconnectionstatechange = null;pc.close();pc = null; }
    if (media) { media.getTracks().forEach(track => track.stop());media = null; }
    video.srcObject = null;start.disabled = document.body.dataset.enabled !== 'true';stop.disabled = true;
    if (target) {
      try { await fetch(target,{method:'DELETE',headers:{'X-CSRF-Token':csrf},credentials:'same-origin',keepalive:true}); }
      catch (_) { /* Closing the peer connection also lets MediaMTX expire the session. */ }
    }
  }
  async function checked(response) {
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Verbindung fehlgeschlagen (HTTP ${response.status}).`);
    }
    return response;
  }
  start.addEventListener('click',async () => {
    await cleanup();start.disabled = true;stop.disabled = false;
    const current = generation;
    try {
      if (!window.RTCPeerConnection) throw new Error('Dieser Browser unterstützt WebRTC nicht.');
      if (mode === 'publish') {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('Kamera-Publish benötigt eine sichere HTTPS-Verbindung.');
        const stream = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},frameRate:{ideal:30}},audio:true});
        if (current !== generation) { stream.getTracks().forEach(track => track.stop());return; }
        media = stream;video.srcObject = media;
      }
      message.textContent = 'WebRTC-Verbindung wird aufgebaut …';
      const ice = await (await checked(await fetch('/api/webrtc/ice',{credentials:'same-origin',cache:'no-store'}))).json();
      if (current !== generation) return;
      const peer = new RTCPeerConnection(ice);pc = peer;
      if (mode === 'publish') {
        const capabilities = RTCRtpSender.getCapabilities('video');
        const codecs = (capabilities?.codecs || []).filter(codec => codec.mimeType.toLowerCase() === 'video/h264');
        if (!codecs.length) throw new Error('Dieser Browser kann kein H.264 senden. Bitte einen passenden Browser oder OBS verwenden.');
        codecs.sort((a,b) => Number(!a.sdpFmtpLine?.includes('profile-level-id=42')) - Number(!b.sdpFmtpLine?.includes('profile-level-id=42')));
        for (const track of media.getTracks()) {
          const sender = peer.addTrack(track,media);
          if (track.kind === 'video') {
            const transceiver = peer.getTransceivers().find(item => item.sender === sender);
            if (!transceiver.setCodecPreferences) throw new Error('Dieser Browser unterstützt die erforderliche H.264-Auswahl nicht.');
            transceiver.setCodecPreferences(codecs);
          }
        }
      } else {
        peer.addTransceiver('video',{direction:'recvonly'});peer.addTransceiver('audio',{direction:'recvonly'});
        const stream = new MediaStream();video.srcObject = stream;
        peer.ontrack = event => stream.addTrack(event.track);
      }
      peer.onconnectionstatechange = () => {
        if (peer.connectionState === 'connected') message.textContent = mode === 'publish' ? 'Kamera wird gesendet.' : 'Vorschau verbunden. Ton über den Player einschalten.';
        if (['failed','closed'].includes(peer.connectionState)) { message.textContent = 'Verbindung beendet. WebRTC-Port und Codecs prüfen.';cleanup(); }
      };
      await peer.setLocalDescription(await peer.createOffer());
      await new Promise((resolve,reject) => {
        const timer = setTimeout(() => { peer.removeEventListener('icegatheringstatechange',changed);reject(new Error('ICE-Kandidaten konnten nicht rechtzeitig ermittelt werden.')); },10000);
        function changed() { if (peer.iceGatheringState === 'complete' || peer.connectionState === 'closed') { clearTimeout(timer);peer.removeEventListener('icegatheringstatechange',changed);resolve(); } }
        peer.addEventListener('icegatheringstatechange',changed);changed();
      });
      if (current !== generation) return;
      const response = await checked(await fetch(`/api/webrtc/${slot}/${mode}?program=${encodeURIComponent(program)}`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/sdp','X-CSRF-Token':csrf},body:peer.localDescription.sdp}));
      const location = response.headers.get('Location');
      if (current !== generation) { if (location) fetch(location,{method:'DELETE',headers:{'X-CSRF-Token':csrf},keepalive:true});return; }
      resource = location;
      await peer.setRemoteDescription({type:'answer',sdp:await response.text()});
      video.play().catch(() => {});
    } catch (error) {
      if (current === generation) { message.textContent = error.name === 'NotAllowedError' ? 'Zugriff auf Kamera oder Mikrofon wurde nicht erlaubt.' : error.message;await cleanup(); }
    }
  });
  stop.addEventListener('click',() => { message.textContent = 'Verbindung beendet.';cleanup(); });
  const check = setInterval(async () => {
    try {
      const response = await fetch('/api/expert-mode',{cache:'no-store'});
      if (!response.ok || !(await response.json()).expert_mode) { await cleanup();start.disabled = true;message.textContent = 'Bitte in StreamDesk anmelden und den Expertenmodus aktivieren.'; }
    } catch (_) { /* A temporary UI outage does not interrupt an established peer. */ }
  },10000);
  window.addEventListener('pagehide',() => { clearInterval(check);cleanup(); });
})();

'use strict';
(() => {
  const find = selector => document.querySelector(selector);
  let status, advanced, loading = false, lastLoad = 0, signature = '';
  const labels = {auto:'Automatisch · OBS → Handy → Source 3 → Pull → Offline',source1:'Source 1 fest gewählt',source2:'Source 2 fest gewählt',source3:'Source 3 fest gewählt',pull:'RTSP-Pull fest gewählt',offline:'Offline-Video fest gewählt'};
  const systemTheme = matchMedia('(prefers-color-scheme: light)');
  function resolveTheme() {
    const theme = document.documentElement.dataset.theme;
    document.documentElement.dataset.resolvedTheme = theme === 'light' || theme === 'system' && systemTheme.matches ? 'light' : 'dark';
  }
  systemTheme.addEventListener('change',resolveTheme);
  resolveTheme();
  function setMode(enabled) {
    const changed=document.documentElement.dataset.expert!==String(enabled);
    document.documentElement.dataset.expert = String(enabled);
    find('#expert-menu-state').textContent = enabled ? 'Aktiv' : 'Aus';
    for (const panel of document.querySelectorAll('[data-expert-only]')) {
      panel.hidden = !enabled;
      if(!enabled||changed)for (const control of panel.querySelectorAll('input,select,button')) control.disabled = !enabled;
    }
    if (find('#webrtc-fields')) find('#webrtc-fields').disabled = !enabled || !advanced;
    if (!enabled && location.hash.startsWith('#expert-')) {
      history.replaceState(null,'','#expert');showView();
    }
  }
  function protocols() {
    const list = find('#protocol-status');list.replaceChildren();
    const rtc = document.createElement('p');
    const active = advanced.webrtc && advanced.webrtc_runtime !== false;
    rtc.textContent = !advanced.webrtc ? 'WebRTC ist deaktiviert. Ein Administrator kann den Server im Formular darunter aktivieren.' : advanced.webrtc_runtime === false ? 'WebRTC ist konfiguriert, aber auf dem laufenden Server noch deaktiviert. Konfiguration erneut speichern und Status aktualisieren.' : `WebRTC ist aktiviert · UDP/ICE: ${advanced.webrtc_ice_address || 'nicht eingerichtet'}.`;
    list.append(rtc);
    const srt = document.createElement('p');
    srt.textContent = `SRT: ${advanced.srt.enabled ? 'aktiviert' : 'deaktiviert'} · Listener: ${advanced.srt.address}. ` + (advanced.srt.auth_ready ? 'Deine Publish-Berechtigung ist vorhanden; die gespeicherten Zugangsdaten sind konsistent.' : 'Deine Publish-Berechtigung oder gespeicherten Zugangsdaten konnten nicht bestätigt werden.');
    list.append(srt);
    if (advanced.srt.publish_passphrase_required) {
      const note = document.createElement('p');note.textContent = 'Für deinen SRT-Eingang ist zusätzlich eine Verschlüsselungs-Passphrase konfiguriert. Diese im Encoder separat hinterlegen; sie ist unabhängig vom Medienpasswort.';list.append(note);
    }
    if (!advanced.srt.runtime_checked) {
      const note = document.createElement('p');note.className = 'small muted';note.textContent = 'Laufzeitstatus noch nicht bestätigt. Angezeigt werden die gespeicherten Einstellungen.';list.append(note);
    }
    for (const link of document.querySelectorAll('[data-webrtc-link]')) {
      link.setAttribute('aria-disabled',String(!active));link.tabIndex = active ? 0 : -1;
    }
    find('#webrtc-availability').textContent = active ? 'WebRTC ist freigeschaltet. Kamera oder Vorschau auf Wunsch starten.' : 'Kamera und Vorschau werden nach der WebRTC-Aktivierung freigeschaltet.';
    const suggestion = find('#webrtc-use-host');
    if (suggestion) suggestion.textContent = 'Ingest-Host übernehmen: ' + advanced.webrtc_suggested_host;
  }
  function nativeFields() {
    const item = advanced?.native.find(row => row.source === find('#native-source').value);
    if (!item) return;
    find('#native-enabled').checked = item.enabled;
    for (const key of ['format','segment','retention']) {
      const select = find('#native-' + key);
      if (![...select.options].some(option => option.value === item[key])) select.append(new Option(item[key] + ' (bestehend)',item[key]));
      select.value = item[key];
    }
  }
  async function loadAdvanced(force = false) {
    if (!status?.expert_mode || loading || !force && Date.now() - lastLoad < 10000) return;
    loading = true;
    try {
      advanced = await api('/api/expert');
      if (!status?.expert_mode) return;
      lastLoad = Date.now();
      find('#viewer-url').value = advanced.viewer_url;
      const nativeSelect=find('#native-source'),oldSource=nativeSelect.value;
      if(JSON.stringify([...nativeSelect.options].map(option=>option.value))!==JSON.stringify(advanced.native.map(row=>row.source))){nativeSelect.replaceChildren(...advanced.native.map(row=>new Option(row.label||window.StreamDeskRouting?.sourceName(row.source)||row.source,row.source)));nativeSelect.value=advanced.native.some(row=>row.source===oldSource)?oldSource:'live';}
      if (force) {
        nativeFields();
        if (find('#webrtc-enabled')) {
          find('#webrtc-enabled').checked = advanced.webrtc;
          find('#webrtc-hosts').value = advanced.webrtc_hosts.join(', ');
        }
      }
      find('#native-status').textContent = advanced.native.map(row => `${row.source}: ${row.enabled ? 'aktiv' : 'aus'}`).join(' · ') + (advanced.native_storage_ready ? ` · ${advanced.native_free_mb} MB frei` : ' · Aufnahmeverzeichnis fehlt: Installer im Update-Modus ausführen.');
      find('#viewer-disable').disabled = !advanced.viewer_url;
      find('#viewer-copy').disabled = !advanced.viewer_url;
      if (find('#webrtc-fields')) find('#webrtc-fields').disabled = false;
      protocols();
    } catch (error) { notify(error.message,true); }
    finally { loading = false; }
  }
  function outputButtons() {
    const list = find('#individual-outputs');
    const key = JSON.stringify([status.outputs,status.output_states,status.expert_mode,status.ok,status.state]);
    if (key === signature) return;
    signature = key;
    list.replaceChildren();
    for (const output of status.outputs || []) {
      const running = (status.output_states?.[output.kind] || 'stopped') !== 'stopped';
      const button = document.createElement('button');
      button.type = 'button';button.className = running ? 'danger' : 'secondary';
      button.textContent = platformName(output.kind) + (running ? ' stoppen' : ' starten');
      button.disabled = !status.expert_mode || !status.ok || status.state === 'renewing';
      button.addEventListener('click',() => action(() => api(`/api/outputs/${output.kind}/${running ? 'stop' : 'start'}`,{}),'Streamingziel aktualisiert.',list));
      list.append(button);
    }
    if (!list.children.length) list.textContent = 'Zuerst einen Streaming-Ausgang einrichten.';
  }
  window.addEventListener('streamdesk:status',event => {
    const previous = status;
    status = event.detail;
    document.documentElement.dataset.theme = status.theme || 'system';
    resolveTheme();
    setMode(status.expert_mode);
    // Keep unsaved form choices while background polling updates stream health.
    if (!previous || previous.expert_mode !== status.expert_mode) find('#expert-mode').checked = status.expert_mode;

    find('#source-mode-status').textContent = 'Source 1 und Source 2 sind feste Standardquellen. Die Priorität wird je Ausgang aus den zugeordneten Quellen bestimmt.';
    outputButtons();
    if (location.hash.startsWith('#expert')) loadAdvanced(!advanced || !previous || !previous.expert_mode && status.expert_mode);
  });
  const submit = (selector, callback, message) => find(selector).addEventListener('submit',event => {
    event.preventDefault(); action(callback,message,find(selector));
  });
  submit('#theme-form',async () => {
    const theme = find('#theme').value;
    await api('/api/preferences',{theme});document.documentElement.dataset.theme = theme;resolveTheme();
  },'Darstellung gespeichert.');
  submit('#expert-form',async () => {
    const data = await api('/api/expert-mode',{enabled:find('#expert-mode').checked});
    if (!data.expert_mode) advanced = null;
    setMode(data.expert_mode);lastLoad = 0;
  },'Bedienmodus gespeichert.');

  submit('#native-form',async () => {
    await api('/api/native-recording',{source:find('#native-source').value,enabled:find('#native-enabled').checked,format:find('#native-format').value,segment:find('#native-segment').value,retention:find('#native-retention').value});
    await loadAdvanced(true);
  },'Native Aufnahmeeinstellungen gespeichert.');
  find('#native-source').addEventListener('change',nativeFields);
  find('#webrtc-server-form')?.addEventListener('submit',event => {
    event.preventDefault();action(async () => {
      await api('/api/admin/webrtc',{enabled:find('#webrtc-enabled').checked,hosts:find('#webrtc-hosts').value.split(',').map(host => host.trim()).filter(Boolean)});
      await loadAdvanced(true);
    },'WebRTC-Konfiguration gespeichert.',event.currentTarget);
  });
  find('#webrtc-use-host')?.addEventListener('click',() => {
    if (!advanced) return;
    const hosts = new Set(find('#webrtc-hosts').value.split(',').map(host => host.trim()).filter(Boolean));
    hosts.add(advanced.webrtc_suggested_host);find('#webrtc-hosts').value = [...hosts].join(', ');
  });
  find('#protocol-refresh').addEventListener('click',() => loadAdvanced(true));
  for (const link of document.querySelectorAll('[data-webrtc-link]')) link.addEventListener('click',event => {
    if (link.getAttribute('aria-disabled') === 'true') { event.preventDefault();notify('WebRTC zuerst im Formular darüber aktivieren.',true); }
  });
  for (const [selector,enabled] of [['#viewer-enable',true],['#viewer-disable',false]]) find(selector).addEventListener('click',() => action(async () => {
    const data = await api('/api/viewer-link',{enabled});find('#viewer-url').value = data.url;await loadAdvanced(true);
  },enabled ? 'Neuer Zuschauer-Link erstellt. Bisherige Links sind ungültig.' : 'Zuschauer-Link widerrufen.',find(selector).closest('section')));
  find('#viewer-copy').addEventListener('click',async () => {
    try { await navigator.clipboard.writeText(find('#viewer-url').value);notify('Zuschauer-Link kopiert.'); }
    catch (_) { notify('Bitte den Link markieren und manuell kopieren.',true); }
  });
  async function segments() {
    try {
      const data = await api('/api/native-recordings');const list = find('#native-list');list.replaceChildren();
      if (!data.segments.length) { list.textContent = 'Noch keine nativen Aufnahmesegmente vorhanden.';return; }
      for (const segment of data.segments) {
        const row = document.createElement('details');row.className = 'native-segment';
        const title = document.createElement('summary');title.textContent = `${segment.label||segment.source} · ${new Date(segment.modified * 1000).toLocaleString('de-DE')} · ${bytes(segment.size)}`;
        const link = document.createElement('a');link.href = segment.url;link.textContent = 'Segment herunterladen';link.download = segment.name;
        row.append(title,link);
        if (segment.name.endsWith('.mp4')) row.addEventListener('toggle',() => {
          let video = row.querySelector('video');
          if (row.open && !video) { video = document.createElement('video');video.controls = true;video.playsInline = true;video.preload = 'none';video.src = segment.url;row.append(video); }
          if (!row.open && video) { video.pause();video.removeAttribute('src');video.load();video.remove(); }
        });
        list.append(row);
      }
    } catch (error) { notify(error.message,true); }
  }
  find('#native-reload').addEventListener('click',segments);
  window.addEventListener('hashchange',() => {
    if (location.hash.startsWith('#expert')) loadAdvanced(!advanced);
    if (location.hash === '#recordings') segments();
  });
  setMode(document.documentElement.dataset.expert === 'true');
  if (location.hash === '#recordings') segments();
})();

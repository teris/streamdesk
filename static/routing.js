'use strict';
(() => {
  const find=selector=>document.querySelector(selector);
  let status,model,loading=false,sourceSignature='',expertSignature='',selectedSource='source1',selectedTarget='main';
  const make=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
  function sourceName(key){
    if(key==='live')return 'Standardprogramm';
    const source=status?.sources?.find(row=>row.key===key);if(source)return source.label;
    const group=status?.programs?.find(row=>row.id===key);return group?'Programm · '+group.targets.map(labelFor).join(' + '):key;
  }
  function field(form,title,type='text',value=''){const label=make('label',title),input=make('input');input.type=type;input.value=value;label.append(input);form.append(label);return input;}
  function button(text,callback,style='secondary'){const node=make('button',text,style);node.type='button';node.addEventListener('click',callback);return node;}
  function labelFor(kind){return status?.outputs?.find(row=>row.kind===kind)?.label||model?.outputs.find(row=>row.kind===kind)?.label||{twitch:'Twitch',youtube:'YouTube',custom:'Eigener Anbieter'}[kind]||kind;}
  function chain(keys){return (status?.sources||model?.sources||[]).filter(row=>keys.includes(row.key)).map(row=>row.label+' ('+row.priority+')').join(' → ')||'Keine Quelle zugeordnet';}
  function program(data=status){
    if(!data)return;
    const select=find('#program-select'),values=[{value:'main',label:'Standardprogramm · Source 1 & 2'},...(data.outputs||[]).map(row=>({value:row.kind,label:row.label}))];
    if(JSON.stringify([...select.options].map(option=>[option.value,option.textContent]))!==JSON.stringify(values.map(row=>[row.value,row.label])))select.replaceChildren(...values.map(row=>new Option(row.label,row.value)));
    if(!values.some(row=>row.value===selectedTarget))selectedTarget='main';select.value=selectedTarget;
    const target=data.outputs?.find(row=>row.kind===selectedTarget),pid=target?.program||'main';
    const current=data.programs?.find(row=>row.id===pid),preview=find('#source3 iframe'),toggle=find('#source3 .preview-toggle');
    const url=current?.preview_url||data.public_url+'/program/main/';
    find('#program-link').value=url;find('#program-link-open').href=url;
    const pl=current?.playlist;if(find('#program-playout'))find('#program-playout').textContent=pl?.preparing?'Playlist wird vorbereitet · '+pl.name:pl?.active?'▷ '+pl.name+' · '+pl.video+' · Position '+Math.floor(pl.offset)+' s':pl?.paused?'Live hat Vorrang · '+pl.name+' pausiert':pl?.error||'';
    find('#program-webrtc-open').href=current?.webrtc_url||data.public_url+'/webrtc/3/play/';
    find('#program-webrtc-open').hidden=!data.expert_mode;
    find('#program-route').textContent='Priorität: '+chain(current?.sources||['source1','source2'])+(current?.sources?.length?' → Offline-Video':'');
    find('#destination').textContent=(current?.targets||[]).filter(kind=>data.outputs?.some(output=>output.kind===kind&&output.configured!==false)).map(labelFor).join(' + ')||'Lokale Programmvorschau';
    find('#active-source').textContent=current?.selected_source?sourceName(current.selected_source):current?.offline_playing?'Offline-Video':'Standby';
    const available=!!current?.available;
    preview.hidden=currentView!=='dashboard'||!programPreviewWanted||!available;
    const relative='/program/'+pid+'/';
    if(!preview.hidden&&preview.getAttribute('src')!==relative)preview.src=relative;
    if(preview.hidden&&preview.getAttribute('src')!=='about:blank')preview.src='about:blank';
    window.StreamDeskPreviewAudio?.sync();
    toggle.disabled=!available;toggle.textContent=!available?'Vorschau wird vorbereitet':programPreviewWanted?'Vorschau schließen':'Vorschau öffnen';
    find('#source3 .placeholder p').textContent=available?'Vorschau geschlossen':'Das Programm wird vorbereitet.';
    find('#program-hint').textContent='Ausgewählt: '+(target?.label||'Standardprogramm')+'. '+(current?.sources?.length?'Auch ohne gestartetes Streamingziel verfügbar.':'Diesem Ausgang zuerst im Expertenmodus Quellen zuordnen.');
  }
  function credentialValue(container,title,value){const label=make('label',title),code=make('code',value);label.append(code,button('Kopieren',async()=>{try{await navigator.clipboard.writeText(value);notify('Kopiert.');}catch(_){notify('Bitte den Text markieren und manuell kopieren.',true);}},'ghost'));container.append(label);}
  function sourceCards(data){
    const signature=JSON.stringify(data.sources.map(row=>[row.key,row.label,row.protocol,row.fixed,row.enabled,row.priority]));
    if(signature!==sourceSignature){
      sourceSignature=signature;const list=find('#source-cards');list.replaceChildren();
      const pills=find('#dashboard-source-pills');pills.querySelectorAll('[data-source-pill]').forEach(node=>node.remove());
      for(const source of data.sources){
        const card=make('article',undefined,'panel source');card.id=source.fixed?source.key:'input-'+source.key;card.dataset.sourceKey=source.key;
        const heading=make('div',undefined,'source-heading'),title=make('div');title.append(make('span',source.key.replace('source','Source ')+' · Ebene '+source.priority,'source-number'),make('h3',source.label));heading.append(title,make('span','Prüfe …','badge'));
        const preview=make('div',undefined,'preview'),placeholder=make('div',undefined,'placeholder');placeholder.append(make('span','▣'),make('p','Bildvorschau bei Bedarf öffnen'));const frame=make('iframe');frame.title=source.label+' Vorschau';frame.allow='autoplay; fullscreen';frame.hidden=true;preview.append(placeholder,frame);
        const footer=make('div',undefined,'source-footer'),toggle=button('Vorschau öffnen',()=>{frame.hidden=!frame.hidden;frame.src=frame.hidden?'about:blank':'/preview/source/'+source.key+'/';toggle.textContent=frame.hidden?'Vorschau öffnen':'Vorschau schließen';},'ghost source-preview-toggle');footer.append(make('span','— Mbit/s','rate'),toggle);
        card.append(heading,preview,footer,make('p',(source.fixed?'Feste Standardquelle':'Zusätzliche Quelle')+' · '+source.protocol.toUpperCase(),'small muted'));
        const details=make('details',undefined,'source-credentials');details.append(make('summary','Verbindungsdaten · '+source.label));const fields=make('div',undefined,'credential-fields');details.append(fields);
        if(['rtmp','srt','webrtc','mpegts','rtp','moq'].includes(source.protocol)){
          details.addEventListener('toggle',async()=>{
            if(!details.open){fields.replaceChildren();return;}if(fields.childElementCount)return;
            fields.textContent='Zugangsdaten werden geladen …';
            try{const result=await api('/api/ingest/'+source.key);if(!details.open)return;fields.replaceChildren();
              credentialValue(fields,'Publish-Adresse',result[result.protocol]);
              fields.append(make('p','Nur Listener verwenden, die ein Administrator unter Protokolle aktiviert hat. H.264 und AAC sind die kompatibelste Wahl.','small muted'));
              const separate=make('details');separate.append(make('summary','Getrennte Felder für andere Apps'));
              if(result.protocol==='srt'){credentialValue(separate,'SRT-Server',result.srt_server);credentialValue(separate,'Publish-Stream-ID',result.stream_id);credentialValue(separate,'SRT-Leseadresse',result.srt_read);separate.append(make('p','Modus Caller · Latenz 1000 ms · Paketgröße 1316','small muted'));}
              else if(result.username){credentialValue(separate,'Medien-Benutzername',result.username);credentialValue(separate,'Medien-Passwort',result.password);}
              if(result.protocol==='rtmp'&&result.rtmps)credentialValue(separate,'RTMPS-Adresse',result.rtmps);
              if(result.sdp)credentialValue(separate,'RTP-SDP',result.sdp);
              fields.append(separate,button('Zugangsdaten verbergen',()=>{details.open=false;fields.replaceChildren();},'ghost'));
            }catch(error){fields.textContent=error.message;}
          });card.append(details);
        }else card.append(make('p','Pull-Adresse und Aktivierung im Expertenmodus verwalten.','small muted'));
        list.append(card);
        const pill=make('a',undefined,'source-pill');pill.href='#sources';pill.dataset.sourcePill=source.key;pills.insertBefore(pill,find('#dash-recording'));
      }
    }
    for(const source of data.sources){const card=find('[data-source-key="'+source.key+'"]'),state=!data.ok?'unknown':!source.enabled?'disabled':source.state;
      card.querySelector('h3').textContent=source.key==='source1'&&data.replay_id?'Source 1 · Wiederholung':source.label;
      const label={online:'Online',offline:'Offline',stalled:'Keine Daten',unknown:'Unbekannt',disabled:'Deaktiviert'}[state]||'Prüfe …';
      card.querySelector('.badge').textContent=label;card.querySelector('.badge').className='badge '+state;
      card.querySelector('.rate').textContent=source.state==='online'?Number(source.mbps).toLocaleString('de-DE',{minimumFractionDigits:2,maximumFractionDigits:2})+' Mbit/s':'— Mbit/s';
      card.querySelector('.source-preview-toggle').disabled=!source.enabled;
      const pill=find('[data-source-pill="'+source.key+'"]');pill.textContent='● '+source.label+' · '+label;pill.className='source-pill '+state;
    }
    const record=find('#record-source'),previous=record.value,choices=[...data.sources.map(row=>[row.key,row.label]),['live','Standardprogramm'],...(data.programs||[]).filter(row=>row.id!=='main'&&row.sources.length).map(row=>[row.id,'Programm · '+row.targets.map(labelFor).join(' + ')])];
    if(JSON.stringify([...record.options].map(option=>option.value))!==JSON.stringify(choices.map(row=>row[0]))){record.replaceChildren(...choices.map(row=>new Option(row[1],row[0])));record.value=choices.some(row=>row[0]===previous)?previous:'live';}
  }
  function render(data){status=data;sourceCards(data);program(data);if(!data.expert_mode){model=null;expertSignature='';find('#routing-source-editor').replaceChildren();}else if(location.hash.startsWith('#expert'))load();}
  async function load(force=false){if(!window.StreamDeskServices.allowed('advanced_routing')||!status?.expert_mode||loading||model&&!force)return;loading=true;
    try{model=await api('/api/routing');if(!status.expert_mode)return;experts();
      find('#policy-healthy').value=model.policy.healthy_seconds;find('#policy-stall').value=model.policy.stall_seconds;find('#policy-retry').value=model.policy.retry_seconds;find('#policy-native-standby').checked=!!model.policy.native_standby;
    }catch(error){notify(error.message,true);}finally{loading=false;}}
  function sourceEditor(){
    const source=model.sources.find(row=>row.key===selectedSource)||model.sources[0];selectedSource=source.key;
    const nav=find('#routing-source-nav');nav.replaceChildren();
    for(const row of model.sources){const tab=button(row.label,()=>{selectedSource=row.key;sourceEditor();},'secondary');tab.setAttribute('aria-pressed',String(row.key===selectedSource));nav.append(tab);}
    const editor=find('#routing-source-editor');editor.replaceChildren(make('h3',source.label));
    if(source.fixed)editor.append(make('p','Feste Standardquelle · '+source.protocol.toUpperCase()+' · Priorität '+source.priority+'. Name, Protokoll und Priorität bleiben unverändert.','small muted'));
    else{
      const form=make('form'),name=field(form,'Name','text',source.label),priority=field(form,'Priorität / Ebene','number',source.priority);name.maxLength=60;priority.min=3;priority.max=999;
      const typeLabel=make('label','Verbindung'),type=make('select');for(const [value,label]of[['srt','SRT-Publish'],['rtmp','RTMP-Publish'],['webrtc','WebRTC/WHIP'],['mpegts','MPEG-TS Publish'],['rtp','RTP Publish'],['moq','Media-over-QUIC'],['rtsp','RTSP-Pull'],['proxy','Pfad-Proxy']])type.append(new Option(label,value));type.value=source.protocol==='rtsps'?'rtsp':source.protocol;typeLabel.append(type);form.append(typeLabel);
      const url=field(form,'Neue Pull-/UDP-Adresse (leer = behalten)','password');url.autocomplete='new-password';
      const sdpLabel=make('label','Neue RTP-SDP'),sdp=make('textarea');sdp.rows=7;sdp.maxLength=8192;sdpLabel.append(sdp);form.append(sdpLabel);
      const fields=()=>{url.parentElement.hidden=!['rtsp','mpegts','rtp','proxy'].includes(type.value);sdpLabel.hidden=type.value!=='rtp';};fields();type.addEventListener('change',fields);
      const enabledLabel=make('label',' Quelle aktiviert','feature-check'),enabled=make('input');enabled.type='checkbox';enabled.checked=source.enabled;enabledLabel.prepend(enabled);form.append(enabledLabel);
      const demandLabel=make('label',' Source nur bei Lesebedarf verbinden','feature-check'),demand=make('input');demand.type='checkbox';demand.checked=!!source.source_on_demand;demandLabel.prepend(demand);form.append(demandLabel);
      const save=make('button','Quelleneinstellungen speichern','secondary');form.append(save,button('Quelle entfernen',()=>action(async()=>{await api('/api/routing/sources/'+source.key+'/delete',{});selectedSource='source1';await load(true);},'Quelle entfernt. Vorhandene Aufnahmen bleiben erhalten.',form),'ghost'));
      form.addEventListener('submit',event=>{event.preventDefault();const body={label:name.value,priority:Number(priority.value),protocol:type.value,url:url.value,sdp:sdp.value,enabled:enabled.checked,source_on_demand:demand.checked};action(async()=>{await api('/api/routing/sources/'+source.key,body);url.value='';sdp.value='';await load(true);},'Quelle gespeichert.',form);});editor.append(form);
    }
    const routes=make('form'),heading=make('h4','Diese Quelle an folgende Ausgänge routen');routes.append(heading);
    for(const output of model.outputs){const label=make('label',output.label+(output.configured?'':' · Zugangsdaten fehlen'),'feature-check'),input=make('input');input.type='checkbox';input.value=output.kind;input.checked=output.sources.includes(source.key);input.disabled=(status.output_states?.[output.kind]||'stopped')!=='stopped';label.prepend(input);routes.append(label);}
    routes.append(make('p','Laufende Ausgänge bleiben unverändert. Für eine neue Zuordnung den betroffenen Ausgang zuerst stoppen.','small muted'),make('button','Zielzuordnung für '+source.label+' speichern','secondary'));
    routes.addEventListener('submit',event=>{event.preventDefault();const targets=[...routes.querySelectorAll('input:checked')].map(input=>input.value);action(async()=>{await api('/api/routing/sources/'+source.key+'/targets',{targets});await load(true);},'Zielzuordnung gespeichert.',routes);});editor.append(routes);
  }
  function experts(){
    if(!model)return;sourceEditor();const list=find('#routing-output-list');list.replaceChildren();
    for(const output of model.outputs){const details=make('details',undefined,'routing-output'),summary=make('summary',output.label+' · '+(output.fixed?'Standard':output.platform));details.append(summary,make('p','Priorität: '+chain(output.sources),'small muted'));
      if(output.configured||!output.fixed){const form=make('form'),label=field(form,'Name','text',output.label),secret=field(form,output.platform==='custom'?'Neue Zieladresse (optional)':'Neuer Streamschlüssel (optional)','password');secret.autocomplete='new-password';form.append(make('button','Änderungen speichern','secondary'));
        form.addEventListener('submit',event=>{event.preventDefault();const body={label:label.value,[output.platform==='custom'?'url':'key']:secret.value};action(async()=>{await api('/api/routing/outputs/'+output.kind,body);secret.value='';await load(true);},'Ausgang gespeichert.',form);});details.append(form);
        if(!output.fixed)details.append(button('Ausgang entfernen',()=>action(async()=>{await api('/api/routing/outputs/'+output.kind+'/delete',{});await load(true);},'Ausgang entfernt.',details),'ghost'));
      }else{const link=make('a','Zugangsdaten in Einstellungen hinterlegen');link.href='#settings';details.append(link);}list.append(details);
    }
    find('#source-create button').disabled=model.sources.length>=model.limits.sources;
    find('#routing-output-create button').disabled=model.outputs.length>=model.limits.outputs;
    overview();
  }
  function overview(){if(!model)return;const wrapper=find('#routing-overview');wrapper.replaceChildren();const table=make('table');const header=make('tr');for(const title of['Ausgang','Quellenpriorität','Aktuell'])header.append(make('th',title));table.append(header);
    for(const output of model.outputs){const row=make('tr'),program=status?.programs?.find(group=>group.id===output.program),name=make('td',output.label),route=make('td',chain(output.sources)),current=make('td',program?.selected_source?sourceName(program.selected_source):program?.offline_playing?'Offline-Video':'Standby');row.append(name,route,current);row.append(make('td'));row.lastChild.append(button('Vorschau',()=>{selectedTarget=output.kind;location.hash='#dashboard';},'ghost'));table.append(row);}wrapper.append(table);}
  find('#program-select').addEventListener('change',event=>{selectedTarget=event.target.value;program();});
  find('#program-link-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(find('#program-link').value);notify('Programmvorschau-Link kopiert.');}catch(_){notify('Bitte den Link markieren und kopieren.',true);}});
  find('#source-protocol').addEventListener('change',()=>{const protocol=find('#source-protocol').value;find('#source-pull-field').hidden=!['rtsp','mpegts','rtp','proxy'].includes(protocol);find('#source-sdp-field').hidden=protocol!=='rtp';});
  find('#source-create').addEventListener('submit',event=>{event.preventDefault();const body={label:find('#source-label').value,protocol:find('#source-protocol').value,url:find('#source-url').value,sdp:find('#source-sdp').value};action(async()=>{const result=await api('/api/routing/sources',body);find('#source-create').reset();find('#source-pull-field').hidden=true;find('#source-sdp-field').hidden=true;selectedSource=result.key;await load(true);},'Zusätzliche Quelle angelegt. Jetzt ihre Ausgänge wählen.',event.currentTarget);});
  find('#routing-policy-form').addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api('/api/routing/policy',{healthy_seconds:Number(find('#policy-healthy').value),stall_seconds:Number(find('#policy-stall').value),retry_seconds:Number(find('#policy-retry').value),native_standby:find('#policy-native-standby').checked});await load(true);},'Fallbackregeln gespeichert.',event.currentTarget);});
  find('#routing-output-platform').addEventListener('change',()=>{const custom=find('#routing-output-platform').value==='custom';find('#routing-key-field').hidden=custom;find('#routing-url-field').hidden=!custom;});
  find('#routing-output-create').addEventListener('submit',event=>{event.preventDefault();const body={label:find('#routing-output-label').value,platform:find('#routing-output-platform').value,key:find('#routing-output-key').value,url:find('#routing-output-url').value};action(async()=>{await api('/api/routing/outputs',body);find('#routing-output-create').reset();find('#routing-key-field').hidden=false;find('#routing-url-field').hidden=true;await load(true);},'Ausgang angelegt. Unter Quellen & Routing die gewünschten Quellen zuordnen.',event.currentTarget);});
  window.addEventListener('hashchange',()=>{if(['#expert-routing','#expert-outputs'].includes(location.hash))load(true);});
  window.addEventListener('streamdesk:status',event=>{status=event.detail;if(model&&status.expert_mode)overview();});
  window.StreamDeskRouting={render,program,sourceName,selectTarget(kind){selectedTarget=kind;program();}};
  if(typeof state!=='undefined'&&state)render(state);
})();

'use strict';
(() => {
  const q=selector=>document.querySelector(selector),make=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
  const timelineDays=new WeakMap();
  const days=['Mo','Di','Mi','Do','Fr','Sa','So'];
  function segments(rule){
    const minute=value=>Number(value.split(':')[0])*60+Number(value.split(':')[1]);
    const start=minute(rule.start),length=(minute(rule.end)-start+1440)%1440||1440,result=[];
    for(const day of rule.days){const begin=day*1440+start,end=begin+length;result.push([begin,Math.min(10080,end)]);if(end>10080)result.push([0,end-10080]);}return result;
  }
  function timeline(container,rules,playlists,pick){
    if(!container)return;container.replaceChildren();
    if(!rules.length){container.append(make('p','Noch keine Zeitfenster geplant.','small muted'));return;}
    const chosen=timelineDays.get(container)??null,toolbar=make('div',undefined,'timeline-toolbar');
    for(const [label,value]of[['Woche',null],...days.map((day,index)=>[day,index])]){const button=make('button',label,'ghost');button.type='button';button.setAttribute('aria-pressed',String(chosen===value));button.onclick=()=>{timelineDays.set(container,value);timeline(container,rules,playlists,pick);};toolbar.append(button);}container.append(toolbar);
    const base=chosen===null?0:chosen*1440,span=chosen===null?10080:1440;
    const table=make('div',undefined,'timeline-table'),head=make('div',undefined,'timeline-heading');head.append(make('strong','Playlist'));
    const week=make('div',undefined,'timeline-week');for(const day of(chosen===null?days:['00:00','04:00','08:00','12:00','16:00','20:00']))week.append(make('span',day));week.style.gridTemplateColumns='repeat('+(chosen===null?7:6)+',1fr)';head.append(week);table.append(head);
    const ids=[...new Set(rules.map(rule=>rule.playlist_id))];
    for(const [rowIndex,id]of ids.entries()){
      const name=playlists.find(item=>item.id===id)?.name||'Playlist',row=make('div',undefined,'timeline-row');row.append(make('strong',name));
      const track=make('div',undefined,'timeline-track');if(chosen!==null)track.classList.add('timeline-day');
      for(const [index,rule]of rules.entries())if(rule.playlist_id===id)for(const [start,end]of segments(rule)){
        if(start>=base+span||end<=base)continue;const begin=Math.max(start,base),finish=Math.min(end,base+span);
        const bar=make('button',chosen===null?'':rule.start+'–'+rule.end,'timeline-bar color-'+rowIndex%4);bar.type='button';bar.style.left=((begin-base)/span*100)+'%';bar.style.width=((finish-begin)/span*100)+'%';bar.title=(rule.title||name)+' · '+days.join('/').split('/')[Math.floor(start/1440)]+' '+rule.start+'–'+rule.end;bar.setAttribute('aria-label',bar.title+' bearbeiten');bar.onclick=()=>pick(index);track.append(bar);
      }
      row.append(track);table.append(row);
    }
    container.append(table,make('p','Zeitfenster anklicken, um sie zu bearbeiten. Die Übersicht zeigt die wiederkehrende Woche in der gewählten Zeitzone.','small muted'));
  }
  window.StreamDeskTimeline={render:timeline};
  for(const [id,parent]of[['studio-settings','[data-view="settings-appearance"]'],['ftp-settings','[data-view="account"]'],['admin-ftp-settings','[data-view="administration-ftp"]']]){const element=q('#'+id);if(element&&q(parent))q(parent).append(element);}
  const form=q('#planner-form');let data,selected=null,dirty=false,loading=false,preferencesLoaded=false,ftpAt=0;
  for(let index=0;index<7;index++){const label=make('label',days[index]),input=make('input');input.type='checkbox';input.value=index;input.name='day';label.prepend(input);q('#planner-days').append(label);}
  function reset(){selected=null;dirty=false;form.reset();form.elements.timezone.value='Europe/Berlin';form.querySelector('[name=day][value="0"]').checked=true;q('#planner-editor-title').textContent='Geplanten Stream hinzufügen';if(data)fields();}
  function fields(plan){
    form.elements.playlist_id.replaceChildren(new Option('Playlist wählen',''),...data.playlists.map(row=>new Option(row.name,row.id)));
    const targets=q('#planner-targets');targets.replaceChildren(make('legend','Automatisch verbinden mit'));
    for(const output of data.outputs){const label=make('label',output.label+(output.configured?'':' · noch nicht eingerichtet'),'feature-check'),input=make('input');input.type='checkbox';input.name='target';input.value=output.kind;input.disabled=!output.configured||!output.allowed;input.checked=plan?.targets.includes(output.kind)||false;label.prepend(input);targets.append(label);}
    q('#planner-twitch-status').textContent=data.twitch_schedule_connected?'Twitch ist für die Zeitplanübertragung verbunden.':'Für die Zeitplanübertragung Twitch unter Einstellungen → Twitch erneut verbinden. Die lokale Ausspielung funktioniert unabhängig davon.';
    if(plan){for(const name of['title','start','end','timezone','playlist_id'])form.elements[name].value=plan[name];for(const name of['enabled','sync_twitch'])form.elements[name].checked=plan[name];for(const checkbox of form.querySelectorAll('[name=day]'))checkbox.checked=plan.days.includes(Number(checkbox.value));}
  }
  function edit(plan){selected=plan.id;dirty=false;fields(plan);q('#planner-editor-title').textContent='Sendeplan bearbeiten';form.scrollIntoView({behavior:'smooth',block:'start'});}
  function render(preserve=false){
    const list=q('#planner-list');list.replaceChildren();
    for(const plan of data.plans){const row=make('article',undefined,'planner-card'),heading=make('h3',plan.title),status=make('span',plan.enabled?'Aktiv':'Pausiert','badge'),description=make('p',plan.days.map(day=>days[day]).join(', ')+' · '+plan.start+'–'+plan.end+' · '+plan.timezone+' · '+plan.targets.map(kind=>data.outputs.find(row=>row.kind===kind)?.label||kind).join(', '),'small');
      const editButton=make('button','Bearbeiten','secondary');editButton.type='button';editButton.onclick=()=>edit(plan);
      const remove=make('button','Löschen','ghost');remove.type='button';remove.onclick=()=>{if(!confirm('Sendeplan „'+plan.title+'“ löschen?'))return;action(async()=>{await api('/api/planner/'+plan.id,{},'DELETE');if(selected===plan.id)reset();await load();},'Sendeplan gelöscht.',row);};row.append(heading,status,description);if(plan.sync_message)row.append(make('p',plan.sync_message,'small muted'));row.append(editButton,remove);list.append(row);}
    timeline(q('#planner-timeline'),data.plans.filter(row=>row.enabled),data.playlists,index=>edit(data.plans.filter(row=>row.enabled)[index]));
    if(!dirty){const plan=data.plans.find(row=>row.id===selected);fields(plan);}
  }
  async function load(preserve=false){if(loading||!window.StreamDeskServices.allowed('automation')||!window.StreamDeskServices.allowed('playlists'))return;loading=true;try{data=await api('/api/planner');render(preserve);}catch(error){notify(error.message,true);}finally{loading=false;}}
  form.oninput=()=>dirty=true;
  form.onsubmit=event=>{event.preventDefault();action(async()=>{const body={title:form.elements.title.value,enabled:form.elements.enabled.checked,start:form.elements.start.value,end:form.elements.end.value,timezone:form.elements.timezone.value.trim(),days:[...form.querySelectorAll('[name=day]:checked')].map(input=>Number(input.value)),playlist_id:Number(form.elements.playlist_id.value),targets:[...form.querySelectorAll('[name=target]:checked')].map(input=>input.value),sync_twitch:form.elements.sync_twitch.checked};const result=await api('/api/planner'+(selected?'/'+selected:''),body);selected=result.id;dirty=false;await load();},'Sendeplan gespeichert.',form);};
  q('#planner-new').onclick=reset;q('#planner-cancel').onclick=reset;
  const preferences=q('#studio-preferences-form');
  async function loadPreferences(){if(preferencesLoaded)return;preferencesLoaded=true;try{const result=await api('/api/studio/preferences');for(const key of['switch_text','replay_label','replay_corner'])preferences.elements[key].value=result[key];}catch(error){preferencesLoaded=false;notify(error.message,true);}}
  preferences.onsubmit=event=>{event.preventDefault();action(async()=>{await api('/api/studio/preferences',Object.fromEntries(new FormData(preferences)));},'Umschaltbild und Playlist-Kennzeichnung gespeichert.',preferences);};
  function connectionFields(container,info){
    container.replaceChildren();
    const fields=[['Server (Ingest)',info.host],['Port',String(info.port)],['Protokoll',info.protocol||'FTP mit explizitem TLS'],['Übertragungsmodus','Passiv'],['FTP-Benutzername',info.account?.username||'Noch nicht angelegt'],['Medienbibliothek',info.library_path||'/Bibliothek']];
    for(const [title,value]of fields){const field=make('div',undefined,'ftp-field'),label=make('label',title),input=make('input');input.type='text';input.readOnly=true;input.value=value;input.setAttribute('aria-label',title);label.append(input);field.append(label);
      if(title==='Server (Ingest)'||title==='Port'||title==='FTP-Benutzername'&&info.account){const copy=make('button','Kopieren','ghost');copy.type='button';copy.setAttribute('aria-label',title+' kopieren');copy.onclick=async()=>{try{if(navigator.clipboard){await navigator.clipboard.writeText(value);notify(title+' kopiert.');}else{input.select();notify('Wert markiert. Bitte kopieren.');}}catch(error){input.select();notify('Wert markiert. Bitte kopieren.');}};field.append(copy);}container.append(field);
    }
    if(info.library_error)container.append(make('p',info.library_error,'small'));
    if(info.account)container.append(make('p','Passwort: das für diesen FTP-Zugang festgelegte Passwort. Es wird nicht angezeigt.','small muted'));
  }
  function ftpStatus(info){
    if(!info.configured)return 'FTP ist auf diesem Server noch nicht eingerichtet. Die Administration muss das Update mit --enable-ftp ausführen.';
    if(!info.account)return 'Für diesen Benutzer ist noch kein FTP-Zugang angelegt.';
    if(!info.user.active)return 'Das StreamDesk-Konto ist deaktiviert. Eine FTP-Anmeldung ist gesperrt.';
    return info.account.enabled?'FTP-Zugang ist freigegeben. Verwende die folgenden Verbindungsdaten.':'FTP-Zugang ist gesperrt. Die Verbindungsdaten bleiben gespeichert.';
  }
  function renderImports(list,imports){
    if(!list)return;list.replaceChildren();
    if(!imports.length){list.append(make('p','Noch keine abgeschlossenen FTP-Übertragungen.','small muted'));return;}
    for(const item of imports){
      const row=make('article',undefined,'upload-item');row.dataset.ftpImport=item.id;
      const size=item.size>=1073741824?(item.size/1073741824).toFixed(1)+' GB':(item.size/1048576).toFixed(1)+' MB';
      row.append(make('strong',item.filename),make('p',new Date(item.created*1000).toLocaleString('de-DE')+' · '+size+' · '+({queued:'Wartet',processing:'Wird verarbeitet',ready:'Fertig',error:'Fehler'}[item.state]||item.state),'small'),make('p',item.message,'small muted'));
      if(item.state==='processing'&&item.progress!==null){const progress=make('progress');progress.max=100;progress.value=item.progress;progress.setAttribute('aria-label',item.filename+' Umwandlung');row.append(progress,make('p','Umwandlung: '+Math.round(item.progress)+' %','small'));}
      if(item.state==='ready'&&item.video_id){const link=make('a','Video ansehen ↗');link.href='/media/video/'+item.video_id;link.target='_blank';link.rel='noopener';row.append(link);}
      if(item.state==='error'&&item.retryable){const retry=make('button','Erneut importieren','secondary');retry.type='button';retry.onclick=()=>action(async()=>{await api('/api/ftp/imports/'+item.id+'/retry',{});await loadFTP();},'FTP-Import erneut eingereiht.',row);row.append(retry);}
      if(item.state==='error'&&item.retained&&item.retryable){const remove=make('button','Quelldatei löschen','ghost');remove.type='button';remove.onclick=()=>{if(!confirm('Die zurückbehaltene Quelldatei „'+item.filename+'“ löschen und ihren Speicher freigeben?'))return;action(async()=>{await api('/api/ftp/imports/'+item.id+'/source',{},'DELETE');await loadFTP();},'Quelldatei entfernt.',row);};row.append(remove);}
      list.append(row);
    }
  }
  async function loadFTP(){
    if(!window.StreamDeskServices.allowed('ftp'))return;
    try{const result=await api('/api/ftp');q('#ftp-account-status').textContent=ftpStatus(result);connectionFields(q('#ftp-connection'),result);q('#ftp-password-form').hidden=!result.account;
      for(const container of [q('#ftp-import-list'),q('#media-ftp-import-list')])renderImports(container,result.imports);
      const media=q('#media-ftp-imports');media.hidden=!result.configured||!result.account;
      if(!media.dataset.seen&&result.imports.some(row=>row.state!=='ready')){media.open=true;media.dataset.seen='1';}
      ftpAt=Date.now();
    }catch(error){q('#ftp-account-status').textContent=error.message;notify(error.message,true);}
  }
  q('#ftp-password-form').onsubmit=event=>{event.preventDefault();const f=event.currentTarget;action(async()=>{await api('/api/ftp/password',{password:f.elements.password.value});f.reset();},'FTP-Passwort geändert.',f);};
  const admin=q('#admin-ftp-form');let adminLoading=false,adminRequest=0;
  function adminFields(info){
    q('#admin-ftp-status').textContent=info.user.username+' · '+ftpStatus(info);connectionFields(q('#admin-ftp-connection'),info);
    admin.elements.enabled.checked=info.account?info.account.enabled:true;admin.elements.password.required=!info.account;admin.querySelector('[type=submit]').disabled=!info.configured;
  }
  async function loadAdminAccount(){
    if(!admin?.elements.user_id.value)return;
    const id=Number(admin.elements.user_id.value),request=++adminRequest;
    q('#admin-ftp-status').textContent='FTP-Zugang wird geladen …';admin.querySelector('[type=submit]').disabled=true;
    try{const info=await api('/api/admin/users/'+id+'/ftp');if(request===adminRequest)adminFields(info);}
    catch(error){if(request===adminRequest)q('#admin-ftp-status').textContent=error.message;notify(error.message,true);}
  }
  async function adminFTP(){
    if(!admin||adminLoading||!window.StreamDeskServices.allowed('ftp'))return;adminLoading=true;
    try{const previous=admin.elements.user_id.value,result=await api('/api/admin');admin.elements.user_id.replaceChildren(...result.users.filter(row=>row.role!=='moderator').map(row=>new Option(row.username+(row.active?'':' · deaktiviert'),row.id)));if([...admin.elements.user_id.options].some(option=>option.value===previous))admin.elements.user_id.value=previous;await loadAdminAccount();}
    catch(error){q('#admin-ftp-status').textContent=error.message;notify(error.message,true);}finally{adminLoading=false;}
  }
  if(admin){
    admin.elements.user_id.onchange=()=>{admin.elements.password.value='';admin.querySelector('.form-feedback')?.remove();loadAdminAccount();};
    admin.onsubmit=event=>{
      event.preventDefault();const id=Number(admin.elements.user_id.value);admin.elements.user_id.disabled=true;
      action(async()=>{const result=await api('/api/admin/users/'+id+'/ftp',{enabled:admin.elements.enabled.checked,password:admin.elements.password.value});admin.elements.password.value='';adminFields(result);await loadFTP();},'FTP-Zugang gespeichert.',admin).finally(()=>{admin.elements.user_id.disabled=false;});
    };
  }
  function view(){if(location.hash==='#planner')load(true);if(location.hash==='#settings-appearance')loadPreferences();if(['#account','#media'].includes(location.hash))loadFTP();if(location.hash==='#administration-ftp')adminFTP();}
  window.addEventListener('hashchange',view);window.addEventListener('DOMContentLoaded',()=>{reset();view();});
  window.addEventListener('streamdesk:status',()=>{if(['#account','#media'].includes(location.hash)&&Date.now()-ftpAt>10000){ftpAt=Date.now();loadFTP();}});
})();

'use strict';
(() => {
  const q=selector=>document.querySelector(selector);
  let library, profiles, folder=null,selected=null,items=[],rules=[],loading=false,profileLoading=false,dirty=false,profileDirty=false,scope='default',lastUpload='',lastUsage='',lastMediaRead=0;
  const node=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
  const button=(text,callback)=>{const el=node('button',text,'ghost');el.type='button';el.onclick=callback;return el;};
  const duration=seconds=>Math.floor(seconds/60)+' min '+Math.round(seconds%60)+' s';
  function folders(select,value=folder){select.replaceChildren(new Option('Hauptordner',''),...library.folders.map(row=>new Option(path(row.id),row.id)));select.value=value??'';}
  function path(id){const names=[];let count=0;while(id!==null&&count++<9){const row=library.folders.find(row=>row.id===id);if(!row)break;names.unshift(row.name);id=row.parent_id;}return names.join(' / ')||'Hauptordner';}
  async function load(preserve=false){
    if(loading||!window.StreamDeskServices.allowed('playlists'))return;loading=true;
    try{library=await api('/api/playlists');lastMediaRead=Date.now();render(preserve);}catch(error){notify(error.message,true);}finally{loading=false;}
  }
  function render(preserve=false){
    const tree=q('#playlist-folder-tree');tree.replaceChildren();
    function branch(parent,level=0){for(const row of library.folders.filter(row=>row.parent_id===parent)){const link=button(row.name,()=>{folder=row.id;selected=null;dirty=false;render();});link.style.marginLeft=(level*12)+'px';link.setAttribute('aria-pressed',String(folder===row.id));tree.append(link);branch(row.id,level+1);}}
    tree.append(button('Hauptordner',()=>{folder=null;selected=null;dirty=false;render();}));branch(null);
    q('#playlist-folder-path').textContent=path(folder);q('#playlist-upload').dataset.folderId=folder??'';q('#playlist-upload').dataset.folderLabel=path(folder);
    const currentFolder=library.folders.find(row=>row.id===folder),edit=q('#playlist-folder-edit');edit.closest('details').hidden=!currentFolder;
    if(!preserve){edit.elements.name.value=currentFolder?.name||'';folders(edit.elements.parent_id,currentFolder?.parent_id??null);}
    const list=q('#playlist-list');list.replaceChildren();
    for(const row of library.playlists.filter(row=>row.folder_id===folder)){const pick=button(row.name+' · '+row.items.length+' '+(row.items.length===1?'Video':'Videos'),()=>{selected=row.id;dirty=false;render();});pick.setAttribute('aria-pressed',String(selected===row.id));list.append(pick);}
    if(!list.children.length)list.textContent='Noch keine Playlist in diesem Ordner.';
    const playlist=library.playlists.find(row=>row.id===selected);q('#playlist-editor').hidden=!playlist;
    if(playlist&&(!preserve||!dirty)){q('#playlist-edit').elements.name.value=playlist.name;folders(q('#playlist-edit').elements.folder_id,playlist.folder_id);items=[...playlist.items];renderItems();}
    if(playlist&&preserve&&dirty){items=items.filter(id=>library.videos.some(row=>row.id===id));renderItems();}
    const videoSelect=q('#playlist-add-video'),previous=videoSelect.value;videoSelect.replaceChildren(...library.videos.map(row=>new Option(path(row.folder_id)+' / '+row.name+' · '+duration(row.duration),row.id)));videoSelect.value=previous||library.videos[0]?.id||'';
    const videos=q('#playlist-videos');videos.replaceChildren();
    for(const row of library.videos.filter(row=>row.folder_id===folder)){
      const line=node('div',undefined,'playlist-media-row');line.append(node('span',row.name+' · '+duration(row.duration)));
      const move=node('select');move.setAttribute('aria-label',row.name+' verschieben');folders(move,row.folder_id);move.onchange=()=>action(async()=>{await api('/api/playlists/videos/'+row.id+'/folder',{folder_id:move.value?Number(move.value):null});await load(true);},'Video verschoben.',line);
      const preview=node('a','Vorschau ↗');preview.href='/media/video/'+row.id;preview.target='_blank';preview.rel='noopener';
      line.append(move,preview,window.StreamDeskMedia.controls(row,()=>load(true)));videos.append(line);
    }
    if(!videos.children.length)videos.textContent='Noch keine Videos in diesem Ordner. Vorhandene Offline-Videos findest du im Hauptordner.';
  }
  function renderItems(){
    const list=q('#playlist-items');list.replaceChildren();
    items.forEach((id,index)=>{const row=library.videos.find(video=>video.id===id),line=node('li');line.append(node('span',row?.name||'Video fehlt'));
      for(const [label,delta]of[['↑',-1],['↓',1]]){const move=button(label,()=>{[items[index],items[index+delta]]=[items[index+delta],items[index]];dirty=true;renderItems();});move.disabled=index+delta<0||index+delta>=items.length;move.setAttribute('aria-label','Video '+(delta<0?'nach oben':'nach unten'));line.append(move);}
      line.append(button('Entfernen',()=>{items.splice(index,1);dirty=true;renderItems();}));list.append(line);
    });
    q('#playlist-duration').textContent=items.length+' '+(items.length===1?'Video':'Videos')+' · '+duration(items.reduce((sum,id)=>sum+(library.videos.find(row=>row.id===id)?.duration||0),0))+' pro Schleife';
  }
  q('#playlist-edit').oninput=()=>dirty=true;
  q('#playlist-add-item').onclick=()=>{const id=Number(q('#playlist-add-video').value);if(id){items.push(id);dirty=true;renderItems();}};
  function submit(id,callback,message){q(id).onsubmit=event=>{event.preventDefault();action(()=>callback(event.currentTarget),message,event.currentTarget);};}
  submit('#playlist-create',async form=>{const result=await api('/api/playlists',{name:form.elements.name.value,folder_id:folder,items:[]});selected=result.id;dirty=false;form.reset();await load();},'Playlist angelegt.');
  submit('#playlist-edit',async form=>{await api('/api/playlists/'+selected,{name:form.elements.name.value,folder_id:form.elements.folder_id.value?Number(form.elements.folder_id.value):null,items});folder=form.elements.folder_id.value?Number(form.elements.folder_id.value):null;dirty=false;await load();},'Playlist gespeichert.');
  submit('#playlist-folder-form',async form=>{const result=await api('/api/playlist-folders',{name:form.elements.name.value,parent_id:folder});folder=result.id;selected=null;form.reset();await load();},'Ordner angelegt.');
  submit('#playlist-folder-edit',async form=>{await api('/api/playlist-folders/'+folder,{name:form.elements.name.value,parent_id:form.elements.parent_id.value?Number(form.elements.parent_id.value):null});await load();},'Ordner gespeichert.');
  q('#playlist-folder-delete').onclick=()=>action(async()=>{await api('/api/playlist-folders/'+folder,{},'DELETE');folder=null;await load();},'Leerer Ordner gelöscht.',q('#playlist-folder-edit'));
  q('#playlist-delete').onclick=()=>action(async()=>{await api('/api/playlists/'+selected,{},'DELETE');selected=null;dirty=false;await load();},'Playlist gelöscht. Videos bleiben erhalten.',q('#playlist-edit'));
  async function loadProfiles(){
    if(profileLoading||!state?.expert_mode||!window.StreamDeskServices.allowed('playlists'))return;profileLoading=true;
    try{if(!library)await load();profiles=await api('/api/playout');const select=q('#playlist-scope');select.replaceChildren(new Option('Allgemein · alle Ausgänge ohne eigene Regel','default'),...profiles.sources.filter(row=>row.key!=='source1').map(row=>new Option('Hinter '+row.label,'source:'+row.key)),...profiles.outputs.map(row=>new Option('Ausgang · '+row.label,'output:'+row.kind)));select.value=scope;if(!select.value){scope='default';select.value=scope;}if(!profileDirty)profileFields();}catch(error){notify(error.message,true);}finally{profileLoading=false;}
  }
  function profileFields(){
    const profile=profiles.profiles.find(row=>row.scope===scope);q('#playlist-profile-enabled').checked=profile?.enabled||false;q('#playlist-delay').value=(profile?.delay_seconds??600)/60;q('#playlist-auto-start').checked=profile?.auto_start||false;q('#playlist-timezone').value=profile?.timezone||'Europe/Berlin';
    const fallback=q('#playlist-fallback');fallback.replaceChildren(new Option('Keine Playlist · normales Offline-Video',''),...library.playlists.map(row=>new Option(path(row.folder_id)+' / '+row.name,row.id)));fallback.value=profile?.playlist_id??'';rules=structuredClone(profile?.schedules||[]);renderRules();
  }
  function renderRules(){
    const wrapper=q('#playlist-schedules');wrapper.replaceChildren();rules.forEach((rule,index)=>{
      const row=node('div',undefined,'playlist-rule');const playlist=node('select');playlist.setAttribute('aria-label','Playlist im Zeitfenster');playlist.replaceChildren(...library.playlists.map(row=>new Option(row.name,row.id)));playlist.value=rule.playlist_id;playlist.onchange=()=>{rule.playlist_id=Number(playlist.value);profileDirty=true;};row.append(playlist);
      for(const key of['start','end']){const label=node('label',key==='start'?'Von':'Bis'),input=node('input');input.type='time';input.required=true;input.value=rule[key];input.onchange=()=>{rule[key]=input.value;profileDirty=true;};label.append(input);row.append(label);}
      const days=node('fieldset',undefined,'playlist-weekdays'),legend=node('legend','Wochentage');days.append(legend);['Mo','Di','Mi','Do','Fr','Sa','So'].forEach((name,day)=>{const label=node('label',name),input=node('input');input.type='checkbox';input.checked=rule.days.includes(day);input.onchange=()=>{rule.days=input.checked?[...rule.days,day].sort():rule.days.filter(value=>value!==day);profileDirty=true;};label.prepend(input);days.append(label);});row.append(days,button('Zeitfenster entfernen',()=>{rules.splice(index,1);profileDirty=true;renderRules();}));wrapper.append(row);
    });
  }
  q('#playlist-scope').onchange=event=>{scope=event.target.value;profileDirty=false;profileFields();};
  q('#playlist-profile-form').oninput=()=>profileDirty=true;
  q('#playlist-add-schedule').onclick=()=>{if(!library.playlists.length){notify('Bitte zuerst eine Playlist mit Videos anlegen.',true);return;}rules.push({playlist_id:library.playlists[0].id,start:'00:00',end:'00:00',days:[0,1,2,3,4,5,6]});profileDirty=true;renderRules();};
  submit('#playlist-profile-form',async()=>{await api('/api/playout',{scope,enabled:q('#playlist-profile-enabled').checked,playlist_id:q('#playlist-fallback').value?Number(q('#playlist-fallback').value):null,delay_seconds:Math.round(Number(q('#playlist-delay').value)*60),timezone:q('#playlist-timezone').value.trim(),schedules:rules,auto_start:q('#playlist-auto-start').checked});profileDirty=false;await loadProfiles();},'Ausspielregel gespeichert. Live-Quellen behalten Vorrang.');
  window.addEventListener('streamdesk:uploads-changed',()=>{if(location.hash==='#playlists')load(true);});
  window.addEventListener('hashchange',()=>{if(location.hash==='#playlists')load(true);if(location.hash==='#expert-playlists')loadProfiles();});
  window.addEventListener('streamdesk:status',event=>{const usage=JSON.stringify([event.detail.offline_video?.id,event.detail.programs?.map(row=>[row.id,row.playlist?.active,row.playlist?.name])]);if(location.hash==='#playlists'&&(usage!==lastUsage||Date.now()-lastMediaRead>10000)){lastUsage=usage;load(true);}const upload=event.detail.upload;if(location.hash==='#playlists'&&upload&&lastUpload!==upload.state){lastUpload=upload.state;q('#playlist-upload-status').textContent=upload.message||'';load(true);}if(location.hash==='#expert-playlists'&&!profiles)loadProfiles();});
  window.addEventListener('DOMContentLoaded',()=>{if(location.hash==='#playlists')load();if(location.hash==='#expert-playlists')loadProfiles();});
})();

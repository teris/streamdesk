'use strict';
(() => {
  const q=selector=>document.querySelector(selector);
  const checkedVideos=new Set(),pickedVideos=new Set();
  let pickerPage=0;
  const inLibrary=()=>['#media','#playlists'].includes(location.hash);
  let library, profiles, folder=null,selected=null,items=[],rules=[],loading=null,profileLoading=false,dirty=false,profileDirty=false,scope='source:source2',lastUpload='',lastUsage='',lastMediaRead=0,page=0,renderedFolder,folderIndex=new Map(),videoIndex=new Map(),lastLibrary='';
  const node=(tag,text,className)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;};
  const button=(text,callback)=>{const el=node('button',text,'ghost');el.type='button';el.onclick=callback;return el;};
  const duration=seconds=>Math.floor(seconds/60)+' min '+Math.round(seconds%60)+' s';
  function folders(select,value=folder){select.replaceChildren(new Option('Hauptordner',''),...library.folders.map(row=>new Option(path(row.id),row.id)));select.value=value??'';}
  function path(id){const names=[];let count=0;while(id!==null&&count++<9){const row=folderIndex.get(id);if(!row)break;names.unshift(row.name);id=row.parent_id;}return names.join(' / ')||'Hauptordner';}
  async function load(preserve=false){
    if(!window.StreamDeskServices.allowed('playlists'))return;
    if(loading){await loading;return load(preserve);}
    loading=(async()=>{
      try{const next=await api('/api/playlists'),signature=JSON.stringify(next);lastMediaRead=Date.now();
        if(preserve&&signature===lastLibrary)return;
        library=next;lastLibrary=signature;folderIndex=new Map(library.folders.map(row=>[row.id,row]));videoIndex=new Map(library.videos.map(row=>[row.id,row]));
        if(folder!==null&&!folderIndex.has(folder))folder=null;
        for(const id of checkedVideos)if(!videoIndex.has(id))checkedVideos.delete(id);
        render(preserve);
      }catch(error){q('#playlist-library-status').textContent=q('#playlist-management-status').textContent=error.message;notify(error.message,true);}
    })();
    try{await loading;}finally{loading=null;}
  }
  function render(preserve=false){
    const tree=q('#playlist-folder-tree');tree.replaceChildren();
    const children=new Map(),visited=new Set();
    for(const row of library.folders){const parent=folderIndex.has(row.parent_id)?row.parent_id:null;if(!children.has(parent))children.set(parent,[]);children.get(parent).push(row);}
    const browse=id=>{folder=id;page=0;render(true);};
    function branch(parent,level=0){for(const row of children.get(parent)||[]){if(visited.has(row.id))continue;visited.add(row.id);const link=button(row.name,()=>browse(row.id));link.style.marginLeft=(Math.min(level,8)*12)+'px';link.setAttribute('aria-pressed',String(folder===row.id));tree.append(link);branch(row.id,level+1);}}
    const root=button('Hauptordner',()=>browse(null));root.setAttribute('aria-pressed',String(folder===null));tree.append(root);branch(null);
    for(const row of library.folders)if(!visited.has(row.id)){children.set(null,[row]);branch(null);}
    q('#playlist-library-status').textContent=library.folders.length+' Ordner · '+library.videos.length+' Videos';
    q('#playlist-management-status').textContent=library.playlists.length+' Playlists · '+library.videos.length+' verfügbare Videos';
    const create=q('#playlist-create'),createFolder=create.elements.folder_id.value;folders(create.elements.folder_id,createFolder?Number(createFolder):null);
    q('#playlist-folder-path').textContent=path(folder);q('#playlist-upload').dataset.folderId=folder??'';q('#playlist-upload').dataset.folderLabel=path(folder);
    const currentFolder=library.folders.find(row=>row.id===folder),edit=q('#playlist-folder-edit');edit.closest('details').hidden=!currentFolder;
    if(!preserve||renderedFolder!==folder){edit.elements.name.value=currentFolder?.name||'';folders(edit.elements.parent_id,currentFolder?.parent_id??null);}
    renderedFolder=folder;
    const list=q('#playlist-list');list.replaceChildren();
    for(const row of library.playlists){const pick=button('Bearbeiten: '+row.name+' · '+path(row.folder_id)+' · '+row.items.length+' '+(row.items.length===1?'Video':'Videos'),()=>{selected=row.id;dirty=false;render();q('#playlist-editor').scrollIntoView({behavior:'smooth',block:'start'});});pick.setAttribute('aria-pressed',String(selected===row.id));list.append(pick);}
    if(!list.children.length)list.textContent='Noch keine Playlist angelegt.';
    const playlist=library.playlists.find(row=>row.id===selected);q('#playlist-editor').hidden=!playlist;q('#playlist-empty').hidden=!!playlist;
    if(playlist&&(!preserve||!dirty)){q('#playlist-edit').elements.name.value=playlist.name;folders(q('#playlist-edit').elements.folder_id,playlist.folder_id);items=[...playlist.items];renderItems();}
    if(playlist&&preserve&&dirty){items=items.filter(id=>library.videos.some(row=>row.id===id));renderItems();}
    renderPicker();
    const videos=q('#playlist-videos');videos.replaceChildren();
    const visible=library.videos.filter(row=>row.folder_id===folder);page=Math.min(page,Math.max(0,Math.ceil(visible.length/50)-1));
    for(const row of visible.slice(page*50,(page+1)*50)){
      const line=node('div',undefined,'playlist-media-row'),check=node('input');check.type='checkbox';check.dataset.playlistVideo=row.id;check.checked=checkedVideos.has(row.id);check.setAttribute('aria-label',row.name+' für Playlist auswählen');check.onchange=()=>{if(check.checked)checkedVideos.add(row.id);else checkedVideos.delete(row.id);selectionCount();};const label=node('label',undefined,'feature-check');label.append(check,node('span',row.name+' · '+duration(row.duration)));line.append(label);
      const move=node('select');move.setAttribute('aria-label',row.name+' verschieben');folders(move,row.folder_id);move.onchange=()=>action(async()=>{await api('/api/playlists/videos/'+row.id+'/folder',{folder_id:move.value?Number(move.value):null});await load(true);},'Video verschoben.',line);
      const preview=node('a','Vorschau ↗');preview.href='/media/video/'+row.id;preview.target='_blank';preview.rel='noopener';
      line.append(move,preview,window.StreamDeskMedia.controls(row,()=>load(true)));videos.append(line);
    }
    const paging=q('#playlist-video-pages');paging.replaceChildren();
    if(visible.length>50){const back=button('← Zurück',()=>{page--;render(true);}),next=button('Weiter →',()=>{page++;render(true);});back.disabled=page===0;next.disabled=(page+1)*50>=visible.length;paging.append(back,node('span','Seite '+(page+1)+' / '+Math.ceil(visible.length/50)),next);}
    const bulk=q('#playlist-bulk-target'),target=bulk.value;bulk.replaceChildren(new Option('Playlist wählen',''),...library.playlists.map(row=>new Option(path(row.folder_id)+' / '+row.name,row.id)));bulk.value=(!preserve&&selected)||target||selected||'';selectionCount();
    if(!videos.children.length)videos.textContent='Noch keine Videos in diesem Ordner. Vorhandene Offline-Videos findest du im Hauptordner.';
  }
  function selectionCount(){
    q('#playlist-selection-count').textContent=checkedVideos.size+' Videos ausgewählt.';
    const visible=library?.videos.filter(row=>row.folder_id===folder)||[];q('#playlist-select-all').checked=!!visible.length&&visible.every(row=>checkedVideos.has(row.id));
    q('#playlist-bulk-add').disabled=!checkedVideos.size;
  }
  q('#playlist-select-all').onchange=event=>{for(const row of library.videos.filter(row=>row.folder_id===folder)){if(event.target.checked)checkedVideos.add(row.id);else checkedVideos.delete(row.id);}render(true);};
  q('#playlist-selection-clear').onclick=()=>{checkedVideos.clear();render(true);};
  q('#playlist-bulk-add').onclick=()=>{
    const id=Number(q('#playlist-bulk-target').value),target=library.playlists.find(row=>row.id===id);
    if(!target){notify('Bitte zuerst eine Ziel-Playlist wählen.',true);return;}
    const added=[...checkedVideos].filter(id=>library.videos.some(row=>row.id===id));
    const base=selected===id&&dirty?items:target.items;
    if(base.length+added.length>200){notify('Maximal 200 Videoeinträge je Playlist.',true);return;}
    if(selected!==id){selected=id;dirty=false;render();}
    items=[...base,...added];dirty=true;checkedVideos.clear();render(true);location.hash='#playlists';requestAnimationFrame(()=>q('#playlist-editor').scrollIntoView({behavior:'smooth',block:'start'}));notify('Videos ergänzt. Mit „Playlist speichern“ übernehmen.');
  };
  function renderPicker(){
    const select=q('#playlist-pick-folder'),previous=select.options.length?select.value:'all';
    select.replaceChildren(new Option('Alle Medienordner','all'),new Option('Hauptordner',''),...library.folders.map(row=>new Option(path(row.id),row.id)));select.value=previous;
    const term=q('#playlist-pick-search').value.trim().toLocaleLowerCase('de-DE');
    const matches=library.videos.filter(row=>(select.value==='all'||String(row.folder_id??'')===select.value)&&(!term||(row.name+' '+path(row.folder_id)).toLocaleLowerCase('de-DE').includes(term)));
    pickerPage=Math.min(pickerPage,Math.max(0,Math.ceil(matches.length/20)-1));const list=q('#playlist-video-picker');list.replaceChildren();
    for(const row of matches.slice(pickerPage*20,(pickerPage+1)*20)){
      const label=node('label',undefined,'feature-check playlist-pick-row'),check=node('input');check.type='checkbox';check.dataset.playlistPick=row.id;check.checked=pickedVideos.has(row.id);check.onchange=()=>{if(check.checked)pickedVideos.add(row.id);else pickedVideos.delete(row.id);pickerCount();};label.append(check,node('span',row.name+' · '+path(row.folder_id)+' · '+duration(row.duration)));list.append(label);
    }
    q('#playlist-picker-summary').textContent=matches.length+' passende Videos';
    if(!matches.length)list.textContent='Keine passenden Videos. Neue Dateien unter „Medien“ hochladen.';
    const pages=q('#playlist-picker-pages');pages.replaceChildren();
    if(matches.length>20){const back=button('← Zurück',()=>{pickerPage--;renderPicker();}),next=button('Weiter →',()=>{pickerPage++;renderPicker();});back.disabled=pickerPage===0;next.disabled=(pickerPage+1)*20>=matches.length;pages.append(back,node('span','Seite '+(pickerPage+1)+' / '+Math.ceil(matches.length/20)),next);}
    for(const id of pickedVideos)if(!videoIndex.has(id))pickedVideos.delete(id);pickerCount();
  }
  function pickerCount(){q('#playlist-picker-count').textContent=pickedVideos.size+' Videos markiert';q('#playlist-add-item').disabled=!pickedVideos.size;}
  q('#playlist-pick-folder').onchange=()=>{pickerPage=0;renderPicker();};
  q('#playlist-pick-search').oninput=()=>{pickerPage=0;renderPicker();};
  q('#playlist-picker-clear').onclick=()=>{pickedVideos.clear();renderPicker();};
  function renderItems(){
    const list=q('#playlist-items');list.replaceChildren();
    items.forEach((id,index)=>{const row=videoIndex.get(id),line=node('li');line.append(node('span',row?.name||'Video fehlt'));
      for(const [label,delta]of[['↑',-1],['↓',1]]){const move=button(label,()=>{[items[index],items[index+delta]]=[items[index+delta],items[index]];dirty=true;renderItems();});move.disabled=index+delta<0||index+delta>=items.length;move.setAttribute('aria-label','Video '+(delta<0?'nach oben':'nach unten'));line.append(move);}
      line.append(button('Entfernen',()=>{items.splice(index,1);dirty=true;renderItems();}));list.append(line);
    });
    q('#playlist-duration').textContent=items.length+' '+(items.length===1?'Video':'Videos')+' · '+duration(items.reduce((sum,id)=>sum+(videoIndex.get(id)?.duration||0),0))+' pro Schleife';
  }
  q('#playlist-edit').oninput=()=>dirty=true;
  q('#playlist-add-item').onclick=()=>{if(items.length+pickedVideos.size>200){notify('Maximal 200 Videoeinträge je Playlist.',true);return;}items.push(...pickedVideos);pickedVideos.clear();dirty=true;renderItems();renderPicker();notify('Videos ergänzt. Mit „Playlist speichern“ übernehmen.');};
  function submit(id,callback,message){q(id).onsubmit=event=>{event.preventDefault();action(()=>callback(event.currentTarget),message,event.currentTarget);};}
  submit('#playlist-create',async form=>{const result=await api('/api/playlists',{name:form.elements.name.value,folder_id:form.elements.folder_id.value?Number(form.elements.folder_id.value):null,items:[]});selected=result.id;dirty=false;form.reset();await load();},'Playlist angelegt.');
  submit('#playlist-edit',async form=>{await api('/api/playlists/'+selected,{name:form.elements.name.value,folder_id:form.elements.folder_id.value?Number(form.elements.folder_id.value):null,items});dirty=false;await load();},'Playlist gespeichert.');
  submit('#playlist-folder-form',async form=>{const result=await api('/api/playlist-folders',{name:form.elements.name.value,parent_id:folder});folder=result.id;page=0;form.reset();await load(true);},'Ordner angelegt.');
  submit('#playlist-folder-edit',async form=>{await api('/api/playlist-folders/'+folder,{name:form.elements.name.value,parent_id:form.elements.parent_id.value?Number(form.elements.parent_id.value):null});await load();},'Ordner gespeichert.');
  q('#playlist-folder-delete').onclick=()=>action(async()=>{await api('/api/playlist-folders/'+folder,{},'DELETE');folder=null;await load();},'Leerer Ordner gelöscht.',q('#playlist-folder-edit'));
  q('#playlist-delete').onclick=()=>{if(!confirm('Playlist löschen? Die Videodateien bleiben erhalten.'))return;return action(async()=>{await api('/api/playlists/'+selected,{},'DELETE');selected=null;dirty=false;await load();},'Playlist gelöscht. Videos bleiben erhalten.',q('#playlist-edit'));};
  async function loadProfiles(){
    if(profileLoading||!state?.expert_mode||!window.StreamDeskServices.allowed('playlists'))return;profileLoading=true;
    try{if(!library)await load();profiles=await api('/api/playout');const select=q('#playlist-scope');select.replaceChildren(new Option('Source 2 · gemeinsame Playlist für alle Ausgänge','source:source2'));scope='source:source2';select.value=scope;if(!profileDirty)profileFields();}catch(error){notify(error.message,true);}finally{profileLoading=false;}
  }
  function profileFields(){
    const profile=profiles.profiles.find(row=>row.scope===scope)||profiles.profiles.find(row=>row.scope==='default');q('#playlist-profile-enabled').checked=profile?.enabled||false;q('#playlist-delay').value=(profile?.delay_seconds??600)/60;q('#playlist-auto-start').checked=profile?.auto_start||false;q('#playlist-timezone').value=profile?.timezone||'Europe/Berlin';
    const fallback=q('#playlist-fallback');fallback.replaceChildren(new Option('Keine Playlist · normales Offline-Video',''),...library.playlists.map(row=>new Option(path(row.folder_id)+' / '+row.name,row.id)));fallback.value=profile?.playlist_id??'';rules=structuredClone(profile?.schedules||[]);renderRules();
  }
  function renderRules(){
    const wrapper=q('#playlist-schedules');wrapper.replaceChildren();rules.forEach((rule,index)=>{
      const row=node('div',undefined,'playlist-rule');const playlist=node('select');playlist.setAttribute('aria-label','Playlist im Zeitfenster');playlist.replaceChildren(...library.playlists.map(row=>new Option(row.name,row.id)));playlist.value=rule.playlist_id;playlist.onchange=()=>{rule.playlist_id=Number(playlist.value);profileDirty=true;};row.append(playlist);
      for(const key of['start','end']){const label=node('label',key==='start'?'Von':'Bis'),input=node('input');input.type='time';input.required=true;input.value=rule[key];input.onchange=()=>{rule[key]=input.value;profileDirty=true;};label.append(input);row.append(label);}
      const days=node('fieldset',undefined,'playlist-weekdays'),legend=node('legend','Wochentage');days.append(legend);['Mo','Di','Mi','Do','Fr','Sa','So'].forEach((name,day)=>{const label=node('label',name),input=node('input');input.type='checkbox';input.checked=rule.days.includes(day);input.onchange=()=>{rule.days=input.checked?[...rule.days,day].sort():rule.days.filter(value=>value!==day);profileDirty=true;};label.prepend(input);days.append(label);});row.append(days,button('Zeitfenster entfernen',()=>{rules.splice(index,1);profileDirty=true;renderRules();}));wrapper.append(row);
    });window.StreamDeskTimeline?.render(q('#playlist-timeline'),rules,library.playlists,index=>{const row=wrapper.children[index];row?.scrollIntoView({behavior:'smooth',block:'center'});row?.querySelector('select')?.focus();});
  }
  q('#playlist-scope').onchange=event=>{scope=event.target.value;profileDirty=false;profileFields();};
  q('#playlist-profile-form').oninput=()=>profileDirty=true;
  q('#playlist-add-schedule').onclick=()=>{if(!library.playlists.length){notify('Bitte zuerst eine Playlist mit Videos anlegen.',true);return;}rules.push({playlist_id:library.playlists[0].id,start:'00:00',end:'00:00',days:[0,1,2,3,4,5,6]});profileDirty=true;renderRules();};
  submit('#playlist-profile-form',async()=>{await api('/api/playout',{scope,enabled:q('#playlist-profile-enabled').checked,playlist_id:q('#playlist-fallback').value?Number(q('#playlist-fallback').value):null,delay_seconds:Math.round(Number(q('#playlist-delay').value)*60),timezone:q('#playlist-timezone').value.trim(),schedules:rules,auto_start:q('#playlist-auto-start').checked});profileDirty=false;await loadProfiles();},'Ausspielregel gespeichert. Live-Quellen behalten Vorrang.');
  window.addEventListener('streamdesk:uploads-changed',()=>{if(inLibrary())load(true);});
  window.addEventListener('hashchange',()=>{if(inLibrary())load(true);if(location.hash==='#expert-playlists')loadProfiles();});
  window.addEventListener('streamdesk:status',event=>{const usage=JSON.stringify([event.detail.offline_video?.id,event.detail.programs?.map(row=>[row.id,row.playlist?.active,row.playlist?.name])]);if(inLibrary()&&(usage!==lastUsage||Date.now()-lastMediaRead>10000)){lastUsage=usage;load(true);}const upload=event.detail.upload;if(inLibrary()&&upload&&lastUpload!==upload.state){lastUpload=upload.state;q('#playlist-upload-status').textContent=upload.message||'';load(true);}if(location.hash==='#expert-playlists'&&!profiles)loadProfiles();});
  window.addEventListener('DOMContentLoaded',()=>{if(inLibrary())load();if(location.hash==='#expert-playlists')loadProfiles();});
})();

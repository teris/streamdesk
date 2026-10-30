'use strict';
(() => {
  const token=document.querySelector('meta[name="csrf-token"]').content;
  const jobs=[],views=new WeakMap(),drafts=new Map();
  let running=false,paused=false,restored=false;
  const el=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
  const button=(text,callback)=>{const node=el('button',text,'ghost');node.type='button';node.onclick=callback;return node;};
  const uid=()=>Array.from(crypto.getRandomValues(new Uint8Array(18)),value=>value.toString(16).padStart(2,'0')).join('');
  const bytes=value=>value>=1073741824?(value/1073741824).toFixed(1)+' GB':value>=1048576?(value/1048576).toFixed(1)+' MB':Math.round(value/1024)+' KB';
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const terminal=row=>['ready','error','removed'].includes(row.state);
  const labels={waiting:'Wartet',uploading:'Wird hochgeladen',queued:'Wartet auf Umwandlung',checking:'Video wird geprüft',processing:'Wird umgewandelt',ready:'Fertig',error:'Fehlgeschlagen',removed:'Aus Warteschlange entfernt'};
  async function get(path){
    const response=await fetch(path,{credentials:'same-origin',cache:'no-store'});
    const data=await response.json();if(!response.ok){const error=new Error(data.error||'Status konnte nicht geladen werden.');error.status=response.status;throw error;}return data;
  }
  function emit(row){
    window.dispatchEvent(new CustomEvent('streamdesk:uploads-changed',{detail:{video_id:row.video_id,job_id:row.id}}));
    if(typeof refresh==='function')refresh().catch(()=>{});
  }
  function apply(row,data){row.state=data.state;row.progress=data.progress;row.message=data.message;row.video_id=data.video_id;row.sent=row.size;row.upload=100;}
  function rowNode(row){
    const node=el('article',undefined,'upload-item');node.dataset.uploadId=row.id;
    const title=el('strong',row.name),state=el('span','','badge'),heading=el('div',undefined,'upload-item-heading');heading.append(title,state);
    const folder=el('p',row.folderLabel||'','small muted'),uploadText=el('p','','small'),convertText=el('p','','small'),message=el('p','','small muted');
    const upload=el('progress'),conversion=el('progress');upload.max=conversion.max=100;upload.setAttribute('aria-label',row.name+' Upload');conversion.setAttribute('aria-label',row.name+' Umwandlung');
    const remove=button('Aus Warteschlange entfernen',()=>{row.state='removed';row.file=null;render();});
    const retry=button('Erneut versuchen',()=>{row.state='waiting';row.message='';row.failedLookup=true;paused=false;render();pump();});
    const open=el('a','Video ansehen ↗');open.target='_blank';open.rel='noopener';
    node.append(heading,folder,uploadText,upload,convertText,conversion,message,remove,retry,open);
    return {node,state,uploadText,convertText,upload,conversion,message,remove,retry,open};
  }
  function render(){
    const done=jobs.filter(row=>row.state==='ready').length,waiting=jobs.filter(row=>row.state==='waiting').length,active=jobs.find(row=>!terminal(row)&&row.state!=='waiting');
    for(const container of document.querySelectorAll('[data-upload-queue]')){
      let view=views.get(container);
      if(!view){const heading=el('h3','Upload-Warteschlange'),summary=el('p','','small'),note=el('p','Dateien werden nacheinander hochgeladen und umgewandelt. Für noch wartende Uploads diese Seite geöffnet lassen; der Wechsel zwischen Menüpunkten ist möglich.','small muted'),list=el('div',undefined,'upload-items');const clear=button('Abgeschlossene Einträge ausblenden',()=>{for(let i=jobs.length-1;i>=0;i--)if(terminal(jobs[i]))jobs.splice(i,1);render();});container.append(heading,summary,note,list,clear);view={summary,list,clear,rows:new Map()};views.set(container,view);}
      container.hidden=!jobs.length;
      const summary=done+' von '+jobs.length+' fertig'+(active?' · '+active.name+': '+(labels[active.state]||active.state):'')+(waiting?' · '+waiting+' warten':'')+(paused?' · Warteschlange pausiert':'');
      if(view.summary.textContent!==summary)view.summary.textContent=summary;
      for(const [id,item]of view.rows)if(!jobs.some(row=>row.id===id)){item.node.remove();view.rows.delete(id);}
      for(const row of jobs){let item=view.rows.get(row.id);if(!item){item=rowNode(row);view.rows.set(row.id,item);view.list.append(item.node);}
        const index=jobs.indexOf(row);if(view.list.children[index]!==item.node)view.list.insertBefore(item.node,view.list.children[index]||null);
        item.state.textContent=labels[row.state]||row.state;item.node.dataset.state=row.state;
        item.upload.value=row.upload||0;item.uploadText.textContent='Upload: '+Math.round(row.upload||0)+' % · '+bytes(row.sent||0)+' von '+bytes(row.size);
        if(row.state==='checking'){item.conversion.removeAttribute('value');item.convertText.textContent='Umwandlung: Video wird geprüft …';}
        else{item.conversion.value=row.progress||0;item.convertText.textContent='Umwandlung: '+Math.round(row.progress||0)+' %'+(row.state==='processing'&&row.progress>=99?' · Datei wird abgeschlossen …':'');}
        item.message.textContent=row.message||'';item.remove.hidden=row.state!=='waiting'||!row.file;item.retry.hidden=row.state!=='error'||!row.file;
        item.open.hidden=row.state!=='ready'||!row.video_id;if(row.video_id)item.open.href='/media/video/'+row.video_id;
      }
      view.clear.hidden=!jobs.some(terminal);
    }
  }
  async function existing(row){try{return await get('/api/uploads/'+row.id);}catch(error){if(error.status===404)return null;throw error;}}
  function send(row){
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();xhr.open('POST',row.endpoint);xhr.setRequestHeader('X-CSRF-Token',token);xhr.responseType='json';xhr.timeout=0;
      row.state='uploading';row.upload=0;row.sent=0;row.progress=0;row.message='';render();
      xhr.upload.onprogress=event=>{if(event.lengthComputable){row.upload=Math.min(100,event.loaded/event.total*100);row.sent=Math.min(row.size,row.size*event.loaded/event.total);render();}};
      xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300&&xhr.response?.ok){row.upload=100;row.sent=row.size;row.state='queued';render();resolve(xhr.response);return;}const error=new Error(xhr.response?.error||(xhr.status===413?'Datei zu groß oder Upload-Limit im Reverse Proxy zu niedrig.':'Upload fehlgeschlagen (HTTP '+xhr.status+').'));error.status=xhr.status;error.busy=xhr.response?.code==='upload_busy';reject(error);};
      xhr.onerror=()=>reject(new Error('Verbindung beim Upload unterbrochen. Erneut versuchen prüft zuerst den Serverstatus.'));
      xhr.ontimeout=()=>reject(new Error('Upload-Zeitlimit erreicht. Bitte Verbindung prüfen und erneut versuchen.'));
      const data=new FormData();data.append('video',row.file);data.append('upload_id',row.id);if(row.endpoint.includes('/playlists/'))data.append('folder_id',row.folder??'');xhr.send(data);
    });
  }
  async function process(row){
    let job=await existing(row);
    if(job?.state==='error'&&row.file){row.id=uid();job=null;render();}
    if(!job){
      if(!row.file)throw new Error('Die Datei muss erneut ausgewählt werden.');
      while(true){
        const status=await get('/api/uploads');
        if(row.state==='removed')return;
        if(status.busy){row.state='waiting';row.message='Eine vorherige Datei wird auf dem Server verarbeitet.';render();await delay(1000);continue;}
        if(row.endpoint.includes('/playlists/')&&!window.StreamDeskServices.allowed('playlists'))throw new Error('Playlist-Uploads wurden durch die Administration gesperrt.');
        try{await send(row);break;}catch(error){if(error.busy){row.state='waiting';row.message=error.message;render();await delay(1200);continue;}throw error;}
      }
    }
    let failures=0;
    while(true){
      try{job=await get('/api/uploads/'+row.id);failures=0;apply(row,job);render();}
      catch(error){if(error.status===401||error.status===403)throw error;if(++failures>=5){paused=true;throw new Error('Serverstatus nicht erreichbar. Bitte Verbindung prüfen und erneut versuchen.');}await delay(1000);continue;}
      if(row.state==='ready'){row.file=null;emit(row);return;}
      if(row.state==='error'){const error=new Error(row.message||'Video konnte nicht verarbeitet werden.');error.processing=true;throw error;}
      await delay(500);
    }
  }
  async function pump(){
    if(running||paused||!restored)return;running=true;
    try{let row;while(!paused&&(row=jobs.find(item=>!terminal(item)))){try{await process(row);}catch(error){row.state='error';row.message=error.message;if(!error.processing&&(!error.status||error.status===401||error.status===403))paused=true;render();}}}
    finally{running=false;render();}
  }
  function enqueue(form){
    const files=[...form.querySelector('[name=video]').files],pending=jobs.filter(row=>!terminal(row)).length;
    if(!files.length)return;if(files.length+pending>50){notify('Maximal 50 Dateien gleichzeitig in der Warteschlange.',true);return;}
    for(const file of files){let error='';if(!file.name.toLowerCase().endsWith('.mp4'))error='Bitte eine MP4-Datei auswählen.';
      jobs.push({id:uid(),name:file.name,file,endpoint:form.dataset.uploadUrl||'/api/upload',folder:form.dataset.folderId?Number(form.dataset.folderId):null,folderLabel:form.dataset.folderLabel||'Offline-Videos',size:file.size,upload:0,sent:0,progress:0,state:error?'error':'waiting',message:error});}
    form.reset();render();pump();
  }
  for(const form of document.querySelectorAll('[data-upload-form]'))form.addEventListener('submit',event=>{event.preventDefault();enqueue(form);});
  window.addEventListener('DOMContentLoaded',async()=>{
    try{const data=await get('/api/uploads');for(const job of data.jobs.filter(row=>['queued','checking','processing'].includes(row.state)).reverse())if(!jobs.some(row=>row.id===job.id))jobs.unshift({...job,name:job.filename,upload:100,sent:job.size,file:null});}
    catch(error){if(error.status!==401)notify(error.message,true);}finally{restored=true;render();pump();}
  });

  let serverLookup=false;
  window.addEventListener('streamdesk:status',event=>{
    const upload=event.detail.upload;if(!upload?.job_id)return;
    const row=jobs.find(item=>item.id===upload.job_id);
    if(row&&upload.stage){const previous=row.state;apply(row,{state:upload.stage,progress:upload.progress,message:upload.message,video_id:upload.video_id});render();if(row.state==='ready'&&previous!=='ready')emit(row);return;}
    if(row||serverLookup||!['queued','processing'].includes(upload.state))return;
    serverLookup=true;
    get('/api/uploads/'+upload.job_id).then(job=>{if(!jobs.some(item=>item.id===job.id)){jobs.unshift({...job,name:job.filename,upload:100,sent:job.size,file:null,folderLabel:job.kind==='ftp'?'FTP-Upload':'Server-Upload'});render();pump();}}).catch(()=>{}).finally(()=>serverLookup=false);
  });

  function mediaControls(video,changed){
    const wrapper=el('div',undefined,'media-controls'),form=el('form',undefined,'media-rename-form'),label=el('label','Neuer Videoname'),input=el('input');
    const draft=drafts.get(video.id);form.hidden=!draft;input.value=draft?.name??video.name;input.maxLength=120;input.required=true;input.setAttribute('aria-label',video.name+' umbenennen');label.append(input);
    const save=el('button','Namen speichern','secondary');save.type='submit';
    form.append(label,save,button('Abbrechen',()=>{drafts.delete(video.id);form.hidden=true;}));
    input.oninput=()=>drafts.set(video.id,{name:input.value});
    form.onsubmit=event=>{event.preventDefault();const name=input.value.trim();action(async()=>{await api('/api/videos/'+video.id+'/rename',{name});drafts.delete(video.id);await changed();},'Video umbenannt.',form);};
    const rename=button('Umbenennen',()=>{form.hidden=false;drafts.set(video.id,{name:input.value});input.focus();input.select();});
    const remove=button('Löschen',async()=>{
      remove.disabled=true;
      try{
        const latest=await api('/api/videos/'+video.id),references=latest.in_playlists||[];
        if(latest.can_delete===false){notify(latest.delete_reason||'Dieses Video wird noch verwendet.',true);await changed();return;}
        if(!confirm('Video „'+latest.name+'“ endgültig löschen?'+(references.length?'\nEs wird dabei aus diesen Playlists entfernt: '+references.join(', '):'')))return;
        await action(async()=>{await api('/api/videos/'+video.id+'/delete',{remove_from_playlists:references.length>0});drafts.delete(video.id);for(const row of jobs)if(row.video_id===video.id){row.video_id=null;row.message='Video wurde gelöscht.';}render();},'Video gelöscht.',wrapper);
        await changed();
      }catch(error){notify(error.message,true);}finally{remove.disabled=video.can_delete===false;}
    });
    remove.disabled=video.can_delete===false;wrapper.append(rename,remove,form);
    if(video.delete_reason)wrapper.append(el('p',video.delete_reason,'small muted media-delete-reason'));
    else if(video.in_playlists?.length)wrapper.append(el('p','In Playlists: '+video.in_playlists.join(', '),'small muted'));
    return wrapper;
  }
  window.StreamDeskMedia={controls:mediaControls};
})();

'use strict';
(() => {
  const meta=document.querySelector('meta[name=streamdesk-services]');
  let flags=meta?JSON.parse(meta.content):{},adminLoading=false,loaded=false;
  const routes={playlists:['playlists'],'expert-playlists':['playlists'],'settings-twitch':['twitch'],'settings-youtube':['youtube'],'settings-custom':['custom_outputs'],
    'expert-discord':['discord'],'expert-recording':['recording'],'expert-playback':['playback'],
    'expert-viewers':['viewers'],'expert-renewal':['automation'],'expert-routing':['advanced_routing'],
    'expert-outputs':['advanced_routing'],'expert-automation':['automation','notifications']};
  const allowed=key=>flags[key]!==false;
  const output=kind=>allowed(({twitch:'twitch',youtube:'youtube',custom:'custom_outputs'})[kind.split('-')[0]])&&(['twitch','youtube','custom'].includes(kind)||allowed('advanced_routing'));
  function view(name){return !routes[name]||routes[name].some(allowed);}
  function apply(){
    for(const node of document.querySelectorAll('[data-service]'))node.classList.toggle('service-disabled',!node.dataset.service.split(' ').some(allowed));
    for(const link of document.querySelectorAll('a[href^="#"]')){
      const restricted=!!routes[link.hash.slice(1)]&&!view(link.hash.slice(1));
      link.classList.toggle('service-disabled',restricted);
    }
    const blocked=document.querySelector('#service-blocked');
    if(blocked){
      const name=location.hash.slice(1)||'dashboard';blocked.hidden=view(name);
      if(!view(name))document.querySelectorAll('.app-view').forEach(node=>node.hidden=true);
    }
    for(const option of document.querySelectorAll('.chat-platform option,.chat-target option,#widget-platform option')){
      const keys=option.value==='both'?['twitch','youtube']:['twitch','youtube','discord'].includes(option.value)?[option.value]:[];
      if(keys.some(key=>!allowed(key)))option.disabled=true;
    }
  }
  async function loadAdmin(force=false){
    const list=document.querySelector('#admin-service-list');
    if(!list||adminLoading||loaded&&!force)return;
    adminLoading=true;
    try{
      const data=await api('/api/admin/services');loaded=true;const wasLoaded=!!list.children.length,opened=new Set([...list.querySelectorAll('details[open]')].map(node=>node.dataset.group));list.replaceChildren();
      document.querySelector('#service-runtime-status').textContent=data.runtime_pending?'Freigaben gespeichert. Der Abgleich mit MediaMTX steht noch aus und wird erneut versucht.':'';
      for(const group of [...new Set(data.services.map(row=>row.group))]){
        const section=document.createElement('details');section.className='panel service-group';section.dataset.group=group;section.open=wasLoaded?opened.has(group):group===data.services[0].group;
        const title=document.createElement('summary');title.textContent=group;const count=document.createElement('span');count.className='badge';count.textContent=data.services.filter(row=>row.group===group&&row.enabled).length+' / '+data.services.filter(row=>row.group===group).length+' freigegeben';title.append(count);
        const grid=document.createElement('div');grid.className='service-grid';section.append(title,grid);
        for(const item of data.services.filter(row=>row.group===group)){
          const card=document.createElement('div');card.className='service-card';card.dataset.serviceId=item.id;
          const name=document.createElement('h3');name.textContent=item.label;
          const badge=document.createElement('span');badge.className='badge '+(item.enabled?'good':'service-off');badge.textContent=item.enabled?'Freigegeben':'Gesperrt';
          const description=document.createElement('p');description.className='small muted';description.textContent=item.description;
          const button=document.createElement('button');button.type='button';button.className=item.enabled?'secondary':'primary';button.textContent=item.enabled?'Für alle sperren':'Für alle freigeben';button.setAttribute('aria-label',item.label+' '+(item.enabled?'sperren':'freigeben'));
          button.onclick=()=>action(async()=>{
            const result=await api('/api/admin/services',{id:item.id,enabled:!item.enabled});
            flags=Object.fromEntries(result.services.map(row=>[row.id,row.enabled]));apply();await loadAdmin(true);
            if(result.warning)notify(result.warning,true);
          },item.enabled?'Dienst gesperrt. Die Konfiguration bleibt erhalten.':'Dienst wieder freigegeben.',card);
          card.append(name,badge,description,button);grid.append(card);
        }
        list.append(section);
      }
    }catch(error){notify(error.message,true);}finally{adminLoading=false;}
  }
  window.StreamDeskServices={allowed,output,view,apply};
  window.addEventListener('streamdesk:status',event=>{
    const next=event.detail.services||flags,changed=JSON.stringify(flags)!==JSON.stringify(next);flags=next;apply();
    if(changed&&typeof showView==='function')showView();
  });
  window.addEventListener('hashchange',()=>{apply();if(location.hash==='#administration-services')loadAdmin(true);});
  window.addEventListener('DOMContentLoaded',()=>{apply();if(location.hash==='#administration-services')loadAdmin();});
})();

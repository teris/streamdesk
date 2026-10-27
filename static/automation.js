'use strict';
(()=>{
  const $=selector=>document.querySelector(selector);
  let loaded=false,loading=false;
  const button=(text,callback)=>{const item=document.createElement('button');item.type='button';item.className='ghost';item.textContent=text;item.addEventListener('click',callback);return item;};
  async function load(){
    const status=window.state;if(!status?.expert_mode||loading||!window.StreamDeskServices.view('expert-automation'))return;
    loading=true;
    try{
      const [data,notifications]=await Promise.all([window.StreamDeskServices.allowed('automation')?api('/api/automation'):Promise.resolve({available_hooks:[],hooks:[],jobs:[],export:{enabled:false,url:'',username:''}}),window.StreamDeskServices.allowed('notifications')?api('/api/notifications'):Promise.resolve({enabled:false,webhook:'',email:'',smtp_host:'',smtp_port:465,smtp_user:''})]);loaded=true;
      const actions=$('#automation-action');actions.replaceChildren(...data.available_hooks.map(name=>new Option(name,name)));
      const hooks=$('#automation-hooks');hooks.replaceChildren(...data.hooks.map(row=>{const line=document.createElement('p');line.textContent=`${row.event} → ${row.action_name} `;line.append(button('Entfernen',async()=>{await api('/api/automation/hooks/'+row.id,{},'DELETE');await load();}));return line;}));
      const jobs=$('#automation-jobs');jobs.replaceChildren(...data.jobs.map(row=>{const line=document.createElement('p');line.textContent=`${new Date(row.run_at*1000).toLocaleString()} · ${row.kind} · ${row.status} `;if(row.status==='pending')line.append(button('Abbrechen',async()=>{await api('/api/automation/jobs/'+row.id,{},'DELETE');await load();}));return line;}));
      $('#automation-export-enabled').checked=data.export.enabled;$('#automation-export-url').value=data.export.url;$('#automation-export-user').value=data.export.username;
      $('#notification-enabled').checked=notifications.enabled;$('#notification-webhook').value=notifications.webhook;$('#notification-email').value=notifications.email;$('#notification-smtp-host').value=notifications.smtp_host;$('#notification-smtp-port').value=notifications.smtp_port;$('#notification-smtp-user').value=notifications.smtp_user;
    }catch(error){notify(error.message,true);}finally{loading=false;}
  }
  $('#automation-hook-form')?.addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api('/api/automation/hooks',{event:$('#automation-event').value,action_name:$('#automation-action').value});await load();},'Hook gespeichert.',event.currentTarget);});
  $('#automation-job-form')?.addEventListener('submit',event=>{event.preventDefault();action(async()=>{const kind=$('#automation-kind').value,target=$('#automation-target').value.trim();const payload=kind.startsWith('record_')?{source:target||'live'}:{kind:target};await api('/api/automation/jobs',{kind,payload,run_at:new Date($('#automation-time').value).getTime()/1000});await load();},'Auftrag eingeplant.',event.currentTarget);});
  $('#automation-export-form')?.addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api('/api/automation/export',{enabled:$('#automation-export-enabled').checked,url:$('#automation-export-url').value.trim(),username:$('#automation-export-user').value,password:$('#automation-export-password').value});$('#automation-export-password').value='';await load();},'Export gespeichert.',event.currentTarget);});
  $('#notification-form')?.addEventListener('submit',event=>{event.preventDefault();action(async()=>{await api('/api/notifications',{enabled:$('#notification-enabled').checked,webhook:$('#notification-webhook').value.trim(),email:$('#notification-email').value.trim(),smtp_host:$('#notification-smtp-host').value.trim(),smtp_port:Number($('#notification-smtp-port').value),smtp_user:$('#notification-smtp-user').value.trim(),smtp_password:$('#notification-smtp-password').value});$('#notification-smtp-password').value='';await load();},'Benachrichtigungen gespeichert.',event.currentTarget);});
  window.addEventListener('hashchange',()=>{if(location.hash==='#expert-automation')load();});
  window.addEventListener('streamdesk:status',event=>{window.state=event.detail;if(!event.detail.expert_mode)loaded=false;if(location.hash==='#expert-automation'&&!loaded)load();});
})();

'use strict';
(() => {
  const find=selector=>document.querySelector(selector);
  const form=find('#discord-form');
  let expert=false,loaded=false,loading=false,edited=false;
  const channel=find('#discord-channel-id'),token=find('#discord-bot-token');
  form.addEventListener('input',()=>edited=true);
  async function load(force=false){
    if(!window.StreamDeskServices.allowed('discord')||!expert||loading||(!force&&loaded))return;
    loading=true;
    try{
      const data=await api('/api/discord');
      loaded=true;
      const badge=find('#discord-connection-state');badge.textContent=data.connected?'Verbunden':'Noch nicht verbunden';badge.classList.toggle('good',data.connected);
      find('#discord-connection-description').textContent=data.connected?`Verbunden mit #${data.channel_name} · Kanal ${data.channel_id}`:'Verbinde einen Bot mit einem Textkanal deines Discord-Servers.';
      if(!edited)channel.value=data.channel_id;
      find('#discord-disconnect').disabled=!data.connected;
    }catch(error){notify(error.message,true);}finally{loading=false;}
  }
  form.addEventListener('submit',event=>{
    event.preventDefault();if(!form.reportValidity())return;
    const body={channel_id:channel.value.trim(),bot_token:token.value.trim()};
    action(async()=>{await api('/api/discord',body);token.value='';edited=false;await load(true);await loadChat();},'Discord-Chat verbunden.',form);
  });
  find('#discord-disconnect').addEventListener('click',()=>action(async()=>{
    await api('/api/discord/disconnect',{});token.value='';edited=false;await load(true);await loadChat();
  },'Discord getrennt.',form));
  window.addEventListener('streamdesk:status',event=>{
    expert=event.detail.expert_mode;
    if(!expert){loaded=false;edited=false;channel.value='';token.value='';}
    else if(location.hash==='#expert-discord')load();
  });
  window.addEventListener('hashchange',()=>{if(location.hash==='#expert-discord')load();});
})();

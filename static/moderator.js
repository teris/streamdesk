'use strict';
(() => {
  const csrf=document.querySelector('meta[name=csrf-token]').content;
  const call=async(path,body)=>{
    const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Aktion fehlgeschlagen.');return data;
  };
  let messages=[];
  async function poll(){
    try{const data=await call('/api/chat');messages=data.messages;ChatUI.draw(document.querySelector('.chat-messages'),messages);
      document.querySelector('#moderator-status').textContent=Object.entries(data.connections).map(([name,value])=>`${name}: ${value}`).join(' · ');
    }catch(error){document.querySelector('#feedback').textContent=error.message;}
    setTimeout(poll,2000);
  }
  document.querySelector('.chat-compose').addEventListener('submit',async event=>{
    event.preventDefault();const target=document.querySelector('.chat-target').value;
    const targets=target==='both'?['twitch','youtube']:[target];
    try{await call('/api/chat/send',{message:document.querySelector('.chat-message').value,targets,nonce:crypto.randomUUID().replaceAll('-','')});document.querySelector('.chat-message').value='';}
    catch(error){document.querySelector('#feedback').textContent=error.message;}
  });
  document.querySelector('#logout').onclick=async()=>{await call('/api/logout',{});location.href='/login';};
  document.querySelector('#moderator-password').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget;
    try{await call('/api/password',Object.fromEntries(new FormData(form)));form.reset();document.querySelector('#feedback').textContent='Dein Passwort wurde geändert.';}
    catch(error){document.querySelector('#feedback').textContent=error.message;}
  });
  poll();
})();

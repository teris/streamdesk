'use strict';
(() => {
  const frame=document.querySelector('#source3 iframe'),button=document.querySelector('#program-audio-toggle'),volume=document.querySelector('#program-volume'),value=document.querySelector('#program-volume-value'),status=document.querySelector('#program-audio-status');
  let desired={muted:true,volume:.7};
  function player(){try{return !frame.hidden&&frame.getAttribute('src')!=='about:blank'?frame.contentWindow.StreamDeskPlayer:null;}catch(_){return null;}}
  function render(data){
    const audible=!data.muted&&data.volume>0;
    button.textContent=audible?'Ton ausschalten':'Ton einschalten';button.setAttribute('aria-pressed',String(audible));volume.value=Math.round(data.volume*100);value.value=Math.round(data.volume*100)+' %';
    status.textContent=audible?'Ton der Programmvorschau ist an.':'Vorschau ist stumm. Ton bei Bedarf einschalten.';
  }
  function sync(){
    const api=player(),available=!!api;button.disabled=!available;volume.disabled=!available;
    if(available){render(api.audioState());return;}
    button.textContent='Ton einschalten';button.setAttribute('aria-pressed','false');status.textContent=frame.hidden?'Vorschau öffnen, um den Ton einzuschalten.':'Vorschau wird geladen …';
  }
  async function apply(settings){
    const api=player();if(!api){sync();return;}
    try{const data=await api.setAudio(settings);desired={muted:data.muted,volume:data.volume};render(data);}
    catch(error){desired.muted=true;sync();status.textContent=error.message;}
  }
  button.addEventListener('click',()=>{const data=player()?.audioState();if(data)apply({muted:!data.muted&&data.volume>0,volume:data.volume||.7});});
  volume.addEventListener('input',()=>apply({volume:Number(volume.value)/100,muted:Number(volume.value)===0}));
  frame.addEventListener('load',()=>{const api=player();if(api){api.setEmbedded(true);apply(desired);}sync();});
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==frame.contentWindow||event.data?.type!=='streamdesk:preview-audio'||typeof event.data.muted!=='boolean'||!Number.isFinite(event.data.volume))return;
    desired={muted:event.data.muted,volume:Math.max(0,Math.min(1,event.data.volume))};sync();
  });
  window.StreamDeskPreviewAudio={sync};sync();
})();

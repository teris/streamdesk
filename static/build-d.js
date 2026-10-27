'use strict';
(() => {
  const q = selector => document.querySelector(selector);
  const decode = value => Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/') + '='.repeat((4-value.length%4)%4)), c => c.charCodeAt(0));
  const encode = value => btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');

  async function scenes() {
    if(!window.StreamDeskServices.allowed('advanced_routing'))return;
    const data = await api('/api/scenes'), list = q('#scene-list');
    list.replaceChildren();
    for (const scene of data.scenes) {
      const row=document.createElement('div');row.className='user-row';
      const label=document.createElement('span');label.textContent=`${scene.name} · ${scene.sources.join(' → ')} · ${scene.targets.join(', ')||'kein Ziel'}`;
      const apply=document.createElement('button');apply.className='secondary';apply.textContent='Anwenden';
      apply.onclick=()=>action(async()=>{await api(`/api/scenes/${scene.id}/apply`,{});await scenes();},'Szene angewendet.',row);
      const remove=document.createElement('button');remove.className='ghost';remove.textContent='Löschen';
      remove.onclick=()=>action(async()=>{await api(`/api/scenes/${scene.id}`,{},'DELETE');await scenes();},'Szene gelöscht.',row);
      row.append(label,apply,remove);list.append(row);
    }
    if (!data.scenes.length) list.textContent='Noch keine Szenen gespeichert.';
  }
  q('#scene-form')?.addEventListener('submit', event => {
    event.preventDefault();const form=event.currentTarget,body=Object.fromEntries(new FormData(form));
    body.sources=body.sources.split(',').map(x=>x.trim()).filter(Boolean);
    body.targets=body.targets.split(',').map(x=>x.trim()).filter(Boolean);
    body.video_id=body.video_id?Number(body.video_id):null;
    action(async()=>{await api('/api/scenes',body);await scenes();form.reset();},'Szene gespeichert.',form);
  });

  async function passkeys() {
    const data=await api('/api/passkeys'),list=q('#passkey-list');list.replaceChildren();
    for(const item of data.credentials){
      const row=document.createElement('div');row.className='user-row';
      const label=document.createElement('span');label.textContent=`${item.label} · ${new Date(item.created*1000).toLocaleDateString()}`;
      const remove=document.createElement('button');remove.className='ghost';remove.textContent='Entfernen';
      remove.onclick=()=>action(async()=>{await api(`/api/passkeys/${item.id}`,{},'DELETE');await passkeys();},'Passkey entfernt.',row);
      row.append(label,remove);list.append(row);
    }
    if(!data.credentials.length)list.textContent='Noch kein Passkey registriert.';
  }
  q('#passkey-add')?.addEventListener('click',()=>action(async()=>{
    if(!window.PublicKeyCredential)throw new Error('Dieser Browser unterstützt keine Passkeys.');
    const options=await api('/api/passkeys/register/options',{});
    const credential=await navigator.credentials.create({publicKey:{
      challenge:decode(options.challenge),rp:{id:options.rp_id,name:'MediaMTX - StreamDesk'},
      user:{id:decode(options.user_id),name:options.username,displayName:options.username},
      pubKeyCredParams:[{type:'public-key',alg:-7},{type:'public-key',alg:-257}],
      timeout:60000,attestation:'none',authenticatorSelection:{residentKey:'preferred',userVerification:'required'},
      excludeCredentials:options.exclude.map(id=>({type:'public-key',id:decode(id)}))
    }});
    const result=await api('/api/passkeys/register',{credential_id:encode(credential.rawId),
      client_data:encode(credential.response.clientDataJSON),attestation_object:encode(credential.response.attestationObject),
      label:navigator.userAgentData?.platform||'Passkey'});
    const output=q('#recovery-codes');output.hidden=false;output.textContent='Recovery-Codes – jetzt sicher speichern:\n'+result.recovery_codes.join('\n');
    await passkeys();
  },'Passkey registriert.',q('#passkey-list')));

  q('#language')?.addEventListener('change',event=>action(async()=>{
    await api('/api/preferences',{language:event.target.value});location.reload();
  },'Sprache gespeichert.',q('#language-form')));
  scenes().catch(error=>notify(error.message,true));
  passkeys().catch(error=>notify(error.message,true));
})();

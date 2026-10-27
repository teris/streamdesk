'use strict';
(() => {
  const form=document.querySelector('form'),csrf=form.querySelector('[name=csrf]').value,feedback=document.querySelector('#passkey-feedback');
  const decode=value=>Uint8Array.from(atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4)),c=>c.charCodeAt(0));
  const encode=value=>btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  async function call(path,body){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error);return data;}
  document.querySelector('#passkey-login').onclick=async()=>{
    try{
      const username=form.elements.username.value.trim();if(!username)throw new Error('Bitte zuerst den Benutzernamen eingeben.');
      const options=await call('/api/passkeys/login/options',{username});
      if(!options.allow.length)throw new Error('Für dieses Konto ist kein Passkey registriert.');
      const credential=await navigator.credentials.get({publicKey:{challenge:decode(options.challenge),rpId:options.rp_id,timeout:60000,userVerification:'required',allowCredentials:options.allow.map(id=>({type:'public-key',id:decode(id)}))}});
      await call('/api/passkeys/login',{credential_id:encode(credential.rawId),client_data:encode(credential.response.clientDataJSON),authenticator_data:encode(credential.response.authenticatorData),signature:encode(credential.response.signature)});
      location.href='/';
    }catch(error){feedback.textContent=error.message;}
  };
  document.querySelector('#recovery-login').onclick=async()=>{
    try{const username=form.elements.username.value.trim(),code=prompt('Recovery-Code');if(!code)return;
      await call('/api/recovery/login',{username,code});location.href='/';
    }catch(error){feedback.textContent=error.message;}
  };
})();

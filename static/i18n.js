'use strict';
(() => {
  const language = document.documentElement.lang === 'en' ? 'en' : 'de';
  const strings = {
    de: {
      dashboard:'Dashboard', sources:'Quellen', videos:'Offline-Videos', recordings:'Aufnahmen',
      chat:'Chat & Widget', settings:'Einstellungen', account:'Mein Konto', logout:'Abmelden',
      administration:'Administration', saveAppearance:'Darstellung speichern', language:'Sprache',
      scenes:'Szenen', passkeys:'Passkeys & Recovery', addPasskey:'Passkey hinzufügen'
    },
    en: {
      dashboard:'Dashboard', sources:'Sources', videos:'Offline videos', recordings:'Recordings',
      chat:'Chat & widget', settings:'Settings', account:'My account', logout:'Sign out',
      administration:'Administration', saveAppearance:'Save appearance', language:'Language',
      scenes:'Scenes', passkeys:'Passkeys & recovery', addPasskey:'Add passkey'
    }
  };
  window.StreamDeskI18n = {language, t:key => strings[language][key] || key};
  for (const node of document.querySelectorAll('[data-i18n]')) {
    node.textContent = window.StreamDeskI18n.t(node.dataset.i18n);
  }
})();

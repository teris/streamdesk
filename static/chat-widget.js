'use strict';
const token = location.pathname.split('/').pop();
const params = new URLSearchParams(location.search); const filter = ['twitch', 'youtube', 'discord'].includes(params.get('platform')) ? params.get('platform') : 'all';
if (params.get('transparent') === '1') document.body.classList.add('transparent');
(async function poll() {
  try {
    const response = await fetch('/api/chat/widget-data/' + encodeURIComponent(token), { cache: 'no-store', credentials: 'omit' });
    if (!response.ok) throw new Error(response.status === 404 ? 'Widget-Link ungültig oder erneuert' : 'Chat nicht erreichbar');
    const data = await response.json(); ChatUI.draw(document.querySelector('#widget-messages'), data.messages, filter);
    document.querySelector('#widget-status').textContent = Object.entries(data.connections).filter(([platform]) => filter === 'all' || filter === platform).map(([platform, status]) => ({twitch:'Twitch',youtube:'YouTube',discord:'Discord'}[platform] || platform) + ': ' + status).join(' · ');
  } catch (error) { document.querySelector('#widget-status').textContent = error.message; if (error.message.startsWith('Widget-Link')) document.querySelector('#widget-messages').replaceChildren(); }
  setTimeout(poll, 2000);
})();

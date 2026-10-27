'use strict';
window.ChatUI = {
  draw(container, messages, filter = 'all') {
    const shown = messages.filter(m => filter === 'all' || m.platform === filter);
    const signature = JSON.stringify(shown);
    if (container.dataset.signature === signature) return;
    const follow = container.scrollHeight - container.scrollTop - container.clientHeight < 70;
    const position = container.scrollTop; container.dataset.signature = signature; container.replaceChildren();
    if (!shown.length) { const empty = document.createElement('p'); empty.className = 'chat-empty'; empty.textContent = 'Noch keine Nachrichten. Twitch verbinden und für YouTube eine Live-Sendung mit aktiviertem Chat auswählen.'; container.append(empty); }
    for (const message of shown) {
      const row = document.createElement('article'); row.className = 'chat-row ' + message.platform;
      const header = document.createElement('div'); header.className = 'chat-message-header';
      const badge = document.createElement('span'); badge.className = 'chat-platform'; badge.textContent = {twitch:'TW',youtube:'YT',discord:'DC'}[message.platform] || '?';
      const author = document.createElement('strong'); author.textContent = message.author || 'Nachricht';
      const time = document.createElement('time'); const date = new Date(message.time); time.textContent = Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString(document.documentElement.lang || 'de', { hour: '2-digit', minute: '2-digit' });
      header.append(badge, author, time); const text = document.createElement('p'); text.textContent = message.text; row.append(header, text); container.append(row);
    }
    if (follow) container.scrollTop = container.scrollHeight; else container.scrollTop = position;
  }
};

function update() { document.querySelector('#clock').textContent = new Date().toLocaleTimeString('de-DE'); } update(); setInterval(update, 1000);

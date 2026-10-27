"""Deduplizated webhook and optional SMTP notifications."""
import json
import smtplib
import ssl
import threading
import time
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr
from outbound_http import public_addresses, PublicSMTP

from flask import jsonify, request


class NotificationFeatures:
    def __init__(self, core):
        self.c=core
        self.states={}
        self.sent={}
        with core.db() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS notification_settings(
              user_id INTEGER PRIMARY KEY,webhook TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',
              smtp_host TEXT NOT NULL DEFAULT '',smtp_port INTEGER NOT NULL DEFAULT 465,
              smtp_user TEXT NOT NULL DEFAULT '',smtp_password TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 0)''')
        self.install_routes()

    def install_routes(self):
        c=self.c
        expert=lambda function:c.login_required(c.expert_required(function))

        @c.app.get('/api/notifications')
        @expert
        def notification_status(user):
            return jsonify(self.public(user))

        @c.app.post('/api/notifications')
        @expert
        def notification_save(user):
            body=c.FEATURES.body()
            enabled=body.get('enabled')
            if type(enabled) is not bool:raise c.Error('Ungültiger Benachrichtigungsschalter.')
            webhook=str(body.get('webhook','')).strip()
            if webhook:c.validate_public_http(webhook)
            email=str(body.get('email','')).strip()
            if email and (len(email)>254 or '@' not in email or any(ord(char)<33 for char in email) or parseaddr(email)[1] != email):raise c.Error('Ungültige E-Mail-Adresse.')
            host=str(body.get('smtp_host','')).strip()
            try:port=int(body.get('smtp_port',465))
            except (TypeError,ValueError):raise c.Error('Ungültiger SMTP-Port.') from None
            if not 1 <= port <= 65535:
                raise c.Error('Ungültiger SMTP-Port.')
            if enabled and host:
                try:
                    public_addresses(host, port, c.resolve_host_ips, c.ingest_ips())
                except (ValueError,OSError):
                    raise c.Error('Bitte einen öffentlichen SMTP-Host verwenden.') from None
            if enabled and not webhook and not (email and host):raise c.Error('Webhook oder vollständige SMTP-Einstellungen angeben.')
            previous=c.rows('SELECT * FROM notification_settings WHERE user_id=?',(user['id'],))
            password=str(body.get('smtp_password',''))
            encrypted_password=c.encrypt(password) if password else previous[0]['smtp_password'] if previous else ''
            values=(user['id'],c.encrypt(webhook),c.encrypt(email),c.encrypt(host),port,
                    c.encrypt(str(body.get('smtp_user','')).strip()),encrypted_password,int(enabled))
            c.write('''INSERT INTO notification_settings(user_id,webhook,email,smtp_host,smtp_port,smtp_user,smtp_password,enabled)
                       VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET webhook=excluded.webhook,email=excluded.email,
                       smtp_host=excluded.smtp_host,smtp_port=excluded.smtp_port,smtp_user=excluded.smtp_user,
                       smtp_password=excluded.smtp_password,enabled=excluded.enabled''',values)
            return jsonify(ok=True)

    def public(self,user):
        rows=self.c.rows('SELECT * FROM notification_settings WHERE user_id=?',(user['id'],))
        if not rows:return {'enabled':False,'webhook':'','email':'','smtp_host':'','smtp_port':465,'smtp_user':''}
        row=rows[0]
        return {'enabled':bool(row['enabled']),'webhook':self.c.decrypt(row['webhook']),'email':self.c.decrypt(row['email']),
                'smtp_host':self.c.decrypt(row['smtp_host']),'smtp_port':row['smtp_port'],'smtp_user':self.c.decrypt(row['smtp_user'])}

    def observe(self,user,sources,output_states,free_bytes):
        if not self.c.SERVICES.enabled('notifications'):return
        current={'offline':not any(row.get('state')=='online' for row in sources),
                 'forward_error':any(value=='error' for value in output_states.values()),
                 'storage_low':free_bytes<500*1048576}
        previous=self.states.get(user['id'],{})
        self.states[user['id']]=current
        for event,active in current.items():
            if active and not previous.get(event) and time.monotonic()-self.sent.get((user['id'],event),-3600)>=300:
                self.sent[(user['id'],event)]=time.monotonic()
                threading.Thread(target=self.deliver,args=(user,event),daemon=True).start()

    def deliver(self,user,event):
        if not self.c.SERVICES.enabled('notifications'):return
        found=self.c.rows('SELECT * FROM notification_settings WHERE user_id=? AND enabled=1',(user['id'],))
        if not found:return
        row=found[0]
        labels={'offline':'Alle Streamquellen sind offline.','forward_error':'Mindestens ein Streamingziel meldet einen Fehler.',
                'storage_low':'Der freie Speicher ist unter 500 MB gefallen.'}
        message=labels[event]
        webhook=self.c.decrypt(row['webhook'])
        if webhook:
            try:
                self.c.validate_public_http(webhook)
                with self.c.public_https(webhook,data=json.dumps({'event':event,'message':message,'user':user['username']}).encode(),
                                         headers={'Content-Type':'application/json'},method='POST',timeout=10):pass
            except (OSError,ValueError,self.c.Error):
                self.c.logging.warning('Benachrichtigungs-Webhook fehlgeschlagen (Benutzer-ID %s).',user['id'])
        email,host=self.c.decrypt(row['email']),self.c.decrypt(row['smtp_host'])
        if email and host:
            try:
                content=EmailMessage()
                content['From']=email;content['To']=email;content['Subject']='StreamDesk: '+event
                content.set_content(message)
                with PublicSMTP(host,row['smtp_port'],timeout=10,context=ssl.create_default_context(),
                                resolver=self.c.resolve_host_ips,blocked=self.c.ingest_ips()) as smtp:
                    username=self.c.decrypt(row['smtp_user'])
                    if username:smtp.login(username,self.c.decrypt(row['smtp_password']))
                    smtp.send_message(content)
            except (OSError,ValueError,smtplib.SMTPException):
                self.c.logging.warning('Benachrichtigungs-E-Mail fehlgeschlagen (Benutzer-ID %s).',user['id'])

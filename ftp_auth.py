#!/usr/bin/env python3
"""Pure-FTPd external authentication. Never imports or starts the web application."""
import json
import os
from pathlib import Path
import re
import sqlite3
from cryptography.fernet import Fernet
from werkzeug.security import check_password_hash


def authenticate(environ=None):
    env=os.environ if environ is None else environ
    data=Path(env.get('STREAMDESK_DATA','/var/lib/streamdesk'))
    account=env.get('AUTHD_ACCOUNT','');password=env.get('AUTHD_PASSWORD','')
    if not re.fullmatch(r'sd_[a-z][a-z0-9_-]{0,39}_\d+',account) or not 12<=len(password)<=256:return None
    # Explicit FTPS is mandatory for credentials and data. No plaintext fallback.
    if env.get('AUTHD_ENCRYPTED') not in ('1','2'):return None
    with sqlite3.connect(data.resolve().as_uri()+'/app.db?mode=ro',uri=True,timeout=3) as db:
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT f.*,u.active,u.role FROM ftp_accounts f JOIN users u ON f.user_id=u.id WHERE f.username=? AND f.enabled=1 AND u.active=1 AND u.role!='moderator'",(account,)).fetchone()
        if not row or not check_password_hash(row['password'],password):return None
        policy=db.execute("SELECT value FROM settings WHERE name='service_policy'").fetchone()
        if policy:
            flags=json.loads(Fernet((data/'fernet.key').read_bytes()).decrypt(policy[0].encode()).decode())
            if not isinstance(flags,dict) or any(flags.get(key,True) is not True for key in ('ftp','playlists')):return None
    home=data/'ftp'/str(row['user_id'])
    if not home.is_dir() or any(p.is_symlink() for p in [home,home.parent,data]) or not home.resolve().is_relative_to(data.resolve()/'ftp'):return None
    uid=int(env['STREAMDESK_FTP_UID']);gid=int(env['STREAMDESK_FTP_GID'])
    if uid<=0 or gid<=0:return None
    return dict(uid=uid,gid=gid,home=str(home.resolve()))


def main():
    try:result=authenticate()
    except Exception:result=None
    if result:print('auth_ok:1\nuid:'+str(result['uid'])+'\ngid:'+str(result['gid'])+'\ndir:'+result['home']+'\nslow_tilde_expansion:1\nend')
    else:print('auth_ok:-1\nend')

if __name__=='__main__':main()

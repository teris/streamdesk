"""Browser regression for FTP creation feedback, selected-account details and ingest host."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from media_smoke import port,until


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshots-dir',type=Path);args=parser.parse_args()
    server=None;core=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-ftp-ui-',dir='/tmp') as directory:
        base=Path(directory);config=base/'media.yml';config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{}}));clip=base/'fixture.mp4';clip.write_bytes(b'fixture')
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),STREAMDESK_FTP_ENABLED='1',STREAMDESK_INGEST='ingest.example.test',STREAMDESK_FTP_HOST='wrong-web.example.test',STREAMDESK_PUBLIC='https://panel.example.test',COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):
            admin=core.add_user('ftpadmin','FTP-UI-Admin-Fixture-123',admin=True)
            uid=core.add_user('ftpviewer','FTP-UI-User-Fixture-123')
        clock=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));clock.start()
        try:
            server=make_server('127.0.0.1',port(),core.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start();address='http://127.0.0.1:'+str(server.server_port)
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,args=['--no-sandbox']);admin_context=browser.new_context(viewport={'width':1440,'height':1050});user_context=browser.new_context(viewport={'width':1440,'height':1050});page=admin_context.new_page();user=user_context.new_page();errors=[]
                for tab in (page,user):tab.on('pageerror',lambda error:errors.append(str(error)))
                def login(tab,username,password):
                    tab.goto(address+'/login');tab.locator('[name=username]').fill(username);tab.locator('[name=password]').fill(password);tab.locator('button[type=submit]').click();tab.wait_for_url(address+'/')
                login(page,'ftpadmin','FTP-UI-Admin-Fixture-123');page.goto(address+'/#administration-ftp')
                form=page.locator('#admin-ftp-form');form.locator('[name=user_id]').select_option(str(uid));page.wait_for_function("() => document.querySelector('#admin-ftp-status').textContent.includes('ftpviewer')")
                assert form.locator('[name=password]').get_attribute('required') is not None
                form.locator('[name=password]').fill('FTP-UI-Created-Password-123')
                def save(enabled):
                    form.locator('[name=enabled]').set_checked(enabled)
                    with page.expect_response(lambda response:response.url.endswith('/api/admin/users/'+str(uid)+'/ftp') and response.request.method=='POST') as response:
                        form.locator('[type=submit]').click()
                    assert response.value.status==200,response.value.text()
                    page.wait_for_function("() => document.querySelector('#admin-ftp-form .form-feedback')?.textContent==='FTP-Zugang gespeichert.'")
                    assert 'Wird gespeichert' not in form.inner_text()
                    assert not form.locator('[name=password]').input_value()
                save(True)
                connection=page.locator('#admin-ftp-connection');assert connection.get_by_label('Server (Ingest)',exact=True).input_value()=='ingest.example.test'
                assert connection.get_by_label('Port',exact=True).input_value()=='2121';username=connection.get_by_label('FTP-Benutzername',exact=True).input_value();assert username=='sd_'+core.NAMESPACE+'_'+str(uid)
                assert connection.get_by_label('Protokoll',exact=True).input_value()=='FTP mit explizitem TLS'
                assert connection.get_by_role('button',name='Server (Ingest) kopieren').count()==1
                assert form.locator('[name=password]').get_attribute('required') is None
                page.goto(address+'/#administration');page.goto(address+'/#administration-ftp');until(lambda:form.locator('[name=user_id]').input_value()==str(uid));until(lambda:connection.get_by_label('FTP-Benutzername',exact=True).input_value()==username)
                save(False);assert 'gesperrt' in page.locator('#admin-ftp-status').inner_text()
                page.reload();form=page.locator('#admin-ftp-form');form.locator('[name=user_id]').select_option(str(uid));page.wait_for_function("() => document.querySelector('#admin-ftp-status').textContent.includes('ftpviewer')")
                assert not form.locator('[name=enabled]').is_checked();save(True)
                if args.screenshots_dir:args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(args.screenshots_dir/('ftp-verwaltung-'+core.APP_VERSION+'.png')),full_page=True)
                login(user,'ftpviewer','FTP-UI-User-Fixture-123');user.goto(address+'/#account');user.wait_for_function("() => document.querySelector('#ftp-account-status').textContent.includes('freigegeben')")
                own=user.locator('#ftp-settings');assert own.get_by_label('Server (Ingest)',exact=True).input_value()=='ingest.example.test';assert own.get_by_label('FTP-Benutzername',exact=True).input_value()==username
                assert own.locator('xpath=ancestor::*[@data-view="account"]').count()==1
                assert own.get_by_label('Medienbibliothek',exact=True).input_value().startswith('/Bibliothek')
                assert own.locator('details[open]').count()==1;assert 'passiven Modus' in own.inner_text();assert own.get_by_label('Protokoll',exact=True).input_value()=='FTP mit explizitem TLS'
                assert user.locator('#admin-ftp-form').count()==0;assert user.request.get(address+'/api/admin/users/'+str(uid)+'/ftp').status==403
                assert 'FTP-UI-Created-Password-123' not in user.content()
                if args.screenshots_dir:user.screenshot(path=str(args.screenshots_dir/('ftp-verbindung-'+core.APP_VERSION+'.png')),full_page=True)
                home=core.DATA/'ftp'/str(uid);large=home/'UI 6 GiB.mp4'
                with large.open('wb') as stream:stream.truncate(6*1024**3)
                ident='ui-large-ftp-fixture'
                core.write("INSERT INTO ftp_imports(id,user_id,path,size,state,message,created) VALUES (?,?,?,?,'error','Frühere Größenbegrenzung.',?)",(ident,uid,str(large),large.stat().st_size,time.time()))
                user.goto(address+'/#media');imports=user.locator('#media-ftp-import-list');entry=imports.locator('[data-ftp-import="'+ident+'"]')
                entry.wait_for();assert '6.0 GB' in entry.inner_text();assert user.locator('#media-ftp-imports').get_attribute('open') is not None
                with user.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/ftp/imports/'+ident+'/retry')) as retry:
                    entry.get_by_role('button',name='Erneut importieren',exact=True).click()
                assert retry.value.status==200;user.wait_for_function('() => !busy');assert core.rows('SELECT state FROM ftp_imports WHERE id=?',(ident,))[0]['state']=='queued'
                private=core.DATA/'uploads'/('ftp-'+'a'*32+'.mp4');private.parent.mkdir(exist_ok=True);private.write_bytes(b'retained-source')
                discarded='ui-discard-ftp-fixture';core.write("INSERT INTO ftp_imports(id,user_id,path,size,state,message,staging,created) VALUES (?,?,?,15,'error','Umwandlung fehlgeschlagen.',?,?)",(discarded,uid,str(home/'Zurückbehalten.mp4'),str(private),time.time()))
                job='ui-progress-ftp-fixture';owner=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
                core.UPLOADS.register(owner,job,'Fortschritt.mp4',100,'ftp',None);core.UPLOADS.update(job,uid,'processing',42,'Video wird umgewandelt.')
                core.write("INSERT INTO ftp_imports(id,user_id,path,size,state,message,upload_id,created) VALUES (?,?,?,100,'processing','Video wird umgewandelt.',?,?)",(job,uid,str(home/'Fortschritt.mp4'),job,time.time()))
                user.goto(address+'/#account');user.goto(address+'/#media')
                progress=imports.locator('[data-ftp-import="'+job+'"] progress');until(lambda:progress.count()==1);assert progress.get_attribute('value')=='42'
                user.on('dialog',lambda dialog:dialog.accept())
                with user.expect_response(lambda response:response.request.method=='DELETE' and response.url.endswith('/api/ftp/imports/'+discarded+'/source')) as deletion:
                    imports.locator('[data-ftp-import="'+discarded+'"]').get_by_role('button',name='Quelldatei löschen',exact=True).click()
                assert deletion.value.status==200;user.wait_for_function('() => !busy');assert not private.exists()
                folder=core.write('INSERT INTO playlist_folders(user_id,name) VALUES (?,?)',(uid,'Sendearchiv'))
                nested=core.write('INSERT INTO playlist_folders(user_id,name,parent_id) VALUES (?,?,?)',(uid,'Abendprogramm',folder))
                import json
                videos=[]
                for index,name in enumerate(('Highlights','Interview','Rückblick')):
                    path=core.DATA/'media'/'ftpviewer'/('ui-'+str(index)+'.mp4');path.write_bytes(b'ui-fixture')
                    videos.append(core.write('INSERT INTO videos(user_id,name,path,duration,size,created,folder_id) VALUES (?,?,?,?,?,?,?)',(uid,name,str(path),120,10,int(time.time()),nested)))
                core.write('INSERT INTO playlists(user_id,name,folder_id,items) VALUES (?,?,?,?)',(uid,'Wiederholung am Abend',nested,json.dumps(videos)))
                core.write('INSERT INTO playlists(user_id,name,items) VALUES (?,?,?)',(uid,'Highlights',json.dumps(videos[:2])))
                user.goto(address+'/#playlists');user.locator('#playlist-list button').filter(has_text='Wiederholung am Abend').click();user.goto(address+'/#media');user.locator('#playlist-folder-tree button').get_by_text('Abendprogramm',exact=True).click();user.goto(address+'/#playlists');user.locator('#playlist-picker summary').click()
                if args.screenshots_dir:
                    user.evaluate('window.scrollTo(0,0)');user.screenshot(path=str(args.screenshots_dir/('playlists-'+core.APP_VERSION+'.png')),full_page=True)
                    user.goto(address+'/#media');user.evaluate('window.scrollTo(0,0)');user.screenshot(path=str(args.screenshots_dir/('medien-'+core.APP_VERSION+'.png')),full_page=True)
                for tab,hash_ in ((page,'administration-ftp'),(user,'account'),(user,'media')):
                    tab.set_viewport_size({'width':390,'height':844});tab.goto(address+'/#'+hash_);tab.wait_for_timeout(300);assert tab.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert not errors,errors;browser.close()
            print('PASS: FTP account feedback and connection data, media import status for 6-GiB files, retry, retained-source deletion, measured conversion progress, tenant permissions and mobile layout.')
        finally:
            clock.stop()
            if server:server.shutdown()
            if core:
                core.JOBS.shutdown(wait=True)
                for directory,dirs,files in os.walk(core.DATA/'ftp'):Path(directory).chmod(0o700)

if __name__=='__main__':main()

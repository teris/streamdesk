"""Large nested library: global playlist management, pagination and preserved drafts."""
import argparse
import json
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


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screenshots-dir',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='streamdesk-library-ui-',dir='/tmp') as temporary:
        base=Path(temporary);config=base/'media.yml';config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{}}));clip=base/'fixture.mp4';clip.write_bytes(b'library-fixture')
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):uid=core.add_user('library','Library-Fixture-Password-123')
        user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
        root=core.write('INSERT INTO playlist_folders(user_id,name) VALUES (?,?)',(uid,'Sendearchiv'))
        nested=core.write('INSERT INTO playlist_folders(user_id,name,parent_id) VALUES (?,?,?)',(uid,'Sommer',root))
        for number in range(98):core.write('INSERT INTO playlist_folders(user_id,name,parent_id) VALUES (?,?,?)',(uid,'Ordner '+str(number),root))
        for number in range(601):(Path(user['offline']).parent/f'fixture-{number}.mp4').write_bytes(clip.read_bytes())
        with core.db() as db:
            db.executemany('INSERT INTO videos(user_id,name,path,duration,size,created) VALUES (?,?,?,?,?,?)',[(uid,f'Video {number:03d}',str(Path(user['offline']).parent/f'fixture-{number}.mp4'),10,15,int(time.time())) for number in range(600)])
        nested_video=core.write('INSERT INTO videos(user_id,name,path,duration,size,created,folder_id) VALUES (?,?,?,?,?,?,?)',(uid,'Sommerfilm',str(Path(user['offline']).parent/'fixture-600.mp4'),10,15,int(time.time()),nested))
        playlist=core.write('INSERT INTO playlists(user_id,name,folder_id,items) VALUES (?,?,?,?)',(uid,'Vorhandene Playlist',nested,json.dumps([nested_video])))
        # Enough playlists to catch repeated per-video JSON parsing in status/library requests.
        with core.db() as db:db.executemany('INSERT INTO playlists(user_id,name,folder_id,items) VALUES (?,?,?,?)',[(uid,'Archivliste '+str(number),nested,json.dumps([nested_video]*200)) for number in range(49)])
        clock=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));clock.start()
        server=make_server('127.0.0.1',0,core.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start();address='http://127.0.0.1:'+str(server.server_port)
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.on('dialog',lambda dialog:dialog.accept())
                page.goto(address+'/login');page.locator('[name=username]').fill('library');page.locator('[name=password]').fill('Library-Fixture-Password-123');page.locator('button[type=submit]').click();page.wait_for_url(address+'/');page.goto(address+'/#media')
                page.wait_for_function("() => document.querySelector('#playlist-library-status').textContent.includes('100 Ordner')")
                assert page.locator('#playlist-videos').is_visible();assert not page.locator('#playlist-list').is_visible()
                assert page.locator('#playlist-videos .playlist-media-row').count()==50
                page.goto(address+'/#playlists');assert not page.locator('#playlist-videos').is_visible();assert page.locator('#playlist-list').is_visible()
                assert page.locator('#playlist-list button').count()==50
                page.locator('#playlist-list button').filter(has_text='Vorhandene Playlist').click();page.wait_for_selector('#playlist-editor:not([hidden])')
                page.locator('#playlist-edit [name=name]').fill('Entwurf bleibt erhalten')
                page.goto(address+'/#media');start=time.monotonic();page.locator('#playlist-folder-tree button').get_by_text('Sommer',exact=True).click();page.wait_for_function("() => document.querySelector('#playlist-folder-path').textContent==='Sendearchiv / Sommer'")
                elapsed=time.monotonic()-start;assert elapsed<2,elapsed
                assert page.locator('#playlist-videos .playlist-media-row').count()==1
                page.goto(address+'/#playlists');assert page.locator('#playlist-edit [name=name]').input_value()=='Entwurf bleibt erhalten'
                page.locator('#playlist-picker summary').click();page.locator('#playlist-pick-search').fill('Video 00')
                assert page.locator('#playlist-video-picker input').count()==10
                page.locator('#playlist-video-picker input').nth(0).check();page.locator('#playlist-video-picker input').nth(1).check();page.locator('#playlist-add-item').click()
                assert page.locator('#playlist-items li').count()==3
                page.locator('#playlist-edit button.primary').click();page.wait_for_function("() => document.querySelector('#playlist-edit .form-feedback')?.textContent==='Playlist gespeichert.'")
                page.wait_for_function('() => !busy');assert core.rows('SELECT name FROM playlists WHERE id=?',(playlist,))[0]['name']=='Entwurf bleibt erhalten'
                assert len(json.loads(core.rows('SELECT items FROM playlists WHERE id=?',(playlist,))[0]['items']))==3
                page.reload();page.wait_for_function("() => document.querySelector('#playlist-list').textContent.includes('Entwurf bleibt erhalten')")
                page.locator('#playlist-list button').filter(has_text='Entwurf bleibt erhalten').click();page.locator('#playlist-delete').click();page.wait_for_function("() => !document.querySelector('#playlist-list').textContent.includes('Entwurf bleibt erhalten')");page.wait_for_function('() => !busy')
                assert not core.rows('SELECT id FROM playlists WHERE id=?',(playlist,));assert core.rows('SELECT id FROM videos WHERE id=?',(nested_video,))
                page.goto(address+'/#media');page.locator('#playlist-video-pages').get_by_text('Weiter →',exact=True).click();assert 'Seite 2 / 13' in page.locator('#playlist-video-pages').inner_text();assert page.locator('#playlist-videos .playlist-media-row').count()==50
                for view in ('media','playlists'):
                    page.set_viewport_size({'width':390,'height':844});page.goto(address+'/#'+view);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert not errors,errors;browser.close()
            print(f'PASS: 100 folders, 602 videos, 50 playlists; nested folder opens in {elapsed:.2f}s, separate media/playlist views, checkbox picker, existing playlists editable/deletable, drafts survive view/folder changes, 50-row pagination and mobile layout.')
        finally:clock.stop();server.shutdown();core.JOBS.shutdown(wait=True)

if __name__=='__main__':main()

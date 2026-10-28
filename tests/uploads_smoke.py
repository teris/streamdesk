"""Real multi-file upload and FFmpeg progress, rename and confirmed deletion in Chromium.
Temporary media and database only; no external account or media server is contacted.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',required=True,type=Path);parser.add_argument('--ffprobe',required=True,type=Path)
    parser.add_argument('--screenshots-dir',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='streamdesk-uploads-') as temporary:
        base=Path(temporary);(base/'bin').mkdir()
        for key in ('ffmpeg','ffprobe'):(base/'bin'/key).symlink_to(getattr(args,key).resolve())
        config=base/'media.yml';config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{}}))
        fixture=base/'sample.mp4'
        subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','testsrc2=s=960x540:r=30','-t','12','-c:v','libx264','-preset','ultrafast','-crf','16','-pix_fmt','yuv420p','-threads','1','-movflags','+faststart',str(fixture)],capture_output=True,check=True)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),MEDIAMTX_CONFIG=str(config),STREAMDESK_DEFAULT_CLIP=str(fixture),COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):
            uid=core.add_user('uploadstudio','Uploads-Smoke-Password-123')
        server=make_server('127.0.0.1',0,core.app,threaded=True);address='http://localhost:'+str(server.server_port);core.PUBLIC=address
        threading.Thread(target=server.serve_forever,daemon=True).start()
        changes=[];original=core.UPLOADS.update
        def track(*args,**kwargs):
            if len(args)>3 and args[2]=='processing':changes.append(float(args[3]))
            return original(*args,**kwargs)
        try:
            with patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time())),patch.object(core.UPLOADS,'update',side_effect=track),sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000},locale='de-DE')
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(address+'/login');page.fill('[name=username]','uploadstudio');page.fill('[name=password]','Uploads-Smoke-Password-123');page.click('form button[type=submit]');page.wait_for_url(address+'/')
                csrf=page.locator('meta[name=csrf-token]').get_attribute('content');headers={'X-CSRF-Token':csrf}
                page.goto(address+'/#playlists');page.wait_for_selector('#playlist-folder-form')
                page.fill('#playlist-folder-form [name=name]','Upload-Ordner');page.click('#playlist-folder-form button');page.wait_for_function('() => !busy')
                folder=core.rows('SELECT id FROM playlist_folders WHERE user_id=?',(uid,))[0]['id']
                assert page.locator('#playlist-upload [name=video]').get_attribute('multiple') is not None
                cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':5,'downloadThroughput':10*1024*1024,'uploadThroughput':2*1024*1024})
                payload=fixture.read_bytes()
                page.set_input_files('#playlist-upload [name=video]',[{'name':'Erster Film.mp4','mimeType':'video/mp4','buffer':payload},{'name':'Defekte Datei.mp4','mimeType':'video/mp4','buffer':b'not-a-video'},{'name':'Zweiter Film.mp4','mimeType':'video/mp4','buffer':payload}])
                page.click('#playlist-upload button')
                page.wait_for_function("() => {const p=document.querySelector('[data-view=playlists] .upload-item progress');return p&&p.value>0&&p.value<100}",timeout=30000)
                page.wait_for_function("() => {const row=document.querySelector('[data-view=playlists] .upload-item[data-state=processing]');const p=row?.querySelectorAll('progress')[1];return p&&p.value>0&&p.value<100}",timeout=60000)
                if args.screenshots_dir:
                    args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.evaluate('document.activeElement.blur();window.scrollTo(0,0)')
                    page.locator('#playlist-upload').locator('xpath=..').screenshot(path=str(args.screenshots_dir/'upload-progress.png'),style='#toast{visibility:hidden!important}')
                # Moving between menu views must keep pending browser files and the transfer alive.
                page.click('.menu-link[href="#videos"]');page.locator('.upload-drawer>summary').click()
                assert page.locator('[data-view=videos] .upload-item').count()==3
                assert page.locator('#upload-form [name=video]').get_attribute('multiple') is not None
                page.click('.menu-link[href="#playlists"]')
                page.wait_for_function("() => document.querySelectorAll('[data-view=playlists] .upload-item[data-state=ready]').length===2&&document.querySelectorAll('[data-view=playlists] .upload-item[data-state=error]').length===1",timeout=180000)
                assert any(0<value<99 for value in changes),changes
                converted=core.rows('SELECT * FROM videos WHERE user_id=? AND folder_id=? ORDER BY id',(uid,folder))
                assert len(converted)==2
                for video in converted:
                    assert Path(video['path']).is_file() and video['duration']>11
                    probe=subprocess.run([str(args.ffprobe),'-v','error','-show_streams','-of','json',video['path']],capture_output=True,text=True,check=True)
                    assert '"codec_type": "audio"' in probe.stdout
                assert len(core.rows("SELECT id FROM video_uploads WHERE user_id=? AND state='error'",(uid,)))==1
                first=converted[0];row=page.locator('#playlist-videos .playlist-media-row').filter(has_text=first['name'])
                row.get_by_role('button',name='Umbenennen',exact=True).click();row.locator('.media-rename-form input').fill('Mein umbenannter Film.mp4');row.get_by_role('button',name='Namen speichern').click();page.wait_for_function('() => !busy')
                page.wait_for_selector('#playlist-videos .playlist-media-row',state='visible')
                assert core.rows('SELECT name,path FROM videos WHERE id=?',(first['id'],))[0]=={'name':'Mein umbenannter Film.mp4','path':first['path']}
                result=page.request.post(address+'/api/playlists',headers=headers,data={'name':'Upload-Auswahl','items':[video['id'] for video in converted],'folder_id':folder});assert result.status==200;playlist=result.json()['id']
                page.goto(address+'/#playlists');page.wait_for_selector('#playlist-folder-tree');page.locator('#playlist-folder-tree').get_by_role('button',name='Upload-Ordner',exact=True).click()
                row=page.locator('#playlist-videos .playlist-media-row').filter(has_text='Mein umbenannter Film.mp4')
                page.once('dialog',lambda dialog:dialog.accept())
                with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/videos/'+str(first['id'])+'/delete')) as deletion:
                    row.get_by_role('button',name='Löschen',exact=True).click()
                assert deletion.value.status==200
                page.wait_for_function('() => !busy')
                assert not Path(first['path']).exists()
                import json
                assert json.loads(core.rows('SELECT items FROM playlists WHERE id=?',(playlist,))[0]['items'])==[converted[1]['id']]
                # Renaming is also available in the original offline-video library.
                page.goto(address+'/#videos');page.wait_for_selector('[data-video-id="'+str(converted[1]['id'])+'"]')
                card=page.locator('[data-video-id="'+str(converted[1]['id'])+'"]');card.get_by_role('button',name='Umbenennen',exact=True).click();card.locator('.media-rename-form input').fill('Zweiter Name.mp4');card.get_by_role('button',name='Namen speichern').click();page.wait_for_function('() => !busy')
                assert core.rows('SELECT name FROM videos WHERE id=?',(converted[1]['id'],))[0]['name']=='Zweiter Name.mp4'
                selected=core.rows('SELECT selected_video_id FROM users WHERE id=?',(uid,))[0]['selected_video_id']
                selected_card=page.locator('[data-video-id="'+str(selected)+'"]');assert selected_card.get_by_role('button',name='Löschen',exact=True).is_disabled();assert 'Aktuelles Offline-Video' in selected_card.inner_text()
                page.set_viewport_size({'width':390,'height':844})
                for view in ('videos','playlists'):
                    page.goto(address+'/#'+view);page.wait_for_selector('[data-view="'+view+'"]:visible');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),view
                assert not errors,errors
                browser.close();print('PASS: multi-file upload, measured network/conversion progress, queue across views, failed-file continuation, real H264/AAC conversion, rename in both libraries, confirmed reference-safe deletion, protected selected video and mobile layout.')
        finally:
            core.JOBS.shutdown(wait=True);server.shutdown()


if __name__=='__main__':main()

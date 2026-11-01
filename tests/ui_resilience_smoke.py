"""Browser regression for delayed bootstrap, stalled reads and coalesced UI refreshes."""
import argparse
import os
from pathlib import Path
import re
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
    parser.add_argument('--browser',choices=('chromium','firefox'),default='chromium')
    parser.add_argument('--baseline-ref',help='Serve an older Git revision to reproduce its original failure (diagnostic only).')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='streamdesk-ui-resilience-',dir='/tmp') as temporary:
        base=Path(temporary);config=base/'media.yml';clip=base/'clip.mp4'
        config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{}}));clip.write_bytes(b'fixture')
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),MEDIAMTX_CONFIG=str(config),STREAMDESK_DEFAULT_CLIP=str(clip),STREAMDESK_FTP_ENABLED='1',COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0')
        sys.path.insert(0,str(root));import app as core
        with patch.object(core.threading,'Thread'):uid=core.add_user('resilience','UI-Resilience-Fixture-123',admin=True)
        client=core.app.test_client()
        with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='resilience')
        headers={'X-CSRF-Token':'resilience'}
        assert client.post('/api/admin/users/'+str(uid)+'/ftp',json={'enabled':True,'password':'FTP-Resilience-Fixture-123'},headers=headers).status_code==200
        server=make_server('127.0.0.1',0,core.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
        address='http://127.0.0.1:'+str(server.server_port)
        signer=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));signer.start()
        try:
            with sync_playwright() as p:
                browser=getattr(p,args.browser).launch(headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000})
                # Re-sign after freezing the test clock.
                with client.session_transaction() as session:session['uid']=uid
                context.add_cookies([{'name':core.app.config['SESSION_COOKIE_NAME'],'value':client.get_cookie(core.app.config['SESSION_COOKIE_NAME']).value,'url':address}])
                page=context.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
                def wait_for(predicate):
                    deadline=time.monotonic()+12
                    while not predicate():
                        if time.monotonic()>deadline:raise AssertionError('Expected browser request did not arrive.')
                        page.wait_for_timeout(20)
                if args.baseline_ref:
                    def old_frontend(route):
                        path=route.request.url.split('/static/',1)[1].split('?',1)[0]
                        body=subprocess.check_output(['git','show',args.baseline_ref+':static/'+path],cwd=root)
                        route.fulfill(status=200,content_type='application/javascript',body=body)
                    page.route('**/static/*.js?*',old_frontend)
                    def old_document(route):
                        response=route.fetch();body=response.text()
                        service=re.search(r'\s*<script src="/static/services\.js[^>]+></script>',body)[0]
                        body=body.replace(service,'');body=body.replace('    <script src="/static/app.js',service+'\n    <script src="/static/app.js')
                        route.fulfill(response=response,body=body)
                    page.route(address+'/',old_document)
                held=[]
                page.route('**/static/services.js?*',lambda route:held.append(route))
                page.goto(address+'/',wait_until='commit')
                page.wait_for_function("() => !!document.querySelector('a[href=\"#planner\"]')")
                page.wait_for_timeout(300)
                for view in ('planner','media','account'):
                    page.locator('a.menu-link[href="#'+view+'"]').click();page.wait_for_timeout(70)
                wait_for(lambda:bool(held))
                held.pop().continue_();page.wait_for_load_state('domcontentloaded')
                page.wait_for_function("() => !!window.StreamDeskServices && typeof api==='function'")
                assert not errors,('delayed bootstrap',errors)
                page.unroute('**/static/services.js?*')
                if args.baseline_ref:raise AssertionError('Expected the committed frontend to reproduce the reported error.')

                held_app=[];page.route('**/static/app.js?*',lambda route:held_app.append(route))
                page.goto(address+'/?fixture=app-delay',wait_until='commit')
                page.wait_for_function("() => !!document.querySelector('a[href=\"#planner\"]')")
                page.wait_for_timeout(150)
                for view in ('planner','media','account','administration-services','planner'):
                    page.evaluate('(view) => location.hash=view',view);page.wait_for_timeout(50)
                wait_for(lambda:bool(held_app));held_app.pop().continue_()
                page.wait_for_load_state('domcontentloaded')
                page.wait_for_function("() => document.querySelector('#planner-twitch-status').textContent.includes('Twitch')")
                page.unroute('**/static/app.js?*');assert not errors,('delayed core script',errors)

                # All simultaneous reads share one request instead of queueing a
                # new request for every status or hashchange event.
                media=[]
                def hold_media(route):media.append((route,route.fetch()))
                page.route('**/api/playlists',hold_media)
                page.goto(address+'/#media');page.wait_for_function("() => location.hash==='#media'")
                wait_for(lambda:bool(media))
                page.evaluate("""() => {for(let i=0;i<20;i++)window.dispatchEvent(new CustomEvent('streamdesk:status',{detail:{...state,offline_video:{id:1000+i}}}));} """)
                page.wait_for_timeout(100);assert len(media)==1,len(media)
                route,response=media[0];route.fulfill(response=response)
                page.wait_for_timeout(500);assert len(media)==1,('queued background reads',len(media))

                # An actual edit during an old GET still needs a fresh read;
                # coalescing must not lose the new folder.
                page.goto(address+'/#playlists');page.goto(address+'/#media')
                wait_for(lambda:len(media)>=2)
                page.locator('#playlist-folder-form [name=name]').fill('Während der Abfrage angelegt')
                with page.expect_response(lambda response:response.url.endswith('/api/playlist-folders') and response.request.method=='POST'):
                    page.locator('#playlist-folder-form button').click()
                route,response=media[1];route.fulfill(response=response)
                wait_for(lambda:len(media)>=3)
                route,response=media[2];route.fulfill(response=response)
                page.wait_for_function("() => !busy && document.querySelector('#playlist-folder-tree').textContent.includes('Während der Abfrage angelegt')")
                page.wait_for_timeout(200);assert len(media)==3,len(media)
                page.unroute('**/api/playlists')

                ftp=[]
                page.route('**/api/ftp',lambda route:ftp.append((route,route.fetch())))
                for view in ('account','media','account','media','account'):
                    page.evaluate('(view) => location.hash=view',view);page.wait_for_timeout(40)
                assert len(ftp)==1,('overlapping FTP reads',len(ftp))
                route,response=ftp[0];route.fulfill(response=response)
                page.wait_for_function("() => document.querySelector('#ftp-account-status').textContent.includes('freigegeben')")
                page.evaluate("() => window.preservedConnection=document.querySelector('#ftp-connection input')")
                page.goto(address+'/#media');page.goto(address+'/#account')
                wait_for(lambda:len(ftp)>=2)
                route,response=ftp[1];route.fulfill(response=response)
                page.wait_for_timeout(200)
                assert page.evaluate("() => window.preservedConnection===document.querySelector('#ftp-connection input')")
                page.unroute('**/api/ftp')

                # A malformed policy must never throw or implicitly enable a
                # service. A valid status restores it without a page reload.
                statuses=[]
                page.route('**/api/status',lambda route:statuses.append((route,route.fetch())))
                def malformed(route):
                    response=route.fetch();body=re.sub(r'(<meta name="streamdesk-services" content=")[^"]*',r'\1{broken',response.text())
                    route.fulfill(response=response,body=body)
                bad_url=address+'/?fixture=malformed';page.route(bad_url,malformed)
                page.goto(bad_url+'#planner')
                assert page.evaluate("() => !StreamDeskServices.allowed('playlists') && !StreamDeskServices.allowed('unknown')")
                wait_for(lambda:bool(statuses))
                route,response=statuses[0];route.fulfill(response=response)
                page.wait_for_function("() => StreamDeskServices.allowed('playlists') && document.querySelector('#planner-twitch-status').textContent.includes('Twitch')")
                page.unroute('**/api/status');page.unroute(bad_url)

                # Emulate a suspended tab. Its library/FTP handlers do no work;
                # the shared status fetch still cannot overlap itself.
                page.goto(address+'/#media');page.wait_for_timeout(150)
                requests=[];page.on('request',lambda request:requests.append(request.url))
                page.evaluate("""() => {Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});for(let i=0;i<30;i++)window.dispatchEvent(new CustomEvent('streamdesk:status',{detail:{...state,offline_video:{id:2000+i}}}));} """)
                page.wait_for_timeout(200)
                assert not any(url.endswith(('/api/ftp','/api/playlists')) for url in requests),requests
                page.evaluate("() => {delete document.hidden;}")

                statuses=[];page.route('**/api/status',lambda route:statuses.append((route,route.fetch())))
                page.evaluate("() => {for(let i=0;i<20;i++)void refresh();}")
                wait_for(lambda:bool(statuses));page.wait_for_timeout(100);assert len(statuses)==1,len(statuses)
                page.evaluate("() => {void refresh(true);void refresh(true);}")
                route,response=statuses[0];route.fulfill(response=response)
                wait_for(lambda:len(statuses)>=2)
                route,response=statuses[1];route.fulfill(response=response)
                page.wait_for_timeout(100);assert len(statuses)==2,len(statuses)
                page.unroute('**/api/status')

                # Reading errors have a deadline; a timeout does not affect
                # POST uploads, which deliberately retain no total deadline.
                pending=[];page.route('**/api/ui-stalled-fixture',lambda route:pending.append(route))
                result=page.evaluate("""async () => {const original=window.setTimeout;window.setTimeout=(fn,ms,...args)=>original(fn,ms===15000?100:ms,...args);try{await api('/api/ui-stalled-fixture');return 'unexpected';}catch(error){return error.message;}finally{window.setTimeout=original;}}""")
                assert 'nicht rechtzeitig' in result,result
                for route in pending:route.abort()

                # A blocked script gives a visible recovery instruction, not
                # an exception cascade or implicitly enabled services.
                page.route('**/static/services.js?*',lambda route:route.abort())
                page.goto(address+'/?fixture=blocked#planner')
                page.wait_for_function("() => document.querySelector('#alert').textContent.includes('nicht vollständig geladen')")
                for view in ('media','account','planner'):
                    page.locator('a.menu-link[href="#'+view+'"]').click()
                page.wait_for_timeout(100)
                assert not errors,errors
                browser.close()
                print('PASS ('+args.browser+'): delayed or blocked service bootstrap, 20 coalesced media/status refreshes, fresh data after concurrent edit, single FTP read, preserved connection fields, fail-closed malformed policy recovery, suspended-tab reads and stalled-read deadline; no uncaught page errors.')
        finally:signer.stop();server.shutdown();core.JOBS.shutdown(wait=True)


if __name__=='__main__':main()

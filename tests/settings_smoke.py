"""Browser regression for separated provider settings and the expert Discord guide.
All credentials and Discord responses are local fixtures; no external account is contacted.
"""
import argparse
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest.mock import patch

import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots-dir',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='streamdesk-settings-') as temporary:
        base=Path(temporary);config=base/'media.yml'
        config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{}}))
        clip=base/'fixture.mp4';clip.write_bytes(b'settings-fixture')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        address='http://localhost:'+str(port)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),MEDIAMTX_CONFIG=str(config),
                          STREAMDESK_DEFAULT_CLIP=str(clip),STREAMDESK_PUBLIC=address,COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):
            uid=core.add_user('demo','Settings-Fixture-Password-123',admin=True)
        server=make_server('127.0.0.1',port,core.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def discord(token,path,body=None):
            if path.endswith('/messages') or '/messages?' in path:return []
            return {'id':'123456789012345678','type':0,'name':'Teststudio'}
        try:
            # Host clock corrections must not invalidate unrelated UI test sessions.
            with patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(core.time.time())),patch.object(core.CHAT,'discord_api',side_effect=discord) as discord_calls,patch.object(core,'validate_output',side_effect=lambda value:value),sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                context=browser.new_context(viewport={'width':1440,'height':1000})
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(address+'/login');page.fill('[name=username]','demo');page.fill('[name=password]','Settings-Fixture-Password-123')
                page.locator('form button[type=submit]').click();page.wait_for_url(address+'/')
                def view(name):
                    page.goto(address+'/#'+name)
                    page.wait_for_selector('[data-view="'+name+'"]:visible')
                def snapshot(name):
                    if args.screenshots_dir:
                        args.screenshots_dir.mkdir(parents=True,exist_ok=True)
                        page.evaluate('document.activeElement.blur(); window.scrollTo(0,0)')
                        page.screenshot(path=str(args.screenshots_dir/name),full_page=True)
                view('settings');page.wait_for_selector('#target-list .target-item')
                assert page.locator('#target-list .target-item').count()==3
                assert not page.locator('#twitch-output-form').is_visible()
                assert not page.locator('#youtube-output-form').is_visible()
                assert not page.locator('#discord-form').is_visible()
                assert not page.locator('#theme-form').is_visible()
                view('settings-twitch');page.fill('#twitch-output-form [name=key]','fixture-twitch-key-123456')
                page.click('#twitch-output-form button[type=submit]');page.wait_for_function('() => !busy')
                assert core.rows("SELECT endpoint FROM outputs WHERE user_id=? AND kind='twitch'",(uid,))
                assert page.locator('.menu-link[href="#settings"]').get_attribute('aria-current')=='page'
                assert not page.locator('#youtube-output-form').is_visible()
                view('settings-youtube');page.fill('#youtube-output-form [name=key]','fixture-youtube-key-123456')
                page.click('#youtube-output-form button[type=submit]');page.wait_for_function('() => !busy')
                page.locator('.provider-broadcasts summary').click();assert page.locator('#yt-load').is_visible()
                snapshot('settings-youtube-'+core.APP_VERSION+'.png')
                view('settings-custom');page.fill('#custom-output-url','rtmps://fixture.invalid/app#fixture-custom-key')
                page.click('#output-form button[type=submit]');page.wait_for_function('() => !busy')
                view('settings');page.click('[data-target-preset="twitch,youtube"]');page.click('#save-targets')
                page.wait_for_function('() => !busy')
                assert {row['kind'] for row in core.rows('SELECT kind FROM outputs WHERE user_id=? AND selected=1',(uid,))}=={'twitch','youtube'}
                snapshot('settings-overview-'+core.APP_VERSION+'.png')
                view('settings-youtube');page.click('[data-remove-output="youtube"]');page.wait_for_function('() => !busy')
                assert not core.rows("SELECT kind FROM outputs WHERE user_id=? AND kind='youtube'",(uid,))
                assert core.rows("SELECT kind FROM outputs WHERE user_id=? AND kind='twitch'",(uid,))
                page.goto(address+'/#expert-discord');page.wait_for_function("() => location.hash === '#expert'")
                assert not page.locator('#discord-setup-guide').is_visible()
                assert discord_calls.call_count==0
                page.check('#expert-mode');page.click('#expert-form button');page.wait_for_function("() => !busy && document.documentElement.dataset.expert==='true'")
                view('expert-discord');page.wait_for_selector('#discord-setup-guide')
                assert page.locator('#discord-setup-guide .setup-steps>li').count()==5
                assert 'Message Content Intent' in page.locator('#discord-setup-guide').inner_text()
                assert page.locator('#discord-bot-token').get_attribute('autocomplete')=='new-password'
                page.fill('#discord-channel-id','admin');page.fill('#discord-bot-token','Fixture-Discord-Bot-Token-1234567890')
                page.click('#discord-form button[type=submit]')
                assert discord_calls.call_count==0
                page.fill('#discord-channel-id','123456789012345678');page.click('#discord-form button[type=submit]')
                page.wait_for_function("() => !busy && document.querySelector('#discord-connection-state').textContent==='Verbunden'")
                assert page.input_value('#discord-bot-token')==''
                assert 'Teststudio' in page.locator('#discord-connection-description').inner_text()
                snapshot('discord-guide-'+core.APP_VERSION+'.png')
                view('expert');page.uncheck('#expert-mode');page.click('#expert-form button')
                page.wait_for_function("() => !busy && document.documentElement.dataset.expert==='false'")
                view('chat');page.wait_for_selector('[data-view="chat"] .chat-discord-status')
                assert page.request.get(address+'/api/chat').json()['discord_ready']
                view('expert');page.check('#expert-mode');page.click('#expert-form button');page.wait_for_function('() => !busy')
                page.set_viewport_size({'width':390,'height':844})
                for theme in ('dark','light'):
                    view('settings-appearance');page.select_option('#theme',theme);page.click('#theme-form button');page.wait_for_function('() => !busy')
                    for name in ('settings','settings-twitch','settings-youtube','settings-custom','settings-appearance','expert-discord'):
                        view(name)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,name)
                    if theme=='light':
                        view('settings');snapshot('settings-mobile-'+core.APP_VERSION+'.png')
                assert 'v'+core.APP_VERSION in page.locator('footer').inner_text()
                assert not errors,errors
                browser.close();core.CHAT.prune(set())
                print('PASS: isolated provider settings, key save/selection/removal, expert-only Discord setup, five-step guide, existing chat, release version and mobile dark/light views.')
        finally:
            core.CHAT.prune(set());server.shutdown()


if __name__=='__main__':main()

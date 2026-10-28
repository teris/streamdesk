"""Two-browser regression for global admin service policy; no external accounts."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import yaml


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots-dir',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='streamdesk-services-') as temporary:
        base=Path(temporary);config=base/'media.yml';clip=base/'offline.mp4'
        config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{'foreign':{'source':'publisher'}}}))
        clip.write_bytes(b'local-browser-fixture')
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),MEDIAMTX_CONFIG=str(config),
                          STREAMDESK_DEFAULT_CLIP=str(clip),COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):
            admin_id=core.add_user('studioadmin','Services-Fixture-Password-123',admin=True)
            uid=core.add_user('viewer','Services-Fixture-Password-123')
        core.write('INSERT INTO discord_auth(user_id,channel_id,channel_name,bot_token) VALUES (?,?,?,?)',
                   (uid,'123456789012345678','Fixture',core.encrypt('Fixture-Bot-Token-1234567890123456')))
        core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',
                   (uid,'twitch',core.encrypt('rtmps://fixture.invalid/live#Fixture-Key-123')))
        before=core.rows('SELECT * FROM outputs WHERE user_id=?',(uid,))
        server=make_server('127.0.0.1',0,core.app,threaded=True)
        address='http://localhost:'+str(server.server_port);core.PUBLIC=address
        threading.Thread(target=server.serve_forever,daemon=True).start()
        errors=[]
        try:
            # Host clock corrections must not invalidate unrelated UI test sessions.
            with patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(core.time.time())),patch.object(core.CHAT,'discord_api',return_value=[]),sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                def login(name):
                    context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page()
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(address+'/login');page.fill('[name=username]',name);page.fill('[name=password]','Services-Fixture-Password-123')
                    page.click('form button[type=submit]');page.wait_for_url(address+'/');return page
                admin=login('studioadmin');user=login('viewer')
                admin.goto(address+'/#administration-services');admin.wait_for_selector('[data-service-id="discord"]')
                assert admin.locator('.service-card').count()==13
                assert not user.locator('a[href="#administration-services"]').count()
                assert user.request.get(address+'/api/admin/services').status==403
                user.goto(address+'/#expert');user.check('#expert-mode');user.click('#expert-form button');user.wait_for_function('() => !busy')
                def toggle(key,enabled):
                    card=admin.locator('[data-service-id="'+key+'"]')
                    group=card.locator('xpath=ancestor::details');
                    if group.get_attribute('open') is None:group.locator('summary').click()
                    card.locator('button').click();admin.wait_for_function('() => !busy')
                    assert ('Freigegeben' if enabled else 'Gesperrt') in card.inner_text()
                toggle('discord',False)
                user.goto(address+'/#expert-discord');user.wait_for_selector('#service-blocked:visible')
                assert not user.locator('#discord-form').is_visible()
                assert user.request.get(address+'/api/discord').status==403
                assert not user.request.get(address+'/api/chat').json()['discord_ready']
                assert core.rows('SELECT bot_token FROM discord_auth WHERE user_id=?',(uid,))
                toggle('discord',True)
                user.wait_for_selector('#discord-form:visible')
                assert user.request.get(address+'/api/chat').json()['discord_ready']
                toggle('twitch',False)
                user.goto(address+'/#settings-twitch');user.wait_for_selector('#service-blocked:visible')
                user.goto(address+'/#settings');user.wait_for_selector('#target-list .target-item')
                assert user.locator('[data-output-kind="twitch"]').is_disabled()
                assert 'Durch Admin gesperrt' in user.locator('#target-list').inner_text()
                assert core.rows('SELECT * FROM outputs WHERE user_id=?',(uid,))==before
                toggle('automation',False);toggle('notifications',False)
                user.goto(address+'/#expert-automation');user.wait_for_selector('#service-blocked:visible')
                toggle('notifications',True)
                user.wait_for_selector('#notification-form:visible')
                assert not user.locator('#automation-job-form').is_visible()
                admin.set_viewport_size({'width':390,'height':844})
                assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth')
                user.set_viewport_size({'width':390,'height':844})
                assert user.evaluate('document.documentElement.scrollWidth<=innerWidth')
                if args.screenshots_dir:
                    args.screenshots_dir.mkdir(parents=True,exist_ok=True)
                    admin.set_viewport_size({'width':1440,'height':1000})
                    admin.evaluate('document.activeElement.blur(); window.scrollTo(0,0)')
                    admin.screenshot(path=str(args.screenshots_dir/f'admin-services-{core.APP_VERSION}.png'),full_page=True)
                assert not errors,errors
                browser.close()
                print('PASS: admin-only service page, independent user session, live disable/re-enable, retained credentials, blocked APIs and mobile layout.')
        finally:
            core.CHAT.prune(set());server.shutdown()


if __name__=='__main__':main()

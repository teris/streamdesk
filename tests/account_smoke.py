"""Local browser regression for real WebAuthn, scenes and editable automation forms.
Uses only temporary data and a Chromium virtual authenticator; no external services.
"""
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
import yaml


def main():
    with tempfile.TemporaryDirectory(prefix='streamdesk-account-') as temporary:
        base=Path(temporary)
        config=base/'media.yml';config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[], 'paths':{}}))
        clip=base/'offline.mp4';clip.write_bytes(b'account-fixture')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        address='http://localhost:'+str(port)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),MEDIAMTX_CONFIG=str(config),
                          STREAMDESK_DEFAULT_CLIP=str(clip),STREAMDESK_PUBLIC=address,COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0')
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):
            uid=core.add_user('alice','Account-Fixture-Password-123',admin=True)
        # No output is started; this credential is a non-routable fixture only.
        core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,0)',
                   (uid,'twitch',core.encrypt('rtmps://fixture.invalid/live#fixture-key')))
        server=make_server('127.0.0.1',port,core.app,threaded=True)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                context=browser.new_context();page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                cdp=context.new_cdp_session(page);cdp.send('WebAuthn.enable')
                cdp.send('WebAuthn.addVirtualAuthenticator',{'options':{'protocol':'ctap2','transport':'usb',
                         'hasResidentKey':True,'hasUserVerification':True,'isUserVerified':True,'automaticPresenceSimulation':True}})
                page.goto(address+'/login');page.fill('[name=username]','alice');page.fill('[name=password]','Account-Fixture-Password-123')
                page.locator('form button[type=submit]').click();page.wait_for_url(address+'/')
                page.goto(address+'/#account');page.wait_for_selector('#passkey-add');page.click('#passkey-add')
                page.wait_for_selector('#recovery-codes:not([hidden])')
                assert len(core.rows('SELECT id FROM webauthn_credentials WHERE user_id=?',(uid,)))==1
                page.click('#logout');page.wait_for_url('**/login')
                page.fill('[name=username]','alice');page.click('#passkey-login');page.wait_for_url(address+'/')
                page.goto(address+'/#account');page.wait_for_selector('#passkey-list .user-row')
                page.goto(address+'/#expert');page.check('#expert-mode');page.click('#expert-form button')
                page.wait_for_function("() => !busy && document.documentElement.dataset.expert === 'true'")
                page.goto(address+'/#expert-routing')
                page.wait_for_selector('#scene-form',timeout=5000)
                page.fill('#scene-form [name=name]','Browser scene');page.fill('#scene-form [name=targets]','twitch')
                page.click('#scene-form button');page.wait_for_selector('#scene-list .user-row')
                page.wait_for_function("() => document.querySelector('#scene-form [name=name]').value === ''")
                page.goto(address+'/#expert-automation');page.wait_for_selector('#automation-export-url')
                page.wait_for_timeout(1000)
                page.fill('#automation-export-url','https://unsaved.example/')
                page.wait_for_timeout(5000)
                assert page.input_value('#automation-export-url')=='https://unsaved.example/'
                page.goto(address+'/#account');page.wait_for_selector('#passkey-list .user-row')
                page.click('#passkey-list button')
                page.wait_for_function("() => document.querySelector('#passkey-list').textContent.includes('Noch kein Passkey')")
                assert not core.rows('SELECT id FROM webauthn_credentials WHERE user_id=?',(uid,))
                assert not errors,errors
                browser.close()
                print('PASS: browser passkey registration/login with verified virtual authenticator; scenes save/reset; automation polling preserves edits.')
        finally:
            server.shutdown()


if __name__=='__main__':main()

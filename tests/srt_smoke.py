"""Local authenticated SRT publishing and source switching, without public streams.

python tests/srt_smoke.py --mediamtx /path/to/mediamtx --ffmpeg /path/to/ffmpeg
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import yaml


def port(udp=False):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediamtx', required=True, type=Path)
    parser.add_argument('--ffmpeg', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='streamdesk-srt-smoke-') as temporary:
        base = Path(temporary)
        (base / 'bin').mkdir()
        (base / 'bin' / 'ffmpeg').symlink_to(args.ffmpeg.resolve())
        api, rtsp, hls, srt = port(), port(), port(), port(True)
        config = base / 'mediamtx.yml'
        config.write_text(yaml.safe_dump({'api': True, 'apiAddress': f'127.0.0.1:{api}',
            'rtsp': True, 'rtspAddress': f'127.0.0.1:{rtsp}', 'rtspTransports': ['tcp'],
            'rtmp': False, 'srt': True, 'srtAddress': f'127.0.0.1:{srt}',
            'hls': True, 'hlsAddress': f'127.0.0.1:{hls}', 'hlsVariant': 'mpegts',
            'webrtc': False, 'moq': False, 'authInternalUsers': [], 'paths': {}}))
        clip = base / 'standby.mp4'
        subprocess.run([str(args.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=640x360:r=15',
            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', '1', '-c:v', 'libx264', '-threads', '1',
            '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(clip)], check=True)
        os.environ.update(STREAMDESK_ENGINE='0', STREAMDESK_DATA=str(base / 'data'),
            STREAMDESK_DEFAULT_CLIP=str(clip), STREAMDESK_INGEST='127.0.0.1', MEDIAMTX_CONFIG=str(config),
            MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/', MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',
            MEDIAMTX_HLS=f'http://127.0.0.1:{hls}/', MEDIAMTX_SRT_PORT=str(srt),
            COOKIE_SECURE='0', PATH=str(base / 'bin') + os.pathsep + os.environ['PATH'])
        sys.path.insert(0, str(root))
        import app as core
        with patch.object(core.threading, 'Thread'):
            uid = core.add_user('alice', 'SRT-Fixture-Password-12345')
        user = core.rows('SELECT * FROM users WHERE id=?', (uid,))[0]
        cfg = yaml.safe_load(config.read_text())
        for entry in cfg['authInternalUsers']:
            if entry['user'] == 'any':
                # Loopback is not allowed to anonymously publish to the SRT input.
                entry['permissions'] = [permission for permission in entry['permissions'] if permission['action'] != 'publish']
                entry['permissions'].append({'action': 'publish', 'path': user['prefix'] + 'live'})
        core.atomic(config, yaml.safe_dump(cfg))
        client = core.app.test_client()
        with client.session_transaction() as session:
            session.update(uid=uid, version=1, csrf='srt-fixture')
        url = client.get('/api/ingest').json['srt']
        processes = []
        with (base / 'media.log').open('wb') as media_log, (base / 'sender.log').open('wb') as sender_log:
            try:
                processes.append(subprocess.Popen([str(args.mediamtx.resolve()), str(config)], stdout=media_log, stderr=subprocess.STDOUT))
                for _ in range(50):
                    try:
                        core.mtx('config/global/get')
                        break
                    except core.Error:
                        time.sleep(.1)
                sender = subprocess.Popen([str(args.ffmpeg.resolve()), '-v', 'error', '-nostdin', '-re', '-f', 'lavfi',
                    '-i', 'testsrc=size=640x360:rate=15', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                    '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', '-tune', 'zerolatency', '-pix_fmt', 'yuv420p',
                    '-g', '15', '-c:a', 'aac', '-f', 'mpegts', url], stdout=subprocess.DEVNULL, stderr=sender_log)
                processes.append(sender)
                core.ENGINE.thread = threading.Thread(target=core.ENGINE.run, daemon=True)
                core.ENGINE.thread.start()
                observed = False
                started = time.monotonic()
                while time.monotonic() - started < 25:
                    if sender.poll() is not None:
                        raise AssertionError('SRT sender exited unexpectedly')
                    observed |= core.ENGINE.snapshot.get(uid, {}).get('selected') == 2
                    time.sleep(.25)
                assert observed, 'SRT did not become the selected live source'
                assert core.mtx('paths/get/' + user['prefix'] + 'source2')['online']
                response = client.get('/preview/2/index.m3u8')
                assert response.status_code == 200 and b'#EXTM3U' in response.data
                client.post('/api/expert-mode',json={'enabled':True},headers={'X-CSRF-Token':'srt-fixture'})
                diagnostic = client.get('/api/expert').json
                assert diagnostic['srt']['auth_ready'] and diagnostic['srt']['runtime_checked']
                assert sender.poll() is None
                print('PASS: generated SRT URL authenticates, publishes H.264/AAC for 25 seconds, switches to Source 2 and provides HLS preview.')
            finally:
                core.ENGINE.running = False
                if core.ENGINE.thread:
                    core.ENGINE.thread.join(timeout=10)
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if sys.exc_info()[0]:
                    secret = core.decrypt(user['media_secret'])
                    for name in ('media.log', 'sender.log'):
                        print(name + ':\n' + (base / name).read_text().replace(secret, '[redacted]')[-3500:])


if __name__ == '__main__':
    main()

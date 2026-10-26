"""Unprivileged, temporary browser compositor. Settings arrive only through stdin."""
import ipaddress
import json
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    settings = json.loads(sys.stdin.readline())
    clip = settings['clip']
    destination = settings['destination']
    url = settings['url']
    fps = max(1, min(30, settings.get('fps', 10)))
    ingest = set(settings.get('ingest_ips') or [])
    if settings.get('ingest_ip'):
        ingest.add(settings['ingest_ip'])
    pinned = {}
    process = None
    browser = None

    def interrupt(*_):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)

    def public_address(value):
        try:
            parsed = urlsplit(value)
            if parsed.scheme not in ('http', 'https', 'ws', 'wss') or not parsed.hostname:
                return False
            host = parsed.hostname
            addresses = {r[4][0] for r in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
            if not addresses:
                return False
            if host in pinned:
                if addresses - pinned[host]:
                    return False
            else:
                if any(not ipaddress.ip_address(a).is_global or a in ingest for a in addresses):
                    return False
                pinned[host] = frozenset(addresses)
            return all(ipaddress.ip_address(a).is_global and a not in ingest for a in addresses)
        except (OSError, ValueError):
            return False

    def route(request):
        if public_address(request.request.url):
            request.continue_()
        else:
            request.abort()

    def websocket(route):
        if public_address(route.url):
            route.connect_to_server()
        else:
            route.close()

    try:
        launch_args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--mute-audio']
        rules = (settings.get('host_resolver_rules') or '').strip()
        if rules:
            launch_args.append('--host-resolver-rules=' + rules)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=launch_args)
            context = browser.new_context(viewport={'width': 1920, 'height': 1080}, device_scale_factor=1,
                                          service_workers='block', accept_downloads=False)
            context.route('**/*', route)
            context.route_web_socket('**/*', websocket)
            page = context.new_page()
            if settings.get('demo_html'):
                page.set_content(settings['demo_html'], wait_until='domcontentloaded')
                response = None
            else:
                if not public_address(url):
                    raise RuntimeError('Overlay target rejected')
                response = page.goto(url, wait_until='domcontentloaded', timeout=25000)
            if response is not None and response.status >= 400:
                raise RuntimeError('Overlay could not be loaded')
            # The page stays alive: JavaScript, animation and alert WebSockets run in real time.
            command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                       '-re', '-stream_loop', '-1', '-i', clip,
                       '-thread_queue_size', '8', '-probesize', '32768', '-analyzeduration', '0',
                       '-f', 'image2pipe', '-framerate', str(fps), '-vcodec', 'png', '-i', 'pipe:0',
                       '-filter_complex_threads', '1', '-filter_complex', '[0:v][1:v]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]',
                       '-map', '[v]', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1',
                       '-tune', 'zerolatency', '-profile:v', 'baseline', '-bf', '0', '-pix_fmt', 'yuv420p',
                       '-b:v', '4500k', '-maxrate', '4500k', '-bufsize', '9000k', '-r', '30', '-g', '60',
                       '-c:a', 'copy', '-f', 'rtsp', '-rtsp_transport', 'tcp', destination]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while process.poll() is None:
                start = time.monotonic()
                png = page.screenshot(type='png', omit_background=True, timeout=10000)
                process.stdin.write(png)
                process.stdin.flush()
                time.sleep(max(0, 1 / fps - (time.monotonic() - start)))
            raise RuntimeError('Compositor stopped')
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        # Do not log overlay URLs, query tokens, or page content.
        print('Browser-Overlay konnte nicht wiedergegeben werden.', file=sys.stderr)
        sys.exit(65)

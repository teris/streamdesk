"""Authenticated playback of tenant-owned native recordings."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request

from flask import Response, jsonify, request


class PlaybackFeatures:
    def __init__(self, core, media):
        self.c, self.media = core, media
        self.probes = {}
        self.remux_slots = threading.BoundedSemaphore(2)
        self.install_routes()

    def base(self):
        config = self.media.config()
        if not config.get('playback', False):
            raise self.c.Error('Playback ist deaktiviert. Ein Administrator kann es im Expertenmodus aktivieren.')
        override = os.getenv('MEDIAMTX_PLAYBACK')
        if override:
            return override.rstrip('/') + '/'
        address = urllib.parse.urlsplit('tcp://' + str(config.get('playbackAddress', ':9996')))
        host = address.hostname or '127.0.0.1'
        if host in ('0.0.0.0', '::'):
            host = '127.0.0.1'
        host = '[' + host + ']' if ':' in host else host
        return ('https' if config.get('playbackEncryption') else 'http') + '://' + host + ':' + str(address.port or 9996) + '/'

    def source(self, user, source):
        if source not in self.c.MODEL.record_sources(user):
            raise self.c.Error('Aufnahmequelle nicht gefunden.', http_status=404)
        return user['prefix'] + source

    def timestamp(self, value):
        try:
            if not isinstance(value, str) or len(value) > 50:
                raise ValueError()
            result = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if result.utcoffset() is None:
                raise ValueError()
            return result.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise self.c.Error('Bitte einen Zeitpunkt mit Zeitzone angeben.', http_status=400) from None

    def url(self, source, start, duration):
        return '/api/playback/' + source + '/media?' + urllib.parse.urlencode(
            {'start': start, 'duration': duration, 'format': 'fmp4'})

    def duration(self, path):
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key not in self.probes:
            try:
                result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                         '-show_entries', 'format=duration:stream=codec_type,codec_name', '-of', 'json', str(path)],
                                        capture_output=True, text=True, timeout=10, check=True)
                details = json.loads(result.stdout)
                duration = float(details['format']['duration'])
                if not math.isfinite(duration) or duration <= 0:
                    return None
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                return None
            if len(self.probes) > 1000:
                self.probes.clear()
            self.probes[key] = {'duration':duration, 'audio':next((stream['codec_name'] for stream in details.get('streams', [])
                                                                if stream.get('codec_type') == 'audio'), None)}
        return self.probes[key]['duration']

    def ts_segments(self, user, source):
        directory = self.media.recording_directory(user, source)
        result = []
        # A bounded recent archive view; file download remains available separately.
        for path in sorted(directory.glob('*.ts'), reverse=True)[:200]:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                start = datetime.strptime(path.stem, '%Y-%m-%d_%H-%M-%S-%f_%z').timestamp()
                duration = self.duration(path)
                if duration:
                    result.append((start, duration, path))
            except (ValueError, OSError):
                continue
        return sorted(result)

    def remux(self, segments, start, duration):
        chosen = [(at, length, path) for at, length, path in segments if at + length > start and at < start + duration]
        if not chosen or chosen[0][0] > start + 0.1:
            raise self.c.Error('Für diesen Zeitraum ist kein Segment vorhanden.', http_status=404)
        end = chosen[0][0] + chosen[0][1]
        contiguous = [chosen[0]]
        for row in chosen[1:]:
            if row[0] > end + 0.5:
                break
            contiguous.append(row)
            end = row[0] + row[1]
        if not self.remux_slots.acquire(blocking=False):
            raise self.c.Error('Beide Playback-Konvertierungen sind belegt. Bitte kurz warten.', http_status=429)
        manifest = None
        process = None
        errors = None
        try:
            errors = tempfile.TemporaryFile()
            # Paths originate exclusively from recording_directory; no client filenames.
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ffconcat', delete=False) as file:
                manifest = Path(file.name)
                for _, _, path in contiguous:
                    escaped = str(path).replace("'", "'\\''")
                    file.write("file '" + escaped + "'\n")
            first = contiguous[0][2]
            stat = first.stat()
            audio = self.probes.get((str(first), stat.st_mtime_ns, stat.st_size), {}).get('audio')
            filters = ['-bsf:a', 'aac_adtstoasc'] if audio == 'aac' else []
            process = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', str(manifest),
                '-ss', str(max(0, start - contiguous[0][0])), '-t', str(min(duration, end - start)),
                '-map', '0:v:0?', '-map', '0:a:0?', '-c', 'copy', *filters, '-movflags',
                'frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', 'pipe:1'],
                stdout=subprocess.PIPE, stderr=errors)
        except OSError:
            if manifest:
                manifest.unlink(missing_ok=True)
            if errors:
                errors.close()
            self.remux_slots.release()
            raise self.c.Error('FFmpeg konnte für Playback nicht gestartet werden.') from None

        closed = False
        def cleanup():
            nonlocal closed
            if not closed:
                closed = True
                aborted = process.poll() is None
                if aborted:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                process.wait()
                if process.returncode and not aborted:
                    errors.seek(0)
                    self.c.logging.warning('Playback-Remux fehlgeschlagen: %s', errors.read(4096).decode(errors='replace'))
                errors.close()
                process.stdout.close()
                manifest.unlink(missing_ok=True)
                self.remux_slots.release()
        try:
            first_chunk = process.stdout.read(64 * 1024)
            if len(first_chunk) < 64 * 1024:
                process.wait()
                if not first_chunk or process.returncode:
                    raise self.c.Error('Dieses MPEG-TS-Segment konnte nicht wiedergegeben werden. Codec und Segmentdownload prüfen.')
        except (OSError, self.c.Error):
            cleanup()
            raise

        def stream():
            try:
                yield first_chunk
                while chunk := process.stdout.read(256 * 1024):
                    yield chunk
            finally:
                cleanup()
        response = Response(stream(), content_type='video/mp4', headers={'Accept-Ranges':'none', 'Cache-Control':'private, no-store'})
        response.call_on_close(cleanup)
        return response

    def install_routes(self):
        c, media = self.c, self.media
        expert = lambda function: c.login_required(c.expert_required(function))

        @c.app.get('/api/playback/status')
        @expert
        def playback_status(user):
            config = media.config()
            return jsonify(enabled=bool(config.get('playback', False)),
                           address=config.get('playbackAddress', ':9996') if user['admin'] else '',
                           sources=list(c.MODEL.record_sources(user)),labels={source:c.MODEL.source_label(user,source) for source in c.MODEL.record_sources(user)})

        @c.app.post('/api/admin/playback')
        @expert
        def configure_playback(user):
            if not user['admin']:
                raise c.Error('Nur Administratoren können globale Listener ändern.', http_status=403)
            body = media.body()
            enabled = media.boolean(body, 'enabled')
            change = {'playback': enabled}
            if 'address' in body:
                value = body['address']
                try:
                    if not isinstance(value, str):
                        raise ValueError()
                    parsed = urllib.parse.urlsplit('tcp://' + value)
                    if parsed.hostname not in ('127.0.0.1', '::1', 'localhost') or not parsed.port or parsed.path or parsed.username or parsed.query or parsed.fragment:
                        raise ValueError()
                except ValueError:
                    raise c.Error('Playback benötigt eine Loopback-Adresse, z. B. 127.0.0.1:9996.', http_status=400) from None
                change['playbackAddress'] = value
            elif enabled and not media.config().get('playback', False):
                change['playbackAddress'] = '127.0.0.1:9996'
            media.apply_global(change, {'playback':False, 'playbackAddress':':9996'})
            return jsonify(ok=True)

        @c.app.get('/api/playback/<source>/spans')
        @expert
        def playback_spans(user, source):
            name = self.source(user, source)
            base = self.base()
            query = {'path': name}
            start, end = request.args.get('start'), request.args.get('end')
            for key, value in (('start', start), ('end', end)):
                if value:
                    query[key] = self.timestamp(value).isoformat()
            if start and end and self.timestamp(start) >= self.timestamp(end):
                raise c.Error('Das Ende muss nach dem Start liegen.', http_status=400)
            fmt = media.config()['paths'].get(name, {}).get('recordFormat', 'fmp4')
            if fmt == 'mpegts':
                segments = self.ts_segments(user, source)
                items = [{'start':datetime.fromtimestamp(at, timezone.utc).isoformat(), 'duration':length}
                         for at, length, _ in segments if (not start or at+length > self.timestamp(start).timestamp())
                         and (not end or at < self.timestamp(end).timestamp())]
            else:
                req = urllib.request.Request(base + 'list?' + urllib.parse.urlencode(query), headers=media.media_headers(user))
                try:
                    with urllib.request.urlopen(req, timeout=15) as response:
                        data = response.read(2 * 1024 * 1024 + 1)
                    if len(data) > 2 * 1024 * 1024:
                        raise ValueError()
                    items = json.loads(data)
                    if not isinstance(items, list):
                        raise ValueError()
                    items = [{'start':self.timestamp(row['start']).isoformat(), 'duration':float(row['duration'])}
                             for row in items[-200:]]
                except (OSError, ValueError, KeyError, TypeError):
                    raise c.Error('Playback-Segmente konnten nicht geladen werden. Server und Aufnahmeformat prüfen.') from None
            return jsonify(format=fmt, spans=[dict(row, url=self.url(source, row['start'], min(row['duration'], 3600))) for row in items])

        @c.app.get('/api/playback/<source>/media')
        @expert
        def playback_media(user, source):
            name = self.source(user, source)
            base = self.base()
            start = self.timestamp(request.args.get('start'))
            try:
                duration = float(request.args.get('duration', ''))
                if not math.isfinite(duration) or not 0 < duration <= 3600:
                    raise ValueError()
            except ValueError:
                raise c.Error('Die Wiedergabedauer muss zwischen 0 und 3600 Sekunden liegen.', http_status=400) from None
            fmt = request.args.get('format', 'fmp4')
            if fmt not in ('fmp4', 'mp4'):
                raise c.Error('Ungültiges Playback-Format.', http_status=400)
            if media.config()['paths'].get(name, {}).get('recordFormat', 'fmp4') == 'mpegts':
                return self.remux(self.ts_segments(user, source), start.timestamp(), duration)
            query = urllib.parse.urlencode({'path':name, 'start':start.isoformat(), 'duration':duration, 'format':fmt})
            try:
                response = urllib.request.urlopen(urllib.request.Request(base+'get?'+query, headers=media.media_headers(user)), timeout=20)
            except OSError:
                raise c.Error('Für diesen Zeitraum ist keine Wiedergabe verfügbar.', http_status=404) from None

            def stream():
                try:
                    while chunk := response.read(256 * 1024):
                        yield chunk
                finally:
                    response.close()
            return Response(stream(), content_type='video/mp4', headers={'Accept-Ranges':'none', 'Cache-Control':'private, no-store'})

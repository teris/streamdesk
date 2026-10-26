"""One on-demand browser-compatible program encoder per tenant."""
import subprocess
import time
from routing_model import job_key


class ProgramPreview:
    def __init__(self, core):
        self.c = core
        self.jobs = {}
        self.retry = {}

    def path(self, user, program='main'):
        return self.c.MODEL.program(user,program)['rtc_path']

    def start(self, user, program='main'):
        c = self.c
        definition = c.MODEL.program(user,program)
        key = job_key(user,program)
        with c.LOCK:
            job = self.jobs.get(key)
            if job and job['process'].poll() is None:
                job['used'] = time.monotonic()
                return job
            self.stop(key)
            # The program is normalized to H264 without B-frames. Only its AAC
            # audio needs converting to Opus for browser WebRTC playback.
            command = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
                '-rtsp_transport', 'tcp', '-timeout', '15000000', '-analyzeduration', '1000000', '-probesize', '1000000',
                '-i', c.RTSP + definition['path'], '-map', '0:v:0', '-map', '0:a:0?',
                '-c:v', 'copy',
                '-c:a', 'libopus', '-ar', '48000', '-ac', '2', '-b:a', '96k', '-f', 'rtsp', '-rtsp_transport', 'tcp',
                c.RTSP + self.path(user,program)]
            try:
                with (c.DATA / ('program-preview-' + str(user['id']) + ('-'+program if program!='main' else '') + '.log')).open('wb') as log:
                    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
            except OSError:
                raise c.Error('Programmvorschau konnte nicht gestartet werden.') from None
            job = {'process':process,'used':time.monotonic(),'program':program}
            self.jobs[key] = job
            return job

    def ensure(self, user, program='main'):
        job = self.start(user,program)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if job['process'].poll() is not None:
                break
            try:
                if self.c.mtx('paths/get/' + self.path(user,program)).get('online'):
                    return self.path(user,program)
            except self.c.Error:
                pass
            time.sleep(.1)
        raise self.c.Error('Die WebRTC-Programmvorschau liefert noch kein Signal. FFmpeg und MediaMTX prüfen.')

    def stop(self, uid):
        job = self.jobs.pop(uid, None)
        if job and job['process'].poll() is None:
            job['process'].terminate()
            try:
                job['process'].wait(timeout=2)
            except subprocess.TimeoutExpired:
                job['process'].kill()
                job['process'].wait()

    def monitor(self, users, paths):
        c, now = self.c, time.monotonic()
        with c.LOCK:
            active = {job_key(user,program['id']) for user in users for program in c.MODEL.programs(user)}
            for key in list(self.jobs):
                if key not in active:
                    self.stop(key)
            self.retry = {key:at for key,at in self.retry.items() if key in active}
            for user in users:
                for definition in c.MODEL.programs(user):
                    pid = definition['id'];key = job_key(user,pid)
                    readers = bool(paths.get(definition['rtc_path'],{}).get('readers'))
                    job = self.jobs.get(key)
                    if job and job['process'].poll() is not None:
                        self.stop(key);self.retry[key] = now+5;job=None
                    if job and readers:
                        job['used'] = now
                    elif job and now-job['used']>20:
                        self.stop(key)
                    elif not job and readers and now>=self.retry.get(key,0):
                        self.start(user,pid)

    def close(self):
        with self.c.LOCK:
            for uid in list(self.jobs):
                self.stop(uid)

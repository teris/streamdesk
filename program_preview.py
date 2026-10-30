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
        self.c.SERVICES.require('webrtc')
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
            # audio needs converting to Opus. Preserve its timing relative to
            # the copied video, including after a delayed playlist start.
            command = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
                '-rtsp_transport', 'tcp', '-timeout', '15000000', '-analyzeduration', '2000000', '-probesize', '4000000',
                '-i', c.RTSP + definition['path'], '-map', '0:v:0', '-map', '0:a:0',
                '-c:v', 'copy',
                '-c:a', 'libopus', '-ar', '48000', '-ac', '2', '-b:a', '96k',
                '-af', 'aresample=async=1', '-max_interleave_delta', '1000000', '-flush_packets', '1', '-f', 'rtsp', '-rtsp_transport', 'tcp', '-pkt_size', '1200',
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
        # WHEP negotiation can still be gathering ICE candidates after the
        # encoder becomes ready. It must not be reaped as an idle preview.
        job['pending_until']=time.monotonic()+45
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if job['process'].poll() is not None:
                break
            try:
                state=self.c.mtx('paths/get/' + self.path(user,program))
                codecs={str(track.get('codec','') if isinstance(track,dict) else track).lower() for track in (state.get('tracks2') or state.get('tracks') or [])}
                if state.get('online') and {'h264','opus'}<=codecs:
                    job['used']=time.monotonic()
                    return self.path(user,program)
            except self.c.Error:
                pass
            time.sleep(.1)
        key=job_key(user,program)
        with self.c.LOCK:
            if self.jobs.get(key) is job:self.stop(key)
        raise self.c.Error('Das Programm liefert noch kein vollständiges H.264-/Opus-Signal für WebRTC. Bitte erneut starten; der Vorschauprozess wurde zurückgesetzt.')

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
        if not self.c.SERVICES.enabled('webrtc'):
            self.close()
            return
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
                    elif job and now-job['used']>20 and now>=job.get('pending_until',0):
                        self.stop(key)
                    elif not job and readers and now>=self.retry.get(key,0):
                        self.start(user,pid)

    def close(self):
        with self.c.LOCK:
            for uid in list(self.jobs):
                self.stop(uid)

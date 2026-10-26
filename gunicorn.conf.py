import os
bind = os.getenv('STREAMDESK_BIND', '0.0.0.0:8080')
workers = 1  # The source manager and in-memory chat must have a single owner.
threads = 8
timeout = 120
accesslog = None
errorlog = '-'
capture_output = False


def worker_exit(server, worker):
    try:
        import app
        app.ENGINE.running = False
        thread = getattr(app.ENGINE, 'thread', None)
        if thread is not None:
            thread.join(timeout=5)
    except Exception:
        pass

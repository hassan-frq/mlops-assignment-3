# gunicorn.conf.py — Production Gunicorn configuration

import os

# Bind
bind = "0.0.0.0:5000"

# Small fixed worker count keeps memory within the 128Mi pod request; scale with pods.
workers = int(os.environ.get("WEB_CONCURRENCY", 2))

# Use sync workers (default). Switch to gevent/gthread if latency matters.
worker_class = "sync"

# Restart workers after this many requests to guard against memory leaks.
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Timeouts
timeout = 120
graceful_timeout = 30
keepalive = 5


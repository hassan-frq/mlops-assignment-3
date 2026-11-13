# gunicorn.conf.py — Production Gunicorn configuration

import multiprocessing

# Bind
bind = "0.0.0.0:5000"

# Workers: 2–4 × CPU cores is the typical sweet spot for I/O-bound workloads.
workers = multiprocessing.cpu_count() * 2 + 1

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

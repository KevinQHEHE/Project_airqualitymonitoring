#!/usr/bin/env python3
"""
Gunicorn configuration file for Air Quality Monitoring System
"""

import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "/home/dlhnhom2/air-quality-monitoring/logs/access.log"
errorlog = "/home/dlhnhom2/air-quality-monitoring/logs/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "air_quality_monitoring"

# Daemon mode
daemon = False
pidfile = "/home/dlhnhom2/air-quality-monitoring/logs/air_quality_monitoring.pid"

# User/group to run as
user = "dlhnhom2"
group = "dlhnhom2"

# Preload application for better performance
preload_app = True

# Application callable
wsgi_module = "wsgi:app"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Air Quality Monitoring System")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading Air Quality Monitoring System")

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Air Quality Monitoring System is ready. Listening on: %s", server.address)

def on_exit(server):
    """Called just before exiting."""
    server.log.info("Shutting down Air Quality Monitoring System")

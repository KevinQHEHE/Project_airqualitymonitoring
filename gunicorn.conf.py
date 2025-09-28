#!/usr/bin/env python3
"""
Optimized Gunicorn configuration for Air Quality Monitoring System
Automatically configured for system resources
"""

import multiprocessing
import os

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes (optimized for this system)
workers = 1
worker_class = "sync"
worker_connections = 100
timeout = 30
keepalive = 2

# Restart workers after this many requests
max_requests = 100
max_requests_jitter = 50

# Logging
accesslog = "/home/azureuser/air-quality-monitoring/logs/access.log"
errorlog = "/home/azureuser/air-quality-monitoring/logs/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "air_quality_monitoring"

# Daemon mode
daemon = False
pidfile = "/home/azureuser/air-quality-monitoring/logs/gunicorn.pid"

# User/group to run as
user = "azureuser"
group = "azureuser"

# Preload application for better performance
preload_app = True

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def on_starting(server):
    server.log.info("Starting Air Quality Monitoring System")

def on_reload(server):
    server.log.info("Reloading Air Quality Monitoring System")

def when_ready(server):
    server.log.info("Air Quality Monitoring System is ready. Listening on: %s", server.address)

def on_exit(server):
    server.log.info("Shutting down Air Quality Monitoring System")

#!/bin/bash
echo "=== Air Quality Monitoring System Logs ==="
echo
echo "--- Application Error Logs (last 20 lines) ---"
tail -20 logs/error.log 2>/dev/null || echo "No error logs found"
echo
echo "--- Application Access Logs (last 10 lines) ---"
tail -10 logs/access.log 2>/dev/null || echo "No access logs found"
echo
echo "--- Nginx Error Logs (last 10 lines) ---"
tail -10 logs/nginx_error.log 2>/dev/null || echo "No nginx error logs found"
echo
echo "--- System Service Logs (last 20 lines) ---"
sudo journalctl -u air-quality-monitoring.service -n 20 --no-pager

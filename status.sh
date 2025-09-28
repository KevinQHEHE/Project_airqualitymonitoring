#!/bin/bash
echo "=== Air Quality Monitoring System Status ==="
echo

HAS_MONGOD=0
if systemctl list-unit-files --type=service --no-legend --no-pager | grep -q '^mongod.service'; then
    HAS_MONGOD=1
fi

echo "Service Status:"
if sudo systemctl is-active --quiet air-quality-monitoring.service; then
    echo "[OK] Application: RUNNING"
else
    echo "[ERR] Application: STOPPED"
fi
if sudo systemctl is-active --quiet nginx; then
    echo "[OK] Nginx: RUNNING"
else
    echo "[ERR] Nginx: STOPPED"
fi
if [ "$HAS_MONGOD" -eq 1 ]; then
    if sudo systemctl is-active --quiet mongod; then
        echo "[OK] MongoDB: RUNNING"
    else
        echo "[ERR] MongoDB: STOPPED"
    fi
else
    echo "[--] MongoDB: not managed locally"
fi

echo
echo "Port Status:"
PORT_REGEX=':(80|8000)'
if [ "$HAS_MONGOD" -eq 1 ]; then
    PORT_REGEX=':(80|8000|27017)'
fi
ss -tlnp | grep -E "$PORT_REGEX" || echo "No services listening on expected ports"

echo
echo "Recent Logs:"
echo "--- Application Logs ---"
tail -5 logs/error.log 2>/dev/null || echo "No error logs found"
echo "--- Nginx Access Logs ---"
tail -3 logs/nginx_access.log 2>/dev/null || echo "No access logs found"
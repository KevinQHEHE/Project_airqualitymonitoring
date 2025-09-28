#!/bin/bash
echo "Restarting Air Quality Monitoring System..."

HAS_MONGOD=0
if systemctl list-unit-files --type=service --no-legend --no-pager | grep -q '^mongod.service'; then
    HAS_MONGOD=1
fi

if [ "$HAS_MONGOD" -eq 1 ]; then
    sudo systemctl restart mongod
fi
sudo systemctl restart air-quality-monitoring.service
sudo systemctl restart nginx
sleep 3
echo "Services restarted. Checking status:"
SERVICES="air-quality-monitoring.service nginx"
if [ "$HAS_MONGOD" -eq 1 ]; then
    SERVICES="$SERVICES mongod"
fi
for svc in $SERVICES; do
    if sudo systemctl is-active --quiet "$svc"; then
        echo "[OK] $svc is active"
    else
        echo "[ERR] $svc is not active"
    fi
done
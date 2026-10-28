#!/bin/bash
# Hearth launcher with crash rollback.
# server.py self-updates by exiting with code 42; systemd restarts this
# wrapper, which relaunches the (new) code. If the process dies fast
# 3 times in a row, restore .lastgood and block that build's sha so the
# updater does not reinstall it.
cd /opt/hearth || exit 1
fails=0
while true; do
  start=$(date +%s)
  /usr/bin/python3 /opt/hearth/server.py 8471
  code=$?
  now=$(date +%s)
  if [ "$code" -eq 42 ]; then
    fails=0
  elif [ $((now - start)) -lt 15 ]; then
    fails=$((fails + 1))
  else
    fails=0
  fi
  if [ "$fails" -ge 3 ] && [ -d /opt/hearth/.lastgood ]; then
    cp /opt/hearth/.lastgood/*.py /opt/hearth/ 2>/dev/null || true
    for f in index.html requirements.txt hearth.service admin_keys.txt run.sh; do
      cp "/opt/hearth/.lastgood/$f" /opt/hearth/ 2>/dev/null || true
    done
    rm -rf /opt/hearth/avatars /opt/hearth/assets
    cp -r /opt/hearth/.lastgood/avatars /opt/hearth/ 2>/dev/null || true
    cp -r /opt/hearth/.lastgood/assets /opt/hearth/ 2>/dev/null || true
    if [ -f /opt/hearth/.installed_sha ]; then
      cp /opt/hearth/.installed_sha /opt/hearth/.blocked_sha
      rm -f /opt/hearth/.installed_sha
    fi
    fails=0
  fi
  sleep 2
done

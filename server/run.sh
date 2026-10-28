#!/bin/sh
# Open Toontown, everything in one container: Astron, UberDOG, three districts, the web bridge, the sign-in service, nginx and nightly backups.
mkdir -p /ot/data/phone_logs /ot/data/backups /ot/data/logs /ot/src/astron/databases/astrondb /ot/src/astron/logs
[ -f /ot/data/users.json ] || echo '{"open_registration": true, "users": {}}' > /ot/data/users.json
chmod 666 /ot/data/users.json
L=/ot/data/logs
nginx
python -u /ot/auth_service.py > $L/auth.log 2>&1 &
python -u /ot/wsbridge.py > $L/bridge.log 2>&1 &
python -u /ot/discord_status.py > $L/discord.log 2>&1 &       # edits one Discord message with the number of toons playing (needs data/discord_webhook)
cd /ot/src/astron/linux && chmod +x astrond && ./astrond --loglevel info ../config/astrond-linux.yml > $L/astron.log 2>&1 &
sleep 6
cd /ot/src
COMMON="--max-channels 999999 --stateserver 4002 --messagedirector-ip 127.0.0.1:7199 --eventlogger-ip 127.0.0.1:7197"
python -u -m toontown.uberdog.UDStart --base-channel 1000000 $COMMON etc/Configrc.prc etc/live.prc > $L/ud.log 2>&1 &
UD=$!
sleep 25
python -u -m toontown.ai.AIStart --base-channel 401000000 $COMMON --district-name "Toon Valley" etc/Configrc.prc etc/live.prc > $L/ai1.log 2>&1 &
A1=$!
sleep 15
python -u -m toontown.ai.AIStart --base-channel 402000000 $COMMON --district-name "Giggle Grove" etc/Configrc.prc etc/live.prc > $L/ai2.log 2>&1 &
A2=$!
sleep 15
python -u -m toontown.ai.AIStart --base-channel 403000000 $COMMON --district-name "Silly Meadow" etc/Configrc.prc etc/live.prc > $L/ai3.log 2>&1 &
A3=$!
# nightly backup of the toons and users, keeping 14 days
( while true; do sleep 86400; tar czf /ot/data/backups/auto-$(date +%Y%m%d-%H%M).tgz -C /ot/src/astron databases -C /ot/data users.json 2>/dev/null; ls -1t /ot/data/backups/auto-*.tgz | tail -n +15 | xargs -r rm -f; done ) &
# if the UberDOG or a district dies, exit so Docker restarts everything
while kill -0 $UD 2>/dev/null && kill -0 $A1 2>/dev/null && kill -0 $A2 2>/dev/null && kill -0 $A3 2>/dev/null; do sleep 20; done
echo "a game process died; exiting so the container restarts" >&2
exit 1

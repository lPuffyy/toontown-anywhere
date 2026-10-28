import os, signal, subprocess, time
for pid in os.listdir('/proc'):
    if pid.isdigit():
        try:
            cmd = open('/proc/%s/cmdline' % pid, 'rb').read().replace(b'\0', b' ').decode()
        except Exception:
            continue
        if 'auth_service.py' in cmd and 'restart_auth_service' not in cmd:
            os.kill(int(pid), signal.SIGTERM)
            print('stopped', pid, cmd.strip())
time.sleep(1)
subprocess.Popen('python -u /ot/auth_service.py > /ot/data/logs/auth.log 2>&1', shell=True, start_new_session=True)
print('started')

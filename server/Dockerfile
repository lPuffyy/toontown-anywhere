FROM python:3.9-slim
RUN apt-get update && apt-get install -y --no-install-recommends nginx libgl1 libglib2.0-0 tini && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pytz websockets \
 && pip install --no-cache-dir --pre --index-url https://archive.panda3d.org/simple/ panda3d==1.11.0.dev4085+shaderpipeline.388
# the game's own copy of the Python side of Panda3D 1.11 (Astron support, tasks) on top of the wheel
COPY overlay/direct /usr/local/lib/python3.9/site-packages/direct
# the pure-Python stand-ins for the compiled libotp / libtoontown, loaded into every Python process
RUN printf 'import sys\nsys.path.insert(0, "/ot/src")\ntry:\n    import otpy.install\n    otpy.install.install()\nexcept Exception as e:\n    print("otpy install failed", e, file=sys.stderr)\n' > /usr/local/lib/python3.9/site-packages/sitecustomize.py
COPY auth_service.py wsbridge.py discord_status.py nginx.conf run.sh /ot/
RUN chmod +x /ot/run.sh && cp /ot/nginx.conf /etc/nginx/conf.d/default.conf && rm -f /etc/nginx/sites-enabled/default
WORKDIR /ot/src
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/ot/run.sh"]

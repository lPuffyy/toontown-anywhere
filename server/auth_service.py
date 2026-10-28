import http.server, os, re, json, hashlib, hmac, threading, time
D="/ot/data/phone_logs"; U="/ot/data/users.json"
LOCK=threading.Lock()
FAILS={}   # key -> [timestamps] of failed recovery attempts
def load():
    try: return json.load(open(U))
    except Exception: return {"open_registration":True,"users":{}}
def save(db):
    json.dump(db,open(U+".tmp","w"),indent=1); os.replace(U+".tmp",U); os.chmod(U,0o666)
def pbk(text,salt): return hashlib.pbkdf2_hmac("sha256",text.encode(),bytes.fromhex(salt),100000).hex()
def norm(s): return " ".join(s.lower().split())
def check_name_pw(name,pw):
    if not (2<=len(name)<=20) or not name.replace("_","").replace("-","").isalnum(): return "Usernames are 2-20 letters, numbers, - or _."
    if len(pw)<4: return "Passwords need at least 4 characters."
    return None
def auth(text):
    """returns (error or None, user record or None)"""
    if ":" not in text: return "Please enter a username and password.",None
    name,pw=text.split(":",1); name=name.strip().lower()
    e=check_name_pw(name,pw)
    if e: return e,None
    with LOCK:
        db=load(); u=db["users"].get(name)
        if u is None:
            if not db.get("open_registration",True): return "Unknown user. Ask a parent to add you.",None
            salt=os.urandom(16).hex(); u=db["users"][name]={"salt":salt,"hash":pbk(pw,salt),"dbkey":"user:"+name}
            save(db); return None,u
        if not hmac.compare_digest(u["hash"],pbk(pw,u["salt"])): return "Wrong password.",None
        return None,u
def throttled(keys):
    now=time.time()
    for k in keys:
        FAILS[k]=[t for t in FAILS.get(k,[]) if now-t<3600]
        if len(FAILS[k])>=5: return True
    return False
def note_fail(keys):
    now=time.time()
    for k in keys: FAILS.setdefault(k,[]).append(now)
def set_recovery(text):
    parts=text.split("\n")
    if len(parts)<3: return "Fill in both boxes."
    err,u=auth(parts[0])
    if err or u is None: return err or "Sign in first."
    nick,toon=norm(parts[1]),norm(parts[2])
    if len(nick)<2 or len(toon)<2: return "Answers need at least 2 letters."
    name=parts[0].split(":",1)[0].strip().lower()
    with LOCK:
        db=load(); salt=os.urandom(16).hex()
        db["users"][name]["rec"]={"salt":salt,"nick":pbk(nick,salt),"toon":pbk(toon,salt)}
        save(db)
    return None
GENERIC="Those answers don't match. Ask a parent if you need help."
def recover(text,ip):
    parts=text.split("\n")
    if len(parts)<4: return "Fill in every box."
    name=parts[0].strip().lower(); nick,toon,newpw=norm(parts[1]),norm(parts[2]),parts[3]
    keys=("u:"+name,"ip:"+ip)
    if throttled(keys): return "Too many tries. Try again in an hour or ask a parent."
    e=check_name_pw(name,newpw)
    if e and e.startswith("Passwords"): return e
    with LOCK:
        db=load(); u=db["users"].get(name); rec=(u or {}).get("rec")
        ok=False
        if rec:
            a=hmac.compare_digest(rec["nick"],pbk(nick,rec["salt"]))
            b=hmac.compare_digest(rec["toon"],pbk(toon,rec["salt"]))
            ok=a and b
        else:
            pbk(nick,os.urandom(16).hex())  # keep timing similar
        if not ok:
            note_fail(keys); return GENERIC
        salt=os.urandom(16).hex(); u["salt"]=salt; u["hash"]=pbk(newpw,salt)
        save(db)
    FAILS.pop("u:"+name,None)
    return None
CLOG="/ot/data/logs/client.log"; CLOG_MAX=30*1024*1024; CLOG_RATE={}
def client_log(ip,text):
    now=time.time(); q=CLOG_RATE.setdefault(ip,[]); q[:]=[t for t in q if now-t<3600]
    if len(q)>=6000: return False
    try:
        if os.path.exists(CLOG) and os.path.getsize(CLOG)>CLOG_MAX: return False
        q.append(now)
        with LOCK, open(CLOG,"a",encoding="utf8") as f:
            line=text[:1500].replace(chr(10)," | ")
            f.write("%s %s %s%s"%(time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime(now)),ip,line,chr(10)))
    except Exception: return False
    return True
class H(http.server.BaseHTTPRequestHandler):
    def reply(self,code,msg):
        self.send_response(code); self.end_headers(); self.wfile.write(msg.encode())
    def do_POST(self):
        n=int(self.headers.get("Content-Length","0")); raw=self.rfile.read(n); body=raw.decode("utf-8","replace") if n<4096 else ""
        ip=self.headers.get("X-Forwarded-For") or self.client_address[0]
        if self.path=="/auth":
            err,u=auth(body)
            if err: return self.reply(403,err)
            return self.reply(200,"ok" if u.get("rec") else "setup")
        if self.path=="/setrecovery":
            err=set_recovery(body); return self.reply(403 if err else 200,err or "ok")
        if self.path=="/recover":
            err=recover(body,ip); return self.reply(403 if err else 200,err or "ok")
        if self.path=="/__log":
            # a test session (page opened with ?log=1): keep what the game prints, with the time and the device's address
            return self.reply(204 if client_log(ip,body) else 429,"")
        name=re.sub(r"[^A-Za-z0-9_.-]","_",self.path.strip("/") or "log")
        with open(os.path.join(D,name+(".png" if name.startswith("shot") else ".txt")),"wb") as f: f.write(raw)
        self.reply(200,"ok")
    def log_message(self,*a): pass
http.server.ThreadingHTTPServer(("0.0.0.0",7381),H).serve_forever()

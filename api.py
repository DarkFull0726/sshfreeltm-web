from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, subprocess, json, random, string, hashlib, uuid, base64, threading, time, urllib.request, urllib.parse
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

DAYS_VALID          = 3
SSH_KEY             = os.path.expanduser("~/.ssh/id_bot")
USERS_DB            = "created_users.json"
WEB_SESSIONS        = "web_sessions.json"
VMESS_DB            = "vmess_users.json"
WEB_CREDITS_DEFAULT = 3
WEB_REGEN_HOURS     = 10
WEB_MAX_CREDITS     = 3
ADMIN_PASSWORD      = "DarkIuudjii"
ADMIN_TOKENS        = {}
ADMIN_IPS           = ["38.172.41.107"]
BOT_TOKEN           = "7998209606:AAGNwiDAH5cOhWftedzZosjq7GLElvJRtws"
ADMIN_CHAT_ID       = "6290827127"
BASE_DIR            = "/var/www/sshfreeltm"
MIAMI_IP            = "104.207.144.166"
MIAMI_SSH_PORT      = 22
V2RAY_CFG           = "/usr/local/etc/v2ray/config.json"

notified_visitors = set()

VPS = {
    "mexico": {
        "IP":"216.238.84.148","PORT":22,"DOMAIN":"mxvlt.darkfullhn.xyz",
        "NS":"nsmxvlt.darkfullhn.xyz","LOCAL":True,"BYPASS_PAM":False,
        "NAME":"Mexico","MAINTENANCE":False,
        "PORTS":"SSH:22  |  DNS:53  |  SSL/TLS:443  |  UDP Custom:36712  |  BadVPN:7200  |  BadVPN:7300",
        "CONNECTIONS":[
            {"label":"UDP Custom","value":"[IP]:1-65535@[USER]:[PASS]"},
            {"label":"SSL/TLS 443","value":"[IP]:443@[USER]:[PASS]"},
            {"label":"SSH Directo","value":"[IP]:22@[USER]:[PASS]"}
        ]
    },
    "miami": {
        "IP":"104.207.144.166","PORT":22,"DOMAIN":"mia.darkfullhn.xyz",
        "NS":"nsmia.darkfullhn.xyz","LOCAL":False,"BYPASS_PAM":True,
        "NAME":"Miami (Juegos)","MAINTENANCE":False,
        "PORTS":"SSH:22  |  DNS:53  |  WS Python:80  |  V2Ray WS:443  |  V2Ray WS:8080  |  UDP Custom:36712  |  BadVPN:7200  |  BadVPN:7300",
        "CONNECTIONS":[
            {"label":"UDP Custom","value":"[IP]:1-65535@[USER]:[PASS]"},
            {"label":"WS Puerto 80","value":"[IP]:80@[USER]:[PASS]"},
            {"label":"SSH Directo","value":"[IP]:22@[USER]:[PASS]"}
        ]
    }
}

# ── Sesiones ──

def load_sessions():
    p = os.path.join(BASE_DIR, WEB_SESSIONS)
    if not os.path.exists(p): return {}
    with open(p) as f: return json.load(f)

def save_sessions(data):
    with open(os.path.join(BASE_DIR, WEB_SESSIONS), "w") as f: json.dump(data, f, indent=2)

def get_client_id(req):
    ip = req.headers.get("CF-Connecting-IP") or req.headers.get("X-Forwarded-For","").split(",")[0].strip() or req.remote_addr
    ua = req.headers.get("User-Agent","")
    return hashlib.md5(f"{ip}:{ua}".encode()).hexdigest()[:16]

def get_or_create_session(cid):
    sessions = load_sessions()
    if cid not in sessions:
        sessions[cid] = {"credits":WEB_CREDITS_DEFAULT,"last_regen":datetime.now().isoformat()}
        save_sessions(sessions)
    return sessions[cid]

def apply_regen(cid):
    sessions = load_sessions()
    if cid not in sessions: get_or_create_session(cid); sessions = load_sessions()
    s = sessions[cid]
    last   = datetime.fromisoformat(s["last_regen"])
    earned = int((datetime.now()-last).total_seconds()/3600//WEB_REGEN_HOURS)
    if earned > 0:
        s["credits"]    = min(s["credits"]+earned, WEB_MAX_CREDITS)
        s["last_regen"] = (last+timedelta(hours=earned*WEB_REGEN_HOURS)).isoformat()
        sessions[cid]   = s; save_sessions(sessions)
    return sessions[cid]

def spend_credit(cid):
    sessions = load_sessions(); apply_regen(cid); sessions = load_sessions()
    if sessions[cid]["credits"] <= 0: return False
    sessions[cid]["credits"] -= 1; save_sessions(sessions); return True

def time_to_next(cid):
    sessions = load_sessions()
    if cid not in sessions: return "0h 0m"
    last = datetime.fromisoformat(sessions[cid]["last_regen"])
    rem  = (last+timedelta(hours=WEB_REGEN_HOURS))-datetime.now()
    if rem.total_seconds() <= 0: return "0h 0m"
    return f"{int(rem.total_seconds()//3600)}h {int((rem.total_seconds()%3600)//60)}m"

# ── Notificaciones ──

def get_ip_info(ip):
    try:
        url = f"http://ip-api.com/json/{ip}?fields=country,regionName,city,isp,query"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        res = urllib.request.urlopen(req, timeout=5)
        return json.loads(res.read().decode())
    except: return {}

def parse_device(ua):
    import re
    ua_lower = ua.lower()
    if "iphone" in ua_lower:
        m = re.search(r"iPhone OS ([\d_]+)", ua)
        ver = m.group(1).replace("_",".") if m else ""
        return f"iPhone (iOS {ver})" if ver else "iPhone"
    elif "ipad" in ua_lower: return "iPad"
    elif "android" in ua_lower:
        m = re.search(r"Android[\s/][\d.]+;\s*([^;)]+?)(?:\s*Build|\s*\)|;)", ua)
        if m:
            model = m.group(1).strip()
            if model and len(model) > 2: return f"Android - {model}"
        m2 = re.search(r"Android ([\d.]+)", ua)
        return f"Android {m2.group(1)}" if m2 else "Android"
    elif "windows" in ua_lower: return "Windows PC"
    elif "macintosh" in ua_lower: return "Mac"
    elif "linux" in ua_lower: return "Linux PC"
    return ua[:80]

def send_telegram(msg):
    try:
        data = urllib.parse.urlencode({"chat_id":ADMIN_CHAT_ID,"text":msg,"parse_mode":"Markdown"}).encode()
        req  = urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=5)
    except: pass

def notify_admin(ip, user_agent):
    try:
        info   = get_ip_info(ip)
        device = parse_device(user_agent)
        msg = (f"👁 *NUEVA VISITA WEB*\n━━━━━━━━━━━━━━━━━━━━\n"
               f"🌐 IP: `{ip}`\n"
               f"📍 {info.get('city','?')}, {info.get('regionName','?')}, {info.get('country','?')}\n"
               f"🏢 ISP: {info.get('isp','?')}\n"
               f"📱 {device}")
        send_telegram(msg)
    except: pass

def notify_admin_create(ip, user_agent, username, vps):
    try:
        info   = get_ip_info(ip)
        device = parse_device(user_agent)
        msg = (f"✅ *CUENTA SSH CREADA DESDE WEB*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"👤 Usuario: `{username}`\n🌐 VPS: {vps.upper()}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"🔌 IP: `{ip}`\n"
               f"📍 {info.get('city','?')}, {info.get('regionName','?')}, {info.get('country','?')}\n"
               f"🏢 ISP: {info.get('isp','?')}\n"
               f"📱 {device}")
        send_telegram(msg)
    except: pass

# ── SSH ──

def expiration_date():
    return (datetime.now()+timedelta(days=DAYS_VALID)).strftime("%Y-%m-%d")

def expiration_pretty():
    return (datetime.now()+timedelta(days=DAYS_VALID)).strftime("%d/%m/%Y")

def ssh_run(ip, port, cmd, timeout=30):
    try:
        r = subprocess.run(["ssh","-i",SSH_KEY,"-p",str(port),"-o","StrictHostKeyChecking=no",
            "-o","ConnectTimeout=10","-o","BatchMode=yes","-o","PasswordAuthentication=no",
            f"root@{ip}",cmd], capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0: return True, r.stdout.strip()
        return False, r.stderr.strip()
    except subprocess.TimeoutExpired: return False, "Timeout"
    except Exception as e: return False, str(e)

def create_ssh_local(user, password):
    exp = expiration_date()
    os.system(f"id {user} >/dev/null 2>&1 && userdel -f {user} 2>/dev/null")
    os.system(f"useradd -M -s /bin/false -e {exp} {user} 2>/dev/null")
    os.system(f"echo '{user}:{password}' | chpasswd")
    os.system(f"chage -E {exp} -M 99999 {user}")
    os.system(f"usermod -f 0 {user}")
    return True, None

def create_ssh_remote(ip, port, user, password, bypass_pam=False):
    exp = expiration_date()
    if bypass_pam:
        try:
            h = subprocess.run(["openssl","passwd","-6",password], capture_output=True, text=True)
            pw_hash = h.stdout.strip() if h.returncode==0 else None
        except: pw_hash = None
        if not pw_hash:
            try:
                import crypt; pw_hash = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
            except: return False, "No hash"
        cmd = (f"id {user} >/dev/null 2>&1 && userdel -f {user} 2>/dev/null; "
               f"useradd -M -s /bin/false -e {exp} -p '{pw_hash}' {user} 2>/dev/null && "
               f"chage -E {exp} -M 99999 {user} && usermod -f 0 {user}")
    else:
        cmd = (f"id {user} >/dev/null 2>&1 && userdel -f {user} 2>/dev/null; "
               f"useradd -M -s /bin/false -e {exp} {user} 2>/dev/null && "
               f"echo '{user}:{password}' | chpasswd && "
               f"chage -E {exp} -M 99999 {user} && usermod -f 0 {user}")
    return ssh_run(ip, port, cmd)


def check_port(ip, port, timeout=3):
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((ip, port))
        s.close()
        return result == 0
    except: return False

def get_active_connections(ip, username, password):
    conns = []
    # UDP Custom 36712
    if check_port(ip, 36712):
        conns.append({"label":"UDP Custom", "value":f"{ip}:1-65535@{username}:{password}"})
    # SSL 443
    if check_port(ip, 443):
        conns.append({"label":"SSL/TLS 443", "value":f"{ip}:443@{username}:{password}"})
    # SSH Puerto 80
    if check_port(ip, 80):
        conns.append({"label":"SSH Puerto 80", "value":f"{ip}:80@{username}:{password}"})
    # SSH Puerto 22 siempre activo
    conns.append({"label":"SSH Directo", "value":f"{ip}:22@{username}:{password}"})
    return conns

def get_active_ports(ip):
    ports = []
    port_map = {
        22: "SSH: 22",
        53: "DNS: 53",
        80: "WEB: 80",
        443: "SSL: 443",
        5000: "SOCKS: 5000",
        7200: "BadVPN: 7200",
        7300: "BadVPN: 7300",
        8080: "SOCKS: 8080",
        36712: "UDP: 36712"
    }
    for port, label in port_map.items():
        if check_port(ip, port):
            ports.append(label)
    return "  |  ".join(ports) if ports else "SSH: 22"

def save_user(creator, username, vps_key):
    p = os.path.join(BASE_DIR, USERS_DB); users = []
    if os.path.exists(p):
        with open(p) as f: users = json.load(f)
    users.append({"creator_id":f"web:{creator}","username":username,"vps":vps_key,
        "expiration":(datetime.now()+timedelta(days=DAYS_VALID)).isoformat(),
        "created_at":datetime.now().isoformat()})
    with open(p,"w") as f: json.dump(users, f, indent=2)

# ── VMess ──

def load_vmess_db():
    p = os.path.join(BASE_DIR, VMESS_DB)
    if not os.path.exists(p): return []
    with open(p) as f: return json.load(f)

def save_vmess_db(data):
    with open(os.path.join(BASE_DIR, VMESS_DB), "w") as f: json.dump(data, f, indent=2)

def create_vmess_miami(email, days=3):
    user_id = str(uuid.uuid4())
    ok, out = ssh_run(MIAMI_IP, MIAMI_SSH_PORT, f"cat {V2RAY_CFG}")
    if not ok: return None
    try: config = json.loads(out)
    except: return None
    config["inbounds"][0]["settings"]["clients"].append({"id":user_id,"alterId":0,"email":email})
    new_cfg = json.dumps(config)
    cfg_b64 = base64.b64encode(new_cfg.encode()).decode()
    ssh_run(MIAMI_IP, MIAMI_SSH_PORT, f"echo {cfg_b64} | base64 -d > {V2RAY_CFG}")
    ssh_run(MIAMI_IP, MIAMI_SSH_PORT, "systemctl restart v2ray")
    vmess = {"v":"2","ps":"Miami-SSHFREE","add":"104.207.144.166","port":"443",
             "id":user_id,"aid":"0","net":"ws","type":"none",
             "host":"mia.darkfullhn.xyz","path":"/v2ray","tls":"tls"}
    link = "vmess://" + base64.b64encode(json.dumps(vmess).encode()).decode()
    users = load_vmess_db()
    users.append({"email":email,"id":user_id,
        "expiration":(datetime.now()+timedelta(days=days)).isoformat(),
        "created_at":datetime.now().isoformat()})
    save_vmess_db(users)
    return link

def delete_vmess_miami(user_id, email):
    ok, out = ssh_run(MIAMI_IP, MIAMI_SSH_PORT, f"cat {V2RAY_CFG}")
    if not ok: return
    try:
        config = json.loads(out)
        config["inbounds"][0]["settings"]["clients"] = [
            c for c in config["inbounds"][0]["settings"]["clients"]
            if c.get("id") != user_id and c.get("email") != email
        ]
        new_cfg = json.dumps(config)
        cfg_b64 = base64.b64encode(new_cfg.encode()).decode()
        ssh_run(MIAMI_IP, MIAMI_SSH_PORT, f"echo {cfg_b64} | base64 -d > {V2RAY_CFG}")
        ssh_run(MIAMI_IP, MIAMI_SSH_PORT, "systemctl restart v2ray")
    except: pass

def check_expired_vmess():
    while True:
        try:
            users = load_vmess_db(); now = datetime.now(); active = []
            for u in users:
                if now >= datetime.fromisoformat(u["expiration"]):
                    delete_vmess_miami(u["id"], u["email"])
                else: active.append(u)
            save_vmess_db(active)
        except Exception as e: print(f"VMess auto-delete: {e}")
        time.sleep(3600)

threading.Thread(target=check_expired_vmess, daemon=True).start()

# ── Admin ──

def gen_token():
    t = ''.join(random.choices(string.ascii_letters+string.digits, k=32))
    ADMIN_TOKENS[t] = datetime.now()+timedelta(hours=8)
    return t

def valid_token(token):
    if not token or token not in ADMIN_TOKENS: return False
    if datetime.now() > ADMIN_TOKENS[token]: del ADMIN_TOKENS[token]; return False
    return True

# ── Rutas ──

@app.route("/")
def index():
    with open(os.path.join(BASE_DIR, "iniciosshltm.html")) as f: return f.read()

@app.route("/crear")
def crear():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/zivvpn")
def zivvpn_page():
    with open("/var/www/sshfreeltm/zivvpn.html") as f: return f.read()

@app.route("/vmess")
def vmess_page():
    with open(os.path.join(BASE_DIR, "vmess.html")) as f: return f.read()

@app.route("/admin")
def admin():
    with open(os.path.join(BASE_DIR, "admin.html")) as f: return f.read()

@app.route("/api/visit")
def api_visit():
    cid = get_client_id(request)
    if cid not in notified_visitors:
        notified_visitors.add(cid)
        ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
        ua = request.headers.get("User-Agent","?")
        notify_admin(ip, ua)
    return jsonify({"ok":True})

@app.route("/api/status")
def api_status():
    cid = get_client_id(request); session = apply_regen(cid)
    if cid not in notified_visitors:
        notified_visitors.add(cid)
        ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
        ua = request.headers.get("User-Agent","?")
        notify_admin(ip, ua)
    return jsonify({"credits":session["credits"],"max_credits":WEB_MAX_CREDITS,
        "next_credit":time_to_next(cid),"regen_hours":WEB_REGEN_HOURS,"days_valid":DAYS_VALID})

@app.route("/api/create", methods=["POST"])
def api_create():
    cid = get_client_id(request); data = request.get_json()
    vps_key  = data.get("vps","").lower()
    username = data.get("username","").strip()
    password = data.get("password","").strip()
    if vps_key not in VPS: return jsonify({"ok":False,"error":"VPS invalida"}), 400
    if VPS[vps_key].get("MAINTENANCE"): return jsonify({"ok":False,"error":"Este servidor esta en mantenimiento. Usa Mexico por ahora."}), 503
    if not username or len(username)<3 or len(username)>20: return jsonify({"ok":False,"error":"Usuario entre 3 y 20 caracteres"}), 400
    if not username.isalnum(): return jsonify({"ok":False,"error":"Solo letras y numeros"}), 400
    if not password or len(password)<4: return jsonify({"ok":False,"error":"Contrasena minimo 4 caracteres"}), 400
    session = apply_regen(cid)
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
    is_admin_ip = client_ip in ADMIN_IPS
    if session["credits"] <= 0 and not is_admin_ip: return jsonify({"ok":False,"error":f"Sin creditos. Proximo en: {time_to_next(cid)}"}), 429
    ssh_user = f"ltmsshfree-{username}"; vps_info = VPS[vps_key]; port = vps_info.get("PORT",22)
    if vps_info["LOCAL"]: ok, err = create_ssh_local(ssh_user, password)
    else: ok, err = create_ssh_remote(vps_info["IP"],port,ssh_user,password,bypass_pam=vps_info.get("BYPASS_PAM",False))
    if not ok: return jsonify({"ok":False,"error":f"Error: {err}"}), 500
    if not is_admin_ip: spend_credit(cid)
    save_user(cid, ssh_user, vps_key); session_after = apply_regen(cid)
    ip_vis = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
    notify_admin_create(ip_vis, request.headers.get("User-Agent","?"), ssh_user, vps_key)
    ip = vps_info["IP"]; domain = vps_info["DOMAIN"]
    # Generar conexiones dinamicas del VPS
    raw_conns = vps_info.get("CONNECTIONS", [])
    active_conns = []
    for c in raw_conns:
        val = c["value"].replace("[IP]", ip).replace("[USER]", ssh_user).replace("[PASS]", password)
        active_conns.append({"label": c["label"], "value": val})
    return jsonify({"ok":True,"username":ssh_user,"password":password,"vps":vps_key,
        "vps_name":vps_info["NAME"],"flag":"","ip":ip,"domain":domain,"ns":vps_info["NS"],
        "ports":vps_info.get("PORTS","SSH:22"),
        "expiration":expiration_pretty(),"days":DAYS_VALID,
        "credits_left":session_after["credits"],
        "active_connections":active_conns,
        "connections":{"udp":f"{ip}:1-65535@{ssh_user}:{password}",
            "ssl":f"{ip}:443@{ssh_user}:{password}",
            "ssh80":f"{ip}:80@{ssh_user}:{password}",
            "domain":f"{domain}:80@{ssh_user}:{password}"}})

@app.route("/api/vmess/create", methods=["POST"])
def api_vmess_create():
    cid  = get_client_id(request); data = request.get_json()
    name = data.get("name","").strip()
    if not name or len(name)<3 or not name.isalnum():
        return jsonify({"ok":False,"error":"Nombre invalido"}), 400
    session = apply_regen(cid)
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
    is_admin_ip = client_ip in ADMIN_IPS
    if session["credits"] <= 0 and not is_admin_ip:
        return jsonify({"ok":False,"error":f"Sin creditos. Proximo en: {time_to_next(cid)}"}), 429
    email = f"vmess-{name}-{cid[:6]}"
    link  = create_vmess_miami(email, days=3)
    if not link: return jsonify({"ok":False,"error":"Error creando VMess en Miami"}), 500
    spend_credit(cid)
    exp = (datetime.now()+timedelta(days=3)).strftime("%d/%m/%Y")
    return jsonify({"ok":True,"vmess":link,"expiration":exp,"days":3})

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    if data.get("password") == ADMIN_PASSWORD: return jsonify({"ok":True,"token":gen_token()})
    return jsonify({"ok":False,"error":"Contrasena incorrecta"}), 401

@app.route("/api/admin/stats")
def admin_stats():
    if not valid_token(request.headers.get("X-Token")): return jsonify({"error":"No autorizado"}), 401
    p = os.path.join(BASE_DIR, USERS_DB); users = []
    if os.path.exists(p):
        with open(p) as f: users = json.load(f)
    banned = {}
    if os.path.exists(os.path.join(BASE_DIR,"banned.json")):
        with open(os.path.join(BASE_DIR,"banned.json")) as f: banned = json.load(f)
    coupons = {}
    if os.path.exists(os.path.join(BASE_DIR,"coupons.json")):
        with open(os.path.join(BASE_DIR,"coupons.json")) as f: coupons = json.load(f)
    sessions = load_sessions(); by_vps = {}
    for u in users:
        v = u.get("vps","?"); by_vps[v] = by_vps.get(v,0)+1
    return jsonify({"total_users":len(users),"total_banned":len(banned),
        "total_coupons":len(coupons),"total_sessions":len(sessions),
        "by_vps":by_vps,"users":users,
        "banned":[{"id":k,**v} for k,v in banned.items()],
        "coupons":[{"code":k,**v} for k,v in coupons.items()]})

@app.route("/api/admin/genkey", methods=["POST"])
def admin_genkey():
    if not valid_token(request.headers.get("X-Token")): return jsonify({"error":"No autorizado"}), 401
    data = request.get_json(); credits = int(data.get("credits",1))
    code = "key-ltmssh:"+''.join(random.choices(string.digits, k=8))
    p = os.path.join(BASE_DIR,"coupons.json"); coupons = {}
    if os.path.exists(p):
        with open(p) as f: coupons = json.load(f)
    coupons[code] = {"credits":credits,"used":False,"used_by":None,"created_at":datetime.now().isoformat()}
    with open(p,"w") as f: json.dump(coupons, f, indent=2)
    return jsonify({"ok":True,"code":code,"credits":credits})

@app.route("/api/admin/delete_user", methods=["POST"])
def admin_delete_user():
    if not valid_token(request.headers.get("X-Token")): return jsonify({"error":"No autorizado"}), 401
    data = request.get_json(); username = data.get("username")
    p = os.path.join(BASE_DIR, USERS_DB); users = []
    if os.path.exists(p):
        with open(p) as f: users = json.load(f)
    target = next((u for u in users if u["username"]==username), None)
    if not target: return jsonify({"ok":False,"error":"No encontrado"}), 404
    vps_info = VPS.get(target["vps"],{})
    if vps_info.get("LOCAL"):
        os.system(f"pkill -u {username} 2>/dev/null; userdel -f {username} 2>/dev/null")
    else:
        ip = vps_info.get("IP",""); port = vps_info.get("PORT",22)
        subprocess.run(["ssh","-i",SSH_KEY,"-p",str(port),"-o","StrictHostKeyChecking=no",
            "-o","BatchMode=yes",f"root@{ip}",
            f"pkill -u {username} 2>/dev/null; userdel -f {username} 2>/dev/null"],
            capture_output=True, timeout=15)
    users = [u for u in users if u["username"]!=username]
    with open(p,"w") as f: json.dump(users, f, indent=2)
    return jsonify({"ok":True})


RICHMOND_IP = "165.245.164.107"
RICHMOND_SSH_PORT = 22
ZIVPN_PORT = 5667

def create_zivpn_user(password, days=3):
    import datetime as dt
    exp_date = (dt.datetime.now() + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cmd = (
        "python3 -c \"import json,datetime,subprocess;"
        "users=json.load(open('/etc/zivpn/users.json')) if __import__('os').path.exists('/etc/zivpn/users.json') else [];"
        f"users.append({{'password':'{password}','expires':'{exp_date}','created':str(datetime.datetime.now())}});"
        "open('/etc/zivpn/users.json','w').write(__import__('json').dumps(users,indent=2));"
        "now=datetime.datetime.now();"
        "active=[u['password'] for u in users if datetime.datetime.fromisoformat(u['expires'][:19])>now];"
        "active=active or ['zi'];"
        "cfg=json.load(open('/etc/zivpn/config.json'));"
        "cfg['auth']['config']=list(set(cfg['auth']['config']+active));"
        "open('/etc/zivpn/config.json','w').write(json.dumps(cfg,indent=2));"
        "subprocess.run(['systemctl','restart','zivpn'])\"")
    return ssh_run(RICHMOND_IP, RICHMOND_SSH_PORT, cmd)

@app.route("/api/zivpn/create", methods=["POST"])
def api_zivpn_create():
    import datetime as dt, re
    data = request.get_json() or {}
    cid = get_client_id(request)
    session = apply_regen(cid)
    client_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
    is_admin_ip = client_ip in ADMIN_IPS
    if session["credits"] <= 0 and not is_admin_ip:
        return jsonify({"ok":False,"error":f"Sin creditos. Proximo en: {time_to_next(cid)}"}), 429
    suffix = data.get("suffix","").strip()
    if not suffix or len(suffix) < 3:
        return jsonify({"ok":False,"error":"Sufijo minimo 3 caracteres"}), 400
    if not re.match(r"^[a-zA-Z0-9]+$", suffix):
        return jsonify({"ok":False,"error":"Solo letras y numeros"}), 400
    password = f"ltmfreessh-{suffix}"
    ok, out = create_zivpn_user(password, DAYS_VALID)
    if not ok:
        return jsonify({"ok":False,"error":f"Error: {out}"}), 500
    if not is_admin_ip: spend_credit(cid)
    session_after = apply_regen(cid)
    exp = (dt.datetime.now() + dt.timedelta(days=DAYS_VALID)).strftime("%d/%m/%Y")
    # Notificar al admin
    try:
        client_ip2 = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For","").split(",")[0].strip() or request.remote_addr
        info = get_ip_info(client_ip2)
        ua = request.headers.get("User-Agent","")
        device = parse_device(ua)
        msg = (f"🔐 *ZIV VPN CREADA DESDE WEB*\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"🔑 Password: `{password}`\n"
               f"🌐 VPS: Richmond USA\n"
               f"🔌 Puerto: 5667\n"
               f"📅 Expira: {exp}\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"🌍 IP Visitante: `{client_ip2}`\n"
               f"📍 {info.get('city','?')}, {info.get('regionName','?')}, {info.get('country','?')}\n"
               f"🏢 ISP: {info.get('isp','?')}\n"
               f"📱 {device}")
        send_telegram(msg)
    except: pass
    return jsonify({"ok":True,"password":password,"ip":RICHMOND_IP,"port":ZIVPN_PORT,"expiration":exp,"days":DAYS_VALID,"credits_left":session_after["credits"]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

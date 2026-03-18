import os, subprocess, signal, time, zipfile, json, shutil, io
from flask import Flask, render_template, render_template_string, request, redirect, url_for, session, jsonify, send_file

app = Flask(__name__)
app.secret_key = "ckrpro_ultimate_v6_final_2026"

# Config
UPLOAD_FOLDER = "uploads"
DB_FILE = "database.json"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Global process tracker
processes = {}

# --- DATABASE LOGIC ---
def load_db():
    if not os.path.exists(DB_FILE):
        default = {"user_pw": "codex123", "users": {}, "start_times": {}}
        with open(DB_FILE, "w") as f: json.dump(default, f, indent=4)
        return default
    with open(DB_FILE, "r") as f:
        try:
            data = json.load(f)
            if "users" not in data: data["users"] = {}
            if "user_pw" not in data: data["user_pw"] = "codex123"
            if "start_times" not in data: data["start_times"] = {}
            return data
        except:
            return {"user_pw": "codex123", "users": {}, "start_times": {}}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

ADMIN_PASS = "5656"

# --- INLINE LOGIN TEMPLATE ---
LOGIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login | CKRPRO</title>
    <style>
        body { background: #f8f9fa; color: #1a1a1a; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-card { background: #fff; padding: 35px; border-radius: 20px; width: 300px; text-align: center; border: 1px solid #eee; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        h2 { font-size: 18px; margin-bottom: 20px; font-weight: 800; color: #007aff; }
        input, select { width: 100%; padding: 12px; margin: 10px 0; border-radius: 10px; border: 1px solid #ddd; background: #fff; box-sizing: border-box; outline: none; font-size: 14px; }
        button { width: 100%; padding: 12px; border-radius: 10px; border: none; background: #007aff; color: #fff; font-weight: bold; cursor: pointer; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="login-card">
        <h2>SYSTEM ACCESS</h2>
        <form method="post" action="/login">
            <select name="login_type">
                <option value="user">USER ACCESS</option>
                <option value="admin">ADMIN ROOT</option>
            </select>
            <input type="text" name="username" placeholder="Nickname" required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">LOGIN</button>
        </form>
    </div>
</body>
</html>
'''

# --- AUTH ROUTES ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        l_type = request.form.get("login_type")
        username = request.form.get("username", "").strip().lower()
        pw = request.form.get("password", "").strip()
        db = load_db()
        if l_type == "admin" and username == "admin" and pw == ADMIN_PASS:
            session['is_admin'], session['username'] = True, "admin"
            return redirect(url_for("index"))
        elif l_type == "user":
            if username not in db["users"]:
                db["users"][username] = db["user_pw"]
                save_db(db)
            if pw == db["users"].get(username):
                session['is_admin'], session['username'] = False, username
                return redirect(url_for("index"))
    return render_template_string(LOGIN_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- CORE DASHBOARD ---
@app.route("/")
def index():
    if 'username' not in session: return redirect(url_for("login"))
    u_dir = os.path.join(UPLOAD_FOLDER, session['username'])
    os.makedirs(u_dir, exist_ok=True)
    # Filter only folders (apps)
    apps_list = [{"name": n} for n in os.listdir(u_dir) if os.path.isdir(os.path.join(u_dir, n))]
    return render_template("index.html", apps=apps_list, username=session['username'])

# --- APP PROCESS CONTROL ---
@app.route("/run/<name>")
def run(name):
    user_name = session['username']
    extract_path = os.path.join(UPLOAD_FOLDER, user_name, name, "extracted")
    
    # Identify entry file
    main_file = next((f for f in ["main.py", "bot.py", "index.js", "app.py"] if os.path.exists(os.path.join(extract_path, f))), None)
    
    if main_file:
        log_path = os.path.join(UPLOAD_FOLDER, user_name, name, "logs.txt")
        cmd = ["python3", main_file] if main_file.endswith('.py') else ["node", main_file]
        
        # ADVANCED PROCESS KILL using os.setsid to kill children later
        processes[(user_name, name)] = subprocess.Popen(
            cmd, 
            cwd=extract_path, 
            stdout=open(log_path, "a"), 
            stderr=open(log_path, "a"), 
            preexec_fn=os.setsid
        )
    return redirect(url_for("index"))

@app.route("/stop/<name>")
def stop(name):
    user_name = session['username']
    p = processes.get((user_name, name))
    if p:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except:
            p.terminate()
        del processes[(user_name, name)]
    return redirect(url_for("index"))

@app.route("/restart/<name>")
def restart(name):
    stop(name)
    time.sleep(1)
    return run(name)

# --- TERMINAL & FILE SYSTEM API ---
@app.route("/execute_command", methods=["POST"])
def execute_command():
    data = request.json
    path = os.path.join(UPLOAD_FOLDER, session['username'], data['name'], "extracted")
    try:
        # Executes shell command and returns output
        output = subprocess.check_output(data['command'], shell=True, cwd=path, stderr=subprocess.STDOUT, text=True, timeout=10)
        return jsonify({"output": output})
    except Exception as e:
        return jsonify({"output": str(e)})

@app.route("/list_files/<name>")
def list_files(name):
    path = os.path.join(UPLOAD_FOLDER, session['username'], name, "extracted")
    files = []
    if os.path.exists(path):
        for root, _, filenames in os.walk(path):
            for f in filenames:
                rel_path = os.path.relpath(os.path.join(root, f), path)
                files.append(rel_path)
    return jsonify({"files": sorted(files)})

@app.route("/read_file", methods=["POST"])
def read_file():
    data = request.json
    file_path = os.path.join(UPLOAD_FOLDER, session['username'], data['project'], "extracted", data['filename'])
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return jsonify({"content": f.read()})
    except:
        return jsonify({"content": "Error reading file."})

@app.route("/save_file", methods=["POST"])
def save_file():
    data = request.json
    file_path = os.path.join(UPLOAD_FOLDER, session['username'], data['project'], "extracted", data['filename'])
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data['content'])
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/delete_file", methods=["POST"])
def delete_file_api():
    data = request.json
    path = os.path.join(UPLOAD_FOLDER, session['username'], data['project'], "extracted", data['filename'])
    try:
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"status": "deleted"})
    except:
        return jsonify({"status": "error"})

@app.route("/get_log/<name>")
def get_log(name):
    log_path = os.path.join(UPLOAD_FOLDER, session['username'], name, "logs.txt")
    log_content = ""
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            log_content = f.read()[-2000:] # Last 2000 chars
    
    p = processes.get((session['username'], name))
    status = "RUNNING" if (p and p.poll() is None) else "OFFLINE"
    return jsonify({"log": log_content, "status": status})

# --- FILE OPERATIONS ---
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if file and file.filename.endswith(".zip"):
        app_name = file.filename.rsplit('.', 1)[0].replace(" ", "_")
        user_path = os.path.join(UPLOAD_FOLDER, session['username'], app_name)
        
        if os.path.exists(user_path):
            shutil.rmtree(user_path)
        
        os.makedirs(user_path)
        zip_path = os.path.join(user_path, "project.zip")
        file.save(zip_path)
        
        # Extract ZIP
        extract_dir = os.path.join(user_path, "extracted")
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_dir)
        
        os.remove(zip_path)
    return redirect(url_for("index"))

@app.route("/delete/<name>")
def delete_app(name):
    stop(name)
    app_path = os.path.join(UPLOAD_FOLDER, session['username'], name)
    if os.path.exists(app_path):
        shutil.rmtree(app_path)
    return redirect(url_for("index"))

@app.route("/download/<name>")
def download_app(name):
    extract_dir = os.path.join(UPLOAD_FOLDER, session['username'], name, "extracted")
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(extract_dir):
            for f in files:
                z.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), extract_dir))
    memory_file.seek(0)
    return send_file(memory_file, download_name=f"{name}_backup.zip", as_attachment=True)

if __name__ == "__main__":
    # Change port if needed
    app.run(host="0.0.0.0", port=3522, debug=False)

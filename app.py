import os
import json
import shutil
import secrets
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

# ─── Flask App ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", secrets.token_hex(32))
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

ALLOWED_EXTENSIONS = {'pdf', 'csv', 'xlsx', 'xls'}

# ─── MySQL Connection ────────────────────────────────────────────────────────
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'sai#1919'),
    'database': os.getenv('DB_NAME', 'intelli_credit'),
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def init_database():
    """Create database and tables on first run."""
    # First connect without database to create it
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}`")
    conn.commit()
    cur.close()
    conn.close()

    # Now connect to the database and create tables
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            name VARCHAR(50) PRIMARY KEY,
            default_permissions JSON NOT NULL,
            allowed_child_roles JSON NOT NULL,
            hierarchy_order INT DEFAULT 999,
            description VARCHAR(255)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(200) NOT NULL,
            role VARCHAR(50) NOT NULL,
            custom_permissions JSON DEFAULT NULL,
            created_by INT DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role) REFERENCES roles(name)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(50) UNIQUE NOT NULL,
            company_name VARCHAR(200) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending',
            current_layer INT DEFAULT 0,
            layer2_output LONGTEXT DEFAULT NULL,
            risk_score FLOAT DEFAULT NULL,
            decision VARCHAR(50) DEFAULT NULL,
            decision_conditions TEXT DEFAULT NULL,
            created_by INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME DEFAULT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            application_id INT NOT NULL,
            filename VARCHAR(255) NOT NULL,
            file_type VARCHAR(10) NOT NULL,
            file_size INT DEFAULT 0,
            detected_category VARCHAR(30) DEFAULT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            file_path VARCHAR(500) NOT NULL,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            actor_id INT NOT NULL,
            action VARCHAR(100) NOT NULL,
            target VARCHAR(200) DEFAULT NULL,
            details JSON DEFAULT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX (actor_id),
            INDEX (action)
        )
    """)

    # ─── Seed Default Roles ──────────────────────────────────────────────────
    default_roles = [
        ("SUPER_ADMIN", json.dumps(["*"]), json.dumps(["CREDIT_ANALYST", "VIEWER"]), 1, "Full System Control"),
        ("CREDIT_ANALYST", json.dumps(["CREATE_APP","RUN_PIPELINE","VIEW_RESULTS","VIEW_HISTORY","VIEW_APP"]), json.dumps(["VIEWER"]), 2, "Credit Analyst"),
        ("VIEWER", json.dumps(["VIEW_RESULTS","VIEW_HISTORY","VIEW_APP"]), json.dumps([]), 3, "Read-Only Viewer"),
    ]
    for r in default_roles:
        cur.execute("""
            INSERT IGNORE INTO roles (name, default_permissions, allowed_child_roles, hierarchy_order, description)
            VALUES (%s, %s, %s, %s, %s)
        """, r)

    # ─── Seed Default Super Admin ────────────────────────────────────────────
    cur.execute("SELECT id FROM users WHERE username='admin'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role)
            VALUES (%s, %s, %s, %s)
        """, ("admin", generate_password_hash("admin123"), "Super Administrator", "SUPER_ADMIN"))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database initialized successfully.")


# ─── Helpers ─────────────────────────────────────────────────────────────────
def get_user_permissions(user_role, custom_perms=None):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT default_permissions FROM roles WHERE name=%s", (user_role,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return []
    perms = json.loads(row['default_permissions']) if isinstance(row['default_permissions'], str) else row['default_permissions']
    if custom_perms:
        custom = json.loads(custom_perms) if isinstance(custom_perms, str) else custom_perms
        perms = list(set(perms + custom))
    return perms

def has_permission(permission):
    if not session.get('user_id'):
        return False
    perms = session.get('permissions', [])
    return '*' in perms or permission in perms

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not has_permission(permission):
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def log_audit(actor_id, action, target=None, details=None):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO audit_logs (actor_id, action, target, details) VALUES (%s,%s,%s,%s)",
                    (actor_id, action, target, json.dumps(details) if details else None))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Audit log error: {e}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_case_id():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM applications")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return f"APP-2025-{str(count + 1).zfill(5)}"


# ─── Auth Routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session['permissions'] = get_user_permissions(user['role'], user.get('custom_permissions'))
            session['is_super_admin'] = user['role'] == 'SUPER_ADMIN'
            log_audit(user['id'], 'LOGIN', user['username'])
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

@app.route('/logout')
def logout():
    if session.get('user_id'):
        log_audit(session['user_id'], 'LOGOUT')
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


# ─── Role Management APIs ────────────────────────────────────────────────────
@app.route('/api/roles/list')
@login_required
def list_roles():
    assignable = request.args.get('assignable', 'false') == 'true'
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if assignable and not session.get('is_super_admin'):
        # Return only child roles of the current user's role
        cur.execute("SELECT allowed_child_roles FROM roles WHERE name=%s", (session['role'],))
        row = cur.fetchone()
        if row:
            children = json.loads(row['allowed_child_roles']) if isinstance(row['allowed_child_roles'], str) else row['allowed_child_roles']
            if children:
                placeholders = ','.join(['%s'] * len(children))
                cur.execute(f"SELECT * FROM roles WHERE name IN ({placeholders}) ORDER BY hierarchy_order", tuple(children))
            else:
                cur.close()
                conn.close()
                return jsonify([])
        else:
            cur.close()
            conn.close()
            return jsonify([])
    else:
        cur.execute("SELECT * FROM roles ORDER BY hierarchy_order")

    roles = cur.fetchall()
    # Parse JSON fields
    for r in roles:
        r['default_permissions'] = json.loads(r['default_permissions']) if isinstance(r['default_permissions'], str) else r['default_permissions']
        r['allowed_child_roles'] = json.loads(r['allowed_child_roles']) if isinstance(r['allowed_child_roles'], str) else r['allowed_child_roles']
    cur.close()
    conn.close()
    return jsonify(roles)

@app.route('/api/roles/create', methods=['POST'])
@login_required
@permission_required('MANAGE_ROLES')
def create_role():
    data = request.json
    name = data.get('name', '').upper().replace(' ', '_')
    permissions = data.get('permissions', [])
    children = data.get('allowed_child_roles', [])
    description = data.get('description', '')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT MAX(hierarchy_order) FROM roles")
    max_order = cur.fetchone()[0] or 0

    try:
        cur.execute("""
            INSERT INTO roles (name, default_permissions, allowed_child_roles, hierarchy_order, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, json.dumps(permissions), json.dumps(children), max_order + 1, description))
        conn.commit()
        log_audit(session['user_id'], 'CREATE_ROLE', name)
        return jsonify({"status": "ok", "message": f"Role '{name}' created"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/api/roles/update_perms', methods=['POST'])
@login_required
@permission_required('MANAGE_ROLES')
def update_role_perms():
    data = request.json
    role_name = data.get('role')
    permissions = data.get('permissions', [])
    children = data.get('allowed_child_roles', [])

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE roles SET default_permissions=%s, allowed_child_roles=%s WHERE name=%s",
                (json.dumps(permissions), json.dumps(children), role_name))
    conn.commit()
    log_audit(session['user_id'], 'UPDATE_ROLE_PERMS', role_name)
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/roles/reorder', methods=['POST'])
@login_required
@permission_required('MANAGE_ROLES')
def reorder_roles():
    data = request.json
    roles = data.get('roles', [])
    conn = get_db()
    cur = conn.cursor()
    for i, role_name in enumerate(roles):
        cur.execute("UPDATE roles SET hierarchy_order=%s WHERE name=%s", (i + 1, role_name))
    conn.commit()
    log_audit(session['user_id'], 'REORDER_ROLES', details={"order": roles})
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/roles/delete', methods=['POST'])
@login_required
@permission_required('MANAGE_ROLES')
def delete_role():
    data = request.json
    role_name = data.get('role')
    reassign_to = data.get('reassign_to')

    if role_name == 'SUPER_ADMIN':
        return jsonify({"error": "Cannot delete SUPER_ADMIN"}), 400

    conn = get_db()
    cur = conn.cursor()
    if reassign_to:
        cur.execute("UPDATE users SET role=%s WHERE role=%s", (reassign_to, role_name))
    cur.execute("DELETE FROM roles WHERE name=%s", (role_name,))
    conn.commit()
    log_audit(session['user_id'], 'DELETE_ROLE', role_name)
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/roles/permissions')
@login_required
def list_permissions():
    all_perms = [
        "CREATE_APP", "VIEW_APP", "DELETE_APP", "RUN_PIPELINE",
        "VIEW_RESULTS", "MANAGE_USERS", "MANAGE_ROLES",
        "VIEW_HISTORY", "VIEW_AUDIT_LOGS", "SYSTEM_SETTINGS"
    ]
    return jsonify(all_perms)


# ─── User Management APIs ────────────────────────────────────────────────────
@app.route('/api/users/list')
@login_required
@permission_required('MANAGE_USERS')
def list_users():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT u.id, u.username, u.full_name, u.role, u.created_at,
               c.full_name as created_by_name
        FROM users u LEFT JOIN users c ON u.created_by = c.id
        ORDER BY u.created_at DESC
    """)
    users = cur.fetchall()
    for u in users:
        if u.get('created_at'):
            u['created_at'] = u['created_at'].isoformat()
    cur.close()
    conn.close()
    return jsonify(users)

@app.route('/api/users/create', methods=['POST'])
@login_required
@permission_required('MANAGE_USERS')
def create_user():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    role = data.get('role', '')

    if not all([username, password, full_name, role]):
        return jsonify({"error": "All fields are required"}), 400

    # Verify creator can assign this role
    if not session.get('is_super_admin'):
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT allowed_child_roles FROM roles WHERE name=%s", (session['role'],))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            children = json.loads(row['allowed_child_roles']) if isinstance(row['allowed_child_roles'], str) else row['allowed_child_roles']
            if role not in children:
                return jsonify({"error": "You cannot create users with this role"}), 403

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (username, password_hash, full_name, role, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, generate_password_hash(password), full_name, role, session['user_id']))
        conn.commit()
        log_audit(session['user_id'], 'CREATE_USER', username, {"role": role})
        return jsonify({"status": "ok", "message": f"User '{username}' created"})
    except mysql.connector.IntegrityError:
        return jsonify({"error": "Username already exists"}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/api/users/delete', methods=['POST'])
@login_required
@permission_required('MANAGE_USERS')
def delete_user():
    data = request.json
    user_id = data.get('user_id')
    if user_id == session['user_id']:
        return jsonify({"error": "Cannot delete yourself"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    log_audit(session['user_id'], 'DELETE_USER', str(user_id))
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})


# ─── Application APIs ────────────────────────────────────────────────────────
@app.route('/api/applications', methods=['GET', 'POST'])
@login_required
def applications():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == 'POST':
        if not has_permission('CREATE_APP'):
            return jsonify({"error": "Forbidden"}), 403
        data = request.json
        company_name = data.get('company_name', '').strip()
        if not company_name:
            return jsonify({"error": "Company name is required"}), 400

        case_id = generate_case_id()
        cur.execute("""
            INSERT INTO applications (case_id, company_name, created_by)
            VALUES (%s, %s, %s)
        """, (case_id, company_name, session['user_id']))
        conn.commit()
        app_id = cur.lastrowid
        log_audit(session['user_id'], 'CREATE_APPLICATION', case_id)
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "id": app_id, "case_id": case_id})

    # GET — list applications
    cur.execute("""
        SELECT a.*, u.full_name as creator_name
        FROM applications a JOIN users u ON a.created_by = u.id
        ORDER BY a.created_at DESC
    """)
    apps = cur.fetchall()
    for a in apps:
        if a.get('created_at'):
            a['created_at'] = a['created_at'].isoformat()
        if a.get('completed_at'):
            a['completed_at'] = a['completed_at'].isoformat()
        # Don't send the full layer2_output in the list view
        a.pop('layer2_output', None)
    cur.close()
    conn.close()
    return jsonify(apps)

@app.route('/api/applications/<int:app_id>')
@login_required
def get_application(app_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM applications WHERE id=%s", (app_id,))
    app_data = cur.fetchone()
    if not app_data:
        cur.close()
        conn.close()
        return jsonify({"error": "Not found"}), 404

    # Parse layer2_output if present
    if app_data.get('layer2_output'):
        try:
            app_data['layer2_output'] = json.loads(app_data['layer2_output'])
        except:
            pass

    # Get documents
    cur.execute("SELECT * FROM documents WHERE application_id=%s ORDER BY uploaded_at", (app_id,))
    docs = cur.fetchall()
    for d in docs:
        if d.get('uploaded_at'):
            d['uploaded_at'] = d['uploaded_at'].isoformat()
    app_data['documents'] = docs

    if app_data.get('created_at'):
        app_data['created_at'] = app_data['created_at'].isoformat()
    if app_data.get('completed_at'):
        app_data['completed_at'] = app_data['completed_at'].isoformat()

    cur.close()
    conn.close()
    return jsonify(app_data)

@app.route('/api/applications/history')
@login_required
def application_history():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT a.id, a.case_id, a.company_name, a.status, a.risk_score, a.decision,
               a.created_at, a.completed_at, u.full_name as creator_name
        FROM applications a JOIN users u ON a.created_by = u.id
        WHERE a.status = 'completed'
        ORDER BY a.completed_at DESC
    """)
    apps = cur.fetchall()
    for a in apps:
        if a.get('created_at'):
            a['created_at'] = a['created_at'].isoformat()
        if a.get('completed_at'):
            a['completed_at'] = a['completed_at'].isoformat()
    cur.close()
    conn.close()
    return jsonify(apps)


# ─── File Upload API ─────────────────────────────────────────────────────────
@app.route('/api/upload/<int:app_id>', methods=['POST'])
@login_required
@permission_required('CREATE_APP')
def upload_files(app_id):
    if 'files' not in request.files:
        return jsonify({"error": "No files provided"}), 400

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM applications WHERE id=%s", (app_id,))
    app_data = cur.fetchone()
    if not app_data:
        cur.close()
        conn.close()
        return jsonify({"error": "Application not found"}), 404

    # Create upload directory for this application
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(app_id))
    os.makedirs(upload_dir, exist_ok=True)

    files = request.files.getlist('files')
    uploaded = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(upload_dir, filename)
            file.save(file_path)

            ext = filename.rsplit('.', 1)[1].lower()
            file_type = 'PDF' if ext == 'pdf' else 'Excel' if ext in ['xlsx','xls'] else 'CSV'
            file_size = os.path.getsize(file_path)

            cur2 = conn.cursor()
            cur2.execute("""
                INSERT INTO documents (application_id, filename, file_type, file_size, status, file_path)
                VALUES (%s, %s, %s, %s, 'pending', %s)
            """, (app_id, filename, file_type, file_size, file_path))
            conn.commit()
            doc_id = cur2.lastrowid
            cur2.close()

            uploaded.append({"id": doc_id, "filename": filename, "file_type": file_type, "file_size": file_size})

    log_audit(session['user_id'], 'UPLOAD_FILES', app_data['case_id'], {"count": len(uploaded)})
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "uploaded": uploaded, "count": len(uploaded)})


# ─── Pipeline Execution (WebSocket) ──────────────────────────────────────────
@socketio.on('run_pipeline')
def handle_run_pipeline(data):
    app_id = data.get('app_id')
    if not app_id:
        emit('pipeline_error', {"error": "No app_id provided"})
        return

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Get application
    cur.execute("SELECT * FROM applications WHERE id=%s", (app_id,))
    app_data = cur.fetchone()
    if not app_data:
        emit('pipeline_error', {"error": "Application not found"})
        cur.close()
        conn.close()
        return

    # Get documents
    cur.execute("SELECT * FROM documents WHERE application_id=%s", (app_id,))
    docs = cur.fetchall()
    if not docs:
        emit('pipeline_error', {"error": "No documents uploaded"})
        cur.close()
        conn.close()
        return

    # Update status
    cur2 = conn.cursor()
    cur2.execute("UPDATE applications SET status='processing', current_layer=1 WHERE id=%s", (app_id,))
    conn.commit()
    cur2.close()

    # ─── Layer 1: Data Ingestion (classification) ────────────────────────
    emit('layer_progress', {"layer": 1, "name": "Data Ingestion", "status": "processing", "pct": 10})

    from layer2.utils.dispatcher import DocumentDispatcher

    filepaths = []
    for i, doc in enumerate(docs):
        try:
            meta = DocumentDispatcher.ingest(doc['file_path'])
            # Update detected category in DB
            cur3 = conn.cursor()
            cur3.execute("UPDATE documents SET detected_category=%s, status='done' WHERE id=%s",
                        (meta['target_key'], doc['id']))
            conn.commit()
            cur3.close()
            filepaths.append(doc['file_path'])
            pct = 10 + int((i + 1) / len(docs) * 40)
            emit('layer_progress', {"layer": 1, "name": "Data Ingestion", "status": "processing", "pct": pct})
        except Exception as e:
            print(f"Dispatch error for {doc['filename']}: {e}")

    emit('layer_complete', {"layer": 1, "name": "Data Ingestion", "status": "done"})

    # ─── Layer 2: Financial Extraction ───────────────────────────────────
    emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 5})

    cur4 = conn.cursor()
    cur4.execute("UPDATE applications SET current_layer=2 WHERE id=%s", (app_id,))
    conn.commit()
    cur4.close()

    try:
        from layer2.layer2_processor import IntelliCreditPipeline
        pipeline = IntelliCreditPipeline()

        emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 30})

        result = pipeline.process_files(
            filepaths=filepaths,
            case_id=app_data['case_id'],
            company_name=app_data['company_name']
        )

        output_json = result.model_dump_json(indent=2)

        emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 90})

        # Save to DB
        cur5 = conn.cursor()
        cur5.execute("UPDATE applications SET layer2_output=%s, current_layer=3, status='completed', completed_at=NOW() WHERE id=%s",
                    (output_json, app_id))
        conn.commit()
        cur5.close()

        emit('layer_complete', {"layer": 2, "name": "Financial Extraction", "status": "done", "line_count": len(output_json.splitlines())})

    except Exception as e:
        print(f"Layer 2 pipeline error: {e}")
        cur6 = conn.cursor()
        cur6.execute("UPDATE applications SET status='failed' WHERE id=%s", (app_id,))
        conn.commit()
        cur6.close()
        emit('pipeline_error', {"error": str(e), "layer": 2})
        cur.close()
        conn.close()
        return

    # ─── Layers 3-6: Placeholder progress (future implementation) ────────
    layer_names = {
        3: "Anomaly Detection",
        4: "Web Research",
        5: "Risk Scoring",
        6: "CAM Generation"
    }
    import time
    for layer_num, layer_name in layer_names.items():
        emit('layer_progress', {"layer": layer_num, "name": layer_name, "status": "processing", "pct": 50})
        time.sleep(1.5)
        emit('layer_complete', {"layer": layer_num, "name": layer_name, "status": "done"})

    emit('pipeline_complete', {"app_id": app_id, "case_id": app_data['case_id'], "status": "completed"})
    log_audit(session.get('user_id', 0), 'RUN_PIPELINE', app_data['case_id'])

    cur.close()
    conn.close()


# ─── Audit Logs API ──────────────────────────────────────────────────────────
@app.route('/api/audit_logs')
@login_required
@permission_required('VIEW_AUDIT_LOGS')
def get_audit_logs():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT a.*, u.full_name as actor_name
        FROM audit_logs a LEFT JOIN users u ON a.actor_id = u.id
        ORDER BY a.timestamp DESC LIMIT 200
    """)
    logs = cur.fetchall()
    for log in logs:
        if log.get('timestamp'):
            log['timestamp'] = log['timestamp'].isoformat()
        if log.get('details') and isinstance(log['details'], str):
            try:
                log['details'] = json.loads(log['details'])
            except:
                pass
    cur.close()
    conn.close()
    return jsonify(logs)


# ─── Session Info API ─────────────────────────────────────────────────────────
@app.route('/api/session')
@login_required
def session_info():
    return jsonify({
        "user_id": session.get('user_id'),
        "username": session.get('username'),
        "full_name": session.get('full_name'),
        "role": session.get('role'),
        "permissions": session.get('permissions', []),
        "is_super_admin": session.get('is_super_admin', False)
    })


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_database()
    print("🚀 Intelli-Credit Engine starting on http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)

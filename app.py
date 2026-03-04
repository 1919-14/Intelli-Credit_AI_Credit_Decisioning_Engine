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
    conn = mysql.connector.connect(**DB_CONFIG, autocommit=False)
    return conn

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
            layer3_output LONGTEXT DEFAULT NULL,
            risk_score FLOAT DEFAULT NULL,
            decision VARCHAR(50) DEFAULT NULL,
            decision_conditions TEXT DEFAULT NULL,
            created_by INT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME DEFAULT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # Add layer3_output column if it doesn't exist (for existing databases)
    try:
        cur.execute("ALTER TABLE applications ADD COLUMN layer3_output LONGTEXT DEFAULT NULL AFTER layer2_output")
    except:
        pass  # Column already exists

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
        # Return only roles strictly BELOW the current user's hierarchy level
        cur.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (session['role'],))
        row = cur.fetchone()
        my_order = row['hierarchy_order'] if row else 999
        cur.execute(
            "SELECT * FROM roles WHERE hierarchy_order > %s ORDER BY hierarchy_order",
            (my_order,)
        )
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

@app.route('/api/roles/update_details', methods=['POST'])
@login_required
def update_role_details():
    perms = session.get('permissions', [])
    if '*' not in perms and 'EDIT_ROLES' not in perms:
        return jsonify({"error": "Forbidden"}), 403

    data = request.json
    role_name = data.get('role')
    new_desc = data.get('description')
    new_perms = data.get('permissions', [])

    if not role_name:
        return jsonify({"error": "Role name required"}), 400
    if role_name == 'SUPER_ADMIN':
        return jsonify({"error": "Cannot modify SUPER_ADMIN"}), 403

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE roles SET description = %s, default_permissions = %s WHERE name = %s",
                       (new_desc, json.dumps(new_perms), role_name))
        conn.commit()
        log_audit(session['user_id'], 'UPDATE_ROLE', target=f'role:{role_name}')
        return jsonify({"message": "Role updated"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
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
    if not role_name:
        return jsonify({"error": "Role name required"}), 400

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        # Check if any users are on this role
        cur.execute("SELECT COUNT(*) as cnt FROM users WHERE role=%s", (role_name,))
        row = cur.fetchone()
        user_count = row['cnt'] if row else 0

        if user_count > 0:
            if not reassign_to:
                # Return count so frontend can prompt user to pick a reassignment role
                return jsonify({
                    "error": f"{user_count} user(s) are assigned this role. Provide a 'reassign_to' role to proceed.",
                    "user_count": user_count,
                    "requires_reassign": True
                }), 409
            # Validate the target role exists
            cur2 = conn.cursor()
            cur2.execute("SELECT name FROM roles WHERE name=%s", (reassign_to,))
            if not cur2.fetchone():
                cur2.close()
                return jsonify({"error": f"Reassign target role '{reassign_to}' not found"}), 400
            cur2.close()
            # Reassign users first
            cur3 = conn.cursor()
            cur3.execute("UPDATE users SET role=%s WHERE role=%s", (reassign_to, role_name))
            cur3.close()

        # Now safe to delete the role
        cur4 = conn.cursor()
        cur4.execute("DELETE FROM roles WHERE name=%s", (role_name,))
        cur4.close()

        conn.commit()
        log_audit(session['user_id'], 'DELETE_ROLE', role_name,
                  {"reassigned_to": reassign_to, "user_count": user_count})
        return jsonify({"status": "ok"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/roles/permissions')
@login_required
def list_permissions():
    all_perms = [
        "CREATE_APP", "VIEW_APP", "DELETE_APP", "RUN_PIPELINE",
        "VIEW_RESULTS", "MANAGE_USERS", "MANAGE_ROLES",
        "VIEW_HISTORY", "VIEW_AUDIT_LOGS", "SYSTEM_SETTINGS",
        "EDIT_USERS", "EDIT_ROLES"
    ]
    return jsonify(all_perms)


# ─── User Management APIs ────────────────────────────────────────────────────
@app.route('/api/users/list')
@login_required
@permission_required('MANAGE_USERS')
def list_users():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if session.get('is_super_admin'):
        # Super Admin sees everyone
        cur.execute("""
            SELECT u.id, u.username, u.full_name, u.role, u.created_at,
                   c.full_name as created_by_name, r.hierarchy_order
            FROM users u
            LEFT JOIN users c ON u.created_by = c.id
            LEFT JOIN roles r ON u.role = r.name
            ORDER BY r.hierarchy_order ASC, u.created_at DESC
        """)
    else:
        # Get current user's hierarchy order
        cur.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (session['role'],))
        row = cur.fetchone()
        my_order = row['hierarchy_order'] if row else 999

        # Only return users whose role has a HIGHER order number (lower in hierarchy)
        cur.execute("""
            SELECT u.id, u.username, u.full_name, u.role, u.created_at,
                   c.full_name as created_by_name, r.hierarchy_order
            FROM users u
            LEFT JOIN users c ON u.created_by = c.id
            LEFT JOIN roles r ON u.role = r.name
            WHERE r.hierarchy_order > %s
            ORDER BY r.hierarchy_order ASC, u.created_at DESC
        """, (my_order,))

    users = cur.fetchall()
    for u in users:
        if u.get('created_at'):
            u['created_at'] = u['created_at'].isoformat()
        u.pop('hierarchy_order', None)  # Don't expose internals to frontend
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

    # Verify creator can assign this role (must be strictly lower in hierarchy)
    if not session.get('is_super_admin'):
        conn2 = get_db()
        cur2 = conn2.cursor(dictionary=True)
        cur2.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (session['role'],))
        my_row = cur2.fetchone()
        my_order = my_row['hierarchy_order'] if my_row else 999

        cur2.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (role,))
        target_row = cur2.fetchone()
        cur2.close()
        conn2.close()

        if not target_row or target_row['hierarchy_order'] <= my_order:
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

@app.route('/api/users/update', methods=['POST'])
@login_required
def update_user():
    perms = session.get('permissions', [])
    if '*' not in perms and 'EDIT_USERS' not in perms:
        return jsonify({"error": "Forbidden"}), 403

    data = request.json
    user_id = data.get('id')
    full_name = data.get('full_name')
    role = data.get('role')

    if not user_id or not full_name or not role:
        return jsonify({"error": "Missing fields"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        # Prevent non-SA from assigning SUPER_ADMIN
        if '*' not in perms and role == 'SUPER_ADMIN':
            return jsonify({"error": "Cannot assign SUPER_ADMIN role"}), 403

        if not session.get('is_super_admin'):
            # Get current user's hierarchy order
            cursor.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (session['role'],))
            my_row = cursor.fetchone()
            my_order = my_row['hierarchy_order'] if my_row else 999

            # Get target user's current role hierarchy
            cursor.execute("""
                SELECT r.hierarchy_order FROM users u
                JOIN roles r ON u.role = r.name
                WHERE u.id = %s
            """, (user_id,))
            target_row = cursor.fetchone()
            if not target_row or target_row['hierarchy_order'] <= my_order:
                return jsonify({"error": "You cannot edit users at your level or above"}), 403

            # Also verify the NEW role is below current user
            cursor.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (role,))
            new_role_row = cursor.fetchone()
            if not new_role_row or new_role_row['hierarchy_order'] <= my_order:
                return jsonify({"error": "You cannot assign a role at your level or above"}), 403

        cursor2 = conn.cursor()
        cursor2.execute("UPDATE users SET full_name = %s, role = %s WHERE id = %s",
                       (full_name, role, user_id))

        if cursor2.rowcount == 0:
            conn.rollback()
            cursor2.close()
            return jsonify({"error": "User not found or no changes"}), 404

        cursor2.close()
        conn.commit()
        log_audit(session['user_id'], 'UPDATE_USER', target=f'user_id:{user_id}')
        return jsonify({"message": "User updated successfully"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
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
    cur = conn.cursor(dictionary=True)
    try:
        if not session.get('is_super_admin'):
            # Get current user's hierarchy order
            cur.execute("SELECT hierarchy_order FROM roles WHERE name=%s", (session['role'],))
            my_row = cur.fetchone()
            my_order = my_row['hierarchy_order'] if my_row else 999

            # Check target user's role hierarchy
            cur.execute("""
                SELECT r.hierarchy_order FROM users u
                JOIN roles r ON u.role = r.name
                WHERE u.id = %s
            """, (user_id,))
            target_row = cur.fetchone()
            if not target_row or target_row['hierarchy_order'] <= my_order:
                return jsonify({"error": "You cannot delete users at your level or above"}), 403

        cur2 = conn.cursor()
        cur2.execute("DELETE FROM users WHERE id=%s", (user_id,))
        cur2.close()
        conn.commit()
        log_audit(session['user_id'], 'DELETE_USER', str(user_id))
        return jsonify({"status": "ok"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


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

    # Parse layer3_output if present
    if app_data.get('layer3_output'):
        try:
            app_data['layer3_output'] = json.loads(app_data['layer3_output'])
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

    review_items = []
    for i, doc in enumerate(docs):
        try:
            meta = DocumentDispatcher.ingest(doc['file_path'])
            # Update detected category in DB
            cur3 = conn.cursor()
            cur3.execute("UPDATE documents SET detected_category=%s, status='done' WHERE id=%s",
                        (meta['target_key'], doc['id']))
            conn.commit()
            cur3.close()

            review_items.append({
                "doc_id": doc['id'],
                "filename": doc['filename'],
                "file_type": doc['file_type'],
                "detected_category": meta['target_key'],
                "pages": meta.get('pages', 1),
                "ocr_required": meta.get('ocr_required', False),
                "file_path": doc['file_path']
            })

            pct = 10 + int((i + 1) / len(docs) * 40)
            emit('layer_progress', {"layer": 1, "name": "Data Ingestion", "status": "processing", "pct": pct})
        except Exception as e:
            print(f"Dispatch error for {doc['filename']}: {e}")
            review_items.append({
                "doc_id": doc['id'],
                "filename": doc['filename'],
                "file_type": doc['file_type'],
                "detected_category": "SRC_UNKNOWN",
                "pages": 1,
                "ocr_required": False,
                "file_path": doc['file_path']
            })

    emit('layer_complete', {"layer": 1, "name": "Data Ingestion", "status": "done"})

    # ─── HITL PAUSE: Save review data & wait for human confirmation ──────
    cur_hitl = conn.cursor()
    cur_hitl.execute(
        "UPDATE applications SET status='awaiting_review' WHERE id=%s",
        (app_id,)
    )
    conn.commit()
    cur_hitl.close()

    # Join a room so the confirm endpoint can notify this client
    from flask_socketio import join_room
    join_room(f'app_{app_id}')

    emit('hitl_review_needed', {
        "app_id": app_id,
        "case_id": app_data['case_id'],
        "company_name": app_data['company_name'],
        "documents": review_items
    })

    cur.close()
    conn.close()
    # Pipeline STOPS here — Layer 2 will be triggered by confirm_docs endpoint


# ─── HITL: Confirm Documents & Resume Pipeline ───────────────────────────────
@app.route('/api/applications/<int:app_id>/review_docs')
@login_required
def review_docs(app_id):
    """Return current doc classification data for review."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id as doc_id, filename, file_type, detected_category, file_path
        FROM documents WHERE application_id=%s ORDER BY id
    """, (app_id,))
    docs = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(docs)


@app.route('/api/applications/<int:app_id>/confirm_docs', methods=['POST'])
@login_required
def confirm_docs(app_id):
    """Accept user-confirmed/corrected doc categories, then resume pipeline."""
    data = request.json
    corrections = data.get('documents', [])  # [{doc_id, detected_category}, ...]

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    try:
        # Verify application is in awaiting_review status
        cur.execute("SELECT * FROM applications WHERE id=%s", (app_id,))
        app_data = cur.fetchone()
        if not app_data:
            return jsonify({"error": "Application not found"}), 404
        if app_data['status'] != 'awaiting_review':
            return jsonify({"error": f"Application is not awaiting review (status: {app_data['status']})"}), 400

        # Apply any corrections to document categories
        cur2 = conn.cursor()
        for doc in corrections:
            doc_id = doc.get('doc_id')
            new_category = doc.get('detected_category')
            if doc_id and new_category:
                cur2.execute(
                    "UPDATE documents SET detected_category=%s WHERE id=%s AND application_id=%s",
                    (new_category, doc_id, app_id)
                )
        cur2.close()

        # Update app status to processing
        cur3 = conn.cursor()
        cur3.execute("UPDATE applications SET status='processing', current_layer=2 WHERE id=%s", (app_id,))
        cur3.close()
        conn.commit()

        # Get confirmed file paths
        cur4 = conn.cursor(dictionary=True)
        cur4.execute("SELECT file_path FROM documents WHERE application_id=%s AND status='done'", (app_id,))
        filepaths = [row['file_path'] for row in cur4.fetchall()]
        cur4.close()

        log_audit(session['user_id'], 'HITL_CONFIRM', app_data['case_id'],
                  {"corrections": len(corrections)})

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

    # Notify the frontend via WebSocket to resume progress display
    socketio.emit('pipeline_resumed', {"app_id": app_id}, room=f'app_{app_id}')

    # Run Layer 2+ in a background thread
    socketio.start_background_task(
        _run_pipeline_layer2_onwards,
        app_id, app_data['case_id'], app_data['company_name'], filepaths
    )

    return jsonify({"status": "ok", "message": "Pipeline resuming"})


@app.route('/api/applications/<int:app_id>/cancel_review', methods=['POST'])
@login_required
def cancel_review(app_id):
    """Cancel pipeline — reset app to pending."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE applications SET status='pending', current_layer=0 WHERE id=%s AND status='awaiting_review'", (app_id,))
        conn.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

def _run_pipeline_layer2_onwards(app_id, case_id, company_name, filepaths):
    """Background task: run Layer 2 through Layer 6."""
    import time

    # ─── Layer 2: Financial Extraction ───────────────────────────────────
    socketio.emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 5},
                  room=f'app_{app_id}')

    try:
        from layer2.layer2_processor import IntelliCreditPipeline
        pipeline = IntelliCreditPipeline()

        socketio.emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 30},
                      room=f'app_{app_id}')

        result = pipeline.process_files(
            filepaths=filepaths,
            case_id=case_id,
            company_name=company_name
        )

        output_json = result.model_dump_json(indent=2)

        socketio.emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 90},
                      room=f'app_{app_id}')

        # Save Layer 2 to DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE applications SET layer2_output=%s, current_layer=2 WHERE id=%s",
                    (output_json, app_id))
        conn.commit()
        cur.close()
        conn.close()

        socketio.emit('layer_complete', {"layer": 2, "name": "Financial Extraction", "status": "done",
                      "line_count": len(output_json.splitlines())}, room=f'app_{app_id}')

    except Exception as e:
        print(f"Layer 2 pipeline error: {e}")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE applications SET status='failed' WHERE id=%s", (app_id,))
        conn.commit()
        cur.close()
        conn.close()
        socketio.emit('pipeline_error', {"error": str(e), "layer": 2}, room=f'app_{app_id}')
        return

    # ─── Layer 3: Data Cleaning & Normalization ──────────────────────────
    socketio.emit('layer_progress', {"layer": 3, "name": "Data Cleaning & Normalization", "status": "processing", "pct": 10},
                  room=f'app_{app_id}')

    try:
        from layer3.layer3_adapter import run_layer3_cleaning

        socketio.emit('layer_progress', {"layer": 3, "name": "Data Cleaning & Normalization", "status": "processing", "pct": 30},
                      room=f'app_{app_id}')

        layer3_result = run_layer3_cleaning(
            layer2_output_json=output_json,
            case_id=case_id,
            company_name=company_name
        )

        socketio.emit('layer_progress', {"layer": 3, "name": "Data Cleaning & Normalization", "status": "processing", "pct": 80},
                      room=f'app_{app_id}')

        layer3_json = json.dumps(layer3_result, indent=2, default=str)

        # Save Layer 3 to DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE applications SET layer3_output=%s, current_layer=3 WHERE id=%s",
                    (layer3_json, app_id))
        conn.commit()
        cur.close()
        conn.close()

        summary = layer3_result.get('summary', {})
        socketio.emit('layer_complete', {
            "layer": 3,
            "name": "Data Cleaning & Normalization",
            "status": "done",
            "fields_cleaned": summary.get('fields_cleaned', 0),
            "auto_fixed": summary.get('auto_fixed_count', 0),
            "risk_flags": summary.get('risk_flag_count', 0),
            "review_required": summary.get('review_required', False),
        }, room=f'app_{app_id}')

        print(f"Layer 3 completed: {summary.get('fields_cleaned', 0)} fields cleaned, "
              f"{summary.get('risk_flag_count', 0)} risk flags")

    except Exception as e:
        print(f"Layer 3 pipeline error: {e}")
        # Layer 3 failure is non-fatal — continue with remaining layers
        socketio.emit('layer_complete', {
            "layer": 3,
            "name": "Data Cleaning & Normalization",
            "status": "error",
            "error": str(e)
        }, room=f'app_{app_id}')

    # ─── Layers 4-6: Placeholder progress (future implementation) ────────
    layer_names = {
        4: "Web Research",
        5: "Risk Scoring",
        6: "CAM Generation"
    }
    for layer_num, layer_name in layer_names.items():
        socketio.emit('layer_progress', {"layer": layer_num, "name": layer_name, "status": "processing", "pct": 50},
                      room=f'app_{app_id}')
        time.sleep(1.5)
        socketio.emit('layer_complete', {"layer": layer_num, "name": layer_name, "status": "done"},
                      room=f'app_{app_id}')

    # Mark application as completed
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE applications SET status='completed', completed_at=NOW() WHERE id=%s", (app_id,))
    conn.commit()
    cur.close()
    conn.close()

    socketio.emit('pipeline_complete', {"app_id": app_id, "case_id": case_id, "status": "completed"},
                  room=f'app_{app_id}')



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

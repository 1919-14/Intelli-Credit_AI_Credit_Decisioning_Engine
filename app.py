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

import threading
_layer4_events: dict = {}   # app_id → {"e1": Event, "e2": Event, "e3": Event, "d1": {}, "d2": {}, "d3": {}}
_layer5_events: dict = {}   # app_id → {"e1": Event, "d1": {}}
_layer6_events: dict = {}   # app_id → {"e1": Event, "d1": {}}


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

    # ─── Layer 8: Governance Tables ──────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_inventory (
            id INT AUTO_INCREMENT PRIMARY KEY,
            model_id VARCHAR(50) UNIQUE NOT NULL,
            model_name VARCHAR(200) NOT NULL,
            model_type VARCHAR(100),
            deployment_date DATE,
            developer_team VARCHAR(200),
            model_owner VARCHAR(200),
            rmcb_approval_date DATE,
            rmcb_resolution_no VARCHAR(50),
            last_validation_date DATE,
            next_validation_due DATE,
            model_risk_rating VARCHAR(10) DEFAULT 'HIGH',
            is_third_party BOOLEAN DEFAULT FALSE,
            status VARCHAR(20) DEFAULT 'LIVE',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_change_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            model_id VARCHAR(50) NOT NULL,
            change_type VARCHAR(50) NOT NULL,
            description TEXT,
            impact_assessment TEXT,
            requested_by VARCHAR(100),
            approved_by VARCHAR(100),
            approved_at DATETIME DEFAULT NULL,
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            period VARCHAR(20),
            sample_size INT DEFAULT 0,
            auc_roc FLOAT,
            ks_statistic FLOAT,
            gini_coefficient FLOAT,
            f1_score FLOAT,
            precision_val FLOAT,
            recall_val FLOAT,
            brier_score FLOAT,
            computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS imv_reports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            model_id VARCHAR(50),
            validation_date DATETIME,
            validator VARCHAR(200),
            overall_status VARCHAR(20),
            report_json LONGTEXT,
            next_validation_due DATE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS drift_psi_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            report_date DATETIME,
            overall_status VARCHAR(10),
            red_count INT DEFAULT 0,
            amber_count INT DEFAULT 0,
            green_count INT DEFAULT 0,
            report_json LONGTEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bias_fairness_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            period VARCHAR(20),
            report_type VARCHAR(30),
            overall_status VARCHAR(10),
            report_json LONGTEXT,
            computed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sma_monitoring (
            id INT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(50) NOT NULL,
            dpd INT DEFAULT 0,
            sma_classification VARCHAR(20) DEFAULT 'REGULAR',
            severity VARCHAR(20) DEFAULT 'NORMAL',
            outstanding_lakhs FLOAT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX (case_id),
            INDEX (sma_classification)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS crilc_submissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(50) NOT NULL,
            borrower_name VARCHAR(200),
            outstanding_cr FLOAT DEFAULT 0,
            sma_status VARCHAR(20),
            quarter VARCHAR(10),
            submission_status VARCHAR(20) DEFAULT 'PENDING',
            submitted_at DATETIME DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS retraining_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trigger_type VARCHAR(50),
            status VARCHAR(20) DEFAULT 'INITIATED',
            details_json LONGTEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

    # ─── Seed Layer 8 Model Inventory ────────────────────────────────────────
    try:
        from layer8.block_a_model_registry import seed_model_inventory
        conn2 = get_db()
        seed_model_inventory(conn2)
        conn2.close()
    except Exception as e:
        print(f"  Layer 8 model inventory seed: {e}")

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

    # Parse layer4_output if present
    if app_data.get('layer4_output'):
        try:
            app_data['layer4_output'] = json.loads(app_data['layer4_output'])
        except:
            pass

    # Parse layer5_output if present
    if app_data.get('layer5_output'):
        try:
            app_data['layer5_output'] = json.loads(app_data['layer5_output'])
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
        app_id, app_data['case_id'], app_data['company_name'], filepaths,
        officer_notes=request.json.get('officer_notes', '')
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


# ─── Layer 4 HITL Endpoints ──────────────────────────────────────────────────

@app.route('/api/applications/<int:app_id>/layer4_hitl_1', methods=['POST'])
@login_required
def layer4_hitl_1(app_id):
    """HITL-1: Officer reviews forensic flags (GST + Bank). Submits dismissals."""
    body = request.json or {}
    dismissed_ids = body.get('dismissed_alert_ids', [])     # list of alert_id strings
    dismiss_reasons = body.get('dismiss_reasons', {})       # {alert_id: reason}
    officer_id = str(session.get('user_id', 'unknown'))

    slot = _layer4_events.get(app_id)
    if not slot:
        return jsonify({"error": "No active Layer 4 pipeline for this application"}), 404

    slot['d1'] = {
        'dismissed_alert_ids': dismissed_ids,
        'dismiss_reasons': dismiss_reasons,
        'officer_id': officer_id,
        'submitted_at': datetime.utcnow().isoformat(),
    }
    slot['e1'].set()   # unblock the pipeline thread

    log_audit(session['user_id'], 'L4_HITL_1', None,
              {'dismissed': len(dismissed_ids), 'app_id': app_id})
    return jsonify({"status": "ok", "dismissed": len(dismissed_ids)})


@app.route('/api/applications/<int:app_id>/layer4_hitl_2', methods=['POST'])
@login_required
def layer4_hitl_2(app_id):
    """HITL-2: Officer reviews web research findings. Submits dismissals."""
    body = request.json or {}
    # [{block, finding_id, reason, action:'KEEP'|'DISMISS'}]
    dismissed_findings = [f for f in body.get('findings', []) if f.get('action') == 'DISMISS']
    officer_id = str(session.get('user_id', 'unknown'))

    slot = _layer4_events.get(app_id)
    if not slot:
        return jsonify({"error": "No active Layer 4 pipeline for this application"}), 404

    slot['d2'] = {
        'dismissed_findings': dismissed_findings,
        'officer_id': officer_id,
        'submitted_at': datetime.utcnow().isoformat(),
    }
    slot['e2'].set()

    log_audit(session['user_id'], 'L4_HITL_2', None,
              {'dismissed_findings': len(dismissed_findings), 'app_id': app_id})
    return jsonify({"status": "ok", "dismissed": len(dismissed_findings)})


@app.route('/api/applications/<int:app_id>/layer4_hitl_3', methods=['POST'])
@login_required
def layer4_hitl_3(app_id):
    """HITL-3: Officer overrides feature values before Layer 5 ML scoring."""
    body = request.json or {}
    # [{feature, new_value, reason}]
    feature_overrides = [
        fo for fo in body.get('overrides', [])
        if fo.get('feature') and fo.get('reason', '').strip()
    ]
    officer_id = str(session.get('user_id', 'unknown'))

    slot = _layer4_events.get(app_id)
    if not slot:
        return jsonify({"error": "No active Layer 4 pipeline for this application"}), 404

    slot['d3'] = {
        'feature_overrides': feature_overrides,
        'officer_id': officer_id,
        'submitted_at': datetime.utcnow().isoformat(),
    }
    slot['e3'].set()

    log_audit(session['user_id'], 'L4_HITL_3', None,
              {'overrides': len(feature_overrides), 'app_id': app_id})
    return jsonify({"status": "ok", "overrides": len(feature_overrides)})


# ─── Layer 5 HITL Endpoints ──────────────────────────────────────────────────

@app.route('/api/applications/<int:app_id>/layer5_hitl_reject', methods=['POST'])
@login_required
def layer5_hitl_reject(app_id):
    """HITL: Officer overrides or accepts a Layer 5 Hard Reject."""
    body = request.json or {}
    action = body.get('action')  # "override" or "accept"
    reason = body.get('reason', '')
    officer_id = str(session.get('user_id', 'unknown'))

    slot = _layer5_events.get(app_id)
    if not slot:
        return jsonify({"error": "No active Layer 5 pipeline for this application"}), 404

    slot['d1'] = {
        'action': action,
        'reason': reason,
        'officer_id': officer_id,
        'submitted_at': datetime.utcnow().isoformat(),
    }
    slot['e1'].set()

    log_audit(session['user_id'], 'L5_HITL_REJECT_OVERRIDE', None,
              {'action': action, 'app_id': app_id, 'reason': reason})
    return jsonify({"status": "ok", "action": action})



def _run_pipeline_layer2_onwards(app_id, case_id, company_name, filepaths, officer_notes=''):
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

    # ─── Layer 4: Forensics, Research & Feature Engineering (3× HITL) ───────
    socketio.emit('layer_progress', {"layer": 4, "name": "Forensics & Research",
                  "status": "processing", "pct": 3}, room=f'app_{app_id}')

    try:
        from layer4.layer4_chain import (
            run_stage1_forensics, apply_hitl1_decisions,
            run_stage2_research,  apply_hitl2_decisions,
            run_stage3_build,     apply_hitl3_decisions,
            run_stage4_finalize
        )

        # Parse L2 / L3 data
        l2_data = {}
        try:
            l2_parsed = json.loads(output_json) if isinstance(output_json, str) else output_json
            l2_data = l2_parsed.get('extracted', {}).get('financial_data', {}) or l2_parsed
        except: pass

        l3_data = {}
        try:
            l3_data = json.loads(layer3_json) if isinstance(layer3_json, str) else layer3_json
        except: pass

        company_identifiers = {
            "company_name":  company_name or l2_data.get("company_name", ""),
            "promoter_name": l2_data.get("promoter_name", "") or l2_data.get("assessee_name", ""),
            "gstin":         l2_data.get("gstin", ""),
            "pan_number":    l2_data.get("pan_number", ""),
            "cin":           l2_data.get("cin", ""),
            "din":           l2_data.get("din", ""),
            "industry":      l2_data.get("industry", "") or l2_data.get("nature_of_business", ""),
        }

        l4_data = {
            "layer2_data": l2_data,
            "layer3_data": l3_data,
            "company_identifiers": company_identifiers,
            "officer_notes": officer_notes or "",
            "case_id": case_id,
            "company_name": company_name,
            "hitl_audit_trail": [],
        }

        # Initialise event slots for this app_id
        e1 = threading.Event()
        e2 = threading.Event()
        e3 = threading.Event()
        _layer4_events[app_id] = {"e1": e1, "e2": e2, "e3": e3, "d1": {}, "d2": {}, "d3": {}}

        # ─ STAGE 1: Pure Python Forensics ───────────────
        socketio.emit('layer_progress', {"layer": 4, "name": "Forensics & Research",
                      "status": "processing", "pct": 10,
                      "detail": "Running GST & bank forensics..."}, room=f'app_{app_id}')
        l4_data = run_stage1_forensics(l4_data)

        # Collect forensic alerts for HITL-1
        all_f_alerts = (
            l4_data.get("gst_forensics_alerts", []) +
            l4_data.get("bank_forensics_alerts", [])
        )
        red_amber = [a for a in all_f_alerts if a.get("severity") in ("RED", "AMBER")]

        # ―― HITL-1 PAUSE ――
        socketio.emit('layer4_hitl_forensics', {
            "app_id": app_id,
            "alerts": red_amber,
            "total": len(all_f_alerts),
            "red": sum(1 for a in all_f_alerts if a.get("severity") == "RED"),
            "amber": sum(1 for a in all_f_alerts if a.get("severity") == "AMBER"),
        }, room=f'app_{app_id}')
        e1.wait(timeout=300)   # block until HITL-1 submitted or 5-min timeout

        d1 = _layer4_events[app_id].get("d1", {})
        if d1.get("dismissed_alert_ids"):
            l4_data = apply_hitl1_decisions(
                l4_data,
                dismissed_alert_ids=d1.get("dismissed_alert_ids", []),
                dismiss_reasons=d1.get("dismiss_reasons", {}),
                officer_id=d1.get("officer_id", "unknown")
            )

        # ─ STAGE 2: Web Research ───────────────
        socketio.emit('layer_progress', {"layer": 4, "name": "Forensics & Research",
                      "status": "processing", "pct": 30,
                      "detail": "Running web research (Tavily + Groq)..."}, room=f'app_{app_id}')
        l4_data = run_stage2_research(l4_data)

        # Build research findings payload for HITL-2
        research_findings = {
            "adverse_media": l4_data.get("adverse_media", {}),
            "litigation": l4_data.get("litigation", {}),
            "mca_checks": l4_data.get("mca_checks", {}),
        }

        # ―― HITL-2 PAUSE ――
        socketio.emit('layer4_hitl_research', {
            "app_id": app_id,
            "research_findings": research_findings,
            "sector_risk": l4_data.get("sector_risk", {}),
            "cibil": l4_data.get("cibil", {}),
        }, room=f'app_{app_id}')
        e2.wait(timeout=300)

        d2 = _layer4_events[app_id].get("d2", {})
        if d2.get("dismissed_findings"):
            l4_data = apply_hitl2_decisions(
                l4_data,
                dismissed_findings=d2.get("dismissed_findings", []),
                officer_id=d2.get("officer_id", "unknown")
            )

        # ─ STAGE 3: Officer NLP + Feature Build ──────
        socketio.emit('layer_progress', {"layer": 4, "name": "Forensics & Research",
                      "status": "processing", "pct": 70,
                      "detail": "Building credit feature vector..."}, room=f'app_{app_id}')
        l4_data = run_stage3_build(l4_data)

        from layer4.consolidation.feature_engine import FEATURE_DEFINITIONS
        features_for_hitl = [
            {
                "name": fd["name"],
                "value": l4_data.get("feature_vector", {}).get(fd["name"], fd["default"]),
                "source": fd["source"],
                "default": fd["default"]
            }
            for fd in FEATURE_DEFINITIONS
        ]

        # ―― HITL-3 PAUSE ――
        socketio.emit('layer4_hitl_features', {
            "app_id": app_id,
            "features": features_for_hitl,
            "officer_analysis": l4_data.get("officer_analysis", {}),
        }, room=f'app_{app_id}')
        e3.wait(timeout=300)

        d3 = _layer4_events[app_id].get("d3", {})
        if d3.get("feature_overrides"):
            l4_data = apply_hitl3_decisions(
                l4_data,
                feature_overrides=d3.get("feature_overrides", []),
                officer_id=d3.get("officer_id", "unknown")
            )

        # ─ STAGE 4: Finalize ───────────────
        socketio.emit('layer_progress', {"layer": 4, "name": "Forensics & Research",
                      "status": "processing", "pct": 90,
                      "detail": "Generating AI explanations..."}, room=f'app_{app_id}')
        all_dismissed = d1.get("dismissed_alert_ids", []) if d1 else []
        l4_data = run_stage4_finalize(l4_data, all_dismissed)

        layer4_result = l4_data.get("layer4_output", {})
        layer4_json = json.dumps(layer4_result, indent=2, default=str)

        # Save to DB
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN layer4_output LONGTEXT")
            conn.commit()
        except:
            conn.rollback()
        cur.execute("UPDATE applications SET layer4_output=%s, current_layer=4 WHERE id=%s",
                    (layer4_json, app_id))
        conn.commit()
        cur.close()
        conn.close()

        report = layer4_result.get('forensics_report', {})
        audit_count = len(layer4_result.get('hitl_audit_trail', []))
        socketio.emit('layer_complete', {
            "layer": 4,
            "name": "Forensics & Research",
            "status": "done",
            "red_flags": report.get('red_flag_count', 0),
            "amber_flags": report.get('amber_flag_count', 0),
            "features_computed": len(layer4_result.get('feature_vector', {})),
            "hitl_audit_entries": audit_count,
        }, room=f'app_{app_id}')
        print(f"Layer 4 complete | {audit_count} HITL audit entries")

    except Exception as e:
        print(f"Layer 4 pipeline error: {e}")
        import traceback; traceback.print_exc()
        socketio.emit('layer_complete', {
            "layer": 4, "name": "Forensics & Research",
            "status": "error", "error": str(e)
        }, room=f'app_{app_id}')
    finally:
        _layer4_events.pop(app_id, None)

    # ─── Layer 5: Risk Scoring & Decision Engine ──────────────────────────
    socketio.emit('layer_progress', {"layer": 5, "name": "Risk Scoring", "status": "processing", "pct": 3},
                  room=f'app_{app_id}')

    try:
        from layer5.layer5_chain import run_layer5

        def l5_progress(msg, pct):
            socketio.emit('layer_progress', {"layer": 5, "name": "Risk Scoring",
                          "status": "processing", "pct": pct, "detail": msg},
                          room=f'app_{app_id}')

        def l5_hitl_reject(hard_rules_result):
            # Register event
            e = threading.Event()
            _layer5_events[app_id] = {"e1": e, "d1": {}}
            
            # Emit to frontend
            socketio.emit('layer5_hitl_reject', {
                "app_id": app_id,
                "hard_rules": hard_rules_result
            }, room=f'app_{app_id}')
            
            # Wait for decision
            e.wait()
            
            # Get decision
            data = _layer5_events[app_id].get("d1", {})
            return data

        layer5_result = run_layer5(
            layer4_output=layer4_result if 'layer4_result' in dir() else {},
            layer2_data=l2_data if 'l2_data' in dir() else {},
            company_name=company_name,
            case_id=case_id,
            requested_amount_lakhs=75.0,
            progress_callback=l5_progress,
            hitl_callback=l5_hitl_reject,
        )

        layer5_json = json.dumps(layer5_result, indent=2, default=str)

        # Save to DB
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN layer5_output LONGTEXT")
            conn.commit()
        except:
            conn.rollback()
        cur.execute("UPDATE applications SET layer5_output=%s, current_layer=5 WHERE id=%s",
                    (layer5_json, app_id))
        conn.commit()
        cur.close()
        conn.close()

        decision = layer5_result.get("decision_summary", {})
        socketio.emit('layer_complete', {
            "layer": 5,
            "name": "Risk Scoring",
            "status": "done",
            "decision": decision.get("decision", ""),
            "credit_score": decision.get("final_credit_score", 0),
            "risk_band": decision.get("risk_band", ""),
            "interest_rate": decision.get("interest_rate", 0),
        }, room=f'app_{app_id}')
        print(f"Layer 5 complete: {decision.get('decision')} | Score={decision.get('final_credit_score')}")

    except Exception as e:
        print(f"Layer 5 pipeline error: {e}")
        import traceback; traceback.print_exc()
        socketio.emit('layer_complete', {
            "layer": 5, "name": "Risk Scoring",
            "status": "error", "error": str(e)
        }, room=f'app_{app_id}')

    # ─── Layer 6: HITL Decision Override ──────────────────────────────
    socketio.emit('layer_progress', {"layer": 6, "name": "Decision Override", "status": "processing", "pct": 10},
                  room=f'app_{app_id}')
    
    _layer6_events[app_id] = {"e1": threading.Event(), "d1": {}}
    socketio.emit('hitl_review_needed', {
        "app_id": app_id, 
        "layer": "6_decision",
        "title": "Layer 6: Final Decision Review",
        "message": "Review and optionally override the AI's final credit decision.",
        "decision": layer5_result.get("decision_summary", {})
    }, room=f'app_{app_id}')
    print(f"Waiting for Layer 6 HITL Decision Review on app {app_id}...")

    # Wait up to 24h
    _layer6_events[app_id]["e1"].wait(timeout=86400)
    d1 = _layer6_events[app_id].get("d1", {})
    _layer6_events.pop(app_id, None)

    # Update layer5_result with custom override if provided
    if d1.get('approved'):
        print(f"Layer 6 HITL approved overrides: {d1}")
        overrides = d1.get("overrides", {})
        if overrides:
            if "decision" in overrides: layer5_result["decision_summary"]["decision"] = overrides["decision"]
            
            # Did the amount or rate change?
            amount_changed = "loan_amount" in overrides and str(overrides["loan_amount"]) != str(layer5_result["decision_summary"].get("sanction_amount_lakhs"))
            rate_changed = "interest_rate" in overrides and str(overrides["interest_rate"]) != str(layer5_result["decision_summary"].get("interest_rate"))
            
            if "loan_amount" in overrides: layer5_result["decision_summary"]["sanction_amount_lakhs"] = float(overrides["loan_amount"])
            if "interest_rate" in overrides: layer5_result["decision_summary"]["interest_rate"] = float(overrides["interest_rate"])
            layer5_result["decision_summary"]["override_reason"] = overrides.get("reason", "Accepted AI decision")
            
            # Recalculate metrics if needed
            if amount_changed or rate_changed:
                try:
                    from layer5.step10_loan_structure import compute_loan_structure
                    l2_parsed = json.loads(output_json) if isinstance(output_json, str) else output_json
                    l2 = l2_parsed.get('extracted', {}).get('financial_data', {}) or l2_parsed
                    features = layer5_result.get("validation", {}).get("validated_features", {})
                    conditions = layer5_result.get("decision_summary", {}).get("conditions", [])
                    new_amt = float(layer5_result["decision_summary"]["sanction_amount_lakhs"])
                    new_rate = float(layer5_result["decision_summary"]["interest_rate"])
                    
                    recalc = compute_loan_structure(
                        features, new_rate, conditions, l2, new_amt
                    )
                    
                    # Force the structural splits to match the exact overridden amount
                    term_amount = round(new_amt * 0.60, 2)
                    wc_amount = round(new_amt * 0.40, 2)
                    tenure_months = recalc["loan_structure"]["term_loan"]["tenure_months"]
                    rate_monthly = new_rate / 100 / 12
                    
                    if rate_monthly > 0:
                        emi = term_amount * rate_monthly * (1 + rate_monthly)**tenure_months / ((1 + rate_monthly)**tenure_months - 1)
                    else: emi = term_amount / tenure_months
                    
                    recalc["approved_amount_lakhs"] = new_amt
                    recalc["loan_structure"]["total_sanctioned_lakhs"] = new_amt
                    recalc["loan_structure"]["term_loan"]["amount_lakhs"] = term_amount
                    recalc["loan_structure"]["term_loan"]["rate"] = new_rate
                    recalc["loan_structure"]["term_loan"]["emi_lakhs"] = round(emi, 2)
                    recalc["loan_structure"]["working_capital"]["amount_lakhs"] = wc_amount
                    recalc["loan_structure"]["working_capital"]["rate"] = round(new_rate + 0.75, 2)
                    
                    recalc["limits"]["manual_override_limit"] = new_amt
                    recalc["binding_constraint"] = "MANUAL_OVERRIDE"
                    
                    recalc["hitl_override_note"] = f"Manual Override Matrix: Computed based on {new_amt}L @ {new_rate}%"
                    layer5_result["loan_structure"] = recalc
                except Exception as e:
                    print(f"Failed to recalculate loan metrics: {e}")
            
            # Persist custom changes back to DB (Layer 5 data updated)
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE applications SET layer5_output=%s WHERE id=%s", (json.dumps(layer5_result), app_id))
            conn.commit()
            cur.close()
            conn.close()

    socketio.emit('layer_complete', {"layer": 6, "name": "Decision Override", "status": "done"}, room=f'app_{app_id}')


    # ─── Layer 7: CAM Report Generation (formerly Layer 6) ─────────────
    socketio.emit('layer_progress', {"layer": 7, "name": "CAM Report Generation", "status": "processing", "pct": 10},
                  room=f'app_{app_id}')

    cam_result = {}
    try:
        from layer7.cam_generator import generate_cam_report, generate_audit_json

        socketio.emit('layer_progress', {"layer": 7, "name": "CAM Report Generation", "status": "processing", "pct": 30,
                      "detail": "Compiling 13-section RBI-compliant CAM..."}, room=f'app_{app_id}')

        # Gather all layer data
        app_data = {"case_id": case_id, "company_name": company_name, "app_id": app_id}
        l2_parsed = json.loads(output_json) if isinstance(output_json, str) else output_json
        l3_parsed = json.loads(layer3_json) if 'layer3_json' in dir() and layer3_json else {}
        l4_parsed = layer4_result if 'layer4_result' in dir() else {}
        l5_parsed = layer5_result if 'layer5_result' in dir() else {}

        cam_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"cam_{app_id}")
        cam_result = generate_cam_report(app_data, l2_parsed, l3_parsed, l4_parsed, l5_parsed, cam_dir)

        socketio.emit('layer_progress', {"layer": 7, "name": "CAM Report Generation", "status": "processing", "pct": 70,
                      "detail": "Generating audit JSON..."}, room=f'app_{app_id}')

        audit_json = generate_audit_json(app_data, l2_parsed, l3_parsed, l4_parsed, l5_parsed)

        socketio.emit('layer_progress', {"layer": 7, "name": "CAM Report Generation", "status": "processing", "pct": 90,
                      "detail": "Saving..."}, room=f'app_{app_id}')

        # Save to DB
        cam_meta = json.dumps({
            "cam_hash": cam_result.get("cam_hash", ""),
            "docx_path": cam_result.get("path", ""),
            "sections": cam_result.get("sections", 13),
            "timestamp": cam_result.get("timestamp", ""),
            "audit": audit_json,
        }, default=str)

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN layer7_cam LONGTEXT")
            conn.commit()
        except:
            conn.rollback()
        cur.execute("UPDATE applications SET layer7_cam=%s, current_layer=7 WHERE id=%s",
                    (cam_meta, app_id))
        conn.commit()
        cur.close()
        conn.close()

        socketio.emit('layer_complete', {
            "layer": 7,
            "name": "CAM Report Generation",
            "status": "done",
            "cam_hash": cam_result.get("cam_hash", ""),
            "sections": cam_result.get("sections", 13),
            "audit": audit_json,
        }, room=f'app_{app_id}')
        print(f"Layer 7 CAM complete | Hash: {cam_result.get('cam_hash', '')[:16]}...")

    except Exception as e:
        print(f"Layer 7 CAM error: {e}")
        import traceback; traceback.print_exc()
        socketio.emit('layer_complete', {
            "layer": 7, "name": "CAM Report Generation",
            "status": "error", "error": str(e)
        }, room=f'app_{app_id}')

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


# ─── SHAP LLM Explanation API ─────────────────────────────────────────────────
@app.route('/api/applications/<int:app_id>/shap_explain', methods=['POST'])
@login_required
def shap_explain(app_id):
    """
    Generate (or return cached) LLM explanation for the SHAP decomposition.
    Calls generate_shap_explanation() from layer5.step6_llm_overlay.
    """
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT layer5_output, company_name FROM applications WHERE id=%s", (app_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row.get('layer5_output'):
        return jsonify({"error": "No Layer 5 output found. Run the pipeline first."}), 404

    try:
        l5 = json.loads(row['layer5_output']) if isinstance(row['layer5_output'], str) else row['layer5_output']
    except Exception:
        return jsonify({"error": "Failed to parse Layer 5 output."}), 500

    # Return cached explanation if it exists
    cached = l5.get("shap_explanation")
    if cached:
        return jsonify({"explanation": cached, "cached": True})

    # Generate fresh explanation
    try:
        from layer5.step6_llm_overlay import generate_shap_explanation
        shap_result = l5.get("explanation", {})
        xgb_result = l5.get("xgboost", {})
        decision_summary = l5.get("decision_summary", {})

        # Build shap_result in the format expected by generate_shap_explanation
        shap_input = {
            "top_positive_drivers": shap_result.get("shap_top_positive", []),
            "top_negative_drivers": shap_result.get("shap_top_negative", []),
            "waterfall_narrative": shap_result.get("shap_waterfall", ""),
            "base_value": 0.30,
        }

        explanation = generate_shap_explanation(
            features={},
            shap_result=shap_input,
            xgb_result=xgb_result,
            decision_summary=decision_summary,
            company_name=row.get('company_name', ''),
        )

        # Cache the explanation back into the DB
        try:
            l5["shap_explanation"] = explanation
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("UPDATE applications SET layer5_output=%s WHERE id=%s",
                         (json.dumps(l5), app_id))
            conn2.commit()
            cur2.close()
            conn2.close()
        except Exception as cache_err:
            print(f"Failed to cache SHAP explanation: {cache_err}")

        return jsonify({"explanation": explanation, "cached": False})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to generate explanation: {str(e)}"}), 500



# ─── Layer 6 HITL Decision API ───────────────────────────────────────────────
@app.route('/api/applications/<int:app_id>/layer6_hitl_decision', methods=['POST'])
@login_required
def layer6_hitl_decision(app_id):
    """Handle user's manual override of the AI decision."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    decision = data.get('decision')
    if not decision or decision not in ['APPROVE', 'REJECT', 'CONDITIONAL']:
        return jsonify({"error": "Invalid decision"}), 400

    if app_id in _layer6_events:
        _layer6_events[app_id]["d1"] = {
            "approved": True,
            "overrides": {
                "decision": decision,
                "loan_amount": data.get('loan_amount'),
                "interest_rate": data.get('interest_rate'),
                "reason": data.get('reason'),
                "conditions": data.get('conditions', [])
            }
        }
        _layer6_events[app_id]["e1"].set()
        return jsonify({"status": "Decision override submitted"})
    else:
        return jsonify({"error": "Session expired or layer not active"}), 400

@app.route('/api/applications/<int:app_id>/layer6_risk_check', methods=['POST'])
@login_required
def layer6_risk_check(app_id):
    """Call Groq LLM to evaluate the user's override and provide risk bullet points."""
    data = request.json
    if not data: return jsonify({"error": "Invalid request"}), 400

    new_decision = data.get('decision')
    reason = data.get('reason', '')
    loan_amount = data.get('loan_amount')
    old_decision = data.get('old_decision')
    old_loan_amount = data.get('old_loan_amount')

    if not reason:
        return jsonify({"bullet_points": ["No reason provided for the override. This is highly irregular and adds compliance risk."]})

    prompt = f"""You are a Chief Risk Officer reviewing a credit analyst's manual override of an AI credit model.
Original AI Decision: {old_decision} (Amount: {old_loan_amount}L)
New Human Decision: {new_decision} (Amount: {loan_amount}L)
Analyst's Reason for Override: "{reason}"

Evaluate the risks of this override. Provide EXACTLY 3-4 bullet points in plain text (start each with a bullet character •). Do not use markdown. Make them punchy, specific warnings about what could go wrong if this override is approved. Focus on credit risk, compliance, and alignment.
"""
    try:
        from groq import Groq
        client = Groq(
            api_key=os.getenv("API_KEY")
        )
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": "You are a Chief Risk Officer assessing override risks."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        text = response.choices[0].message.content.strip()
        bullets = [line.strip() for line in text.split('\n') if line.strip() and line.strip().startswith('•')]
        if not bullets:
            bullets = [f"• Risk 1: {text}"]
            
        return jsonify({"bullet_points": bullets})
    except Exception as e:
        print(f"LLM Risk Check Error: {e}")
        return jsonify({"bullet_points": [
            "• Unable to reach Risk AI for deeper analysis.",
            "• Proceeding with an un-validated override carries elevated compliance risk.",
            "• Ensure physical documentation fully supports your stated reason."
        ]})


# ─── CAM Download API ────────────────────────────────────────────────────────
@app.route('/api/applications/<int:app_id>/download_cam/<fmt>')
@login_required
def download_cam(app_id, fmt):
    """Download CAM in DOCX or PDF format."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT layer7_cam, case_id FROM applications WHERE id=%s", (app_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row.get('layer7_cam'):
        return jsonify({"error": "CAM not generated yet. Run the pipeline first."}), 404

    try:
        cam_meta = json.loads(row['layer7_cam']) if isinstance(row['layer7_cam'], str) else row['layer7_cam']
    except:
        return jsonify({"error": "Failed to parse CAM metadata."}), 500

    docx_path = cam_meta.get('docx_path', '')
    if not docx_path or not os.path.exists(docx_path):
        return jsonify({"error": "CAM file not found on disk."}), 404

    case_id = row.get('case_id', 'UNKNOWN')

    if fmt == 'docx':
        from flask import send_file
        return send_file(docx_path, as_attachment=True,
                        download_name=f"CAM_{case_id}.docx",
                        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    elif fmt == 'pdf':
        from flask import send_file
        pdf_path = docx_path.replace('.docx', '.pdf')
        if not os.path.exists(pdf_path):
            from layer7.cam_generator import convert_docx_to_pdf
            success = convert_docx_to_pdf(docx_path, pdf_path)
            if not success or not os.path.exists(pdf_path):
                return jsonify({"error": "PDF conversion failed. Please download DOCX instead."}), 500
        return send_file(pdf_path, as_attachment=True,
                        download_name=f"CAM_{case_id}.pdf",
                        mimetype='application/pdf')
    elif fmt == 'json':
        audit = cam_meta.get('audit', {})
        return jsonify(audit)
    else:
        return jsonify({"error": f"Unsupported format: {fmt}"}), 400


# ─── Digital Signature API ───────────────────────────────────────────────────
@app.route('/api/applications/<int:app_id>/digital_signature', methods=['POST'])
@login_required
def apply_digital_signature(app_id):
    """Apply digital signature to the CAM report."""
    data = request.get_json() or {}
    officer_name = data.get('officer_name', session.get('full_name', 'Unknown'))
    officer_id = data.get('officer_id', session.get('user_id', 0))
    officer_role = data.get('officer_role', session.get('role', 'ANALYST'))

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT layer7_cam, case_id, company_name FROM applications WHERE id=%s", (app_id,))
    row = cur.fetchone()

    if not row or not row.get('layer7_cam'):
        cur.close()
        conn.close()
        return jsonify({"error": "CAM not generated yet."}), 404

    try:
        cam_meta = json.loads(row['layer7_cam']) if isinstance(row['layer7_cam'], str) else row['layer7_cam']
    except:
        cur.close()
        conn.close()
        return jsonify({"error": "Failed to parse CAM."}), 500

    import hashlib
    sig_data = f"{app_id}:{row['case_id']}:{officer_id}:{officer_name}:{datetime.now().isoformat()}"
    signature_hash = hashlib.sha256(sig_data.encode()).hexdigest()

    cam_meta['digital_signature'] = {
        'officer_name': officer_name,
        'officer_id': officer_id,
        'officer_role': officer_role,
        'timestamp': datetime.now().isoformat(),
        'signature_hash': signature_hash,
        'cam_hash': cam_meta.get('cam_hash', ''),
    }

    cur.execute("UPDATE applications SET layer7_cam=%s WHERE id=%s",
                (json.dumps(cam_meta, default=str), app_id))
    conn.commit()

    # Audit log
    try:
        cur.execute("""INSERT INTO audit_logs (actor_id, action, target_type, target_id, details, timestamp)
                       VALUES (%s, 'DIGITAL_SIGNATURE', 'application', %s, %s, NOW())""",
                    (officer_id, app_id, json.dumps({
                        'signature_hash': signature_hash,
                        'case_id': row['case_id'],
                        'company': row['company_name'],
                    })))
        conn.commit()
    except:
        pass

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "signature_hash": signature_hash,
        "officer_name": officer_name,
        "timestamp": cam_meta['digital_signature']['timestamp'],
    })


# ─── CAM Data API (for UI rendering) ────────────────────────────────────────
@app.route('/api/applications/<int:app_id>/cam_data')
@login_required
def get_cam_data(app_id):
    """Return CAM metadata for UI rendering."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT layer7_cam, case_id, company_name FROM applications WHERE id=%s", (app_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row or not row.get('layer7_cam'):
        return jsonify({"error": "CAM not generated yet."}), 404

    try:
        cam_meta = json.loads(row['layer7_cam']) if isinstance(row['layer7_cam'], str) else row['layer7_cam']
        return jsonify({
            "cam_hash": cam_meta.get('cam_hash', ''),
            "sections": cam_meta.get('sections', 0),
            "timestamp": cam_meta.get('timestamp', ''),
            "audit": cam_meta.get('audit', {}),
            "digital_signature": cam_meta.get('digital_signature', None),
        })
    except:
        return jsonify({"error": "Failed to parse CAM data."}), 500


# ─── Layer 8: Governance, Monitoring & Compliance APIs ───────────────────────

@app.route('/api/layer8/model-inventory')
@login_required
def layer8_model_inventory():
    """Return current model inventory."""
    try:
        from layer8.block_a_model_registry import get_model_inventory
        conn = get_db()
        inventory = get_model_inventory(conn)
        conn.close()
        return jsonify(inventory)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/model-inventory/update', methods=['POST'])
@login_required
def layer8_update_model():
    """Update model status/metadata."""
    try:
        from layer8.block_a_model_registry import update_model_status
        data = request.json
        conn = get_db()
        ok = update_model_status(conn, data.get("model_id", "XGB_CREDIT_V4.3"),
                                  data.get("status", "LIVE"),
                                  session.get("username", "system"))
        conn.close()
        return jsonify({"status": "ok", "updated": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/change-control', methods=['GET', 'POST'])
@login_required
def layer8_change_control():
    """Log or list change requests."""
    try:
        from layer8.block_a_model_registry import log_change_request, get_change_log
        conn = get_db()
        if request.method == 'POST':
            data = request.json
            data["requested_by"] = session.get("username", "system")
            change_id = log_change_request(conn, data)
            conn.close()
            log_audit(session['user_id'], 'LAYER8_CHANGE_REQUEST', data.get("model_id"))
            return jsonify({"status": "ok", "change_id": change_id})
        else:
            changes = get_change_log(conn, request.args.get("model_id"))
            conn.close()
            return jsonify(changes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/performance-metrics')
@login_required
def layer8_performance_metrics():
    """Compute and return model performance metrics."""
    try:
        from layer8.block_b_performance import compute_performance_metrics, get_performance_history
        conn = get_db()
        history = get_performance_history(conn, limit=12)
        if not history:
            metrics = compute_performance_metrics([])
        else:
            metrics = history[0]
        conn.close()
        return jsonify({"current": metrics, "history": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/score-distribution')
@login_required
def layer8_score_distribution():
    """Return score distribution stats."""
    try:
        from layer8.block_b_performance import compute_score_distribution
        dist = compute_score_distribution([])
        return jsonify(dist)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/run-imv', methods=['POST'])
@login_required
def layer8_run_imv():
    """Trigger IMV run."""
    try:
        from layer8.block_c_imv import run_imv_check, save_imv_report
        conn = get_db()
        report = run_imv_check(conn)
        report_id = save_imv_report(conn, report)
        conn.close()
        log_audit(session['user_id'], 'LAYER8_IMV_RUN', report.get("model_id"))
        return jsonify({"status": "ok", "report_id": report_id, "report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/imv-reports')
@login_required
def layer8_imv_reports():
    """List IMV reports."""
    try:
        from layer8.block_c_imv import get_imv_reports
        conn = get_db()
        reports = get_imv_reports(conn)
        conn.close()
        return jsonify(reports)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/drift-report')
@login_required
def layer8_drift_report():
    """Run/return PSI + concept drift report."""
    try:
        from layer8.block_d_drift import get_drift_history, get_demo_drift_report
        conn = get_db()
        history = get_drift_history(conn, limit=1)
        conn.close()
        if history and history[0].get("report_json"):
            return jsonify(history[0]["report_json"])
        return jsonify(get_demo_drift_report())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/fairness-report')
@login_required
def layer8_fairness_report():
    """Return sector + MSME fairness report."""
    try:
        from layer8.block_e_fairness import sector_fairness_report, msme_size_fairness
        sector = sector_fairness_report([])
        msme = msme_size_fairness([])
        return jsonify({"sector_fairness": sector, "msme_fairness": msme})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/applications/<case_id>/explanation')
@login_required
def layer8_explanation(case_id):
    """DPDP Act 2023 right-to-explanation endpoint."""
    try:
        from layer8.block_e_fairness import generate_explanation
        conn = get_db()
        explanation = generate_explanation(case_id, conn)
        conn.close()
        if explanation:
            log_audit(session['user_id'], 'DPDP_EXPLANATION_SERVED', case_id)
            return jsonify(explanation)
        return jsonify({"error": "No explanation available for this case"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/sma-dashboard')
@login_required
def layer8_sma_dashboard():
    """Return SMA counts + early warnings."""
    try:
        from layer8.block_f_npa import get_sma_dashboard, get_demo_sma_dashboard
        conn = get_db()
        data = get_sma_dashboard(conn)
        conn.close()
        if data.get("total_monitored", 0) == 0:
            data = get_demo_sma_dashboard()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/sma-update', methods=['POST'])
@login_required
def layer8_sma_update():
    """Update DPD for a sanctioned loan."""
    try:
        from layer8.block_f_npa import update_sma_status
        data = request.json
        conn = get_db()
        result = update_sma_status(conn, data["case_id"], data.get("dpd", 0),
                                    data.get("outstanding_lakhs", 0))
        conn.close()
        return jsonify({"status": "ok", "classification": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/crilc-submissions')
@login_required
def layer8_crilc_submissions():
    """List CRILC submissions."""
    try:
        from layer8.block_f_npa import get_crilc_submissions, get_demo_crilc
        conn = get_db()
        subs = get_crilc_submissions(conn, request.args.get("quarter"))
        conn.close()
        if not subs:
            subs = get_demo_crilc()
        return jsonify(subs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/retraining-status')
@login_required
def layer8_retraining_status():
    """Get retraining status + history."""
    try:
        from layer8.block_h_retrain import get_retraining_status, get_demo_retraining_status
        conn = get_db()
        data = get_retraining_status(conn)
        conn.close()
        if not data.get("history"):
            data = get_demo_retraining_status()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/trigger-retraining', methods=['POST'])
@login_required
def layer8_trigger_retraining():
    """Manually trigger retraining event."""
    try:
        from layer8.block_h_retrain import log_retrain_event
        data = request.json or {}
        conn = get_db()
        rid = log_retrain_event(conn, data.get("trigger", "MANUAL"),
                                 "INITIATED", data.get("details", {}))
        conn.close()
        log_audit(session['user_id'], 'LAYER8_RETRAIN_TRIGGERED', str(rid))
        return jsonify({"status": "ok", "retrain_id": rid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/quarterly-report')
@login_required
def layer8_quarterly_report():
    """Generate quarterly RBI validation report."""
    try:
        from layer8.block_i_report import generate_quarterly_report
        conn = get_db()
        report = generate_quarterly_report(conn)
        conn.close()
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/dashboard-data')
@login_required
def layer8_dashboard_data():
    """Aggregated data for all 6 governance panels."""
    try:
        from layer8.block_j_dashboard import get_dashboard_data
        conn = get_db()
        data = get_dashboard_data(conn)
        conn.close()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/model-documentation')
@login_required
def layer8_model_documentation():
    """Return model documentation package per RBI requirements."""
    try:
        from layer8.block_g_archive import get_model_documentation
        return jsonify(get_model_documentation())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/retention-policy')
@login_required
def layer8_retention_policy():
    """Return DPDP data retention policy."""
    try:
        from layer8.block_g_archive import get_retention_policy
        return jsonify(get_retention_policy())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_database()
    print("🚀 Intelli-Credit Engine starting on http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)


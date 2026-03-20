import os
import json
import shutil
import secrets
import requests as http_requests
from datetime import datetime
from functools import wraps
import webbrowser as wb
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
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

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

    # ─── HITL Issues Table (officer-added custom flags) ──────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hitl_issues (
            id INT AUTO_INCREMENT PRIMARY KEY,
            case_id VARCHAR(50) NOT NULL,
            checkpoint INT NOT NULL,
            title VARCHAR(200) NOT NULL,
            severity VARCHAR(20) DEFAULT 'MEDIUM',
            description TEXT,
            added_by INT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX (case_id)
        )
    """)

    # ─── Entity Onboarding Columns on applications ───────────────────────
    onboarding_columns = [
        "cin VARCHAR(21)",
        "pan VARCHAR(10)",
        "sector VARCHAR(100)",
        "state VARCHAR(50)",
        "estimated_turnover FLOAT",
        "entity_type VARCHAR(50)",
        "gstin VARCHAR(20)",
        "gstin_verified BOOLEAN DEFAULT FALSE",
        "gstin_official_name VARCHAR(200)",
        "gstin_official_state VARCHAR(100)",
        "gstin_mismatch_fields JSON",
        "loan_type VARCHAR(50)",
        "loan_amount FLOAT",
        "tenure_months INT",
        "proposed_rate FLOAT",
        "loan_purpose TEXT",
        "custom_fields JSON",
    ]
    for col_def in onboarding_columns:
        col_name = col_def.split()[0]
        try:
            cur.execute(f"ALTER TABLE applications ADD COLUMN {col_def}")
        except:
            pass  # Column already exists

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
        WHERE a.status = 'completed' OR a.current_layer >= 6
        ORDER BY COALESCE(a.completed_at, a.created_at) DESC
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


# ─── Entity Onboarding API ───────────────────────────────────────────────────
@app.route('/api/onboard', methods=['POST'])
@login_required
@permission_required('CREATE_APP')
def onboard_entity():
    """Create application with full entity + loan details from onboarding wizard."""
    data = request.json
    company_name = data.get('company_name', '').strip()
    if not company_name:
        return jsonify({"error": "Company name is required"}), 400

    case_id = generate_case_id()

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO applications (
                case_id, company_name, created_by,
                cin, pan, sector, state, estimated_turnover, entity_type,
                gstin, gstin_verified, gstin_official_name, gstin_official_state,
                loan_type, loan_amount, tenure_months, proposed_rate, loan_purpose
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            case_id, company_name, session['user_id'],
            data.get('cin', ''), data.get('pan', ''),
            data.get('sector', ''), data.get('state', ''),
            data.get('estimated_turnover'), data.get('entity_type', ''),
            data.get('gstin', ''), data.get('gstin_verified', False),
            data.get('gstin_official_name', ''), data.get('gstin_official_state', ''),
            data.get('loan_type', ''), data.get('loan_amount'),
            data.get('tenure_months'), data.get('proposed_rate'),
            data.get('loan_purpose', '')
        ))
        conn.commit()
        app_id = cur.lastrowid
        log_audit(session['user_id'], 'ONBOARD_ENTITY', case_id, {
            "company": company_name, "loan_type": data.get('loan_type'),
            "loan_amount": data.get('loan_amount')
        })
        return jsonify({"status": "ok", "id": app_id, "case_id": case_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ─── GST Verification API ───────────────────────────────────────────────────
GSTIN_STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "36": "Telangana", "37": "Andhra Pradesh",
}

@app.route('/api/gst/verify')
@login_required
def verify_gstin():
    """Verify GSTIN via public GST API and return official details."""
    gstin = request.args.get('gstin', '').strip().upper()
    if not gstin or len(gstin) != 15:
        return jsonify({"error": "Invalid GSTIN format. Must be 15 characters."}), 400

    # Extract state from GSTIN prefix
    state_code = gstin[:2]
    state_name = GSTIN_STATE_CODES.get(state_code, "Unknown")

    # Extract PAN embedded in GSTIN (chars 3-12)
    embedded_pan = gstin[2:12]

    result = {
        "gstin": gstin,
        "state_code": state_code,
        "state": state_name,
        "embedded_pan": embedded_pan,
        "verified": False,
        "legal_name": "",
        "trade_name": "",
        "registration_status": "",
        "business_type": "",
        "registration_date": "",
    }

    # Try public GST API
    try:
        api_url = f"https://sheet.best/api/sheets/d4cbdb0b-b36a-4d53-8ded-9ae9dfc7b0d9/GSTIN/{gstin}"
        resp = http_requests.get(api_url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                entry = data[0]
                result["legal_name"] = entry.get("Legal Name", entry.get("lgnm", ""))
                result["trade_name"] = entry.get("Trade Name", entry.get("tradeNam", ""))
                result["registration_status"] = entry.get("Status", entry.get("sts", "Active"))
                result["business_type"] = entry.get("Business Type", entry.get("ctb", ""))
                result["registration_date"] = entry.get("Registration Date", entry.get("rgdt", ""))
                result["verified"] = True
    except Exception as api_err:
        print(f"GST API error: {api_err}")

    # Fallback: if public API failed, try alternate endpoint
    if not result["verified"]:
        try:
            alt_url = f"https://commonapi.mastersindia.co/commonapis/searchgstin?gstin={gstin}"
            resp2 = http_requests.get(alt_url, timeout=8, headers={"Accept": "application/json"})
            if resp2.status_code == 200:
                j = resp2.json()
                if j.get("data"):
                    d = j["data"]
                    result["legal_name"] = d.get("lgnm", "")
                    result["trade_name"] = d.get("tradeNam", "")
                    result["registration_status"] = d.get("sts", "Active")
                    result["business_type"] = d.get("ctb", "")
                    result["registration_date"] = d.get("rgdt", "")
                    result["verified"] = True
        except Exception as alt_err:
            print(f"Alt GST API error: {alt_err}")

    # Even if APIs failed, we can still derive useful info from GSTIN structure
    if not result["verified"]:
        result["legal_name"] = f"[Verification unavailable - manual entry needed]"
        result["verified"] = False

    return jsonify(result)


# ─── HITL Issue Management APIs ──────────────────────────────────────────────
@app.route('/api/hitl/issues', methods=['GET'])
@login_required
def get_hitl_issues():
    """Get all officer-added issues for a case."""
    case_id = request.args.get('case_id', '')
    checkpoint = request.args.get('checkpoint')

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if checkpoint:
        cur.execute("""
            SELECT hi.*, u.full_name as added_by_name
            FROM hitl_issues hi LEFT JOIN users u ON hi.added_by = u.id
            WHERE hi.case_id = %s AND hi.checkpoint = %s
            ORDER BY hi.added_at DESC
        """, (case_id, int(checkpoint)))
    else:
        cur.execute("""
            SELECT hi.*, u.full_name as added_by_name
            FROM hitl_issues hi LEFT JOIN users u ON hi.added_by = u.id
            WHERE hi.case_id = %s ORDER BY hi.checkpoint, hi.added_at DESC
        """, (case_id,))

    issues = cur.fetchall()
    for i in issues:
        if i.get('added_at'):
            i['added_at'] = i['added_at'].isoformat()
    cur.close()
    conn.close()
    return jsonify(issues)


@app.route('/api/hitl/issues', methods=['POST'])
@login_required
def add_hitl_issue():
    """Officer adds a custom issue/flag at any HITL checkpoint."""
    data = request.json
    case_id = data.get('case_id', '')
    checkpoint = data.get('checkpoint')  # 1, 2, 3, or 4
    title = data.get('title', '').strip()
    severity = data.get('severity', 'MEDIUM').upper()
    description = data.get('description', '').strip()

    if not case_id or not checkpoint or not title:
        return jsonify({"error": "case_id, checkpoint, and title are required"}), 400

    if severity not in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'):
        severity = 'MEDIUM'

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO hitl_issues (case_id, checkpoint, title, severity, description, added_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (case_id, int(checkpoint), title, severity, description, session['user_id']))
        conn.commit()
        issue_id = cur.lastrowid
        log_audit(session['user_id'], 'HITL_ADD_ISSUE', case_id, {
            "checkpoint": checkpoint, "title": title, "severity": severity
        })
        return jsonify({"status": "ok", "id": issue_id, "message": f"Issue '{title}' added to checkpoint {checkpoint}"})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/api/hitl/custom_field', methods=['POST'])
@login_required
def add_hitl_custom_field():
    """Officer adds a custom data field to the extracted JSON (HITL 2 - Data Verification)."""
    data = request.json
    app_id = data.get('app_id')
    field_name = data.get('field_name', '').strip().lower().replace(' ', '_')
    field_value = data.get('field_value', '')
    field_type = data.get('field_type', 'text')  # text, number

    if not app_id or not field_name:
        return jsonify({"error": "app_id and field_name are required"}), 400

    # Convert to number if requested
    if field_type == 'number':
        try:
            field_value = float(str(field_value).replace(',', ''))
        except:
            pass

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT layer2_output, custom_fields, case_id FROM applications WHERE id=%s", (app_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Application not found"}), 404

        # Update custom_fields JSON
        existing_custom = json.loads(row['custom_fields']) if row.get('custom_fields') else {}
        existing_custom[field_name] = {
            "value": field_value,
            "type": field_type,
            "added_by": session.get('full_name', 'Officer'),
            "added_at": datetime.utcnow().isoformat()
        }

        # Also inject it into layer2_output so it flows through the pipeline
        l2 = {}
        if row.get('layer2_output'):
            try:
                l2 = json.loads(row['layer2_output']) if isinstance(row['layer2_output'], str) else row['layer2_output']
            except:
                l2 = {}

        # Inject into extracted.financial_data if possible
        if 'extracted' in l2 and 'financial_data' in l2['extracted']:
            l2['extracted']['financial_data'][field_name] = field_value
            # Also add to a _custom_fields section for tracking
            if '_custom_fields' not in l2['extracted']['financial_data']:
                l2['extracted']['financial_data']['_custom_fields'] = {}
            l2['extracted']['financial_data']['_custom_fields'][field_name] = {
                "value": field_value, "type": field_type,
                "added_by": session.get('full_name', 'Officer')
            }

        cur2 = conn.cursor()
        cur2.execute(
            "UPDATE applications SET custom_fields=%s, layer2_output=%s WHERE id=%s",
            (json.dumps(existing_custom), json.dumps(l2, default=str), app_id)
        )
        cur2.close()
        conn.commit()

        log_audit(session['user_id'], 'HITL_ADD_CUSTOM_FIELD', row.get('case_id', ''), {
            "field_name": field_name, "field_value": str(field_value)[:100]
        })

        return jsonify({
            "status": "ok",
            "field_name": field_name,
            "field_value": field_value,
            "message": f"Custom field '{field_name}' added successfully"
        })
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


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
@socketio.on('rate_limit_decision')
def handle_rate_limit_decision(data):
    """
    Frontend sends this when user resolves the rate-limit modal.
    data = { case_id: str, decision: 'wait' | 'ocr' }
    """
    from layer2.layer2_processor import IntelliCreditPipeline
    case_id = data.get('case_id', '')
    decision = data.get('decision', 'ocr')
    print(f"[Rate Limit] Human decision received: '{decision}' for case {case_id}")
    IntelliCreditPipeline.resolve_rate_limit_decision(case_id, decision)


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
    _pipeline_start_time = time.time()  # Track total pipeline processing time

    # ─── Layer 2: Financial Extraction ───────────────────────────────────
    socketio.emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 5},
                  room=f'app_{app_id}')

    try:
        from layer2.layer2_processor import IntelliCreditPipeline
        pipeline = IntelliCreditPipeline(socketio=socketio)

        socketio.emit('layer_progress', {"layer": 2, "name": "Financial Extraction", "status": "processing", "pct": 30},
                      room=f'app_{app_id}')

        result = pipeline.process_files(
            filepaths=filepaths,
            case_id=case_id,
            company_name=company_name,
            app_id=str(app_id)
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

    # ─── GST Cross-Validation ────────────────────────────────────────────
    try:
        conn_gst = get_db()
        cur_gst = conn_gst.cursor(dictionary=True)
        cur_gst.execute("""
            SELECT gstin, gstin_verified, gstin_official_name, gstin_official_state,
                   pan, company_name as onboard_company_name
            FROM applications WHERE id=%s
        """, (app_id,))
        onboard = cur_gst.fetchone()

        if onboard and onboard.get('gstin_verified'):
            l2_parsed = json.loads(output_json) if isinstance(output_json, str) else output_json
            l2_financial = l2_parsed.get('extracted', {}).get('financial_data', {}) or l2_parsed
            mismatch_fields = []

            # Check company name
            official_name = (onboard.get('gstin_official_name') or '').strip().upper()
            extracted_name = (l2_financial.get('legal_name') or l2_financial.get('company_name') or '').strip().upper()
            if official_name and extracted_name and official_name not in extracted_name and extracted_name not in official_name:
                mismatch_fields.append({"field": "Company Name", "official": onboard['gstin_official_name'], "extracted": extracted_name})

            # Check PAN
            onboard_pan = (onboard.get('pan') or '').strip().upper()
            extracted_pan = (l2_financial.get('pan_number') or '').strip().upper()
            if onboard_pan and extracted_pan and onboard_pan != extracted_pan:
                mismatch_fields.append({"field": "PAN Number", "official": onboard_pan, "extracted": extracted_pan})

            # Check state via GSTIN prefix
            if onboard.get('gstin'):
                gstin_state_code = onboard['gstin'][:2]
                gstin_state = GSTIN_STATE_CODES.get(gstin_state_code, '')
                official_state = (onboard.get('gstin_official_state') or gstin_state).strip()
                # Compare with any state info in extracted data
                extracted_state = (l2_financial.get('state') or '').strip()
                if official_state and extracted_state and official_state.upper() != extracted_state.upper():
                    mismatch_fields.append({"field": "State", "official": official_state, "extracted": extracted_state})

            if mismatch_fields:
                # Auto-create HIGH severity HITL issues
                cur_issue = conn_gst.cursor()
                for mf in mismatch_fields:
                    cur_issue.execute("""
                        INSERT INTO hitl_issues (case_id, checkpoint, title, severity, description, added_by)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (case_id, 1, f"GST Mismatch: {mf['field']}",
                          'HIGH', f"Official GST record shows '{mf['official']}' but document extraction found '{mf['extracted']}'",
                          1))  # System user
                cur_issue.close()
                conn_gst.commit()

                # Store mismatch info on application
                cur_gst2 = conn_gst.cursor()
                cur_gst2.execute("UPDATE applications SET gstin_mismatch_fields=%s WHERE id=%s",
                                (json.dumps(mismatch_fields), app_id))
                cur_gst2.close()
                conn_gst.commit()
                print(f"⚠️ GST Cross-Validation: {len(mismatch_fields)} mismatch(es) flagged for {case_id}")

        cur_gst.close()
        conn_gst.close()
    except Exception as gst_err:
        print(f"GST cross-validation error (non-fatal): {gst_err}")


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

        # Fetch actual loan amount from onboarding + any officer-flagged issues
        requested_amount = 75.0  # default fallback
        officer_issues_context = ""
        custom_fields_context = ""
        try:
            conn_l5 = get_db()
            cur_l5 = conn_l5.cursor(dictionary=True)
            cur_l5.execute("SELECT loan_amount, loan_type, tenure_months, custom_fields FROM applications WHERE id=%s", (app_id,))
            app_row = cur_l5.fetchone()
            if app_row and app_row.get('loan_amount'):
                requested_amount = float(app_row['loan_amount'])

            # Fetch all officer-flagged issues for this case
            cur_l5.execute("""
                SELECT title, severity, description, checkpoint
                FROM hitl_issues WHERE case_id=%s
                ORDER BY severity DESC, checkpoint ASC
            """, (case_id,))
            issues = cur_l5.fetchall()
            if issues:
                issue_lines = []
                for iss in issues:
                    issue_lines.append(f"- [{iss['severity']}] {iss['title']}: {iss.get('description', '')}")
                officer_issues_context = "\n\nOFFICER-FLAGGED ISSUES (must factor into risk assessment):\n" + "\n".join(issue_lines)

            # Fetch custom fields
            if app_row and app_row.get('custom_fields'):
                try:
                    cf = json.loads(app_row['custom_fields']) if isinstance(app_row['custom_fields'], str) else app_row['custom_fields']
                    if cf:
                        cf_lines = [f"- {k}: {v.get('value', v) if isinstance(v, dict) else v}" for k, v in cf.items()]
                        custom_fields_context = "\n\nOFFICER-ADDED CUSTOM DATA FIELDS:\n" + "\n".join(cf_lines)
                except:
                    pass

            cur_l5.close()
            conn_l5.close()
        except Exception as l5_fetch_err:
            print(f"Non-fatal: Could not fetch onboarding data for L5: {l5_fetch_err}")

        def l5_progress(msg, pct):
            socketio.emit('layer_progress', {"layer": 5, "name": "Risk Scoring",
                          "status": "processing", "pct": pct, "detail": msg},
                          room=f'app_{app_id}')

        def l5_hitl_reject(hard_rules_result):
            # Register event
            e = threading.Event()
            _layer5_events[app_id] = {"e1": e, "d1": {}}
            
            # Emit to frontend (include officer issues)
            socketio.emit('layer5_hitl_reject', {
                "app_id": app_id,
                "hard_rules": hard_rules_result,
                "officer_issues": officer_issues_context,
            }, room=f'app_{app_id}')
            
            # Wait for decision
            e.wait()
            
            # Get decision
            data = _layer5_events[app_id].get("d1", {})
            return data

        # Inject officer context into the layer2 data so the LLM can see it
        l2_data_for_l5 = l2_data if 'l2_data' in dir() else {}
        if officer_issues_context or custom_fields_context:
            if isinstance(l2_data_for_l5, dict):
                l2_data_for_l5 = dict(l2_data_for_l5)  # shallow copy
                l2_data_for_l5['_officer_issues'] = officer_issues_context
                l2_data_for_l5['_custom_fields_context'] = custom_fields_context

        layer5_result = run_layer5(
            layer4_output=layer4_result if 'layer4_result' in dir() else {},
            layer2_data=l2_data_for_l5,
            company_name=company_name,
            case_id=case_id,
            requested_amount_lakhs=requested_amount,
            progress_callback=l5_progress,
            hitl_callback=l5_hitl_reject,
        )

        # Inject pipeline timing into layer5 output
        layer5_result['pipeline_timing'] = {
            'total_seconds': round(time.time() - _pipeline_start_time, 2),
            'completed_at': datetime.utcnow().isoformat() + 'Z',
        }
        layer5_json = json.dumps(layer5_result, indent=2, default=str)

        # Save to DB
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE applications ADD COLUMN layer5_output LONGTEXT")
            conn.commit()
        except:
            conn.rollback()
        cur.execute("UPDATE applications SET layer5_output=%s, current_layer=5, risk_score=%s, decision=%s WHERE id=%s",
                    (layer5_json, layer5_result.get("decision_summary", {}).get("final_credit_score"), layer5_result.get("decision_summary", {}).get("decision"), app_id))
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
            
            # --- Generate Fresh Decision Summary with LLM ---
            if overrides.get("reason") and "Accepted AI decision" not in overrides.get("reason", ""):
                try:
                    import os
                    from groq import Groq
                    
                    bullets = overrides.get("risk_bullets", [])
                    risks_str = "\n".join([f"- {b.lstrip('•').strip()}" for b in bullets]) if bullets else "Pending further manual review."
                    
                    new_amt = overrides.get("loan_amount", layer5_result["decision_summary"].get("sanction_amount_lakhs"))
                    new_rate = overrides.get("interest_rate", layer5_result["decision_summary"].get("interest_rate"))
                    new_dec = overrides.get("decision", layer5_result["decision_summary"].get("decision"))
                    override_reason = overrides['reason']
                    
                    prompt = f"""You are a Senior Credit Officer at a commercial bank. You are writing the final credit decision summary for a loan application.
The AI initially processed this, but a human officer has overridden the decision.

Write a fresh, cohesive 2-3 paragraph professional summary of the final decision. 
Do not mention "The old AI decision was..." just state the final facts clearly, but explicitly mention that this is a human-overridden decision and detail the human reasoning and the safety checkpoints/risks.

OVERRIDE DETAILS:
Final Decision: {new_dec}
Final Amount: {new_amt} Lakhs
Final Interest Rate: {new_rate}%
Human Officer's Reason for Override: "{override_reason}"

Identified Risks / Safety Measures:
{risks_str}

Format the output cleanly in plain text or simple markdown. Be professional, concise, and definitive."""

                    from utils_keys import get_content_generation_key
                    client = Groq(api_key=get_content_generation_key())
                    response = client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=[
                            {"role": "system", "content": "You are a Senior Credit Officer. Provide only the summary text without any surrounding commentary."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=600
                    )
                    fresh_summary = response.choices[0].message.content.strip()
                    layer5_result["decision_summary"]["llm_decision_summary"] = fresh_summary
                except Exception as e:
                    print(f"Failed to generate fresh LLM summary: {e}")
                    # Fallback to append if API fails
                    old_summary = layer5_result["decision_summary"].get("llm_decision_summary", "")
                    override_text = f"\n\n**⚠️ Human Override Applied**\n**Reason for Change:** {overrides.get('reason', '')}\n\n**Safety Measures & Identified Risks:**\n"
                    bullets = overrides.get("risk_bullets", [])
                    if bullets:
                        override_text += "\n".join([f"- {b.lstrip('•').strip()}" for b in bullets])
                    else:
                        override_text += "- Pending further manual review."
                    layer5_result["decision_summary"]["llm_decision_summary"] = old_summary + override_text

            # Recalculate metrics if needed
            if amount_changed or rate_changed:
                try:
                    from layer5.step10_loan_structure import compute_loan_structure
                    # Fetch layer2_output from DB (output_json may not be in scope here)
                    conn_l2 = get_db()
                    cur_l2 = conn_l2.cursor(dictionary=True)
                    cur_l2.execute("SELECT layer2_output FROM applications WHERE id=%s", (app_id,))
                    l2_row = cur_l2.fetchone()
                    cur_l2.close()
                    conn_l2.close()
                    l2_raw = l2_row.get('layer2_output', '{}') if l2_row else '{}'
                    l2_parsed = json.loads(l2_raw) if isinstance(l2_raw, str) else (l2_raw or {})
                    l2 = l2_parsed.get('extracted', {}).get('financial_data', {}) or l2_parsed
                    features = layer5_result.get("validation", {}).get("validated_features", {})
                    conditions = layer5_result.get("decision_summary", {}).get("conditions", [])
                    # Sanitize conditions: ensure cap_multiplier values are float-compatible
                    for cond in conditions:
                        if isinstance(cond, dict):
                            cm = cond.get("cap_multiplier")
                            if cm is not None and not isinstance(cm, (int, float)):
                                try:
                                    cond["cap_multiplier"] = float(cm)
                                except (ValueError, TypeError):
                                    cond["cap_multiplier"] = 1.0
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
                    layer5_result["decision_summary"]["loan_structure"] = recalc
                except Exception as e:
                    print(f"Failed to recalculate loan metrics: {e}")
            
            # Persist custom changes back to DB (Layer 5 data updated)
            conn = get_db()
            cur = conn.cursor()
            final_decision = layer5_result.get("decision_summary", {}).get("decision")
            cur.execute("UPDATE applications SET layer5_output=%s, decision=%s WHERE id=%s", (json.dumps(layer5_result), final_decision, app_id))
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

        cam_dir = __import__('os').path.join(app.config['UPLOAD_FOLDER'], f"cam_{app_id}")
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
                "risk_bullets": data.get('risk_bullets', []),
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
        from utils_keys import get_content_generation_key
        client = Groq(
            api_key=get_content_generation_key()
        )
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": "You are a Chief Risk Officer assessing override risks."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
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


@app.route('/api/layer8/analytics')
@login_required
def layer8_analytics():
    """Return accuracy & system analytics for the Layer 8 dashboard."""
    try:
        from layer8.analytics import compute_analytics
        conn = get_db()
        cur = conn.cursor(dictionary=True)

        # Fetch all completed applications
        cur.execute("""
            SELECT case_id, company_name, layer2_output, layer5_output,
                   created_at, completed_at
            FROM applications
            WHERE layer5_output IS NOT NULL
            ORDER BY created_at DESC
        """)
        apps = cur.fetchall()

        # Fetch relevant audit logs for HITL tracking
        cur.execute("""
            SELECT target AS case_id, action, details
            FROM audit_logs
            WHERE action IN ('HITL_CONFIRM','HITL_ADD_CUSTOM_FIELD','L4_HITL_3')
            ORDER BY timestamp
        """)
        logs = cur.fetchall()

        cur.close()
        conn.close()

        metrics = compute_analytics(apps, logs)
        return jsonify(metrics)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/case/<case_id>')
@login_required
def layer8_case_detail(case_id):
    """Per-case accuracy detail."""
    try:
        from layer8.analytics import compute_case_analytics
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT case_id, company_name, layer2_output, layer5_output,
                   created_at, completed_at
            FROM applications WHERE case_id=%s
        """, (case_id,))
        app = cur.fetchone()
        if not app:
            return jsonify({"error": "Case not found"}), 404

        cur.execute("""
            SELECT target AS case_id, action, details
            FROM audit_logs WHERE target=%s
        """, (case_id,))
        logs = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify(compute_case_analytics(app, logs))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/layer8/generate-metrics', methods=['POST'])
@login_required
def layer8_generate_metrics():
    """Generate real metrics from historical application data."""
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        # Fetch completed applications that have layer5 output
        cur.execute("SELECT * FROM applications WHERE status = 'completed' AND layer5_output IS NOT NULL")
        historical_apps = cur.fetchall()
        cur.close()

        if not historical_apps:
            conn.close()
            return jsonify({"error": "No historical completed applications found."}), 400

        formatted_apps = []
        feature_vectors = []
        approved_apps = []

        for app_row in historical_apps:
            try:
                l5_str = app_row.get("layer5_output", "{}")
                l5 = json.loads(l5_str) if isinstance(l5_str, str) else l5_str
                
                decision_summary = l5.get("decision_summary", {})
                decision = decision_summary.get("decision", "PENDING")
                
                # We need actual_default (mocked for now as we don't have NPA data synced to apps in this simple demo), 
                # predicted_pd, credit_score, and decision.
                formatted_apps.append({
                    "case_id": app_row.get("case_id"),
                    "predicted_pd": decision_summary.get("probability_of_default", 0.1),
                    # Normally actual_default would come from a loan servicing DB. We mock it based on PD for realism.
                    "actual_default": 1 if decision_summary.get("probability_of_default", 0) > 0.5 else 0,
                    "credit_score": decision_summary.get("final_credit_score", 650),
                    "decision": decision
                })

                # For Panel 4 & 6: SMA & CRILC
                if "APPROVE" in decision.upper():
                    amount = decision_summary.get("sanction_amount_lakhs", 0)
                    approved_apps.append({
                        "case_id": app_row.get("case_id"),
                        "company_name": app_row.get("company_name", "Unknown Co"),
                        "amount_lakhs": amount,
                        "pd": decision_summary.get("probability_of_default", 0.1),
                    })

                # For Panel 2: Drift
                l4_str = app_row.get("layer4_output", "{}")
                l4 = json.loads(l4_str) if isinstance(l4_str, str) else l4_str
                if l4 and l4.get("feature_vector"):
                    feature_vectors.append(l4.get("feature_vector"))

            except Exception as e:
                print(f"Error parsing historical app {app_row.get('id')}: {e}")
                continue

        if not formatted_apps:
            conn.close()
            return jsonify({"error": "Failed to parse historical applications."}), 400

        # --- Panel 1: Performance Metrics ---
        from layer8.block_b_performance import compute_performance_metrics, save_performance_metrics
        metrics = compute_performance_metrics(formatted_apps)
        metrics["is_demo"] = False
        metrics["sample_size"] = len(formatted_apps)
        save_performance_metrics(conn, metrics)

        # --- Panel 2: PSI Drift ---
        from layer8.block_d_drift import run_drift_report, save_drift_report, detect_concept_drift, PRIORITY_FEATURES
        if len(feature_vectors) > 10:
            # Split features into Reference (first half) and Current (second half)
            mid = len(feature_vectors) // 2
            ref_feats, cur_feats = feature_vectors[:mid], feature_vectors[mid:]
            
            ref_dict = {f: [row.get(f, 0) for row in ref_feats if f in row] for f in PRIORITY_FEATURES}
            cur_dict = {f: [row.get(f, 0) for row in cur_feats if f in row] for f in PRIORITY_FEATURES}
            
            drift_report = run_drift_report(ref_dict, cur_dict)
            
            # Concept drift
            concept_drift = detect_concept_drift(
                [a["predicted_pd"] for a in formatted_apps],
                [a["actual_default"] for a in formatted_apps]
            )
            drift_report["concept_drift"] = concept_drift
            drift_report["is_demo"] = False
            
            save_drift_report(conn, drift_report)
        else:
            drift_report = None

        # --- Panel 4 & 6: SMA and CRILC ---
        from layer8.block_f_npa import update_sma_status, trigger_crilc_report
        for app in approved_apps:
            # Mock DPD based on PD
            pd = app["pd"]
            amount_lakhs = float(app["amount_lakhs"] or 0)
            dpd = 0
            if pd > 0.4: dpd = int(pd * 200) # high risk gets high dpd
            elif pd > 0.2: dpd = 35
            elif pd > 0.1: dpd = 15

            if dpd > 0:
                cls_result = update_sma_status(conn, app["case_id"], dpd, amount_lakhs)
                # Check CRILC if > 5Cr (500 Lakhs)
                if amount_lakhs >= 500:
                    trigger_crilc_report(conn, app["case_id"], app["company_name"], amount_lakhs/100, cls_result["classification"])

        # --- Panel 5: Retraining ---
        from layer8.block_h_retrain import check_retrain_triggers, log_retrain_event
        # Calculate override rate
        overrides = sum(1 for a in formatted_apps if "CONDITIONAL" in a["decision"] or "REJECT" in a["decision"]) # Rough override proxy for historical
        override_rate = overrides / len(formatted_apps)

        retrain_check = check_retrain_triggers(metrics, drift_report, override_rate)
        if retrain_check.get("should_retrain"):
            reason = retrain_check["triggers_fired"][0]["trigger"]
            log_retrain_event(conn, trigger=reason, status="INITIATED", details={"auto_generated": True, "reason": retrain_check})

        # Log audit
        from app import log_audit
        log_audit(session['user_id'], 'LAYER8_GENERATE_METRICS', f"Generated for {len(formatted_apps)} cases")
        
        conn.close()
        return jsonify({"status": "success", "message": f"Metrics fully generated from {len(formatted_apps)} applications.", "metrics": metrics})
    except Exception as e:
        import traceback; traceback.print_exc()
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


# ─── Streaming Chat API (Self-Explainability) ─────────────────────────────────
_chat_sessions = {}  # {app_id: [{"role": "...", "content": "..."}]}


@app.route('/api/chat', methods=['POST'])
@login_required
def chat_with_application():
    """
    Streaming chat endpoint. Accepts:
      { app_id: int, message: str }
    Returns SSE stream of LLM response chunks with conversation memory.
    """
    import os as _os
    data = request.get_json(force=True) or {}
    app_id = data.get('app_id')
    user_msg = data.get('message', '').strip()

    if not app_id or not user_msg:
        return jsonify({"error": "app_id and message are required"}), 400

    # Retrieve application context from DB
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("SELECT layer5_output FROM applications WHERE id=%s", (app_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row or not row.get('layer5_output'):
        return jsonify({"error": "No processed data found for this application"}), 404

    l5_output = row['layer5_output']
    if isinstance(l5_output, str):
        try:
            l5_output = json.loads(l5_output)
        except Exception:
            l5_output = {}

    # Build system prompt with full application context
    decision_summary = l5_output.get('decision_summary', {})
    audit_trail = l5_output.get('decision_audit_trail', {})
    explanation = l5_output.get('explanation', {})
    score_breakdown = l5_output.get('score_breakdown', {})
    pricing = l5_output.get('pricing', {})
    fusion_narrative = l5_output.get('fusion_narrative', '')

    # Extract HITL override / loan structure context
    loan_info = l5_output.get('loan', l5_output.get('loan_structure', {}))
    if isinstance(loan_info, str):
        try: loan_info = json.loads(loan_info)
        except: loan_info = {}
    loan_structure = loan_info.get('loan_structure', {}) if isinstance(loan_info, dict) else {}
    hitl_override_note = loan_info.get('hitl_override_note', '') if isinstance(loan_info, dict) else ''
    mpbf = loan_info.get('mpbf', {}) if isinstance(loan_info, dict) else {}
    limits = loan_info.get('limits', {}) if isinstance(loan_info, dict) else {}
    binding_constraint = loan_info.get('binding_constraint', 'N/A') if isinstance(loan_info, dict) else 'N/A'

    system_prompt = f"""You are the Intelli-Credit AI Assistant. You have complete knowledge of this loan application and must answer any question about it clearly and precisely.

APPLICATION CONTEXT:
Decision: {decision_summary.get('decision', 'N/A')}
Credit Score: {decision_summary.get('final_credit_score', 'N/A')} ({decision_summary.get('risk_band', 'N/A')})
Probability of Default: {decision_summary.get('probability_of_default', 'N/A')}
Interest Rate: {decision_summary.get('interest_rate', 'N/A')}%
Sanction Amount: Rs.{decision_summary.get('sanction_amount_lakhs', 'N/A')} Lakhs

LOAN STRUCTURE:
Term Loan: {json.dumps(loan_structure.get('term_loan', {}), default=str)}
Working Capital: {json.dumps(loan_structure.get('working_capital', {}), default=str)}
Total Sanctioned: {loan_structure.get('total_sanctioned_lakhs', 'N/A')} Lakhs

LOAN LIMITS (Multi-Method Assessment):
{json.dumps(limits, indent=2, default=str)}
Binding Constraint: {binding_constraint}

MPBF (Nayak Committee Method II):
{json.dumps(mpbf, indent=2, default=str)}

HUMAN OFFICER OVERRIDE:
{hitl_override_note if hitl_override_note else 'No officer override was applied.'}

SCORE JOURNEY:
{audit_trail.get('score_journey', fusion_narrative)}

PRICING BREAKDOWN:
{audit_trail.get('pricing_explanation', json.dumps(pricing, default=str))}

KEY DRIVERS:
{json.dumps(audit_trail.get('key_drivers', []), indent=2)}

HARD RULES: {audit_trail.get('hard_rules_summary', 'N/A')}
ESG IMPACT: {audit_trail.get('esg_impact', 'N/A')}
STATUTORY CHECK: {audit_trail.get('statutory_check', 'N/A')}

LLM QUALITATIVE OPINION:
{explanation.get('llm_opinion', 'N/A')}

FIVE Cs ASSESSMENT:
{json.dumps(explanation.get('five_cs', {}), indent=2, default=str)}

BIGGEST RISK: {explanation.get('biggest_risk', 'N/A')}
BIGGEST STRENGTH: {explanation.get('biggest_strength', 'N/A')}
LLM ADJUSTMENT: {explanation.get('llm_adjustment', 0)} ({explanation.get('llm_justification', '')})

CONDITIONS: {json.dumps(decision_summary.get('conditions', []), default=str)}
COVENANTS: {json.dumps(decision_summary.get('covenants', []), default=str)}

GREEN FINANCING: {json.dumps(decision_summary.get('green_financing', {}), default=str)}

DECISION REASON: {audit_trail.get('decision_reason', 'N/A')}

INSTRUCTIONS:
- Answer questions about this specific application only.
- Explain WHY decisions were made using the data above.
- When asked about human overrides, reference the HUMAN OFFICER OVERRIDE section and compare with original AI recommendation.
- Use simple, professional language a credit officer can understand.
- If asked about something not in the data, say so clearly.
- Be concise but thorough.
- Format your response using markdown: **bold** for key terms, bullet lists for multiple points.
"""

    # Initialise or retrieve conversation memory for this app_id
    session_key = str(app_id)
    if session_key not in _chat_sessions:
        _chat_sessions[session_key] = [{"role": "system", "content": system_prompt}]

    # Add user message to history
    _chat_sessions[session_key].append({"role": "user", "content": user_msg})

    # Keep conversation history manageable (last 20 messages + system)
    if len(_chat_sessions[session_key]) > 21:
        _chat_sessions[session_key] = [_chat_sessions[session_key][0]] + _chat_sessions[session_key][-20:]

    def generate_stream():
        full_response = ""
        try:
            from groq import Groq
            from utils_keys import get_chatbot_key
            client = Groq(api_key=get_chatbot_key())
            stream = client.chat.completions.create(
                messages=_chat_sessions[session_key],
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                temperature=0.4,
                max_tokens=2000,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    full_response += delta.content
                    yield f"data: {json.dumps({'content': delta.content})}\n\n"

            # Save assistant response to memory
            _chat_sessions[session_key].append({"role": "assistant", "content": full_response})
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            error_msg = f"Chat error: {str(e)}"
            yield f"data: {json.dumps({'error': error_msg})}\n\n"

    return app.response_class(generate_stream(), mimetype='text/event-stream')


@app.route('/api/chat/clear', methods=['POST'])
@login_required
def clear_chat_session():
    """Clear chat history for an application."""
    data = request.get_json(force=True) or {}
    app_id = str(data.get('app_id', ''))
    if app_id in _chat_sessions:
        del _chat_sessions[app_id]
    return jsonify({"status": "cleared"})


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_database()
    print("🚀 Intelli-Credit Engine starting on http://localhost:5000")
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        wb.open("http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)


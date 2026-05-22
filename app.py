from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'faultnet-ultra-secret-2024'

DB_PATH = 'faults.db'
ADMIN_PASSWORD = '12345'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS faults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            machine_id TEXT DEFAULT 'UNKNOWN',
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            ai_issue TEXT DEFAULT '-',
            ai_urgency TEXT DEFAULT '-',
            ai_action TEXT DEFAULT '-',
            submitted_by TEXT DEFAULT 'Operator',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def ai_classify(description):
    text = description.lower()

    rules = [
        (['smoke', 'fire', 'flame', 'blaze'],         'Fire Hazard',             'CRITICAL', 'Emergency Stop Now'),
        (['overheat', 'overheating', 'temperature high', 'too hot', 'thermal', 'burning smell'],
                                                       'Thermal Overload',        'CRITICAL', 'Shutdown & Cool Down'),
        (['spark', 'short circuit', 'electrical fault', 'tripped', 'fuse blown', 'arc flash'],
                                                       'Electrical Fault',        'CRITICAL', 'Isolate Power Supply'),
        (['vibration', 'vibrating', 'shaking', 'rattling', 'oscillat'],
                                                       'Mechanical Imbalance',    'HIGH',     'Balance & Realign Unit'),
        (['bearing', 'grinding', 'squealing', 'screech', 'worn'],
                                                       'Bearing Failure',         'HIGH',     'Replace Bearing Immediately'),
        (['leak', 'oil leak', 'hydraulic leak', 'fluid', 'pressure drop', 'seal broken'],
                                                       'Hydraulic Leak',          'HIGH',     'Seal Leak & Repressurize'),
        (['belt', 'conveyor', 'chain', 'misalign', 'slipping'],
                                                       'Mechanical Misalignment', 'MEDIUM',   'Realign & Tighten Belt'),
        (['sensor', 'plc', 'signal', 'reading error', 'software', 'firmware', 'controller'],
                                                       'Sensor / PLC Fault',      'MEDIUM',   'Recalibrate Sensors'),
        (['slow', 'low speed', 'rpm drop', 'reduced performance', 'sluggish'],
                                                       'Motor Degradation',       'MEDIUM',   'Run Load Diagnostic'),
        (['noise', 'loud', 'unusual sound', 'clunking', 'banging'],
                                                       'Structural Resonance',    'MEDIUM',   'Inspect & Dampen'),
        (['coolant', 'cooling', 'fan', 'heat exchanger'],
                                                       'Cooling System Fault',    'HIGH',     'Check Coolant Flow'),
        (['pump', 'flow rate', 'blockage', 'clog'],    'Flow/Pump Blockage',      'HIGH',     'Clear Blockage & Test'),
    ]

    for keywords, issue, urgency, action in rules:
        if any(kw in text for kw in keywords):
            return issue, urgency, action

    return 'General Fault', 'LOW', 'Log & Schedule Inspection'


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            error = 'ACCESS DENIED — Invalid credentials'
    return render_template('access.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/submit', methods=['GET', 'POST'])
def submit():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    success = False
    if request.method == 'POST':
        title        = request.form.get('title', '').strip()
        description  = request.form.get('description', '').strip()
        machine_id   = request.form.get('machine_id', 'UNKNOWN').strip()
        priority     = request.form.get('priority', 'medium')
        submitted_by = request.form.get('submitted_by', 'Operator').strip()

        ai_issue, ai_urgency, ai_action = ai_classify(description)

        conn = get_db()
        conn.execute('''
            INSERT INTO faults
              (title, description, machine_id, priority, status, ai_issue, ai_urgency, ai_action, submitted_by)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
        ''', (title, description, machine_id, priority, ai_issue, ai_urgency, ai_action, submitted_by))
        conn.commit()
        conn.close()
        success = True

    return render_template('index.html', success=success)


@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session:
        return redirect(url_for('login'))

    conn   = get_db()
    faults = conn.execute('SELECT * FROM faults ORDER BY created_at DESC').fetchall()
    conn.close()

    total       = len(faults)
    critical    = sum(1 for f in faults if f['ai_urgency'] == 'CRITICAL' and f['status'] != 'resolved')
    in_progress = sum(1 for f in faults if f['status'] == 'in_progress')
    resolved    = sum(1 for f in faults if f['status'] == 'resolved')
    open_count  = sum(1 for f in faults if f['status'] == 'open')

    return render_template('dashboard.html',
        faults=faults,
        total=total,
        critical=critical,
        in_progress=in_progress,
        resolved=resolved,
        open_count=open_count
    )


@app.route('/update/<int:fault_id>', methods=['POST'])
def update_status(fault_id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    new_status = request.form.get('status', 'open')
    conn = get_db()
    conn.execute('UPDATE faults SET status = ? WHERE id = ?', (new_status, fault_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/delete/<int:fault_id>', methods=['POST'])
def delete_fault(fault_id):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    conn.execute('DELETE FROM faults WHERE id = ?', (fault_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/api/classify', methods=['POST'])
def classify_api():
    data = request.get_json(silent=True) or {}
    description = data.get('description', '')
    if len(description.strip()) < 5:
        return jsonify({'issue': '—', 'urgency': '—', 'action': '—'})
    issue, urgency, action = ai_classify(description)
    return jsonify({'issue': issue, 'urgency': urgency, 'action': action})


# ─── Boot ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

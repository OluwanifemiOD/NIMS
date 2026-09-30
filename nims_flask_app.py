import os
import platform
import subprocess
import json
import csv
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO, BytesIO
from functools import wraps

from flask import (
    Flask, request, redirect, url_for, flash, session,
    send_file, jsonify, Response, render_template_string
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Paths & static creation

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DB_PATH = os.path.join(BASE_DIR, 'devices.db')
os.makedirs(STATIC_DIR, exist_ok=True)

# Static: index.html (dashboard), main.js, style.css
INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>NIMS - Network Inventory</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="/static/style.css" rel="stylesheet">
</head>
<body>
  <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
    <div class="container">
      <a class="navbar-brand" href="#">NIMS</a>
      <div class="collapse navbar-collapse">
        <ul class="navbar-nav ms-auto">
          <li class="nav-item"><a class="nav-link btn btn-sm btn-light text-primary mx-1" href="/change_password">Change Password</a></li>
          <li class="nav-item"><a class="nav-link" href="/logout">Logout</a></li>
        </ul>
      </div>
    </div>
  </nav>

  <div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h2>Network Inventory Dashboard</h2>
      <div>
        <button id="addBtn" class="btn btn-primary me-2" data-bs-toggle="modal" data-bs-target="#addDeviceModal">Add Device</button>
        <a href="/export" class="btn btn-outline-secondary me-2">Export CSV</a>
        <button id="pingAllBtn" class="btn btn-success">Ping All Devices</button>
      </div>
    </div>

    <div class="row mb-3">
      <div class="col-md-4"><div class="card p-3"><h6 class="mb-1">Total Devices</h6><h3 id="total">0</h3></div></div>
      <div class="col-md-4"><div class="card p-3"><h6 class="mb-1">Online</h6><h3 id="online">0</h3></div></div>
      <div class="col-md-4"><div class="card p-3"><h6 class="mb-1">Offline</h6><h3 id="offline">0</h3></div></div>
    </div>

    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover mb-0" id="devicesTable">
          <thead class="table-light">
            <tr>
              <th>Hostname</th><th>IP</th><th>Type</th><th>Department</th>
              <th>Location</th><th>Status</th><th>Last Checked (UTC)</th><th>Actions</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Add Device Modal -->
  <div class="modal fade" id="addDeviceModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
      <form class="modal-content" action="/add" method="post">
        <div class="modal-header">
          <h5 class="modal-title">Add New Device</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <div class="mb-3"><label class="form-label">Hostname</label><input class="form-control" name="hostname" required></div>
          <div class="mb-3"><label class="form-label">IP Address</label><input class="form-control" name="ip_address" required></div>
          <div class="mb-3"><label class="form-label">Device Type</label><input class="form-control" name="device_type"></div>
          <div class="mb-3"><label class="form-label">Department</label><input class="form-control" name="department"></div>
          <div class="mb-3"><label class="form-label">Location</label><input class="form-control" name="location"></div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" type="submit">Add Device</button>
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
        </div>
      </form>
    </div>
  </div>

  <script src="/static/main.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

MAIN_JS = r'''// static/main.js for dashboard interactions
async function fetchDevices() {
  const resp = await fetch('/api/devices');
  if (!resp.ok) return;
  const list = await resp.json();
  renderDevices(list);
}
function renderDevices(devices) {
  const tbody = document.querySelector('#devicesTable tbody');
  tbody.innerHTML = '';
  let total = devices.length, online = 0, offline = 0;
  devices.forEach(d => {
    if (d.status === 'Online') online++;
    if (d.status === 'Offline') offline++;
    const tr = document.createElement('tr');
    tr.dataset.id = d.id;
    tr.innerHTML = `
      <td>${d.hostname}</td>
      <td>${d.ip_address}</td>
      <td>${d.device_type||''}</td>
      <td>${d.department||''}</td>
      <td>${d.location||''}</td>
      <td class="status-cell">${statusBadge(d.status)}</td>
      <td class="last-cell">${d.last_checked || 'Never'}</td>
      <td>
        <button class="btn btn-sm btn-info pingBtn">Ping</button>
        <button class="btn btn-sm btn-danger deleteBtn">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('total').innerText = total;
  document.getElementById('online').innerText = online;
  document.getElementById('offline').innerText = offline;
}
function statusBadge(status) {
  if (!status) return '<span class="text-muted">Unknown</span>';
  if (status === 'Online') return '<span class="text-success fw-bold">Online</span>';
  if (status === 'Offline') return '<span class="text-danger fw-bold">Offline</span>';
  return '<span class="text-muted">Unknown</span>';
}
document.addEventListener('click', async (e) => {
  if (e.target.classList.contains('pingBtn')) {
    const tr = e.target.closest('tr'); const id = tr.dataset.id;
    const resp = await fetch('/api/ping/' + id); const obj = await resp.json();
    tr.querySelector('.status-cell').innerHTML = statusBadge(obj.status);
    tr.querySelector('.last-cell').innerText = obj.last_checked || 'Never';
    fetchDevices();
  }
  if (e.target.classList.contains('deleteBtn')) {
    if (!confirm('Delete device?')) return;
    const tr = e.target.closest('tr'); const id = tr.dataset.id;
    await fetch('/delete/' + id, {method:'POST'}); fetchDevices();
  }
});
async function pingAll(btn) {
  btn.disabled = true; btn.innerText = 'Pinging...';
  const resp = await fetch('/api/ping_all', {method:'POST'});
  if (!resp.ok) { btn.disabled=false; btn.innerText='Ping All Devices'; return; }
  const reader = resp.body.getReader(); const decoder = new TextDecoder();
  let partial = '';
  while(true) {
    const {done, value} = await reader.read(); if (done) break;
    partial += decoder.decode(value, {stream:true});
    const lines = partial.split('\n'); partial = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      const obj = JSON.parse(line);
      const row = document.querySelector('tr[data-id="'+obj.id+'"]');
      if (row) {
        row.querySelector('.status-cell').innerHTML = statusBadge(obj.status);
        row.querySelector('.last-cell').innerText = obj.last_checked || 'Never';
      }
    }
  }
  fetchDevices(); btn.disabled=false; btn.innerText='Ping All Devices';
}
document.getElementById('pingAllBtn').addEventListener('click', function(){ pingAll(this); });
window.addEventListener('load', fetchDevices);
setInterval(fetchDevices, 30000); // auto refresh every 30s
'''

STYLE_CSS = r'''body { background:#f7fafc; font-family:system-ui, Arial, sans-serif; }
.navbar { box-shadow: 0 3px 12px rgba(2,6,23,0.08); }
.card { border-radius: 10px; } .table thead th { background:#f3f6fa; }
'''

# Write static files (overwrite)
with open(os.path.join(STATIC_DIR, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(INDEX_HTML)
with open(os.path.join(STATIC_DIR, 'main.js'), 'w', encoding='utf-8') as f:
    f.write(MAIN_JS)
with open(os.path.join(STATIC_DIR, 'style.css'), 'w', encoding='utf-8') as f:
    f.write(STYLE_CSS)

# -------------------------
# App & DB
# -------------------------
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'replace-with-strong-secret'  # replace for production

db = SQLAlchemy(app)

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(64), nullable=False)
    device_type = db.Column(db.String(64))
    department = db.Column(db.String(64))
    location = db.Column(db.String(120))
    status = db.Column(db.String(32), default='Unknown')
    date_added = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_checked = db.Column(db.DateTime, nullable=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

with app.app_context():
    db.create_all()
    # create default admin if missing
    if not User.query.filter_by(username='admin').first():
        u = User(username='admin'); u.set_password('admin123')
        db.session.add(u); db.session.commit()
        print('Created default admin/admin123')

# -------------------------
# Utilities
# -------------------------
IS_WINDOWS = platform.system().lower().startswith('win')
PING_COUNT_PARAM = '-n' if IS_WINDOWS else '-c'

def ping_ip(ip, timeout=3):
    try:
        proc = subprocess.run(['ping', PING_COUNT_PARAM, '1', ip],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        return proc.returncode == 0
    except Exception:
        return False

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapped

# -------------------------
# Auth
# -------------------------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        uname = request.form.get('username','').strip()
        pwd = request.form.get('password','')
        user = User.query.filter_by(username=uname).first()
        if user and user.check_password(pwd):
            session['user_id'] = user.id
            return redirect('/')
        flash('Invalid credentials', 'danger')
    # simple bootstrap login page
    return render_template_string('''
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<title>Login - NIMS</title></head><body style="background:#f7fafc">
<div class="container d-flex justify-content-center align-items-center" style="height:85vh">
  <div class="card p-4" style="width:380px">
    <h4 class="mb-3">NIMS Login</h4>
    <form method="post">
      <div class="mb-3"><label class="form-label">Username</label><input name="username" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Password</label><input name="password" type="password" class="form-control" required></div>
      <button class="btn btn-primary w-100">Login</button>
    </form>
  </div>
</div></body></html>
''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# -------------------------
# Change Password (accessible via button in admin header)
# -------------------------
@app.route('/change_password', methods=['GET','POST'])
@login_required
def change_password():
    if request.method == 'GET':
        return render_template_string('''
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<title>Change Password</title></head><body style="background:#f7fafc">
<div class="container" style="max-width:520px;padding-top:40px">
  <div class="card p-3">
    <h4 class="mb-3">Change Password</h4>
    <form method="post">
      <div class="mb-3"><label class="form-label">Current Password</label><input name="current_password" type="password" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">New Password</label><input name="new_password" type="password" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Confirm New Password</label><input name="confirm_password" type="password" class="form-control" required></div>
      <div class="d-flex gap-2"><button class="btn btn-primary">Update Password</button><a class="btn btn-secondary" href="/">Cancel</a></div>
    </form>
  </div>
</div>
</body></html>
''')
    # POST: validate and update password
    current = request.form.get('current_password','')
    new = request.form.get('new_password','')
    confirm = request.form.get('confirm_password','')
    user = User.query.get(session.get('user_id'))
    if not user:
        flash('User not found', 'danger'); return redirect('/login')
    if not user.check_password(current):
        flash('Current password incorrect', 'danger'); return redirect('/change_password')
    if new != confirm:
        flash('New passwords do not match', 'danger'); return redirect('/change_password')
    user.set_password(new); db.session.commit()
    flash('Password updated', 'success')
    return redirect('/')

# -------------------------
# API & management
# -------------------------
@app.route('/api/devices')
@login_required
def api_devices():
    devices = Device.query.order_by(Device.hostname).all()
    out = []
    for d in devices:
        out.append({
            'id': d.id,
            'hostname': d.hostname,
            'ip_address': d.ip_address,
            'device_type': d.device_type,
            'department': d.department,
            'location': d.location,
            'status': d.status,
            'last_checked': d.last_checked.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if d.last_checked else None
        })
    return jsonify(out)

@app.route('/api/ping/<int:id>')
@login_required
def api_ping(id):
    d = Device.query.get_or_404(id)
    ok = ping_ip(d.ip_address)
    d.status = 'Online' if ok else 'Offline'
    d.last_checked = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'id': d.id, 'status': d.status, 'last_checked': d.last_checked.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')})

@app.route('/api/ping_all', methods=['POST'])
@login_required
def api_ping_all():
    devices = Device.query.all()
    app_obj = app
    def generate():
        with ThreadPoolExecutor(max_workers=10) as ex:
            future_to_dev = {ex.submit(ping_ip, d.ip_address): d for d in devices}
            for future in as_completed(future_to_dev):
                d = future_to_dev[future]
                try:
                    ok = future.result()
                except Exception:
                    ok = False
                d.status = 'Online' if ok else 'Offline'
                d.last_checked = datetime.now(timezone.utc)
                with app_obj.app_context():
                    db.session.merge(d); db.session.commit()
                yield json.dumps({
                    'id': d.id,
                    'status': d.status,
                    'last_checked': d.last_checked.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                }) + "\n"
    return Response(generate(), mimetype='application/json')

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_device(id):
    d = Device.query.get_or_404(id); db.session.delete(d); db.session.commit()
    return ('', 204)

@app.route('/add', methods=['POST'])
@login_required
def add_device():
    hostname = request.form.get('hostname'); ip = request.form.get('ip_address')
    if not hostname or not ip: return 'missing', 400
    d = Device(hostname=hostname, ip_address=ip,
               device_type=request.form.get('device_type'),
               department=request.form.get('department'),
               location=request.form.get('location'),
               status='Unknown')
    db.session.add(d); db.session.commit()
    return redirect('/')

@app.route('/export')
@login_required
def export_csv():
    devices = Device.query.all()
    sio = StringIO(); writer = csv.writer(sio)
    writer.writerow(['id','hostname','ip_address','device_type','department','location','status','date_added','last_checked'])
    for d in devices:
        writer.writerow([
            d.id, d.hostname, d.ip_address, d.device_type, d.department, d.location, d.status,
            d.date_added.isoformat() if d.date_added else '',
            d.last_checked.astimezone(timezone.utc).isoformat() if d.last_checked else ''
        ])
    return send_file(BytesIO(sio.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name='inventory.csv')

# -------------------------
# Root / static serve
# -------------------------
@app.route('/')
def root():
    if 'user_id' not in session:
        return redirect('/login')
    return send_file(os.path.join(STATIC_DIR, 'index.html'))

# -------------------------
# Seed demo devices if empty
# -------------------------
def seed_demo():
    if Device.query.count() == 0:
        demo = [
            Device(hostname='Router-HQ', ip_address='8.8.8.8', device_type='Router', department='Network', location='HQ'),
            Device(hostname='Switch-A', ip_address='1.1.1.1', device_type='Switch', department='Branch', location='Floor 1'),
            Device(hostname='Server-DB', ip_address='10.255.255.5', device_type='Server', department='Infra', location='DC'),
        ]
        db.session.add_all(demo); db.session.commit()
        print('Seeded demo devices')

with app.app_context():
    seed_demo()

# -------------------------
# Run
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)
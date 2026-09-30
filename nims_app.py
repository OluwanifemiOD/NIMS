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

# -------------------------
# Paths & static creation
# -------------------------
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@100..900&display=swap" rel="stylesheet">
  <link href="/static/style.css" rel="stylesheet">
</head>
<body class="bg-body-tertiary">
  <div class="toast-container position-fixed top-0 end-0 p-3" style="z-index: 1100"></div>

  <nav class="navbar navbar-expand-lg navbar-light bg-white border-bottom">
    <div class="container">
      <a class="navbar-brand d-flex align-items-center" href="#">
        <img src="/static/logo.png" alt="NIMS Logo" height="32" class="me-2">
        <div>
          <span class="fw-bold fs-5">NIMS</span>
          <small class="d-block text-muted" style="font-size: 0.7rem; margin-top: -5px;">Network Inventory Management System</small>
        </div>
      </a>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav" aria-controls="navbarNav" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navbarNav">
        <ul class="navbar-nav ms-auto">
          <li class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" id="navbarDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
              Accounts
            </a>
            <ul class="dropdown-menu" aria-labelledby="navbarDropdown">
              <li><a class="dropdown-item" href="/change_password">Change Password</a></li>
              <li><a class="dropdown-item" href="/logout">Logout</a></li>
            </ul>
          </li>
        </ul>
      </div>
    </div>
  </nav>

  <div class="container mt-4">
    <div class="d-flex justify-content-between align-items-center my-4 flex-wrap gap-2">
      <h2 class="mb-0 fw-bold">Network Inventory Dashboard</h2>
      <div class="d-flex gap-2 flex-wrap">
        <button id="addBtn" class="btn btn-primary border-0 fw-bold" data-bs-toggle="modal" data-bs-target="#addDeviceModal">Add Device</button>
        <a href="/export" class="btn btn-light border-0 fw-bold">Export CSV</a>
        <button id="pingAllBtn" class="btn btn-light border-0 fw-bold">
          <span class="spinner-border spinner-border-sm d-none" role="status" aria-hidden="true"></span>
          <span class="btn-text">Ping All Devices</span>
        </button>
      </div>
    </div>

    <div class="row mb-4 g-3">
      <div class="col-md-4"><div class="card stat-card border-0 p-4" id="totalCard" data-status-filter="">
        <h6 class="text-muted mb-1">Total Devices</h6><h3 id="total" class="mb-0 stat-number">0</h3>
      </div></div>
      <div class="col-md-4"><div class="card stat-card border-0 p-4" id="onlineCard" data-status-filter="Online">
        <h6 class="text-success-emphasis mb-1">Online Devices</h6><h3 id="online" class="mb-0 stat-number">0</h3>
      </div></div>
      <div class="col-md-4"><div class="card stat-card border-0 p-4" id="offlineCard" data-status-filter="Offline">
        <h6 class="text-secondary-emphasis mb-1">Offline Devices</h6><h3 id="offline" class="mb-0 stat-number">0</h3>
      </div></div>
    </div>

    <div class="row mb-3">
      <div class="col">
        <div class="input-group">
          <input type="search" id="searchInput" class="form-control" placeholder="Search by Filter">
          <button class="btn btn-outline-secondary d-none" type="button" id="clearFilterBtn">Clear Filter</button>
        </div>
      </div>
    </div>

    <div class="card border-0 shadow-sm">
      <div class="table-responsive">
        <table class="table align-middle mb-0" id="devicesTable">
          <thead>
            <tr>
              <th>Hostname</th><th>IP</th><th>Type</th><th>Department</th>
              <th>Location</th><th>Status</th><th>Last Checked (UTC)</th><th class="text-center">Actions</th>
            </tr>
          </thead>
          <tbody>
            </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="modal fade" id="addDeviceModal" tabindex="-1" aria-labelledby="addDeviceModalLabel" aria-hidden="true">
    <div class="modal-dialog">
      <form class="modal-content" id="deviceForm">
        <div class="modal-header">
          <h5 class="modal-title" id="addDeviceModalLabel">Add New Device</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <input type="hidden" name="id" id="deviceId">
          <div class="mb-3"><label class="form-label">Hostname</label><input class="form-control" name="hostname" id="hostname" required></div>
          <div class="mb-3"><label class="form-label">IP Address</label><input class="form-control" name="ip_address" id="ip_address" required></div>
          <div class="mb-3"><label class="form-label">Device Type</label><input class="form-control" name="device_type" id="device_type"></div>
          <div class="mb-3"><label class="form-label">Department</label><input class="form-control" name="department" id="department"></div>
          <div class="mb-3"><label class="form-label">Location</label><input class="form-control" name="location" id="location"></div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
          <button class="btn btn-primary" type="submit">Save Device</button>
        </div>
      </form>
    </div>
  </div>
  
  <template id="toastTemplate">
    <div class="toast" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="toast-header">
        <svg class="bd-placeholder-img rounded me-2" width="20" height="20" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid slice" focusable="false"><rect width="100%" height="100%" fill="#007aff"></rect></svg>
        <strong class="me-auto">NIMS Notification</strong>
        <small>Just now</small>
        <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
      <div class="toast-body">
        Hello, world! This is a toast message.
      </div>
    </div>
  </template>

  <script src="/static/main.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

MAIN_JS = r'''// static/main.js for dashboard interactions
let addDeviceModal;
let allDevices = []; // Cache for all devices for filtering
let currentStatusFilter = ''; // State for status filter

// Utility to safely get element value
function safeVal(id) {
    const el = document.getElementById(id);
    return el ? el.value : '';
}

// Utility to safely set element value
function setSafeVal(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.value = value || '';
    }
}

// --- NEW Toast Notification Function ---
function showToast(message, type = 'success') {
    const toastContainer = document.querySelector('.toast-container');
    const toastTemplate = document.getElementById('toastTemplate');
    if (!toastContainer || !toastTemplate) return;

    const toastEl = toastTemplate.content.cloneNode(true).firstElementChild;
    const toastBody = toastEl.querySelector('.toast-body');
    const toastHeaderIcon = toastEl.querySelector('rect');
    
    toastBody.textContent = message;

    if (type === 'danger') {
        toastHeaderIcon.setAttribute('fill', '#dc3545'); // Red
        // toastEl.classList.add('text-bg-danger'); // Optional: for full bg color
    } else if (type === 'info') {
        toastHeaderIcon.setAttribute('fill', '#0dcaf0'); // Info
    } else {
        toastHeaderIcon.setAttribute('fill', '#198754'); // Green
    }

    toastContainer.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

// Fetch and render all devices
async function fetchDevices() {
  try {
    const resp = await fetch('/api/devices');
    if (!resp.ok) {
        showToast('Failed to fetch devices', 'danger');
        return;
    }
    allDevices = await resp.json();
    renderDevices(allDevices);
    filterTable(); // Re-apply filters after rendering
  } catch (e) {
    console.error('Error fetching devices:', e);
    showToast('Error fetching devices', 'danger');
  }
}

// Render device list into the table
function renderDevices(devices) {
  const tbody = document.querySelector('#devicesTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  let total = 0, online = 0, offline = 0;
  
  devices.forEach(d => {
    total++;
    if (d.status === 'Online') online++;
    if (d.status === 'Offline') offline++;
    
    const tr = document.createElement('tr');
    tr.dataset.id = d.id;
    // Store all device data in dataset attributes for editing and filtering
    Object.keys(d).forEach(key => {
        tr.dataset[key] = d[key] || '';
    });
    // Store status explicitly for filtering
    tr.dataset.status = d.status;

    tr.innerHTML = `
      <td data-field="hostname">${d.hostname}</td>
      <td data-field="ip_address">${d.ip_address}</td>
      <td data-field="device_type">${d.device_type||''}</td>
      <td data-field="department">${d.department||''}</td>
      <td data-field="location">${d.location||''}</td>
      <td class="status-cell">${statusBadge(d.status)}</td>
      <td class="last-cell">${d.last_checked || 'Never'}</td>
      <td>
        <div class="d-flex gap-3 justify-content-center">
          <button class="btn btn-link action-ping p-0 pingBtn">
            <span class="btn-text">Ping</span>
            <span class="spinner-border spinner-border-sm d-none" role="status" aria-hidden="true"></span>
          </button>
          <button class="btn btn-link action-edit p-0 editBtn" data-bs-toggle="modal" data-bs-target="#addDeviceModal">Edit</button>
          <button class="btn btn-link action-delete p-0 deleteBtn">Delete</button>
        </div>
      </td>`;
    tbody.appendChild(tr);
  });
  
  document.getElementById('total').innerText = total;
  document.getElementById('online').innerText = online;
  document.getElementById('offline').innerText = offline;
}

// --- NEW Search and Filter Function ---
function filterTable() {
    const searchText = document.getElementById('searchInput').value.toLowerCase();
    const rows = document.querySelectorAll('#devicesTable tbody tr');
    const clearFilterBtn = document.getElementById('clearFilterBtn');

    let isFilterActive = (searchText !== '' || currentStatusFilter !== '');
    clearFilterBtn.classList.toggle('d-none', !isFilterActive);

    rows.forEach(row => {
        // Check 1: Status Filter
        const rowStatus = row.dataset.status;
        const statusMatch = (currentStatusFilter === '' || rowStatus === currentStatusFilter);

        // Check 2: Search Text Filter
        const rowText = row.textContent.toLowerCase();
        const searchMatch = (searchText === '' || rowText.includes(searchText));

        // Show row only if both filters match
        row.style.display = (statusMatch && searchMatch) ? '' : 'none';
    });
}


// Generate a status badge
function statusBadge(status) {
  if (!status || status === 'Unknown') return '<span class="badge status-unknown">Unknown</span>';
  if (status === 'Online') return '<span class="badge status-online">Online</span>';
  if (status === 'Offline') return '<span class="badge status-offline">Offline</span>';
  return `<span class="badge status-unknown">${status}</span>`;
}

// Handle all click events on the document
document.addEventListener('click', async (e) => {
  const target = e.target;
  const pingBtn = target.closest('.pingBtn');
  
  // --- Ping Button ---
  if (pingBtn) {
    const tr = target.closest('tr');
    if (!tr) return;
    const id = tr.dataset.id;
    
    // Show spinner
    pingBtn.disabled = true;
    pingBtn.querySelector('.btn-text').classList.add('d-none');
    pingBtn.querySelector('.spinner-border').classList.remove('d-none');

    try {
        const resp = await fetch('/api/ping/' + id);
        if (!resp.ok) throw new Error('Ping request failed');
        const obj = await resp.json();
        
        // Update table row
        const statusCell = tr.querySelector('.status-cell');
        const lastCell = tr.querySelector('.last-cell');
        if (statusCell) statusCell.innerHTML = statusBadge(obj.status);
        if (lastCell) lastCell.innerText = obj.last_checked || 'Never';
        tr.dataset.status = obj.status; // Update status for filtering

        // Re-fetch all stats and re-apply filters
        fetchDevices();
        showToast(`Device ${obj.hostname} is ${obj.status}`, 'info');
    } catch (err) {
        console.error('Ping failed', err);
        showToast('Ping failed', 'danger');
    } finally {
        // Hide spinner
        pingBtn.disabled = false;
        pingBtn.querySelector('.btn-text').classList.remove('d-none');
        pingBtn.querySelector('.spinner-border').classList.add('d-none');
    }
  }

  // --- Delete Button ---
  if (target.classList.contains('deleteBtn')) {
    if (!await showConfirm('Are you sure you want to delete this device?')) return;
    
    const tr = target.closest('tr');
    if (!tr) return;
    const id = tr.dataset.id;
    try {
        await fetch('/delete/' + id, {method:'POST'});
        showToast('Device deleted', 'success');
        fetchDevices(); // Refresh list after delete
    } catch (e) {
        console.error('Delete failed', e);
        showToast('Delete failed', 'danger');
    }
  }

  // --- Edit Button ---
  if (target.classList.contains('editBtn')) {
    const tr = target.closest('tr');
    if (!tr) return;
    
    document.getElementById('addDeviceModalLabel').innerText = 'Edit Device';
    setSafeVal('deviceId', tr.dataset.id);
    setSafeVal('hostname', tr.dataset.hostname);
    setSafeVal('ip_address', tr.dataset.ip_address);
    setSafeVal('device_type', tr.dataset.device_type);
    setSafeVal('department', tr.dataset.department);
    setSafeVal('location', tr.dataset.location);
  }
});

// --- Add/Edit Form Submission ---
document.getElementById('deviceForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = safeVal('deviceId');
    const url = id ? '/update/' + id : '/add';
    const formData = new FormData(e.target);
    
    try {
        const resp = await fetch(url, {
            method: 'POST',
            body: new URLSearchParams(formData)
        });
        
        if (resp.ok) {
            addDeviceModal.hide();
            fetchDevices();
            showToast(id ? 'Device updated' : 'Device added', 'success');
        } else {
            // Show error toast (e.g., "IP address already exists")
            const errorText = await resp.text();
            showToast(errorText, 'danger');
        }
    } catch (e) {
        console.error('Error saving device', e);
        showToast('Error saving device', 'danger');
    }
});


// --- Ping All Button ---
async function pingAll(btn) {
  // Show spinner
  btn.disabled = true;
  btn.querySelector('.btn-text').classList.add('d-none');
  btn.querySelector('.spinner-border').classList.remove('d-none');

  try {
    const resp = await fetch('/api/ping_all', {method:'POST'});
    if (!resp.ok) { 
        showToast('Ping all request failed', 'danger');
        return; 
    }
    
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let partial = '';
    
    while(true) {
      const {done, value} = await reader.read();
      if (done) break;
      
      partial += decoder.decode(value, {stream:true});
      const lines = partial.split('\n');
      partial = lines.pop(); // Keep the last partial line
      
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
            const obj = JSON.parse(line);
            const row = document.querySelector(`tr[data-id="${obj.id}"]`);
            if (row) {
              const statusCell = row.querySelector('.status-cell');
              const lastCell = row.querySelector('.last-cell');
              if (statusCell) statusCell.innerHTML = statusBadge(obj.status);
              if (lastCell) lastCell.innerText = obj.last_checked || 'Never';
              row.dataset.status = obj.status; // Update status for filtering
            }
        } catch (e) {
            console.warn('Failed to parse JSON line:', e, line);
        }
      }
    }
  } catch (e) {
    console.error('Ping all failed', e);
    showToast('Ping all failed', 'danger');
  } finally {
    fetchDevices(); // Full refresh for stats and to re-apply filters
    // Hide spinner
    btn.disabled = false;
    btn.querySelector('.btn-text').classList.remove('d-none');
    btn.querySelector('.spinner-border').classList.add('d-none');
    showToast('All devices checked', 'info');
  }
}
document.getElementById('pingAllBtn').addEventListener('click', function(){ pingAll(this); });

// --- NEW Search Input Listener ---
document.getElementById('searchInput').addEventListener('input', filterTable);

// --- NEW Stat Card Click Listeners ---
document.querySelectorAll('.stat-card').forEach(card => {
    card.addEventListener('click', () => {
        currentStatusFilter = card.dataset.statusFilter;
        // Update active card style
        document.querySelectorAll('.stat-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        filterTable(); // Apply the filter
    });
});

// --- NEW Clear Filter Button ---
document.getElementById('clearFilterBtn').addEventListener('click', () => {
    currentStatusFilter = '';
    document.getElementById('searchInput').value = '';
    document.querySelectorAll('.stat-card').forEach(c => c.classList.remove('active'));
    filterTable(); // Clear all filters
});

// --- Modal Handling ---
document.addEventListener('DOMContentLoaded', () => {
    const modalEl = document.getElementById('addDeviceModal');
    if (modalEl) {
        addDeviceModal = new bootstrap.Modal(modalEl);
        
        // Reset form when modal is hidden
        modalEl.addEventListener('hidden.bs.modal', () => {
            document.getElementById('addDeviceModalLabel').innerText = 'Add New Device';
            document.getElementById('deviceForm').reset();
            setSafeVal('deviceId', '');
        });
    }
    // Initial fetch
    fetchDevices();
});

// Auto refresh every 30s
// setInterval(fetchDevices, 30000); // Disabled for easier presentation, re-enable if needed

// --- Custom Confirmation Modal (replaces confirm()) ---
function showConfirm(message) {
  return new Promise((resolve) => {
    // Remove existing modal if any
    const existingModal = document.getElementById('confirmModal');
    if (existingModal) existingModal.remove();

    // Create modal structure
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.id = 'confirmModal';
    modal.tabIndex = -1;
    modal.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Please Confirm</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <p>${message}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" id="confirmCancel">Cancel</button>
            <button type="button" class="btn btn-primary" id="confirmOk">OK</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    
    const bsModal = new bootstrap.Modal(modal);
    const btnOk = modal.querySelector('#confirmOk');
    const btnCancel = modal.querySelector('#confirmCancel');

    const closeModal = (result) => {
      bsModal.hide();
      modal.remove();
      resolve(result);
    };

    btnOk.addEventListener('click', () => closeModal(true));
    btnCancel.addEventListener('click', () => closeModal(false));
    modal.addEventListener('hidden.bs.modal', () => closeModal(false));
    
    bsModal.show();
  });
}
'''

STYLE_CSS = r'''body { 
    background-color: #f8f9fa; 
    font-family: 'Geist', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-weight: 600; /* Bolder text */
}
.navbar.bg-white { 
    border-bottom: 1.5px solid #dee2e6; /* Thicker stroke */
}
.card { 
    border-radius: 0.75rem; 
    border: none;
    /* box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); */ /* Shadow removed as requested */
}
/* --- NEW Stat Card Clickable Styles --- */
.stat-card {
    cursor: pointer;
    transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
}
.stat-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 6px 14px rgba(0, 0, 0, 0.07);
}
.stat-card.active {
    box-shadow: 0 0 0 2px #0d6efd; /* Blue border when active */
    transform: translateY(-3px);
}
/* --- End New Styles --- */

.table {
    border-collapse: separate;
    border-spacing: 0;
}
.table th, .table td {
    border-top: none;
    border-bottom: 1.5px solid #f1f3f5; /* Thicker stroke */
    padding: 1rem 1.25rem;
    vertical-align: middle;
}
.table tr:last-child td {
    border-bottom: none;
}
.table thead th { 
    background-color: #ffffff; /* White header */
    border-bottom: 1.5px solid #e9ecef; /* Thicker stroke */
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
    color: #6b7280;
    padding-top: 1rem;
    padding-bottom: 1rem;
}
.table-hover tbody tr:hover {
    background-color: #f8f9fa;
}
/* Ensure table corners are rounded with the card */
.card .table-responsive {
    border-radius: 0.75rem;
}
.card .table {
    border-radius: 0.75rem;
    overflow: hidden;
}
.btn {
    border-radius: 0.375rem; /* rounded-md */
}
/* --- NEW Spinner Alignment in Buttons --- */
.btn .spinner-border {
    vertical-align: middle;
}
.btn .btn-text + .spinner-border {
    margin-left: 0.5rem;
}
/* --- End New Styles --- */

.modal-content {
    border-radius: 0.75rem;
    border: none;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
}
.badge {
    font-size: 0.8rem;
    padding: 0.5em 0.75em;
    border-radius: 0.375rem; /* rounded-md */
    font-weight: 600;
}
.status-online { 
    color: #067d53; /* Fainter text */
    background-color: #e6fcf2; /* Fainter bg */
}
.status-offline { 
    color: #5a6472; /* Fainter grey text */
    background-color: #f3f4f6; /* Fainter grey background */
}
.status-unknown { 
    color: #5a6472; 
    background-color: #f3f4f6; 
}
.form-control {
    background-color: #f9fafb;
    border: 1.5px solid #e5e7eb; /* Thicker stroke */
}
.form-control:focus {
    background-color: #ffffff;
    border-color: #0d6efd;
    border-width: 1.5px; /* Maintain stroke on focus */
    box-shadow: 0 0 0 0.2rem rgba(13,110,253,.25);
}
.stat-number {
    font-size: 2.75rem; /* Larger number */
    font-weight: 700; /* Bolder number */
}
/* Action buttons in table */
.btn-link {
    text-decoration: none;
    font-weight: 600;
    padding-left: 0;
    padding-right: 0;
}
.btn-link:hover {
    text-decoration: underline;
}
/* Custom faint colors for action links */
.action-ping {
    color: #5090f7; /* Fainter blue */
}
.action-edit {
    color: #f5a623; /* Fainter orange */
}
.action-delete {
    color: #f76874; /* Fainter red */
}
'''

# Write static files (overwrite)
try:
    with open(os.path.join(STATIC_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(INDEX_HTML)
    with open(os.path.join(STATIC_DIR, 'main.js'), 'w', encoding='utf-8') as f:
        f.write(MAIN_JS)
    with open(os.path.join(STATIC_DIR, 'style.css'), 'w', encoding='utf-8') as f:
        f.write(STYLE_CSS)
except IOError as e:
    print(f"Warning: Could not write static files. {e}")

# -------------------------
# App & DB
# -------------------------
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DB_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# IMPORTANT: Change this secret key for production!
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_strong_development_secret_key_123')

db = SQLAlchemy(app)

class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(120), nullable=False)
    ip_address = db.Column(db.String(64), nullable=False, unique=True)
    device_type = db.Column(db.String(64))
    department = db.Column(db.String(64))
    location = db.Column(db.String(120))
    status = db.Column(db.String(32), default='Unknown')
    date_added = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_checked = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'device_type': self.device_type,
            'department': self.department,
            'location': self.location,
            'status': self.status,
            'last_checked': self.last_checked.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if self.last_checked else None
        }

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
        try:
            u = User(username='admin'); u.set_password('admin123')
            db.session.add(u); db.session.commit()
            print('='*50)
            print('Created default user: admin / admin123')
            print('Please change this password immediately via the dashboard.')
            print('='*50)
        except Exception as e:
            db.session.rollback()
            print(f"Error creating default user: {e}")

# -------------------------
# Utilities
# -------------------------
IS_WINDOWS = platform.system().lower().startswith('win')
PING_COUNT_PARAM = '-n' if IS_WINDOWS else '-c'

def ping_ip(ip, timeout=3):
    """
    Pings an IP address. Returns True if online, False if offline.
    """
    try:
        # Use a 1-packet ping with a specified timeout
        command = ['ping', PING_COUNT_PARAM, '1', ip]
        if IS_WINDOWS:
            # Windows timeout is in milliseconds
            command.extend(['-w', str(timeout * 1000)])
        else:
            # Linux/macOS timeout is in seconds
            command.extend(['-W', str(timeout)])
            
        proc = subprocess.run(command,
                              stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL, 
                              timeout=timeout + 1) # Process timeout slightly longer
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"Ping timeout for {ip}")
        return False
    except Exception as e:
        print(f"Ping error for {ip}: {e}")
        return False

def login_required(f):
    """
    Decorator to ensure a user is logged in.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
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
            session['username'] = user.username
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('root'))
        
        flash('Invalid username or password.', 'danger')

    # simple bootstrap login page
    return render_template_string('''
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@100..900&display=swap" rel="stylesheet">
<title>Login - NIMS</title></head><body style="background:#f8f9fa; font-family: 'Geist', sans-serif;">
<div class="container d-flex justify-content-center align-items-center" style="min-height:95vh">
  <div class="card p-4 shadow-sm border-0 rounded-3" style="width:100%; max-width:400px">
    <div class="text-center mb-3">
      <img src="/static/logo.png" alt="NIMS Logo" style="height: 48px;">
    </div>
    <h3 class="mb-4 text-center fw-bold text-primary">NIMS</h3>
    
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <form method="post">
      <div class="mb-3"><label class="form-label fw-bold">Username</label><input name="username" class="form-control" required></div>
      <div class="mb-3"><label class="form-label fw-bold">Password</label><input name="password" type="password" class="form-control" required></div>
      <button class="btn btn-primary w-100 mt-2 fw-bold">Login</button>
    </form>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
''')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# -------------------------
# Change Password (accessible via button in admin header)
# -------------------------
@app.route('/change_password', methods=['GET','POST'])
@login_required
def change_password():
    user = User.query.get(session.get('user_id'))
    if not user:
        flash('User not found. Please log in again.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        current = request.form.get('current_password','')
        new = request.form.get('new_password','')
        confirm = request.form.get('confirm_password','')
        
        if not user.check_password(current):
            flash('Current password incorrect.', 'danger')
        elif not new:
            flash('New password cannot be empty.', 'danger')
        elif new != confirm:
            flash('New passwords do not match.', 'danger')
        else:
            try:
                user.set_password(new)
                db.session.commit()
                flash('Password updated successfully.', 'success')
                return redirect(url_for('root'))
            except Exception as e:
                db.session.rollback()
                flash(f'An error occurred: {e}', 'danger')
        
        return redirect(url_for('change_password'))

    # GET request
    return render_template_string('''
<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@100..900&display=swap" rel="stylesheet">
<title>Change Password</title></head><body style="background:#f8f9fa; font-family: 'Geist', sans-serif;">
<div class="container" style="max-width:520px;padding-top:40px">
  <div class="card p-4 shadow-sm border-0 rounded-3">
    <h3 class="mb-4 text-center fw-bold">Change Password</h3>
    
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
            {{ message }}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    <form method="post">
      <div class="mb-3"><label class="form-label fw-bold">Current Password</label><input name="current_password" type="password" class="form-control" required></div>
      <div class="mb-3"><label class="form-label fw-bold">New Password</label><input name="new_password" type="password" class="form-control" required></div>
      <div class="mb-3"><label class="form-label fw-bold">Confirm New Password</label><input name="confirm_password" type="password" class="form-control" required></div>
      <div class="d-flex gap-2 mt-3">
        <button class="btn btn-primary fw-bold" type="submit">Update Password</button>
        <a class="btn btn-secondary fw-bold" href="/">Cancel</a>
      </div>
    </form>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
''')

# -------------------------
# API & management
# -------------------------
@app.route('/api/devices')
@login_required
def api_devices():
    try:
        devices = Device.query.order_by(Device.hostname).all()
        out = [d.to_dict() for d in devices]
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ping/<int:id>')
@login_required
def api_ping(id):
    d = Device.query.get_or_404(id)
    ok = ping_ip(d.ip_address)
    d.status = 'Online' if ok else 'Offline'
    d.last_checked = datetime.now(timezone.utc)
    try:
        db.session.commit()
        return jsonify(d.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/ping_all', methods=['POST'])
@login_required
def api_ping_all():
    try:
        devices = Device.query.all()
    except Exception as e:
        return Response(json.dumps({"error": str(e)}), status=500, mimetype='application/json')
        
    app_obj = app
    
    def generate():
        with ThreadPoolExecutor(max_workers=10) as ex:
            future_to_dev = {ex.submit(ping_ip, d.ip_address): d for d in devices}
            for future in as_completed(future_to_dev):
                d = future_to_dev[future]
                try:
                    ok = future.result()
                    d.status = 'Online' if ok else 'Offline'
                    d.last_checked = datetime.now(timezone.utc)
                    
                    with app_obj.app_context():
                        db.session.merge(d)
                        db.session.commit()
                        
                    yield json.dumps(d.to_dict()) + "\n"
                except Exception as e:
                    with app_obj.app_context():
                        db.session.rollback()
                    print(f"Error processing ping result for {d.hostname}: {e}")
                    yield json.dumps({"id": d.id, "error": str(e)}) + "\n"
                    
    return Response(generate(), mimetype='application/x-json-stream')

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_device(id):
    d = Device.query.get_or_404(id)
    try:
        db.session.delete(d)
        db.session.commit()
        return ('', 204)
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/add', methods=['POST'])
@login_required
def add_device():
    hostname = request.form.get('hostname')
    ip = request.form.get('ip_address')
    if not hostname or not ip: 
        return 'Missing hostname or IP', 400
    
    # Check if IP already exists
    if Device.query.filter_by(ip_address=ip).first():
        return 'IP address already exists', 409
        
    d = Device(hostname=hostname, ip_address=ip,
               device_type=request.form.get('device_type'),
               department=request.form.get('department'),
               location=request.form.get('location'),
               status='Unknown')
    try:
        db.session.add(d)
        db.session.commit()
        return 'Device added', 201
    except Exception as e:
        db.session.rollback()
        return f'Error adding device: {e}', 500

@app.route('/update/<int:id>', methods=['POST'])
@login_required
def update_device(id):
    d = Device.query.get_or_404(id)
    
    hostname = request.form.get('hostname')
    ip = request.form.get('ip_address')
    if not hostname or not ip:
        return 'Missing hostname or IP', 400

    # Check if IP is being changed and if the new one conflicts
    if d.ip_address != ip and Device.query.filter_by(ip_address=ip).first():
        return 'IP address already exists', 409

    d.hostname = hostname
    d.ip_address = ip
    d.device_type = request.form.get('device_type')
    d.department = request.form.get('department')
    d.location = request.form.get('location')
    
    try:
        db.session.commit()
        return 'Device updated', 200
    except Exception as e:
        db.session.rollback()
        return f'Error updating device: {e}', 500

@app.route('/export')
@login_required
def export_csv():
    try:
        devices = Device.query.all()
        sio = StringIO()
        writer = csv.writer(sio)
        
        # Write header
        writer.writerow(['id','hostname','ip_address','device_type','department','location','status','date_added','last_checked'])
        
        # Write data
        for d in devices:
            writer.writerow([
                d.id, d.hostname, d.ip_address, d.device_type, d.department, d.location, d.status,
                d.date_added.isoformat() if d.date_added else '',
                d.last_checked.astimezone(timezone.utc).isoformat() if d.last_checked else ''
            ])
        
        # Prepare file for sending
        output = BytesIO()
        output.write(sio.getvalue().encode('utf-8'))
        output.seek(0)
        sio.close()
        
        return send_file(output, 
                         mimetype='text/csv', 
                         as_attachment=True, 
                         download_name='network_inventory.csv')
    except Exception as e:
        flash(f'Error exporting CSV: {e}', 'danger')
        return redirect(url_for('root'))

# -------------------------
# Root / static serve
# -------------------------
@app.route('/')
@login_required
def root():
    # Serves the static index.html file we created
    return send_file(os.path.join(STATIC_DIR, 'index.html'))

# -------------------------
# Seed demo devices if empty
# -------------------------
def seed_demo():
    if Device.query.count() == 0:
        print("Database is empty. Seeding demo devices...")
        demo = [
            Device(hostname='Core-Router-HQ', ip_address='192.168.1.1', device_type='Router', department='IT', location='Main IDF'),
            Device(hostname='Core-Switch-HQ', ip_address='192.168.1.2', device_type='Switch', department='IT', location='Main IDF'),
            Device(hostname='File-Server-01', ip_address='192.168.1.10', device_type='Server', department='IT', location='Server Room'),
            Device(hostname='Domain-Controller', ip_address='192.168.1.5', device_type='Server', department='IT', location='Server Room'),
            Device(hostname='AP-Finance', ip_address='192.168.2.1', device_type='Access Point', department='Finance', location='Floor 2'),
            Device(hostname='Printer-HR', ip_address='192.168.3.100', device_type='Printer', department='HR', location='Floor 3'),
            # Add a known public IP for a reliable "Online" demo
            Device(hostname='Google-DNS', ip_address='8.8.8.8', device_type='External', department='Services', location='Internet'),
            Device(hostname='Cloudflare-DNS', ip_address='1.1.1.1', device_type='External', department='Services', location='Internet'),
            # Add an unpingable IP for an "Offline" demo
            Device(hostname='Offline-Workstation', ip_address='10.255.255.1', device_type='Workstation', department='Sales', location='Floor 1 (Remote)'),
        ]
        try:
            db.session.add_all(demo)
            db.session.commit()
            print(f'Seeded {len(demo)} demo devices.')
        except Exception as e:
            db.session.rollback()
            print(f"Error seeding database (maybe IP conflict?): {e}")

with app.app_context():
    seed_demo()

# -------------------------
# Run
# -------------------------
if __name__ == '__main__':
    print("NIMS server starting...")
    print(f"Database is at: {DB_PATH}")
    print("Access the app at: http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
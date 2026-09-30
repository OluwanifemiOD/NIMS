// static/main.js for dashboard interactions
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

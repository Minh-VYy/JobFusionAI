// =============================================
// ADMIN DASHBOARD - JavaScript
// =============================================

const API = 'http://localhost:8000/api';
let token = localStorage.getItem('token') || '';
let currentRole = localStorage.getItem('role') || null;
let currentUsername = localStorage.getItem('username') || '';
let graphData = null;
let currentAdminPage = 'dashboard';

// =============================================
// AUTH & INIT
// =============================================
function initAdmin() {
  // Check if logged in as admin
  if (!token || currentRole !== 'admin') {
    // Redirect to public site
    window.location.href = '/';
    return;
  }
  
  // Update UI
  document.getElementById('admin-username').textContent = currentUsername || 'Admin';
  
  // Load initial data
  connectAdminWS();
  refreshDashboard();
  loadTasks();
  loadReviewBadge();
  
  // Show dashboard by default
  showAdminPage('dashboard');
}

function authHeaders() {
  return { 
    'Authorization': `Bearer ${token}`, 
    'Content-Type': 'application/json' 
  };
}

async function apiFetch(path, opts = {}) {
  const r = await fetch(API + path, { headers: authHeaders(), ...opts });
  if (r.status === 401) { 
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    window.location.href = '/';
    return;
  }
  return r.json();
}

function adminLogout() {
  token = '';
  currentRole = null;
  currentUsername = '';
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  localStorage.removeItem('username');
  window.location.href = '/';
}

function goToPublicSite() {
  window.open('/', '_blank');
}

// =============================================
// NAVIGATION
// =============================================
function showAdminPage(name) {
  // Hide all pages
  document.querySelectorAll('.admin-page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  
  // Show selected page
  document.getElementById(`page-${name}`)?.classList.add('active');
  document.getElementById(`nav-${name}`)?.classList.add('active');
  
  currentAdminPage = name;
  
  // Load page data
  if (name === 'dashboard') refreshDashboard();
  if (name === 'tasks') loadTasks();
  if (name === 'review') loadReviewJobs();
  if (name === 'analytics') loadAnalytics();
  if (name === 'graph' && !graphData) loadKnowledgeGraph();
  if (name === 'monitor') loadScheduledJobs();
}

// =============================================
// DASHBOARD
// =============================================
async function refreshDashboard() {
  try {
    const data = await apiFetch('/admin/stats');
    const s = data.system;
    
    // Update stats
    document.getElementById('dash-total-jobs').textContent = s.total_jobs?.toLocaleString('vi') || '—';
    document.getElementById('dash-geocoded').textContent = `${s.geocoded_jobs || 0} (${s.geocoding_rate || 0}%)`;
    document.getElementById('dash-geo-rate').textContent = `${s.geocoding_rate || 0}%`;
    document.getElementById('dash-review').textContent = s.pending_review || '—';
    document.getElementById('dash-active-tasks').textContent = s.running_tasks || '—';
    
    // Update mini task stats
    document.getElementById('task-total').textContent = s.total_tasks || 0;
    document.getElementById('task-running').textContent = s.running_tasks || 0;
    
    // Update review badge
    loadReviewBadge(s.pending_review);
    
    // Update recent activity
    updateRecentActivity(s);
    
  } catch (e) {
    toast('Lỗi tải dashboard: ' + e.message, 'error');
  }
}

function updateRecentActivity(stats) {
  const activityEl = document.getElementById('recent-activity');
  const now = new Date();
  
  const activities = [
    { time: 'Vừa xong', text: `Hệ thống đang chạy ${stats.running_tasks || 0} tasks`, type: 'success' },
    { time: '1 phút trước', text: `Tổng ${stats.total_jobs || 0} việc làm trong database`, type: 'info' },
    { time: '5 phút trước', text: `${stats.pending_review || 0} việc làm cần kiểm duyệt`, type: stats.pending_review > 0 ? 'warning' : 'info' },
    { time: '1 giờ trước', text: `Tỷ lệ geocoding: ${stats.geocoding_rate || 0}%`, type: 'info' },
  ];
  
  activityEl.innerHTML = activities.map(a => `
    <div class="activity-item">
      <span class="activity-time">${a.time}</span>
      <span class="activity-text ${a.type}">${a.text}</span>
    </div>
  `).join('');
}

function runAllTasks() {
  toast('Đang khởi chạy tất cả tasks...', 'info');
  // Implement run all logic
}

function exportData() {
  toast('Đang xuất dữ liệu...', 'info');
  // Implement export logic
}

// =============================================
// TASKS MANAGEMENT
// =============================================
async function loadTasks() {
  try {
    const data = await apiFetch('/admin/tasks');
    
    // Update counts
    const running = data.filter(t => t.status === 'running').length;
    const scheduled = data.filter(t => t.is_scheduled).length;
    const errors = data.filter(t => t.total_errors > 0).length;
    
    document.getElementById('task-total').textContent = data.length;
    document.getElementById('task-running').textContent = running;
    document.getElementById('task-scheduled').textContent = scheduled;
    document.getElementById('task-error').textContent = errors;
    
    // Render table
    const tbody = document.getElementById('tasks-tbody');
    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="table-empty">Chưa có task nào</td></tr>';
      return;
    }
    
    tbody.innerHTML = data.map(t => `
      <tr>
        <td>${t.id}</td>
        <td><strong>${t.name}</strong></td>
        <td><span class="source-tag ${t.source_name}">${t.source_name}</span></td>
        <td><span class="status-badge status-${t.status}">${t.status}</span></td>
        <td>${t.schedule_cron ? `<code>${t.schedule_cron}</code>` : '—'}</td>
        <td>${t.total_scraped || 0}</td>
        <td style="color: ${t.total_errors > 0 ? 'var(--danger)' : 'inherit'}">${t.total_errors || 0}</td>
        <td><small>${t.last_run_at ? new Date(t.last_run_at).toLocaleString('vi') : '—'}</small></td>
        <td>
          <button class="btn btn-sm btn-primary" onclick="runTask(${t.id})" ${t.status === 'running' ? 'disabled' : ''}>▶</button>
          <button class="btn btn-sm btn-outline" onclick="cancelTask(${t.id})" ${t.status !== 'running' ? 'disabled' : ''}>⏹</button>
          <button class="btn btn-sm btn-danger" onclick="deleteTask(${t.id})">🗑</button>
        </td>
      </tr>
    `).join('');
    
  } catch (e) {
    toast('Lỗi tải tasks: ' + e.message, 'error');
  }
}

async function runTask(id) {
  try {
    await apiFetch(`/admin/tasks/${id}/run`, { method: 'POST' });
    toast(`Task #${id} đã khởi động!`, 'success');
    loadTasks();
    refreshDashboard();
  } catch (e) {
    toast('Lỗi: ' + e.message, 'error');
  }
}

async function cancelTask(id) {
  try {
    await apiFetch(`/admin/tasks/${id}/cancel`, { method: 'POST' });
    toast('Đã hủy task', 'warning');
    loadTasks();
  } catch (e) {
    toast('Lỗi: ' + e.message, 'error');
  }
}

async function deleteTask(id) {
  if (!confirm(`Xóa task #${id}?`)) return;
  try {
    await apiFetch(`/admin/tasks/${id}`, { method: 'DELETE' });
    toast('Đã xóa task', 'success');
    loadTasks();
  } catch (e) {
    toast('Lỗi: ' + e.message, 'error');
  }
}

async function createTask(e) {
  e.preventDefault();
  try {
    const body = {
      name: document.getElementById('task-name').value,
      source_name: document.getElementById('task-source').value,
      seed_url: document.getElementById('task-url').value,
      max_pages: parseInt(document.getElementById('task-pages').value || 10),
      is_scheduled: document.getElementById('task-scheduled').checked,
      schedule_cron: document.getElementById('task-cron').value || null,
    };
    
    const task = await apiFetch('/admin/tasks', { method: 'POST', body: JSON.stringify(body) });
    closeModal('create-task-modal');
    
    // Run immediately
    await apiFetch(`/admin/tasks/${task.id}/run`, { method: 'POST' });
    
    toast('Task đã tạo và đang chạy!', 'success');
    loadTasks();
    refreshDashboard();
    
    // Reset form
    e.target.reset();
    document.getElementById('cron-group').style.display = 'none';
    
  } catch (e) {
    toast('Lỗi tạo task: ' + e.message, 'error');
  }
}

// =============================================
// REVIEW
// =============================================
async function loadReviewJobs() {
  try {
    const data = await apiFetch('/admin/jobs/review?limit=50');
    const el = document.getElementById('review-jobs-list');
    
    if (!data.jobs?.length) {
      el.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">✅</div>
          <p>Không có dữ liệu cần kiểm duyệt</p>
        </div>
      `;
      return;
    }
    
    el.innerHTML = data.jobs.map(j => `
      <div class="review-card" id="review-${j.id}">
        <div class="review-card-header">
          <div>
            <div class="review-title">${j.title}</div>
            <div class="review-company">${j.company} • ${j.source_name}</div>
          </div>
          <span class="status-badge status-${j.status}">${j.status}</span>
        </div>
        <div class="review-issue">⚠️ ${j.review_notes || 'Cần kiểm duyệt'}</div>
        <div class="review-actions">
          <button class="btn btn-success btn-sm" onclick="reviewJob(${j.id}, 'approve')">✅ Duyệt</button>
          <button class="btn btn-danger btn-sm" onclick="reviewJob(${j.id}, 'reject')">❌ Từ chối</button>
          <a href="${j.source_url}" target="_blank" class="btn btn-outline btn-sm">🔗 Xem nguồn</a>
        </div>
      </div>
    `).join('');
    
  } catch (e) {
    toast('Lỗi tải dữ liệu kiểm duyệt: ' + e.message, 'error');
  }
}

async function reviewJob(id, action) {
  try {
    await apiFetch(`/admin/jobs/${id}/review`, { 
      method: 'POST', 
      body: JSON.stringify({ action }) 
    });
    
    document.getElementById(`review-${id}`)?.remove();
    toast(action === 'approve' ? '✅ Đã duyệt' : '❌ Đã từ chối', action === 'approve' ? 'success' : 'warning');
    loadReviewBadge();
    refreshDashboard();
    
  } catch (e) {
    toast('Lỗi: ' + e.message, 'error');
  }
}

async function approveAll() {
  if (!confirm('Duyệt tất cả việc làm đang chờ?')) return;
  toast('Đang xử lý...', 'info');
  // Implement approve all logic
}

function loadReviewBadge(count) {
  const b = document.getElementById('review-badge');
  if (count !== undefined) {
    b.textContent = count;
    b.style.display = count > 0 ? 'inline-block' : 'none';
  } else {
    apiFetch('/admin/stats').then(d => {
      b.textContent = d.system?.pending_review || 0;
      b.style.display = d.system?.pending_review > 0 ? 'inline-block' : 'none';
    });
  }
}

// =============================================
// ANALYTICS
// =============================================
async function loadAnalytics() {
  try {
    const data = await apiFetch('/admin/analytics');
    
    // Skills chart
    const sc = document.getElementById('skills-chart');
    const max = data.top_skills?.[0]?.count || 1;
    sc.innerHTML = (data.top_skills || []).slice(0, 10).map(({skill, count}) => `
      <div class="bar-item">
        <div class="bar-label">${skill}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${(count / max * 100).toFixed(1)}%"></div>
        </div>
        <div class="bar-value">${count}</div>
      </div>
    `).join('');
    
    // Source distribution
    const srcEl = document.getElementById('source-chart');
    const colors = {
      vietnamworks: '#6366f1',
      topcv: '#06b6d4',
      itviec: '#10b981',
      unknown: '#94a3b8'
    };
    srcEl.innerHTML = Object.entries(data.source_distribution || {}).map(([k, v]) => `
      <div class="donut-row">
        <span class="donut-dot" style="background: ${colors[k] || '#94a3b8'}"></span>
        <span class="donut-label">${k}</span>
        <span class="donut-value">${v}</span>
      </div>
    `).join('');
    
    // Radius distribution
    const rEl = document.getElementById('radius-chart');
    const rMax = Math.max(...Object.values(data.radius_distribution || {}), 1);
    rEl.innerHTML = Object.entries(data.radius_distribution || {}).map(([k, v]) => `
      <div class="bar-item">
        <div class="bar-label">${k}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width: ${(v / rMax * 100).toFixed(1)}%"></div>
        </div>
        <div class="bar-value">${v}</div>
      </div>
    `).join('');
    
    // Salary stats
    const sal = data.salary_stats || {};
    const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n;
    document.getElementById('salary-stats').innerHTML = `
      <div class="salary-stat">
        <div class="salary-value">${fmt(sal.avg_min || 0)}</div>
        <div class="salary-label">Lương TB</div>
      </div>
      <div class="salary-stat">
        <div class="salary-value">${fmt(sal.min || 0)}</div>
        <div class="salary-label">Thấp nhất</div>
      </div>
      <div class="salary-stat">
        <div class="salary-value">${fmt(sal.max || 0)}</div>
        <div class="salary-label">Cao nhất</div>
      </div>
      <div class="salary-stat">
        <div class="salary-value">${sal.count || 0}</div>
        <div class="salary-label">Có thông tin</div>
      </div>
    `;
    
  } catch (e) {
    toast('Lỗi tải analytics: ' + e.message, 'error');
  }
}

function exportReport() {
  toast('Đang xuất báo cáo...', 'info');
}

// =============================================
// KNOWLEDGE GRAPH
// =============================================
async function loadKnowledgeGraph() {
  try {
    graphData = await apiFetch('/knowledge-graph');
    document.getElementById('graph-placeholder').style.display = 'none';
    renderGraph(graphData);
  } catch (e) {
    toast('Lỗi tải graph: ' + e.message, 'error');
  }
}

function renderGraph(data) {
  const canvas = document.getElementById('graph-canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
  
  const W = canvas.width, H = canvas.height;
  const nodes = data.nodes || [];
  const edges = data.edges || [];
  
  // Simple force layout
  nodes.forEach((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2;
    n.x = W / 2 + Math.cos(angle) * (W * 0.35);
    n.y = H / 2 + Math.sin(angle) * (H * 0.35);
  });
  
  ctx.clearRect(0, 0, W, H);
  
  const colors = {
    programming: '#6366f1',
    data_science: '#06b6d4',
    web_frontend: '#10b981',
    web_backend: '#f59e0b',
    database: '#ef4444',
    devops: '#8b5cf6',
    mobile: '#ec4899',
    unknown: '#94a3b8'
  };
  
  // Draw edges
  edges.slice(0, 100).forEach(e => {
    const s = nodes.find(n => n.id === e.from);
    const t = nodes.find(n => n.id === e.to);
    if (!s || !t) return;
    
    ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
  });
  
  // Draw nodes
  nodes.slice(0, 80).forEach(n => {
    const c = colors[n.group] || '#94a3b8';
    
    ctx.beginPath();
    ctx.arc(n.x, n.y, 6, 0, Math.PI * 2);
    ctx.fillStyle = c;
    ctx.fill();
    
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.font = '11px Outfit';
    ctx.fillText(n.label, n.x + 10, n.y + 4);
  });
}

async function searchSkill() {
  const s = document.getElementById('skill-search-input').value.trim();
  if (!s) return;
  
  try {
    const data = await apiFetch(`/skills/${encodeURIComponent(s)}/related?max_hops=2`);
    const el = document.getElementById('skill-detail-content');
    
    if (!data.related?.length) {
      el.innerHTML = '<p class="text-muted">Không tìm thấy kỹ năng liên quan</p>';
      return;
    }
    
    el.innerHTML = `
      <h4 style="color: var(--accent); margin-bottom: 1rem">${s}</h4>
      <div style="display: flex; flex-wrap: wrap; gap: 0.5rem">
        ${data.related.slice(0, 20).map(r => `
          <span class="skill-tag" title="${r.relation} (${r.weight})">${r.skill}</span>
        `).join('')}
      </div>
    `;
    
  } catch (e) {
    toast('Lỗi tìm kiếm: ' + e.message, 'error');
  }
}

// =============================================
// MONITORING / WEBSOCKET
// =============================================
function connectAdminWS() {
  const ws = new WebSocket('ws://localhost:8000/ws/monitor');
  
  ws.onopen = () => {
    addLog('info', '🟢 WebSocket kết nối thành công');
  };
  
  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'stats_update') {
      updateMonitorStats(msg.data);
    }
  };
  
  ws.onclose = () => {
    addLog('warning', '🟡 WebSocket mất kết nối, đang thử lại...');
    setTimeout(connectAdminWS, 5000);
  };
  
  ws.onerror = () => {
    addLog('error', '🔴 WebSocket lỗi');
  };
}

function updateMonitorStats(data) {
  document.getElementById('active-agents').textContent = data.active_threads || 0;
  document.getElementById('geo-rate').textContent = (data.geocoding_rate || 0) + '%';
  document.getElementById('error-rate').textContent = (data.total_errors || 0) + '%';
  document.getElementById('scrape-speed').textContent = data.scrape_speed || 0;
  
  if (data.last_run_at) {
    addLog('success', `✅ Cập nhật: ${data.total_jobs} jobs | ${data.geocoded_jobs} geocoded`);
  }
}

function addLog(type, msg) {
  const el = document.getElementById('activity-log');
  if (!el) return;
  
  const div = document.createElement('div');
  div.className = `log-entry ${type}`;
  div.textContent = `[${new Date().toLocaleTimeString('vi')}] ${msg}`;
  el.prepend(div);
  
  if (el.children.length > 100) {
    el.removeChild(el.lastChild);
  }
}

async function loadScheduledJobs() {
  try {
    const data = await apiFetch('/admin/stats');
    const el = document.getElementById('scheduled-jobs-list');
    
    if (!data.scheduled_jobs?.length) {
      el.innerHTML = '<div class="empty-state">Chưa có lịch trình nào</div>';
      return;
    }
    
    el.innerHTML = data.scheduled_jobs.map(j => `
      <div style="padding: 0.75rem; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center">
        <div>
          <strong>${j.name}</strong>
          <code style="margin-left: 0.5rem; color: var(--accent)">${j.trigger}</code>
        </div>
        <span style="color: var(--text-secondary); font-size: 0.8rem">
          Lần tới: ${j.next_run ? new Date(j.next_run).toLocaleString('vi') : '—'}
        </span>
      </div>
    `).join('');
    
  } catch (e) {
    console.error('Lỗi tải scheduled jobs:', e);
  }
}

// =============================================
// SETTINGS
// =============================================
function clearAllJobs() {
  if (!confirm('⚠️ CẢNH BÁO: Xóa TẤT CẢ việc làm? Hành động này không thể hoàn tác!')) return;
  if (!confirm('Xác nhận lần 2: Bạn chắc chắn muốn xóa tất cả?')) return;
  toast('Đang xóa tất cả việc làm...', 'warning');
}

function resetSystem() {
  if (!confirm('⚠️ CẢNH BÁO: Reset toàn bộ hệ thống?')) return;
  toast('Đang reset hệ thống...', 'warning');
}

// =============================================
// MODAL HELPERS
// =============================================
function openModal(id) {
  document.getElementById(id).classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

function openCreateTaskModal() {
  openModal('create-task-modal');
}

function toggleSchedule(cb) {
  document.getElementById('cron-group').style.display = cb.checked ? 'block' : 'none';
}

function setCron(v) {
  document.getElementById('task-cron').value = v;
}

// =============================================
// TOAST
// =============================================
function toast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  setTimeout(() => t.classList.remove('show'), 3000);
}

// =============================================
// INIT ON LOAD
// =============================================
window.onload = initAdmin;

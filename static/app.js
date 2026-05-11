
// =============================================
// AI Job Agent Dashboard — Frontend Logic
// =============================================

const API = 'http://localhost:8000/api';
let token = localStorage.getItem('token') || '';
let currentRole = localStorage.getItem('role') || null;
let currentUsername = localStorage.getItem('username') || '';
let map, userMarker, radiusCircle, allMarkers = [];
let currentPage = 'map';
let searchResults = [], searchOffset = 0;
let graphData = null;

async function login(e) {
  e.preventDefault();
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);
  try {
    const r = await fetch(`${API}/auth/login`, { method: 'POST', body: body });
    if (!r.ok) throw new Error('Sai thông tin đăng nhập');
    const data = await r.json();
    token = data.access_token;
    currentRole = data.role;
    currentUsername = data.username;
    localStorage.setItem('token', token);
    localStorage.setItem('role', currentRole);
    localStorage.setItem('username', currentUsername);
    
    // Redirect admin to admin page
    if (currentRole === 'admin') {
      toast('Đăng nhập Admin thành công! Chuyển đến trang quản trị...', 'success');
      setTimeout(() => {
        window.location.href = '/admin';
      }, 1000);
      return;
    }
    
    // Regular user - stay on current page
    closeModal('login-modal');
    updateNavUI();
    toast('Đăng nhập thành công! 🎉', 'success');
  } catch (err) { 
    toast(err.message, 'error'); 
  }
}

function logout() {
  token = '';
  currentRole = null;
  currentUsername = '';
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  localStorage.removeItem('username');
  updateNavUI();
  showPage('map');
  toast('Đã đăng xuất', 'info');
}

function authHeaders() {
  return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function apiFetch(path, opts = {}) {
  const r = await fetch(API + path, { headers: authHeaders(), ...opts });
  if (r.status === 401) { localStorage.removeItem('token'); location.reload(); }
  return r.json();
}

// ── Init ──────────────────────────────────────
function initApp() {
  initMap();
  updateNavUI();
  // Start with landing page for public access
  showPage('landing');
  // Load public stats
  loadPublicStats();
}

function updateNavUI() {
  const isUser = !!token;
  
  // Update auth section in sidebar
  const authGuest = document.getElementById('auth-guest');
  const authUser = document.getElementById('auth-user');
  
  if (isUser) {
    if (authGuest) authGuest.style.display = 'none';
    if (authUser) {
      authUser.style.display = 'block';
      document.getElementById('user-name').textContent = currentUsername;
      document.getElementById('user-role').textContent = 'Member';
    }
  } else {
    if (authGuest) authGuest.style.display = 'block';
    if (authUser) authUser.style.display = 'none';
  }
}

function openLoginModal() {
  openModal('login-modal');
}

async function loadPublicStats() {
  try {
    const data = await apiFetch('/jobs/map/data?radius_km=50');
    const count = data.markers?.length || 0;
    const heroCount = document.getElementById('hero-job-count');
    if (heroCount) {
      heroCount.textContent = count > 0 ? count.toLocaleString('vi') + '+' : '1,000+';
    }
  } catch (e) {
    // Silently fail for public stats
  }
}

// ── Navigation ────────────────────────────────
// All pages in index.html are public
const PUBLIC_PAGES = ['landing', 'map', 'search', 'graph'];

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`page-${name}`)?.classList.add('active');
  document.getElementById(`nav-${name}`)?.classList.add('active');
  currentPage = name;
  
  // Load page-specific data
  if (name === 'map') {
    setTimeout(() => {
      map?.invalidateSize();
      loadMapData();
    }, 100);
  }
  if (name === 'graph' && !graphData) loadKnowledgeGraph();
  
  // Scroll to top
  document.querySelector('.main-content')?.scrollTo(0, 0);
}

// ── Map ───────────────────────────────────────
function initMap() {
  map = L.map('map').setView([16.0544, 108.2022], 13);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap © CARTO', maxZoom: 19
  }).addTo(map);
  map.on('click', e => setUserLocation(e.latlng.lat, e.latlng.lng));
}

function getMarkerColor(source) {
  return source === 'vietnamworks' ? '#6366f1' : source === 'topcv' ? '#22d3ee' : '#10b981';
}

async function loadMapData() {
  const src = document.getElementById('map-source')?.value || '';
  const lat = userMarker ? userMarker.getLatLng().lat : null;
  const lng = userMarker ? userMarker.getLatLng().lng : null;
  const r = parseFloat(document.getElementById('radius-slider').value || 5);
  let url = `/jobs/map/data?radius_km=${r}`;
  if (lat) url += `&user_lat=${lat}&user_lng=${lng}`;
  if (src) url += `&source=${src}`;
  const data = await apiFetch(url);
  allMarkers.forEach(m => map.removeLayer(m));
  allMarkers = [];
  const listEl = document.getElementById('map-job-list');
  listEl.innerHTML = '';
  (data.markers || []).forEach(job => {
    const color = getMarkerColor(job.source);
    const icon = L.divIcon({
      className: '',
      html: `<div style="width:14px;height:14px;background:${color};border:2px solid #fff;border-radius:50%;box-shadow:0 0 8px ${color}88"></div>`,
      iconSize: [14, 14], iconAnchor: [7, 7]
    });
    const m = L.marker([job.lat, job.lng], { icon })
      .addTo(map)
      .bindPopup(`<div class="popup-title">${job.title}</div>
        <div class="popup-company">${job.company}</div>
        <div class="popup-meta">📍 ${job.address || ''}${job.distance_km ? ` • ${job.distance_km}km` : ''}</div>
        <div class="popup-meta">💰 ${job.salary || 'Thỏa thuận'}</div>
        <a class="popup-btn" href="${job.url}" target="_blank">Xem chi tiết →</a>`);
    allMarkers.push(m);
    const card = document.createElement('div');
    card.className = 'job-card';
    card.innerHTML = `<div class="job-card-title">${job.title}</div>
      <div class="job-card-company">${job.company}</div>
      <div class="job-card-meta">
        ${job.distance_km ? `<span class="job-tag distance">📍 ${job.distance_km}km</span>` : ''}
        <span class="job-tag source">${job.source}</span>
        ${(job.skills||[]).slice(0,2).map(s=>`<span class="job-tag">${s}</span>`).join('')}
      </div>`;
    card.onclick = () => { map.setView([job.lat, job.lng], 15); m.openPopup(); };
    listEl.appendChild(card);
  });
  document.getElementById('map-count').textContent = `${data.markers?.length || 0} việc làm`;
}

function filterMapJobs() { loadMapData(); }

function updateRadius(v) {
  document.getElementById('radius-display').textContent = v + ' km';
  document.getElementById('map-radius').textContent = v + 'km';
  if (userMarker) {
    if (radiusCircle) map.removeLayer(radiusCircle);
    const ll = userMarker.getLatLng();
    radiusCircle = L.circle([ll.lat, ll.lng], {
      radius: v * 1000, color: '#6366f1', fillColor: '#6366f188', fillOpacity: 0.08, weight: 2
    }).addTo(map);
  }
  loadMapData();
}

function getUserLocation() {
  navigator.geolocation.getCurrentPosition(
    p => { setUserLocation(p.coords.latitude, p.coords.longitude); toast('Đã xác định vị trí!', 'success'); },
    () => toast('Không lấy được vị trí', 'error')
  );
}

function setUserLocation(lat, lng) {
  if (userMarker) map.removeLayer(userMarker);
  if (radiusCircle) map.removeLayer(radiusCircle);
  userMarker = L.marker([lat, lng], {
    icon: L.divIcon({ className: '', html: '<div style="width:18px;height:18px;background:#f59e0b;border:3px solid #fff;border-radius:50%;box-shadow:0 0 12px #f59e0b"></div>', iconSize: [18,18], iconAnchor: [9,9] })
  }).addTo(map).bindPopup('📍 Vị trí của bạn');
  const r = parseFloat(document.getElementById('radius-slider').value || 5);
  radiusCircle = L.circle([lat, lng], { radius: r * 1000, color: '#6366f1', fillColor: '#6366f188', fillOpacity: 0.08, weight: 2 }).addTo(map);
  map.setView([lat, lng], 13);
  loadMapData();
}

function fillUserLocation() {
  navigator.geolocation.getCurrentPosition(p => {
    document.getElementById('search-lat').value = p.coords.latitude.toFixed(5);
    document.getElementById('search-lng').value = p.coords.longitude.toFixed(5);
    toast('Đã điền vị trí!', 'success');
  }, () => toast('Không lấy được vị trí', 'error'));
}

// ── Search ────────────────────────────────────
async function searchJobs() {
  const query = document.getElementById('search-query').value;
  const skills = document.getElementById('search-skills').value.split(',').map(s=>s.trim()).filter(Boolean);
  const lat = parseFloat(document.getElementById('search-lat').value) || null;
  const lng = parseFloat(document.getElementById('search-lng').value) || null;
  const radius = parseFloat(document.getElementById('search-radius').value || 5);
  const salary = parseFloat(document.getElementById('search-salary').value || 0) * 1e6 || null;
  const semantic = document.getElementById('search-semantic').checked;
  const body = { query, skills, user_lat: lat, user_lng: lng, radius_km: radius, salary_min: salary, semantic, limit: 20, offset: 0 };
  try {
    const data = await apiFetch('/jobs/search', { method: 'POST', body: JSON.stringify(body) });
    searchResults = data.results || [];
    searchOffset = 0;
    renderSearchResults(data);
  } catch(e) { toast('Lỗi tìm kiếm: ' + e.message, 'error'); }
}

function renderSearchResults(data) {
  const header = document.getElementById('search-results-header');
  const list = document.getElementById('search-results-list');
  header.style.display = 'flex';
  document.getElementById('search-count').textContent = `${data.total} kết quả`;
  list.innerHTML = '';
  if (!data.results?.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><p>Không tìm thấy kết quả</p></div>';
    return;
  }
  data.results.forEach(job => {
    const el = document.createElement('div');
    el.className = 'search-job-card';
    el.innerHTML = `<h3>${job.title}</h3>
      <div class="company">${job.company}</div>
      <div class="job-card-meta">
        ${job.distance_km != null ? `<span class="job-tag distance">📍 ${job.distance_km}km</span>` : ''}
        ${job.salary_raw ? `<span class="job-tag salary">💰 ${job.salary_raw}</span>` : ''}
        <span class="job-tag source">${job.source_name}</span>
        ${(job.skills||[]).slice(0,3).map(s=>`<span class="job-tag">${s}</span>`).join('')}
        ${job.semantic_score ? `<span class="job-tag">🧠 ${(job.semantic_score*100).toFixed(0)}%</span>` : ''}
      </div>`;
    el.onclick = () => showJobDetail(job.id);
    list.appendChild(el);
  });
}

async function showJobDetail(id) {
  const job = await apiFetch(`/jobs/${id}`);
  document.getElementById('detail-title').textContent = job.title;
  document.getElementById('job-detail-content').innerHTML = `
    <div class="detail-section"><h4>🏢 Công ty</h4><p>${job.company}</p></div>
    <div class="detail-section"><h4>📍 Địa chỉ</h4><p>${job.address_clean || job.address_raw || 'Chưa rõ'}</p></div>
    <div class="detail-section"><h4>💰 Lương</h4><p>${job.salary_raw || 'Thỏa thuận'}</p></div>
    <div class="detail-section"><h4>🛠️ Kỹ năng</h4><div class="skill-tag-cloud">${(job.skills||[]).map(s=>`<span class="skill-tag">${s}</span>`).join('')}</div></div>
    ${job.related_skills?.length ? `<div class="detail-section"><h4>🕸️ Kỹ năng liên quan (KG)</h4><div class="skill-tag-cloud">${job.related_skills.map(s=>`<span class="skill-tag">${s}</span>`).join('')}</div></div>` : ''}
    <a href="${job.source_url}" target="_blank" class="btn btn-primary" style="margin-top:1rem">Xem tại ${job.source_name} →</a>`;
  openModal('job-detail-modal');
  logInteraction(id, 'click');
}

async function logInteraction(jobId, action) {
  try { await apiFetch('/interactions', { method: 'POST', body: JSON.stringify({ job_id: jobId, action }) }); } catch(e) {}
}

// ── Knowledge Graph ────────────────────────────
async function loadKnowledgeGraph() {
  graphData = await apiFetch('/knowledge-graph');
  document.getElementById('graph-placeholder').style.display = 'none';
  renderGraph(graphData);
}

function renderGraph(data) {
  const canvas = document.getElementById('graph-canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
  const W = canvas.width, H = canvas.height;
  const nodes = data.nodes || [], edges = data.edges || [];
  // Simple force-layout approximation
  nodes.forEach((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2;
    n.x = W/2 + Math.cos(angle) * (W*0.35);
    n.y = H/2 + Math.sin(angle) * (H*0.35);
  });
  ctx.clearRect(0, 0, W, H);
  const colors = { programming:'#6366f1', data_science:'#22d3ee', web_frontend:'#10b981', web_backend:'#f59e0b', database:'#ef4444', devops:'#8b5cf6', mobile:'#ec4899', unknown:'#94a3b8' };
  edges.slice(0,100).forEach(e => {
    const s = nodes.find(n=>n.id===e.from), t = nodes.find(n=>n.id===e.to);
    if (!s||!t) return;
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
  });
  nodes.slice(0,80).forEach(n => {
    const c = colors[n.group] || '#94a3b8';
    ctx.beginPath(); ctx.arc(n.x, n.y, 5, 0, Math.PI*2);
    ctx.fillStyle = c; ctx.fill();
    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.font = '10px Inter';
    ctx.fillText(n.label, n.x + 7, n.y + 4);
  });
}

async function searchSkill() {
  const s = document.getElementById('skill-search-input').value.trim();
  if (!s) return;
  const data = await apiFetch(`/skills/${encodeURIComponent(s)}/related?max_hops=2`);
  const el = document.getElementById('skill-detail-content');
  if (!data.related?.length) { el.innerHTML = '<p style="color:var(--text-muted)">Không tìm thấy kỹ năng liên quan</p>'; return; }
  el.innerHTML = `<h4 style="color:var(--accent);margin-bottom:0.75rem">${s}</h4>
    <div class="skill-tag-cloud">
      ${data.related.slice(0,20).map(r=>`<span class="skill-tag" title="${r.relation} (${r.weight})">${r.skill}</span>`).join('')}
    </div>`;
}

// ── Modal helpers ─────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// ── Toast ─────────────────────────────────────
function toast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── Init on load ──────────────────────────────
window.onload = () => {
  initApp();
};

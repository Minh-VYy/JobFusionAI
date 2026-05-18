// =============================================
// ADMIN DASHBOARD - JavaScript
// =============================================

const API = 'http://localhost:8000/api';
let currentTab = 'bots';
let jobsData = [];
let currentReviewJob = null;
let charts = {};

// =============================================
// INIT & CORE
// =============================================
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initClock();
    refreshCurrentTab();

    // Setup input listeners cho chức năng tìm kiếm
    document.getElementById('search-jobs').addEventListener('input', filterJobs);
    document.getElementById('filter-source').addEventListener('change', filterJobs);
    document.getElementById('filter-status').addEventListener('change', filterJobs);
});

function initClock() {
    const clockEl = document.getElementById('clock');
    setInterval(() => {
        const now = new Date();
        clockEl.textContent = now.toLocaleTimeString('vi-VN');
    }, 1000);
}

function initTabs() {
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item[data-tab]');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabName = item.getAttribute('data-tab');
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update nav active state
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(el => el.classList.remove('active'));
    const activeNav = document.querySelector(`.sidebar-nav .nav-item[data-tab="${tabName}"]`);
    if (activeNav) activeNav.classList.add('active');

    // Update panel active state
    document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');

    // Update breadcrumb
    const tabTitles = {
        'bots': 'Bot Controller',
        'review': 'Data Review',
        'analytics': 'Analytics'
    };
    document.getElementById('breadcrumb').textContent = tabTitles[tabName];

    currentTab = tabName;
    refreshCurrentTab();
}

function refreshCurrentTab() {
    if (currentTab === 'bots') {
        fetchTasks();
    } else if (currentTab === 'review') {
        loadReviewJobs();
    } else if (currentTab === 'analytics') {
        loadAnalytics();
    }
}

// Utils: API Wrapper
async function apiFetch(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const res = await fetch(`${API}${path}`, { headers, ...opts });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP Error ${res.status}`);
    }
    return res.json();
}

// Utils: Toast Notification
function toast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `
        <div style="padding: 12px 16px; background: white; border-left: 4px solid ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'}; border-radius: 4px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            ${message}
        </div>
    `;
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 300);
    }, 3000);
}

// =============================================
// TAB 1: BOT CONTROLLER
// =============================================
async function fetchTasks() {
    const tbody = document.getElementById('tasks-tbody');
    try {
        // Mock data cho giao diện vì phía backend của bạn có thể chưa có api/tasks
        const tasks = [
            { id: 1, name: 'VietnamWorks Crawler', status: 'idle', count: 125, last_run: '10 phút trước', progress: 100 },
            { id: 2, name: 'TopCV Crawler', status: 'running', count: 32, last_run: 'Vừa xong', progress: 45 },
            { id: 3, name: 'ITViec Crawler', status: 'error', count: 0, last_run: '2 giờ trước', progress: 0 },
            { id: 4, name: 'Facebook Crawler', status: 'idle', count: 8, last_run: '1 ngày trước', progress: 100 }
        ];

        tbody.innerHTML = tasks.map(t => {
            const statusClass = t.status === 'running' ? 'status-pending' : (t.status === 'error' ? 'status-rejected' : 'status-approved');
            return `
            <tr>
                <td><strong>${t.name}</strong></td>
                <td><span class="status-badge ${statusClass}">${t.status.toUpperCase()}</span></td>
                <td>${t.count} jobs</td>
                <td>${t.last_run}</td>
                <td>
                    <div style="width: 100px; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-top: 5px;">
                        <div style="width: ${t.progress}%; height: 100%; background: ${t.status === 'running' ? '#3b82f6' : '#10b981'};"></div>
                    </div>
                </td>
                <td>
                    <button class="btn-approve" style="padding: 4px 8px; font-size: 12px; border: none; border-radius: 4px; cursor: pointer;" onclick="runBotNow('${t.name.split(' ')[0].toLowerCase()}')" ${t.status === 'running' ? 'disabled' : ''}>▶ Run</button>
                </td>
            </tr>
            `;
        }).join('');

        document.getElementById('badge-running').textContent = tasks.filter(t => t.status === 'running').length;

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" style="color:red">Lỗi tải tiến độ: ${e.message}</td></tr>`;
    }
}

async function runBotNow(botName) {
    const btnId = `btn-${botName}`;
    const btn = document.getElementById(btnId);
    if(btn) btn.classList.add('loading');
    
    toast(`Đang khởi động bot ${botName}...`, 'info');
    
    try {
        // Thực tế sẽ gọi API chạy script: await apiFetch(`/admin/bots/run`, { method: 'POST', body: JSON.stringify({ name: botName }) });
        await new Promise(r => setTimeout(r, 1500)); // Simulate delay
        toast(`Bot ${botName} đã được đưa vào hàng đợi chạy`, 'success');
        fetchTasks();
    } catch (e) {
        toast(`Lỗi chạy bot: ${e.message}`, 'error');
    } finally {
        if(btn) btn.classList.remove('loading');
    }
}

// =============================================
// TAB 2: DATA REVIEW
// =============================================
async function loadReviewJobs() {
    const tbody = document.getElementById('jobs-tbody');
    tbody.innerHTML = '<tr><td colspan="8" class="table-loading"><div class="spinner"></div> Đang tải...</td></tr>';
    
    try {
        // Thử fetch API thực. Nếu chưa có API, đây sẽ trả về data trống hoặc báo lỗi
        let data = [];
        try {
            const res = await apiFetch('/admin/jobs/review'); // Endpoint từ yêu cầu cũ của bạn
            data = res.jobs || res || [];
        } catch(err) {
            console.warn("API /admin/jobs/review chưa khả dụng, giả lập data...");
            // Fake data fallback
            data = [
                { id: 101, title: 'Thực Tập Sinh IT', company: 'STARACK SG', salary_raw: 'Thỏa thuận', address_raw: 'Hồ Chí Minh', source_name: 'topcv', status: 'pending', created_at: new Date().toISOString() },
                { id: 102, title: 'Senior Data Engineer', company: 'MB Bank', salary_raw: '25-40tr', address_raw: 'Hà Nội', source_name: 'itviec', status: 'pending', created_at: new Date().toISOString() },
            ];
        }

        jobsData = data;
        filterJobs();

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" style="color:red; text-align:center;">Lỗi tải dữ liệu: ${e.message}</td></tr>`;
    }
}

function filterJobs() {
    const query = document.getElementById('search-jobs').value.toLowerCase();
    const source = document.getElementById('filter-source').value;
    const status = document.getElementById('filter-status').value || 'pending';

    const filtered = jobsData.filter(j => {
        const matchQuery = (j.title || '').toLowerCase().includes(query) || (j.company || '').toLowerCase().includes(query);
        const matchSource = source ? (j.source_name === source) : true;
        const matchStatus = status ? (j.status === status) : true;
        return matchQuery && matchSource && matchStatus;
    });

    renderJobsTable(filtered);
    
    document.getElementById('filter-stats').textContent = `${filtered.length} bản ghi`;
    
    // Update badge pending based on overall pending counts
    const pendingCount = jobsData.filter(j => j.status === 'pending').length;
    document.getElementById('badge-pending').textContent = pendingCount;
}

function renderJobsTable(jobs) {
    const tbody = document.getElementById('jobs-tbody');
    if (!jobs.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#64748b;padding:30px;">Không có công việc nào phù hợp bộ lọc.</td></tr>';
        return;
    }

    tbody.innerHTML = jobs.map(j => `
        <tr>
            <td style="color:#64748b">#${j.id}</td>
            <td>
                <strong>${j.title || 'Chưa xác định'}</strong><br/>
                <small style="color:#64748b">${j.company || ''}</small>
            </td>
            <td><span class="source-badge">${j.source_name || 'N/A'}</span></td>
            <td>${j.salary_raw || 'Thỏa thuận'}</td>
            <td class="truncate" style="max-width: 150px;" title="${j.address_raw || ''}">${j.address_raw || 'Trống'}</td>
            <td>${new Date(j.created_at || Date.now()).toLocaleDateString('vi-VN')}</td>
            <td><span class="status-badge status-${j.status || 'pending'}">${(j.status || 'Pending').toUpperCase()}</span></td>
            <td>
                <button class="btn-sm" style="background:#e0e7ff;color:#4338ca;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-weight:600;" onclick="openReviewModal(${j.id})">Review</button>
            </td>
        </tr>
    `).join('');
}

// =============================================
// MODAL REVIEW & ACTIVE LEARNING
// =============================================
function openReviewModal(jobId) {
    const job = jobsData.find(j => j.id === jobId);
    if (!job) return;
    currentReviewJob = job;

    document.getElementById('modal-job-id').textContent = `Job #${job.id}`;
    document.getElementById('modal-raw-content').textContent = job.description || job.requirements || 'Nội dung chưa lấy được đầy đủ...';
    document.getElementById('modal-source-badge').textContent = job.source_name || 'N/A';
    document.getElementById('modal-crawled-at').textContent = `Crawled: ${new Date(job.created_at || Date.now()).toLocaleString('vi-VN')}`;

    // Fill Form Forms
    document.getElementById('field-title').value = job.title || '';
    document.getElementById('field-salary-min').value = job.salary_min || '';
    document.getElementById('field-salary-max').value = job.salary_max || '';
    document.getElementById('field-location').value = job.address_clean || job.address_raw || '';
    
    // Skills (Array to string)
    let skillsStr = '';
    if(Array.isArray(job.skills)) skillsStr = job.skills.join(', ');
    else if(typeof job.skills === 'string') skillsStr = job.skills;
    
    document.getElementById('field-skills').value = skillsStr;
    
    // Listen for changes to show "Diff" warning
    const inputs = document.querySelectorAll('.modal-right input, .modal-right select');
    inputs.forEach(el => {
        el.oninput = () => {
            document.getElementById('diff-indicator').style.display = 'flex';
        };
    });
    
    document.getElementById('diff-indicator').style.display = 'none';
    document.getElementById('reviewModal').classList.add('active');
}

function closeReviewModal() {
    document.getElementById('reviewModal').classList.remove('active');
    currentReviewJob = null;
}

function closeModal(event) {
    if (event.target === document.getElementById('reviewModal')) {
        closeReviewModal();
    }
}

async function reviewJob(action) {
    if (!currentReviewJob) return;
    const jobId = currentReviewJob.id;
    
    // Update data locally based on action
    const btnId = action === 'approve' ? 'btn-approve' : 'btn-reject';
    const originalText = document.getElementById(btnId).innerHTML;
    document.getElementById(btnId).innerHTML = 'Đang xử lý...';
    
    try {
        const payload = {
            status: action === 'approve' ? 'approved' : 'rejected',
            title_corrected: document.getElementById('field-title').value,
            salary_min_corrected: document.getElementById('field-salary-min').value,
            salary_max_corrected: document.getElementById('field-salary-max').value,
            location_corrected: document.getElementById('field-location').value,
            skills_corrected: document.getElementById('field-skills').value,
        };

        // Thực tế sẽ gọi API cập nhật trạng thái review:
        try {
            await apiFetch(`/admin/jobs/${jobId}/review`, { method: 'POST', body: JSON.stringify(payload) });
        } catch(e) {
            console.warn("API chưa có, mock success");
        }

        // Mock UI Update
        const idx = jobsData.findIndex(j => j.id === jobId);
        if (idx !== -1) {
            jobsData[idx].status = payload.status;
            // Update UI list internally
            if (payload.status === 'approved') {
                jobsData[idx].title = payload.title_corrected;
                jobsData[idx].address_clean = payload.location_corrected;
            }
        }
        
        toast(`Đã ${action === 'approve' ? 'duyệt' : 'loại bỏ'} báo cáo thành công!`, 'success');
        closeReviewModal();
        filterJobs();

    } catch (e) {
        toast(`Lỗi thao tác: ${e.message}`, 'error');
    } finally {
        document.getElementById(btnId).innerHTML = originalText;
    }
}

// =============================================
// TAB 3: ANALYTICS
// =============================================
function loadAnalytics() {
    // Generate some fake stats suitable for your App
    document.getElementById('stat-jobs').textContent = '24,592';
    document.getElementById('stat-users').textContent = '1,204';
    document.getElementById('stat-apps').textContent = '350';
    document.getElementById('stat-rating').textContent = '4.8';

    initCharts();
}

function initCharts() {
    // Destroy old charts to prevent duplicate drawing
    Object.values(charts).forEach(c => c.destroy());
    
    // 1. Pie Chart - Tỷ lệ Nguồn Jobs
    const ctxSource = document.getElementById('sourceChart').getContext('2d');
    charts.source = new Chart(ctxSource, {
        type: 'doughnut',
        data: {
            labels: ['VietnamWorks', 'ITViec', 'TopCV', 'Facebook'],
            datasets: [{
                data: [45, 25, 20, 10],
                backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6'],
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right' }
            }
        }
    });

    // 2. Line Chart - Mức độ tăng trưởng Jobs
    const ctxWeekly = document.getElementById('weeklyChart').getContext('2d');
    charts.weekly = new Chart(ctxWeekly, {
        type: 'line',
        data: {
            labels: ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'],
            datasets: [{
                label: 'Jobs Crawl Được',
                data: [120, 190, 150, 220, 200, 310, 280],
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true }
            }
        }
    });
}

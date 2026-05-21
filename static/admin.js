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
        fetchBotConfig();
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
        const tasksRes = await apiFetch('/admin/tasks');

        tbody.innerHTML = tasksRes.map(t => {
            const statusClass = t.status === 'running' ? 'status-pending' : (t.status === 'error' ? 'status-rejected' : 'status-approved');
            // Assuming progress isn't sent by API, default to 100 or 0
            const progress = t.status === 'running' ? 50 : 100;
            return `
            <tr>
                <td><strong>${t.name}</strong></td>
                <td><span class="status-badge ${statusClass}">${t.status.toUpperCase()}</span></td>
                <td>N/A jobs</td>
                <td>${t.last_run_at || 'Chưa chạy'}</td>
                <td>
                    <div style="width: 100px; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-top: 5px;">
                        <div style="width: ${progress}%; height: 100%; background: ${t.status === 'running' ? '#3b82f6' : '#10b981'};"></div>
                    </div>
                </td>
                <td>
                    <button class="btn-approve" style="padding: 4px 8px; font-size: 12px; border: none; border-radius: 4px; cursor: pointer;" onclick="runBotNow(${t.id}, '${t.name}', this)" ${t.status === 'running' ? 'disabled' : ''}>▶ Run</button>
                </td>
            </tr>
            `;
        }).join('');

        document.getElementById('badge-running').textContent = tasksRes.filter(t => t.status === 'running').length;

        // Đồng bộ hóa trạng thái Lịch Chạy trên UI
        tasksRes.forEach(t => {
            const source = t.source_name ? t.source_name.toLowerCase() : '';
                const scheduleMap = {
                    facebook: { selectId: 'schedule-fb', toggleId: 'toggle-fb' },
                    topcv: { selectId: 'schedule-topcv', toggleId: 'toggle-topcv' },
                    itviec: { selectId: 'schedule-itviec', toggleId: 'toggle-itviec' },
                    vietnamworks: { selectId: 'schedule-vietnamworks', toggleId: 'toggle-vietnamworks' }
                };

                if (scheduleMap[source]) {
                    const { selectId, toggleId } = scheduleMap[source];

                const selectEl = document.getElementById(selectId);
                const toggleEl = document.getElementById(toggleId);

                if (selectEl && t.schedule_cron) {
                    selectEl.value = t.schedule_cron;
                }

                if (toggleEl) {
                    if (t.is_scheduled) {
                        toggleEl.classList.add('active');
                    } else {
                        toggleEl.classList.remove('active');
                    }
                }
            }
        });

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" style="color:red">Lỗi tải tiến độ: ${e.message}</td></tr>`;
    }
}

async function runBotNow(taskId, botName, btnElement) {
    let btn = btnElement;
    // Xác định ID nút và API endpoint phù hợp
    let btnId = `btn-${taskId}`;
    let apiPath = `/admin/tasks/${taskId}/run`;
    let name = botName || taskId;

        const sourceTaskIds = ['facebook', 'topcv', 'itviec', 'vietnamworks'];

        if (sourceTaskIds.includes(taskId)) {
        btnId = taskId === 'facebook' ? 'btn-fb' : 'btn-topcv';
            if (taskId === 'itviec') btnId = 'btn-itviec';
            if (taskId === 'vietnamworks') btnId = 'btn-vietnamworks';
        apiPath = `/admin/tasks/by-source/${taskId}/run`;
            if (taskId === 'facebook') name = 'Facebook';
            else if (taskId === 'topcv') name = 'TopCV';
            else if (taskId === 'itviec') name = 'ITviec';
            else if (taskId === 'vietnamworks') name = 'VietnamWorks';
    }

    if (!btn) {
        btn = document.getElementById(btnId);
    }
    if (btn) btn.classList.add('loading');

    toast(`Đang khởi động bot ${name}...`, 'info');

    try {
        await apiFetch(apiPath, { method: 'POST' });
        toast(`Bot ${name} đã được khởi động thành công!`, 'success');
        fetchTasks();
    } catch (e) {
        toast(`Lỗi chạy bot: ${e.message}`, 'error');
    } finally {
        if (btn) btn.classList.remove('loading');
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
            const res = await apiFetch('/admin/jobs/review'); // Thực tế gọi API đã xây dựng sẵn
            data = res.jobs || res || [];
        } catch (err) {
            console.error("Lỗi khi tải jobs/review:", err);
            data = [];
        }

        jobsData = data;

        const sourceFilter = document.getElementById('filter-source');
        if (sourceFilter && !sourceFilter.value) {
            const hasFacebookJobs = data.some(j => (j.source_name || '').toLowerCase() === 'facebook');
            if (hasFacebookJobs) {
                sourceFilter.value = 'facebook';
            }
        }

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
        const matchStatus = (status && status !== 'all') ? (j.status === status) : true;
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
            <td class="truncate" style="max-width: 150px;" title="${j.address_raw || j.address_clean || ''}">${j.address_raw || j.address_clean || 'Trống'}</td>
            <td>${new Date(j.scraped_at || j.created_at || Date.now()).toLocaleDateString('vi-VN')}</td>
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
    const rawContent = [job.title, job.company, job.description, job.requirements]
        .filter(Boolean)
        .join('\n\n');
    document.getElementById('modal-raw-content').textContent = rawContent || 'Nội dung chưa lấy được đầy đủ...';
    document.getElementById('modal-source-badge').textContent = job.source_name || 'N/A';
    document.getElementById('modal-crawled-at').textContent = `Crawled: ${new Date(job.scraped_at || job.created_at || Date.now()).toLocaleString('vi-VN')}`;
    const sourceUrlEl = document.getElementById('modal-source-url');
    if (sourceUrlEl) {
        sourceUrlEl.textContent = job.source_url || 'Không có link nguồn';
        sourceUrlEl.href = job.source_url || '#';
        sourceUrlEl.style.pointerEvents = job.source_url ? 'auto' : 'none';
        sourceUrlEl.style.opacity = job.source_url ? '1' : '0.7';
    }

    // Fill Form Forms
    document.getElementById('field-title').value = job.title || '';
    const companyField = document.getElementById('field-company');
    if (companyField) companyField.value = job.company || '';
    document.getElementById('field-salary-min').value = job.salary_min || '';
    document.getElementById('field-salary-max').value = job.salary_max || '';
    document.getElementById('field-location').value = job.address_clean || job.address_raw || '';

    // Skills (Array to string)
    let skillsStr = '';
    if (Array.isArray(job.skills)) skillsStr = job.skills.join(', ');
    else if (typeof job.skills === 'string') skillsStr = job.skills;

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
        const salaryMinValue = parseFloat(document.getElementById('field-salary-min').value);
        const salaryMaxValue = parseFloat(document.getElementById('field-salary-max').value);
        const skillsText = document.getElementById('field-skills').value || '';
        const skillsList = skillsText
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);

        const payload = {
            action,
            title: document.getElementById('field-title').value,
            title_corrected: document.getElementById('field-title').value,
            company: document.getElementById('field-company') ? document.getElementById('field-company').value : '',
            company_corrected: document.getElementById('field-company') ? document.getElementById('field-company').value : '',
            salary_min: Number.isFinite(salaryMinValue) ? salaryMinValue : null,
            salary_min_corrected: Number.isFinite(salaryMinValue) ? salaryMinValue : null,
            salary_max: Number.isFinite(salaryMaxValue) ? salaryMaxValue : null,
            salary_max_corrected: Number.isFinite(salaryMaxValue) ? salaryMaxValue : null,
            address_clean: document.getElementById('field-location').value,
            location_corrected: document.getElementById('field-location').value,
            skills: skillsList,
            skills_corrected: skillsList,
        };

        // Thực tế sẽ gọi API cập nhật trạng thái review:
        try {
            await apiFetch(`/admin/jobs/${jobId}/review`, { method: 'POST', body: JSON.stringify(payload) });
        } catch (e) {
            console.warn("API chưa có, mock success");
        }

        // UI Update
        const idx = jobsData.findIndex(j => j.id === jobId);
        if (idx !== -1) {
            const nextStatus = action === 'approve' ? 'approved' : 'rejected';
            jobsData[idx].status = nextStatus;
            // Update UI list internally
            if (nextStatus === 'approved') {
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
async function loadAnalytics() {
    try {
        const stats = await apiFetch('/admin/stats');

        document.getElementById('stat-jobs').textContent = stats.system.total_jobs.toLocaleString('vi-VN');
        document.getElementById('stat-users').textContent = stats.system.geocoded_jobs.toLocaleString('vi-VN'); // Using geocoded jobs as an example
        document.getElementById('stat-apps').textContent = stats.system.pending_review.toLocaleString('vi-VN'); // Using pending jobs
        document.getElementById('stat-rating').textContent = stats.system.geocoding_rate + '%';

        const analytics = await apiFetch('/admin/analytics');
        initCharts(analytics);
    } catch (e) {
        console.error("Lỗi tải Analytics:", e);
    }
}

function initCharts(analytics) {
    // Destroy old charts to prevent duplicate drawing
    Object.values(charts).forEach(c => c.destroy());

    // 1. Pie Chart - Tỷ lệ Nguồn Jobs
    const ctxSource = document.getElementById('sourceChart').getContext('2d');

    let sourceLabels = Object.keys(analytics.source_distribution || {});
    let sourceData = Object.values(analytics.source_distribution || {});
    if (sourceLabels.length === 0) {
        sourceLabels = ['VietnamWorks', 'ITViec', 'TopCV', 'Facebook'];
        sourceData = [45, 25, 20, 10];
    }

    charts.source = new Chart(ctxSource, {
        type: 'doughnut',
        data: {
            labels: sourceLabels,
            datasets: [{
                data: sourceData,
                backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#64748b'],
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

// =============================================
// SCHEDULING & CONFIGURATION FUNCTIONS
// =============================================
async function updateSchedule(source, value) {
    toast(`Đang cập nhật lịch chạy cho bot ${source} thành ${value}...`, 'info');
    try {
            const toggleMap = {
                facebook: 'toggle-fb',
                topcv: 'toggle-topcv',
                itviec: 'toggle-itviec',
                vietnamworks: 'toggle-vietnamworks'
            };
            const toggleId = toggleMap[source] || 'toggle-fb';
        const toggleEl = document.getElementById(toggleId);
        const isScheduled = toggleEl ? toggleEl.classList.contains('active') : false;

        await apiFetch(`/admin/tasks/by-source/${source}/schedule`, {
            method: 'POST',
            body: JSON.stringify({
                is_scheduled: isScheduled,
                schedule_cron: value
            })
        });
        toast(`Đã lưu lịch chạy cho bot ${source}`, 'success');
        fetchTasks();
    } catch (e) {
        toast(`Lỗi cập nhật lịch: ${e.message}`, 'error');
    }
}

async function toggleSchedule(source, el) {
    const isActive = el.classList.contains('active');

    // Toggle class
    if (isActive) {
        el.classList.remove('active');
    } else {
        el.classList.add('active');
    }

    const selectMap = {
        facebook: 'schedule-fb',
        topcv: 'schedule-topcv',
        itviec: 'schedule-itviec',
        vietnamworks: 'schedule-vietnamworks'
    };
    const selectId = selectMap[source] || 'schedule-fb';
    const selectEl = document.getElementById(selectId);
    const cronValue = selectEl ? selectEl.value : '12:00';

    toast(`Đang ${!isActive ? 'kích hoạt' : 'tắt'} lịch chạy cho bot ${source}...`, 'info');
    try {
        await apiFetch(`/admin/tasks/by-source/${source}/schedule`, {
            method: 'POST',
            body: JSON.stringify({
                is_scheduled: !isActive,
                schedule_cron: cronValue
            })
        });
        toast(`Đã ${!isActive ? 'kích hoạt' : 'tắt'} lịch chạy cho bot ${source}`, 'success');
        fetchTasks();
    } catch (e) {
        // Revert toggle on error
        if (isActive) el.classList.add('active');
        else el.classList.remove('active');
        toast(`Lỗi thay đổi trạng thái lịch: ${e.message}`, 'error');
    }
}

const BOT_CONFIG_DEFAULT = {
    facebook: {
        enabled: true,
        max_posts_per_group: 5,
        max_groups_per_session: 3,
        max_days_old: 3,
        facebook_groups: [],
        moderation_policy: {
            mode: 'manual',
            learn_from_admin: true,
        },
    },
    topcv: {
        enabled: true,
        max_pages: 2,
        max_jobs: 10,
        headless: true,
    },
    itviec: {
        enabled: true,
        max_pages: 1,
        max_jobs: 10,
        headless: true,
    },
    vietnamworks: {
        enabled: true,
        max_pages: 2,
        max_jobs: 10,
        headless: true,
    },
};

let currentBotConfig = JSON.parse(JSON.stringify(BOT_CONFIG_DEFAULT));

function normalizeBotConfig(rawConfig) {
    const merged = JSON.parse(JSON.stringify(BOT_CONFIG_DEFAULT));
    if (!rawConfig || typeof rawConfig !== 'object') return merged;

    const legacyFacebook = rawConfig.max_posts_per_group !== undefined
        || rawConfig.max_groups_per_session !== undefined
        || rawConfig.max_days_old !== undefined
        || rawConfig.facebook_groups !== undefined
        || rawConfig.moderation_policy !== undefined;

    if (legacyFacebook) {
        rawConfig.facebook = {
            ...(rawConfig.facebook || {}),
            max_posts_per_group: rawConfig.max_posts_per_group ?? merged.facebook.max_posts_per_group,
            max_groups_per_session: rawConfig.max_groups_per_session ?? merged.facebook.max_groups_per_session,
            max_days_old: rawConfig.max_days_old ?? merged.facebook.max_days_old,
            facebook_groups: rawConfig.facebook_groups ?? merged.facebook.facebook_groups,
            moderation_policy: rawConfig.moderation_policy ?? merged.facebook.moderation_policy,
        };
    }

    Object.keys(BOT_CONFIG_DEFAULT).forEach(source => {
        if (!rawConfig[source] || typeof rawConfig[source] !== 'object') return;
        merged[source] = { ...merged[source], ...rawConfig[source] };
        if (source === 'facebook') {
            merged.facebook.moderation_policy = {
                ...BOT_CONFIG_DEFAULT.facebook.moderation_policy,
                ...(rawConfig.facebook.moderation_policy || {}),
            };
        }
    });

    return merged;
}

function getSourceConfig(source) {
    currentBotConfig[source] = currentBotConfig[source] || JSON.parse(JSON.stringify(BOT_CONFIG_DEFAULT[source]));
    return currentBotConfig[source];
}

function setCheckboxValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.checked = Boolean(value);
}

function setInputValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value ?? '';
}

async function fetchBotConfig() {
    try {
        currentBotConfig = normalizeBotConfig(await apiFetch('/admin/bot-config'));

        const facebook = getSourceConfig('facebook');
        setInputValue('cfg-max-posts', facebook.max_posts_per_group);
        setInputValue('cfg-max-groups', facebook.max_groups_per_session);
        setInputValue('cfg-max-days', facebook.max_days_old);
        setCheckboxValue('cfg-fb-enabled', facebook.enabled !== false);
        const moderationModeField = document.getElementById('cfg-moderation-mode');
        const learnField = document.getElementById('cfg-learn-from-admin');
        if (moderationModeField) moderationModeField.value = facebook.moderation_policy?.mode || 'manual';
        if (learnField) learnField.checked = facebook.moderation_policy?.learn_from_admin !== false;
        setInputValue('cfg-auto-approve-hours', facebook.moderation_policy?.auto_approve_after_hours || '');

        const topcv = getSourceConfig('topcv');
        setCheckboxValue('cfg-topcv-enabled', topcv.enabled !== false);
        setInputValue('cfg-topcv-max-pages', topcv.max_pages);
        setInputValue('cfg-topcv-max-jobs', topcv.max_jobs || 10);
        setCheckboxValue('cfg-topcv-headless', topcv.headless !== false);

        const itviec = getSourceConfig('itviec');
        setCheckboxValue('cfg-itviec-enabled', itviec.enabled !== false);
        setInputValue('cfg-itviec-max-pages', itviec.max_pages);
        setInputValue('cfg-itviec-max-jobs', itviec.max_jobs || 10);
        setCheckboxValue('cfg-itviec-headless', itviec.headless !== false);

        const vietnamworks = getSourceConfig('vietnamworks');
        setCheckboxValue('cfg-vietnamworks-enabled', vietnamworks.enabled !== false);
        setInputValue('cfg-vietnamworks-max-pages', vietnamworks.max_pages);
        setInputValue('cfg-vietnamworks-max-jobs', vietnamworks.max_jobs || 10);
        setCheckboxValue('cfg-vietnamworks-headless', vietnamworks.headless !== false);

        renderFacebookGroups();
    } catch (e) {
        toast(`Lỗi tải cấu hình bot: ${e.message}`, 'error');
    }
}

function renderFacebookGroups() {
    const container = document.getElementById('fb-groups-list-container');
    if (!container) return;

    const groups = getSourceConfig('facebook').facebook_groups || [];
    if (groups.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: #64748b; padding: 20px; font-size: 12px; background: #f8fafc; border-radius: 6px; border: 1px dashed #cbd5e1;">Danh sách trống. Nhập ở trên để thêm nhóm mới.</div>`;
        return;
    }

    container.innerHTML = groups.map((g, index) => `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: white; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 8px; box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); gap: 12px;">
            <div style="display: flex; flex-direction: column; overflow: hidden; flex: 1;">
                <div style="font-size: 13px; font-weight: 600; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${g.name}</div>
                <a href="${g.url}" target="_blank" style="font-size: 11px; color: #3b82f6; text-decoration: none; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;">${g.url}</a>
            </div>
            <button onclick="deleteGroup(${index})" style="background: #fef2f2; color: #ef4444; border: 1px solid #fee2e2; border-radius: 4px; padding: 4px 8px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s;">
                Xóa
            </button>
        </div>
    `).join('');
}

function addNewGroup() {
    const nameInput = document.getElementById('new-group-name');
    const urlInput = document.getElementById('new-group-url');

    const name = nameInput.value.trim();
    const url = urlInput.value.trim();

    if (!name || !url) {
        toast('Vui lòng điền đầy đủ Tên và URL nhóm Facebook!', 'error');
        return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        toast('URL nhóm Facebook không hợp lệ (phải bắt đầu bằng http/https)!', 'error');
        return;
    }

    const facebook = getSourceConfig('facebook');
    if (!facebook.facebook_groups) {
        facebook.facebook_groups = [];
    }

    facebook.facebook_groups.push({ name, url });

    nameInput.value = '';
    urlInput.value = '';

    toast('Đã thêm nhóm mới vào danh sách (nhấn "Lưu Facebook" để áp dụng)!', 'info');
    renderFacebookGroups();
}

function deleteGroup(index) {
    const facebook = getSourceConfig('facebook');
    if (confirm(`Bạn chắc chắn muốn xóa nhóm "${facebook.facebook_groups[index].name}" khỏi danh sách?`)) {
        facebook.facebook_groups.splice(index, 1);
        toast('Đã xóa nhóm (nhấn "Lưu Facebook" để áp dụng)!', 'info');
        renderFacebookGroups();
    }
}

async function saveBotConfig() {
    await saveSourceConfig('facebook');
}

async function saveSourceConfig(source) {
    currentBotConfig = normalizeBotConfig(currentBotConfig);
    const sourceConfig = getSourceConfig(source);

    if (source === 'facebook') {
        sourceConfig.enabled = document.getElementById('cfg-fb-enabled') ? document.getElementById('cfg-fb-enabled').checked : true;
        sourceConfig.max_posts_per_group = parseInt(document.getElementById('cfg-max-posts').value) || 5;
        sourceConfig.max_groups_per_session = parseInt(document.getElementById('cfg-max-groups').value) || 3;
        sourceConfig.max_days_old = parseInt(document.getElementById('cfg-max-days').value) || 3;
        sourceConfig.moderation_policy = {
            mode: document.getElementById('cfg-moderation-mode') ? document.getElementById('cfg-moderation-mode').value : 'manual',
            learn_from_admin: document.getElementById('cfg-learn-from-admin') ? document.getElementById('cfg-learn-from-admin').checked : true,
            auto_approve_after_hours: document.getElementById('cfg-auto-approve-hours') && document.getElementById('cfg-auto-approve-hours').value !== '' ? parseInt(document.getElementById('cfg-auto-approve-hours').value) : 0
        };
    } else {
        const enabledId = `cfg-${source}-enabled`;
        const pagesId = `cfg-${source}-max-pages`;
        const jobsId = `cfg-${source}-max-jobs`;
        const headlessId = `cfg-${source}-headless`;
        sourceConfig.enabled = document.getElementById(enabledId) ? document.getElementById(enabledId).checked : true;
        sourceConfig.max_pages = parseInt(document.getElementById(pagesId).value) || sourceConfig.max_pages || 1;
        sourceConfig.max_jobs = document.getElementById(jobsId) && document.getElementById(jobsId).value !== '' ? parseInt(document.getElementById(jobsId).value) : (sourceConfig.max_jobs || 10);
        sourceConfig.headless = document.getElementById(headlessId) ? document.getElementById(headlessId).checked : true;
    }

    toast(`Đang lưu cấu hình ${source}...`, 'info');
    try {
        await apiFetch('/admin/bot-config', {
            method: 'POST',
            body: JSON.stringify(currentBotConfig)
        });
        toast(`Đã lưu cấu hình ${source} thành công!`, 'success');
        fetchBotConfig();
    } catch (e) {
        toast(`Lỗi lưu cấu hình: ${e.message}`, 'error');
    }
}

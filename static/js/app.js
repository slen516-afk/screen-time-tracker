// ==========================================================================
// APP FRONTEND STATE & CONTROLLER (iOS Screen Time Dashboard)
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    // Current State
    let currentTab = 'dashboard';
    let currentRange = 'today';
    let hourlyChart = null;
    let appsData = [];
    let categoriesData = {};
    let limitsData = [];
    let widgetActive = false;

    // Time conversion helpers
    function formatTime(seconds) {
        if (!seconds || seconds <= 0) return '0分';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) {
            return `${h}小時 ${m}分`;
        }
        return `${m}分鐘`;
    }

    function formatTimeShort(seconds) {
        if (!seconds || seconds <= 0) return '0m';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (h > 0) {
            return `${h}h ${m}m`;
        }
        return `${m}m`;
    }

    function sanitizeClass(name) {
        return name.replace(/ & /g, '-').replace(/ /g, '-');
    }

    // Refresh Local Date
    function updateLocalDate() {
        const days = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
        const now = new Date();
        const year = now.getFullYear();
        const month = now.getMonth() + 1;
        const date = now.getDate();
        const dayName = days[now.getDay()];
        document.getElementById('lbl-current-date').innerText = `${year}年${month}月${date}日 ${dayName}`;
    }
    updateLocalDate();

    // ==========================================================================
    // TAB NAVIGATION
    // ==========================================================================
    const menuItems = document.querySelectorAll('.menu-item');
    const panels = document.querySelectorAll('.tab-panel');
    const pageTitle = document.getElementById('page-title');

    menuItems.forEach(item => {
        item.addEventListener('click', () => {
            const tabId = item.getAttribute('data-tab');
            
            // Toggle active menu item
            menuItems.forEach(mi => mi.classList.remove('active'));
            item.classList.add('active');

            // Toggle active tab panel
            panels.forEach(p => p.classList.remove('active'));
            document.getElementById(`tab-${tabId}`).classList.add('active');

            currentTab = tabId;

            // Set Header Page Title
            if (tabId === 'dashboard') pageTitle.innerText = '使用量儀表板';
            else if (tabId === 'limits') pageTitle.innerText = '應用使用限制';
            else if (tabId === 'timeline') pageTitle.innerText = '活動時間線';
            else if (tabId === 'settings') pageTitle.innerText = '設定與管理';

            // Refresh tab data immediately
            refreshData();
        });
    });

    // ==========================================================================
    // CHART.JS INITIALIZATION
    // ==========================================================================
    function initChart(initialData, chartLabels) {
        const ctx = document.getElementById('hourlyUsageChart').getContext('2d');
        
        // Create gorgeous neon gradient
        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, 'rgba(10, 132, 255, 0.85)');
        gradient.addColorStop(1, 'rgba(191, 90, 242, 0.25)');

        const labels = chartLabels || Array.from({length: 24}, (_, i) => `${i}點`);

        hourlyChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: '使用時間 (分鐘)',
                    data: initialData.map(sec => Math.round(sec / 60)),
                    backgroundColor: gradient,
                    borderRadius: 6,
                    borderSkipped: false,
                    hoverBackgroundColor: '#64D2FF'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1C1C1E',
                        titleFont: { family: 'Outfit', size: 13 },
                        bodyFont: { family: 'Inter', size: 12 },
                        borderColor: 'rgba(255,255,255,0.08)',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: function(context) {
                                const mins = context.raw;
                                return `使用量: ${formatTimeShort(mins * 60)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: '#8E8E93',
                            font: { family: 'Outfit', size: 10 }
                        }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.04)' },
                        ticks: {
                            color: '#8E8E93',
                            font: { family: 'Outfit', size: 10 },
                            callback: function(value) {
                                return value + 'm';
                            }
                        }
                    }
                }
            }
        });
    }

    // ==========================================================================
    // DATA FETCHING & UI RENDERING
    // ==========================================================================
    
    // Core Refresh Function called periodically
    function refreshData() {
        if (currentTab === 'dashboard') {
            fetchSummary();
            fetchChartData();
            fetchAppsData();
            fetchTimelineData(); // Needed for LIVE status logic
            fetchCharacterStats(); // Updates the digital avatar card
        } else if (currentTab === 'limits') {
            fetchLimits();
        } else if (currentTab === 'timeline') {
            fetchTimelineData();
        } else if (currentTab === 'settings') {
            fetchSettings();
        }
    }

    // 1. Fetch Summary
    function fetchSummary() {
        fetch(`/api/stats/summary?range=${currentRange}`)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Update Total Screen Time Card
                    document.getElementById('lbl-total-time').innerText = formatTimeShort(data.total_today);

                    // Update trend badge
                    const trendContainer = document.getElementById('lbl-trend-container');
                    const trendBadge = document.getElementById('lbl-trend-badge');
                    
                    if (data.percentage_change >= 0) {
                        trendBadge.innerText = `+${data.percentage_change}% ↗`;
                        trendBadge.className = 'trend-badge'; // Green positive class
                    } else {
                        trendBadge.innerText = `${data.percentage_change}% ↘`;
                        trendBadge.className = 'trend-badge negative';
                    }

                    // Update Categories List Card
                    categoriesData = data.categories;
                    renderCategories();
                }
            });
    }

    // 1.5 Fetch Character / Digital Avatar Stats
    function fetchCharacterStats() {
        fetch('/api/character')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Update Image src
                    document.getElementById('img-avatar').src = data.image_url;
                    
                    // Update Level & Title
                    document.getElementById('lbl-avatar-name').innerText = data.stage_title;
                    document.getElementById('lbl-avatar-stage').innerText = `等級：${data.level} / 5 (${getStageRankName(data.level)})`;
                    document.getElementById('lbl-avatar-desc').innerText = data.description;
                    
                    // Update Badges
                    const badge = document.getElementById('lbl-avatar-badge');
                    badge.innerText = getStatusLabel(data.status);
                    badge.className = `avatar-badge badge-${data.status}`;
                    
                    // Update Meters & Labels
                    document.getElementById('lbl-avatar-edu-time').innerText = `${data.edu_hours}h`;
                    document.getElementById('lbl-avatar-ent-time').innerText = `${data.ent_hours}h`;
                    
                    document.getElementById('bar-avatar-edu').style.width = `${data.exp_percent}%`;
                    document.getElementById('bar-avatar-ent').style.width = `${data.fatigue_percent}%`;
                }
            });
    }

    function getStageRankName(level) {
        switch(level) {
            case 1: return '新手';
            case 2: return '學徒';
            case 3: return '法師';
            case 4: return '賢者';
            case 5: return '真神';
            default: return '未知';
        }
    }

    function getStatusLabel(status) {
        switch(status) {
            case 'normal': return '正常';
            case 'strong': return '極盛';
            case 'weakened': return '萎靡';
            default: return '未知';
        }
    }

    // 2. Fetch Chart Data
    function fetchChartData() {
        fetch(`/api/stats/chart?range=${currentRange}`)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const minsData = data.chart_data.map(sec => Math.round(sec / 60));
                    if (!hourlyChart) {
                        initChart(data.chart_data, data.labels);
                    } else {
                        hourlyChart.data.labels = data.labels || Array.from({length: 24}, (_, i) => `${i}點`);
                        hourlyChart.data.datasets[0].data = minsData;
                        hourlyChart.update();
                    }
                }
            });
    }

    // 3. Fetch Apps List
    function fetchAppsData() {
        fetch(`/api/stats/apps?range=${currentRange}`)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    appsData = data.apps;
                    renderAppsList();
                    populateAppSelectorDropdown();
                }
            });
    }

    // 4. Fetch Timeline
    function fetchTimelineData() {
        fetch(`/api/stats/timeline?range=${currentRange}`)
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // Process LIVE active app card status from timeline

                    if (data.timeline.length > 0) {
                        const latest = data.timeline[0];
                        const endT = new Date(latest.end_time);
                        const diff = (new Date() - endT) / 1000;
                        
                        // If window is active within past 15 seconds
                        if (diff <= 15) {
                            document.getElementById('lbl-active-app-name').innerText = latest.display_name;
                            document.getElementById('lbl-active-app-category').innerText = latest.category;
                            
                            const avatar = document.getElementById('lbl-active-app-avatar');
                            avatar.innerText = latest.display_name.charAt(0);
                            avatar.className = `active-app-icon bg-${sanitizeClass(latest.category)}`;
                            
                            // Find total time for this active app
                            const matchingApp = appsData.find(a => a.app_name === latest.app_name);
                            const totalAppSec = matchingApp ? matchingApp.duration : latest.duration;
                            document.getElementById('lbl-active-app-duration').innerText = `今日已用：${formatTime(totalAppSec)}`;
                        } else {
                            setAppIdleState();
                        }
                    } else {
                        setAppIdleState();
                    }
                    
                    // If current tab is timeline, render the timeline
                    if (currentTab === 'timeline') {
                        renderTimeline(data.timeline);
                    }
                }
            });
    }

    function setAppIdleState() {
        document.getElementById('lbl-active-app-name').innerText = '暫停中 (閒置)';
        document.getElementById('lbl-active-app-category').innerText = '系統目前處於閒置或鎖定狀態';
        const avatar = document.getElementById('lbl-active-app-avatar');
        avatar.innerText = '💤';
        avatar.className = 'active-app-icon bg-Others';
        document.getElementById('lbl-active-app-duration').innerText = '今日監控運作中';
    }

    // Render Categories Share Card
    function renderCategories() {
        const container = document.getElementById('list-categories');
        container.innerHTML = '';

        const allCats = Object.entries(categoriesData).sort((a, b) => b[1] - a[1]);
        const grandTotal = allCats.reduce((sum, item) => sum + item[1], 0);

        if (grandTotal === 0) {
            container.innerHTML = '<div class="loading-spinner">今日無分類活動數據</div>';
            return;
        }

        allCats.forEach(([catName, duration]) => {
            if (duration === 0) return;
            const pct = Math.round((duration / grandTotal) * 100);

            const row = document.createElement('div');
            row.className = 'category-row';
            row.innerHTML = `
                <div class="category-info">
                    <div class="category-indicator bg-${sanitizeClass(catName)}"></div>
                    <span class="category-name">${catName}</span>
                </div>
                <div class="category-info">
                    <span class="category-duration">${formatTimeShort(duration)}</span>
                    <span class="trend-label">(${pct}%)</span>
                </div>
            `;
            container.appendChild(row);
        });
    }

    // Render Top Apps list
    function renderAppsList() {
        const container = document.getElementById('list-top-apps');
        container.innerHTML = '';

        if (appsData.length === 0) {
            container.innerHTML = '<div class="loading-spinner">今日無活動資料</div>';
            return;
        }

        const maxDuration = appsData[0].duration;

        appsData.forEach(app => {
            const pct = maxDuration > 0 ? Math.round((app.duration / maxDuration) * 100) : 0;
            const row = document.createElement('div');
            row.className = 'app-row';
            
            // Build sub-rows if any details
            let subRowsHtml = '';
            if (app.sub_details && app.sub_details.length > 0) {
                app.sub_details.forEach(sub => {
                    subRowsHtml += `
                        <div class="sub-row">
                            <span class="sub-title" title="${sub.title}">${sub.title || '（無標題視窗）'}</span>
                            <span class="sub-duration">${formatTimeShort(sub.duration)}</span>
                        </div>
                    `;
                });
            } else {
                subRowsHtml = '<div class="sub-row"><span class="sub-title">無詳細視窗記錄</span></div>';
            }

            row.innerHTML = `
                <div class="app-row-main" onclick="this.parentElement.classList.toggle('expanded')">
                    <div class="app-row-info">
                        <div class="app-avatar bg-${sanitizeClass(app.category)}">${app.display_name.charAt(0)}</div>
                        <div class="app-details">
                            <span class="app-display-name">${app.display_name}</span>
                            <span class="app-cat-badge">${app.category}</span>
                        </div>
                    </div>
                    <div class="app-time-stats">
                        <div class="app-progress-wrapper">
                            <div class="progress-track">
                                <div class="progress-bar bg-${sanitizeClass(app.category)}" style="width: ${pct}%"></div>
                            </div>
                        </div>
                        <span class="app-duration">${formatTimeShort(app.duration)}</span>
                        <button class="btn-expand-app">
                            <i data-lucide="chevron-down"></i>
                        </button>
                    </div>
                </div>
                <div class="app-sub-details">
                    ${subRowsHtml}
                </div>
            `;
            container.appendChild(row);
        });
        lucide.createIcons();
    }

    // Populate Limit Selection Apps list
    function populateAppSelectorDropdown() {
        const dropdown = document.getElementById('select-limit-app');
        dropdown.innerHTML = '';

        if (appsData.length === 0) {
            dropdown.innerHTML = '<option value="">無應用程式資料</option>';
            return;
        }

        appsData.forEach(app => {
            const opt = document.createElement('option');
            opt.value = app.app_name;
            opt.innerText = `${app.display_name} (${app.app_name})`;
            dropdown.appendChild(opt);
        });
    }

    // Render Timeline View
    function renderTimeline(timeline) {
        const container = document.getElementById('timeline-list');
        container.innerHTML = '';

        if (timeline.length === 0) {
            container.innerHTML = '<div class="loading-spinner">今日無活動歷程紀錄</div>';
            return;
        }

        timeline.forEach(item => {
            const dateObj = new Date(item.start_time);
            const timeStr = dateObj.toLocaleTimeString('zh-Hant', {hour: '2-digit', minute:'2-digit', second:'2-digit'});

            const tlItem = document.createElement('div');
            tlItem.className = 'timeline-item';
            
            tlItem.innerHTML = `
                <div class="timeline-node color-${sanitizeClass(item.category)}"></div>
                <div class="timeline-content">
                    <div class="timeline-meta">
                        <span class="timeline-time">${timeStr}</span>
                        <span class="timeline-duration color-${sanitizeClass(item.category)}">持續 ${formatTime(item.duration)}</span>
                    </div>
                    <h4 class="timeline-app-name">${item.display_name} <span class="app-cat-badge">${item.category}</span></h4>
                    <p class="timeline-title" title="${item.window_title}">${item.window_title || '（活動視窗）'}</p>
                </div>
            `;
            container.appendChild(tlItem);
        });
    }

    // ==========================================================================
    // TAB 2: LIMITS MANAGEMENT
    // ==========================================================================
    function fetchLimits() {
        fetch('/api/limits')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    limitsData = data.limits;
                    renderLimitsList();
                }
            });
    }

    function renderLimitsList() {
        const container = document.getElementById('list-active-limits');
        container.innerHTML = '';

        if (limitsData.length === 0) {
            container.innerHTML = `
                <div class="card col-span-2 text-center" style="grid-column: span 3; padding: 40px;">
                    <i data-lucide="shield-alert" style="width: 48px; height: 48px; margin: 0 auto 15px; color: var(--text-muted);"></i>
                    <h3 style="font-family: var(--font-heading); margin-bottom: 8px;">尚無任何時間限制</h3>
                    <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 20px;">設定使用限制可以協助您控管特定程式的使用時間，避免過度沉迷。</p>
                    <button class="btn btn-primary" onclick="document.getElementById('btn-add-limit-modal').click()" style="margin: 0 auto;">新增第一個使用限制</button>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        limitsData.forEach(lim => {
            // Find current today's duration for this target
            let usageSeconds = lim.usage_seconds || 0;
            let displayName = lim.target;
            let isCategory = lim.target.startsWith('category:');
            let isSite = lim.target.startsWith('site:');
            let categoryName = 'Others';
            let limitTypeLabel = 'App 限額';

            if (isCategory) {
                const cat = lim.target.replace('category:', '');
                categoryName = cat;
                displayName = `${cat} 類別`;
                limitTypeLabel = 'Category 限額';
            } else if (isSite) {
                const site = lim.target.replace('site:', '');
                categoryName = 'Browsers'; // Map to green color
                displayName = `網站關鍵字：${site}`;
                limitTypeLabel = 'Site 限額';
            } else {
                const app = appsData.find(a => a.app_name === lim.target);
                if (app) {
                    displayName = app.display_name;
                    categoryName = app.category;
                } else {
                    displayName = lim.target.replace('.exe', '').toUpperCase();
                }
            }

            const limitSeconds = lim.limit_seconds;
            const pct = Math.min(100, Math.round((usageSeconds / limitSeconds) * 100));

            // Determine warning styling classes
            let progressClass = '';
            if (pct >= 90) progressClass = 'danger';
            else if (pct >= 70) progressClass = 'warning';

            const card = document.createElement('div');
            card.className = 'limit-card';
            
            card.innerHTML = `
                <div class="limit-card-header">
                    <div class="limit-card-title">
                        <h4>${displayName}</h4>
                        <span>${limitTypeLabel}</span>
                    </div>
                    <button class="btn-delete-limit" data-target="${lim.target}" title="刪除限制">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
                <div class="limit-card-body">
                    <div class="limit-time-info">
                        <span>已用 ${formatTimeShort(usageSeconds)}</span>
                        <span>上限 ${formatTimeShort(limitSeconds)}</span>
                    </div>
                    <div class="limit-progress-bar">
                        <div class="limit-progress-fill ${progressClass} bg-${sanitizeClass(categoryName)}" style="width: ${pct}%"></div>
                    </div>
                </div>
                <div class="limit-time-info" style="margin-bottom: 0;">
                    <span class="color-${sanitizeClass(categoryName)}" style="font-weight: 500;">類別：${categoryName}</span>
                    <span class="limit-usage-percent">${pct}%</span>
                </div>
            `;

            // Delete limit event listener
            card.querySelector('.btn-delete-limit').addEventListener('click', function() {
                const target = this.getAttribute('data-target');
                if (confirm(`確認要刪除「${displayName}」的使用限制嗎？`)) {
                    deleteLimit(target);
                }
            });

            container.appendChild(card);
        });
        lucide.createIcons();
    }

    function deleteLimit(target) {
        fetch('/api/limits', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: target })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                fetchLimits();
            } else {
                alert('刪除失敗: ' + data.error);
            }
        });
    }

    // Modal Control: Add Limit
    const modalAddLimit = document.getElementById('modal-add-limit');
    const btnOpenAddLimit = document.getElementById('btn-add-limit-modal');
    const btnCloseAddLimit = document.getElementById('btn-close-limit-modal');
    const btnCancelAddLimit = document.getElementById('btn-cancel-limit-modal');
    const formAddLimit = document.getElementById('form-add-limit');
    
    const selectLimitType = document.getElementById('select-limit-type');
    const groupSelectApp = document.getElementById('group-select-app');
    const groupSelectCategory = document.getElementById('group-select-category');

    btnOpenAddLimit.addEventListener('click', () => {
        modalAddLimit.classList.add('active');
    });

    function closeAddLimitModal() {
        modalAddLimit.classList.remove('active');
        formAddLimit.reset();
        selectLimitType.value = 'app';
        groupSelectApp.classList.remove('d-none');
        groupSelectCategory.classList.add('d-none');
        document.getElementById('group-input-site').classList.add('d-none');
    }

    btnCloseAddLimit.addEventListener('click', closeAddLimitModal);
    btnCancelAddLimit.addEventListener('click', closeAddLimitModal);

    const groupInputSite = document.getElementById('group-input-site');

    selectLimitType.addEventListener('change', () => {
        groupSelectApp.classList.add('d-none');
        groupSelectCategory.classList.add('d-none');
        groupInputSite.classList.add('d-none');
        
        if (selectLimitType.value === 'app') {
            groupSelectApp.classList.remove('d-none');
        } else if (selectLimitType.value === 'category') {
            groupSelectCategory.classList.remove('d-none');
        } else if (selectLimitType.value === 'site') {
            groupInputSite.classList.remove('d-none');
        }
    });

    formAddLimit.addEventListener('submit', (e) => {
        e.preventDefault();

        const type = selectLimitType.value;
        let target = '';

        if (type === 'app') {
            target = document.getElementById('select-limit-app').value;
            if (!target) {
                alert('請先選擇一個應用程式！');
                return;
            }
        } else if (type === 'category') {
            target = `category:${document.getElementById('select-limit-category').value}`;
        } else if (type === 'site') {
            const siteVal = document.getElementById('input-limit-site').value.trim().toLowerCase();
            if (!siteVal) {
                alert('請輸入網站關鍵字！');
                return;
            }
            target = `site:${siteVal}`;
        }

        const hrs = parseInt(document.getElementById('input-limit-hours').value) || 0;
        const mins = parseInt(document.getElementById('input-limit-minutes').value) || 0;
        const totalSeconds = (hrs * 3600) + (mins * 60);

        if (totalSeconds <= 0) {
            alert('限制時間必須大於 0 分鐘！');
            return;
        }

        fetch('/api/limits', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: target, limit_seconds: totalSeconds })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                closeAddLimitModal();
                fetchLimits();
            } else {
                alert('新增失敗: ' + data.error);
            }
        });
    });

    // ==========================================================================
    // TAB 4: SETTINGS & APP CUSTOMIZATION MANAGEMENT
    // ==========================================================================
    const formSettings = document.getElementById('form-settings');
    const inputIdleThreshold = document.getElementById('input-idle-threshold');
    const tableAppList = document.getElementById('table-app-list');
    
    // Modal Edit App Config
    const modalEditApp = document.getElementById('modal-edit-app');
    const btnCloseAppModal = document.getElementById('btn-close-app-modal');
    const btnCancelAppModal = document.getElementById('btn-cancel-app-modal');
    const formEditApp = document.getElementById('form-edit-app');

    function fetchSettings() {
        fetch('/api/settings')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    inputIdleThreshold.value = data.idle_threshold;
                    document.getElementById('input-gemini-key').value = data.gemini_api_key || '';
                    document.getElementById('check-widget-startup').checked = data.auto_start_widget || false;
                    renderAppCategorizerTable();
                }
            });
            
        fetch('/api/settings/startup')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('check-startup-toggle').checked = data.enabled;
                }
            });
    }

    formSettings.addEventListener('submit', (e) => {
        e.preventDefault();
        const threshold = parseInt(inputIdleThreshold.value);
        const geminiKey = document.getElementById('input-gemini-key').value.trim();
        const startupEnabled = document.getElementById('check-startup-toggle').checked;
        const autoStartWidget = document.getElementById('check-widget-startup').checked;

        const saveSettingsPromise = fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                idle_threshold: threshold,
                gemini_api_key: geminiKey,
                auto_start_widget: autoStartWidget
            })
        }).then(res => res.json());

        const saveStartupPromise = fetch('/api/settings/startup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable: startupEnabled })
        }).then(res => res.json());

        Promise.all([saveSettingsPromise, saveStartupPromise])
            .then(([resSettings, resStartup]) => {
                if (resSettings.success && resStartup.success) {
                    alert('系統設定與開機啟動設定儲存成功！');
                } else {
                    const errMsg = (!resSettings.success ? resSettings.error : '') + ' ' + (!resStartup.success ? resStartup.error : '');
                    alert('儲存失敗: ' + errMsg);
                }
            })
            .catch(err => {
                alert('網路錯誤，儲存失敗！');
            });
    });

    function renderAppCategorizerTable() {
        tableAppList.innerHTML = '';
        
        if (appsData.length === 0) {
            tableAppList.innerHTML = '<tr><td colspan="4" class="text-center">尚無任何已追蹤的應用程式。</td></tr>';
            return;
        }

        appsData.forEach(app => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-family: monospace; font-weight: 500;">${app.app_name}</td>
                <td>${app.display_name}</td>
                <td><span class="app-cat-badge bg-${sanitizeClass(app.category)}" style="color:white; padding: 3px 8px;">${app.category}</span></td>
                <td>
                    <button class="btn btn-secondary btn-sm btn-edit-app" 
                            data-appname="${app.app_name}" 
                            data-display="${app.display_name}" 
                            data-category="${app.category}" 
                            style="padding: 4px 10px; font-size: 12px; border-radius: 6px;">
                        編輯
                    </button>
                </td>
            `;

            // Open Edit App Modal Listener
            tr.querySelector('.btn-edit-app').addEventListener('click', function() {
                const appName = this.getAttribute('data-appname');
                const display = this.getAttribute('data-display');
                const category = this.getAttribute('data-category');

                document.getElementById('input-edit-app-name').value = appName;
                document.getElementById('lbl-edit-app-filename').value = appName;
                document.getElementById('input-edit-app-display').value = display;
                document.getElementById('select-edit-app-category').value = category;

                modalEditApp.classList.add('active');
            });

            tableAppList.appendChild(tr);
        });
    }

    function closeAppModal() {
        modalEditApp.classList.remove('active');
        formEditApp.reset();
    }

    btnCloseAppModal.addEventListener('click', closeAppModal);
    btnCancelAppModal.addEventListener('click', closeAppModal);

    formEditApp.addEventListener('submit', (e) => {
        e.preventDefault();

        const appName = document.getElementById('input-edit-app-name').value;
        const display = document.getElementById('input-edit-app-display').value;
        const category = document.getElementById('select-edit-app-category').value;

        fetch('/api/apps/configure', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app_name: appName, display_name: display, category: category })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                closeAppModal();
                fetchAppsData(); // Refreshes app stats and dropdowns
                if (currentTab === 'settings') {
                    // Update table UI
                    setTimeout(fetchSettings, 200);
                }
            } else {
                alert('更新失敗: ' + data.error);
            }
        });
    });

    // ==========================================================================
    // FLOATING DESKTOP WIDGET TRIGGER CONTROL
    // ==========================================================================
    const btnToggleWidget = document.getElementById('btn-toggle-widget');
    const txtWidgetToggle = document.getElementById('txt-widget-toggle');

    function checkWidgetStatus() {
        fetch('/api/widget/status')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    widgetActive = data.is_active;
                    updateWidgetButtonState();
                }
            });
    }

    function updateWidgetButtonState() {
        if (widgetActive) {
            btnToggleWidget.className = 'btn btn-danger';
            txtWidgetToggle.innerText = '關閉桌面小工具';
            // Update icon
            btnToggleWidget.querySelector('i').setAttribute('data-lucide', 'square-x');
        } else {
            btnToggleWidget.className = 'btn btn-primary';
            txtWidgetToggle.innerText = '開啟桌面小工具';
            btnToggleWidget.querySelector('i').setAttribute('data-lucide', 'panels-top-left');
        }
        lucide.createIcons();
    }

    btnToggleWidget.addEventListener('click', () => {
        fetch('/api/widget/toggle', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    widgetActive = data.is_active;
                    updateWidgetButtonState();
                } else {
                    alert('小工具操作失敗: ' + data.error);
                }
            });
    });

    // ==========================================================================
    // RANGE SELECTOR EVENTS
    // ==========================================================================
    const rangeBtns = document.querySelectorAll('.range-btn');
    rangeBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const range = btn.getAttribute('data-range');
            
            // Toggle active class
            rangeBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            currentRange = range;
            
            // Update Card & Chart Titles
            const totalTitle = document.getElementById('lbl-total-time-title');
            const chartTitle = document.getElementById('lbl-chart-title');
            const chartSubtitle = document.getElementById('lbl-chart-subtitle');
            
            if (range === 'today') {
                totalTitle.innerText = '今日使用總時間';
                chartTitle.innerText = '今日活動分佈';
                chartSubtitle.innerText = '每小時使用時間分佈圖';
            } else if (range === 'yesterday') {
                totalTitle.innerText = '昨日使用總時間';
                chartTitle.innerText = '昨日活動分佈';
                chartSubtitle.innerText = '每小時使用時間分佈圖';
            } else if (range === '7days') {
                totalTitle.innerText = '過去 7 天使用總時間';
                chartTitle.innerText = '過去 7 天活動分佈';
                chartSubtitle.innerText = '每日使用時間分佈圖';
            } else if (range === '30days') {
                totalTitle.innerText = '過去 30 天使用總時間';
                chartTitle.innerText = '過去 30 天活動分佈';
                chartSubtitle.innerText = '每日使用時間分佈圖';
            }
            
            // Refresh stats immediately
            refreshData();
        });
    });

    // Startup Init Checks
    checkWidgetStatus();
    refreshData();

    // Set polling timers: update current stats and charts every 3 seconds for ultimate real-time fidelity
    setInterval(refreshData, 3000);
    setInterval(checkWidgetStatus, 5000); // Check widget status less frequently
});

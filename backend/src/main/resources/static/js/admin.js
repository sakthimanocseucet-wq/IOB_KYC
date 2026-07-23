// ====================== ADMIN STATE ======================
const ADMIN_API = '/api/admin';
let refreshInterval = null;
let kycApplications = [];

function dedupApplications(apps) {
    var latest = {};
    for (var i = 0; i < apps.length; i++) {
        var a = apps[i];
        var key = (a.userId || a.id) + '|' + (a.applicationType || 'NORMAL');
        if (!latest[key] || a.id > latest[key].id) {
            latest[key] = a;
        }
    }
    var result = [];
    for (var k in latest) result.push(latest[k]);
    result.sort(function(a, b) { return b.id - a.id; });
    return result;
}


// ====================== AUTH CHECK ======================
function checkAdminAuth() {
    const token = getAuthToken();
    const user = getUser();
    if (!token || (!user || !user.role || (user.role !== 'admin' && user.role !== 'manager' && user.role !== 'officer'))) {
        console.warn('[Admin] Not authenticated or wrong role. Redirecting to login.');
        clearAuthData();
        window.location.href = 'login.html';
        return false;
    }
    try {
        var payload = JSON.parse(atob(token.split('.')[1]));
        var userObj = user || {};
        userObj.employeeId = payload.employeeId || userObj.employeeId || '';
        userObj.branchId = payload.branchId || userObj.branchId || '';
        userObj.employeeName = payload.employeeName || userObj.employeeName || '';
        if (payload.role) userObj.role = (payload.role || '').toLowerCase();
        sessionStorage.setItem('user', JSON.stringify(userObj));
        localStorage.setItem('userBackup', JSON.stringify(userObj));
    } catch(e) {
        console.warn('[Admin] Could not parse JWT payload:', e.message);
    }
    return true;
}

function handleAuthError() {
    clearAuthData();
    console.warn('[Admin] Session expired. Redirecting to login.');
    window.location.href = 'login.html';
}

// ====================== DASHBOARD INIT ======================
document.addEventListener('DOMContentLoaded', function() {
    if (!checkAdminAuth()) return;
    var user = getUser();
    var role = user ? user.role : '';

    var adminOnlyElements = document.querySelectorAll('.admin-only');
    adminOnlyElements.forEach(function(el) {
        el.style.display = (role === 'admin') ? '' : 'none';
    });

    var managerOnlyElements = document.querySelectorAll('.manager-only');
    managerOnlyElements.forEach(function(el) {
        el.style.display = (role === 'admin' || role === 'manager') ? '' : 'none';
    });

    var officerOnlyElements = document.querySelectorAll('.officer-only');
    officerOnlyElements.forEach(function(el) {
        el.style.display = (role === 'officer') ? '' : 'none';
    });

    // Show logged-in user info in top bar
    var userInfoEl = document.getElementById('userInfo');
    if (userInfoEl && user) {
        var roleBadgeColors = { admin: '#dc2626', manager: '#f59e0b', officer: '#3b82f6' };
        var roleBadgeBg = { admin: 'rgba(220,38,38,0.1)', manager: 'rgba(245,158,11,0.1)', officer: 'rgba(59,130,246,0.1)' };
        var displayName = user.employeeName || user.name || user.employeeId || 'Staff';
        var roleLabel = (role || 'admin').toUpperCase();
        var badgeColor = roleBadgeColors[role] || '#6b7280';
        var badgeBg = roleBadgeBg[role] || 'rgba(107,114,128,0.1)';
        userInfoEl.innerHTML = '<span style="margin-right:6px">' + displayName + '</span>' +
            '<span style="background:' + badgeBg + ';color:' + badgeColor + ';padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;text-transform:uppercase">' + roleLabel + '</span>';
    }

    if (document.getElementById('kycTableBody')) {
        loadApplicationsFromAPI();
        refreshInterval = setInterval(refreshDashboard, 30000);
    }
    if (document.getElementById('kycReviewList')) {
        loadReviewListFromAPI();
    }
});

async function loadApplicationsFromAPI() {
    try {
        const token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        const res = await fetch(ADMIN_API + '/applications?page=0&size=50', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.status === 401 || res.status === 403) {
            console.error('[Admin] Auth failed:', res.status);
            handleAuthError();
            return;
        }
        if (res.ok) {
            const data = await res.json();
            if (data.applications && data.applications.length > 0) {
                kycApplications = dedupApplications(data.applications.map(mapBackendApp));
            }
            if (data.duplicates && data.duplicates.length > 0) {
                renderDuplicateAlerts(data.duplicates);
            } else {
                var alertEl = document.getElementById('duplicateAlerts');
                if (alertEl) alertEl.style.display = 'none';
            }
        }
    } catch (e) {
        console.warn('[Admin] Failed to load applications, keeping existing data:', e.message);
    }
    await updateStats();
    renderDashboard();
}

async function loadReviewListFromAPI() {
    try {
        const token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        const res = await fetch(ADMIN_API + '/applications?page=0&size=50', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.status === 401 || res.status === 403) { handleAuthError(); return; }
        if (res.ok) {
            const data = await res.json();
            if (data.applications && data.applications.length > 0) {
                kycApplications = dedupApplications(data.applications.map(mapBackendApp));
            }
        }
    } catch (e) {
        console.warn('[Admin] Failed to load review list, keeping existing data:', e.message);
    }
    loadReviewList();
}

function mapBackendApp(app) {
    var statusMap = { 'DRAFT': 'pending', 'PENDING': 'pending', 'UNDER_REVIEW': 'pending', 'APPROVED': 'approved', 'REJECTED': 'rejected', 'SUPERSEDED': 'superseded' };
    var dob = '';
    if (app.ocrDob) {
        try {
            var d = new Date(app.ocrDob);
            dob = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
        } catch(e) { dob = app.ocrDob; }
    }
    return {
        id: app.id,
        name: app.ocrName || 'Unknown',
        docType: app.docType || 'Aadhaar',
        applicationType: app.applicationType || 'NORMAL',
        riskScore: app.riskScore || 0,
        status: statusMap[app.status] || 'pending',
        date: app.submittedAt ? app.submittedAt.substring(0, 10) : (app.createdAt ? app.createdAt.substring(0, 10) : 'N/A'),
        device: app.device || 'Unknown Device',
        ip: app.ipAddress || 'N/A',
        location: 'India',
        mobile: (app.mobile) || (app.user && app.user.phone) || 'N/A',
        email: (app.email) || (app.user && app.user.email) || 'N/A',
        accountType: (app.accountType || 'SAVINGS').toLowerCase(),
        accountNumber: app.accountNumber || 'N/A',
        gender: app.gender || 'N/A',
        ifscCode: app.ifscCode || 'N/A',
        branchId: app.branchId || 'N/A',
        dob: dob,
        idNumber: app.ocrIdNumber || 'N/A',
        address: app.ocrAddress || 'N/A',
        panNumber: app.ocrPanNumber || 'N/A',
        faceMatch: app.faceMatchPercentage || 0,
        livenessScore: app.livenessPassed ? 85 : 0,
        userId: app.user && app.user.id ? app.user.id : null,
        hasDoc: !!(app.docFilePath || app.aadhaarFrontPath || app.panCardPath),
        hasSelfie: !!(app.selfieFilePath),
        hasAadhaarFront: !!(app.aadhaarFrontPath),
        hasAadhaarBack: !!(app.aadhaarBackPath),
        hasPanCard: !!(app.panCardPath),
        hasPhoto: !!(app.photoFilePath),
        rawStatus: app.status,
        reviewNotes: app.reviewNotes || '',
        qrVerified: app.qrVerified || false,
        qrVerificationStatus: app.qrVerificationStatus || null,
        qrMatchPercentage: app.qrMatchPercentage || 0,
        qrVerifiedAt: app.qrVerifiedAt || null,
        challengeVideoBase64: app.challengeResponseVideoBase64 || null,
        challengeResults: app.challengeResults || null,
        challengeSequence: app.challengeSequence || null,
        qrFaceMatchScore: app.qrFaceMatchScore || null,
        qrFaceMatchStatus: app.qrFaceMatchStatus || null,
        qrFaceConfidence: app.qrFaceConfidence || null,
        verificationTimestamp: app.verificationTimestamp || null
    };
}

var lastDataHash = '';

async function refreshDashboard() {
    if (!checkAdminAuth()) return;
    const indicator = document.getElementById('liveIndicator');
    if (indicator) {
        indicator.style.opacity = '0.5';
        setTimeout(() => { indicator.style.opacity = '1'; }, 300);
    }
    await loadApplicationsFromAPI();
}

function renderDuplicateAlerts(duplicates) {
    var container = document.getElementById('duplicateAlerts');
    var list = document.getElementById('duplicateAlertList');
    var countEl = document.getElementById('duplicateAlertCount');
    if (!container || !list) return;
    if (!duplicates || duplicates.length === 0) {
        container.style.display = 'none';
        return;
    }
    container.style.display = 'block';
    if (countEl) countEl.textContent = duplicates.length + ' alert' + (duplicates.length > 1 ? 's' : '');

    var typeIcons = {
        'mobile': '&#128241;',
        'email': '&#128231;',
        'id_number': '&#128196;',
        'pan_number': '&#128196;',
        'selfie': '&#128247;',
        'photo': '&#128247;',
        'ip_address': '&#127760;'
    };
    var typeColors = {
        'mobile': '#f59e0b',
        'email': '#3b82f6',
        'id_number': '#dc2626',
        'pan_number': '#dc2626',
        'selfie': '#8b5cf6',
        'photo': '#8b5cf6',
        'ip_address': '#059669'
    };

    var html = '';
    for (var i = 0; i < duplicates.length; i++) {
        var d = duplicates[i];
        var icon = typeIcons[d.type] || '&#9888;';
        var color = typeColors[d.type] || 'var(--danger)';
        var appIds = (d.applicationIds || []);
        html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;margin-bottom:8px;background:#fff;border-radius:8px;border-left:4px solid ' + color + ';border-right:1px solid #fecaca;border-top:1px solid #fecaca;border-bottom:1px solid #fecaca">' +
            '<div style="display:flex;align-items:center;gap:12px">' +
                '<span style="font-size:24px">' + icon + '</span>' +
                '<div>' +
                    '<div style="font-weight:600;color:' + color + '">Duplicate ' + d.label + ' detected (' + d.count + ' applications)</div>' +
                    '<div style="font-size:13px;color:var(--gray-600)">Value: <strong>' + d.value + '</strong> &mdash; Users: ' + (d.userIds || []).join(', ') + '</div>' +
                '</div>' +
            '</div>' +
            '<div style="display:flex;gap:8px;flex-shrink:0;align-items:center">' +
                appIds.map(function(aid) {
                    var found = kycApplications.find(function(a) { return a.id === aid; });
                    var label = found ? (found.name || 'App') : 'App';
                    return '<button class="btn btn-sm btn-outline" onclick="viewAppById(' + aid + ')" style="font-size:11px;padding:4px 8px;border-color:' + color + ';color:' + color + '" title="View application for ' + label + '">&#128065; ' + label + '</button>';
                }).join('') +
                (appIds.length >= 2 ? '<button class="btn btn-sm btn-outline" onclick="compareDuplicateApps(' + appIds[0] + ',' + appIds[1] + ')" style="font-size:11px;padding:4px 8px;border-color:' + color + ';color:#fff;background:' + color + '" title="Compare both applications side by side">&#128260; Compare</button>' : '') +
            '</div>' +
        '</div>';
    }
    list.innerHTML = html;
}

function viewAppById(appId) {
    var app = kycApplications.find(function(a) { return a.id === appId; });
    if (app) {
        viewApplication(appId);
        return;
    }
    var token = getAuthToken();
    if (!token) { checkAdminAuth(); return; }
    fetch(ADMIN_API + '/applications/' + appId, {
        headers: { 'Authorization': 'Bearer ' + token }
    }).then(function(res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    }).then(function(data) {
        if (data && data.id) {
            var mapped = mapBackendApp(data);
            kycApplications.push(mapped);
            viewApplication(appId);
        } else {
            showToast('Application not found', 'error');
        }
    }).catch(function(e) {
        showToast('Failed to load application: ' + e.message, 'error');
    });
}

function dataHash(arr) {
    return arr.map(function(a) { return a.id + ':' + a.status + ':' + a.riskScore; }).join('|');
}

async function compareDuplicateApps(id1, id2) {
    var token = getAuthToken();
    if (!token) { checkAdminAuth(); return; }

    async function fetchApp(appId) {
        var found = kycApplications.find(function(a) { return a.id === appId; });
        if (found) return found;
        var res = await fetch(ADMIN_API + '/applications/' + appId, { headers: { 'Authorization': 'Bearer ' + token } });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var data = await res.json();
        if (data && data.id) { var mapped = mapBackendApp(data); kycApplications.push(mapped); return mapped; }
        return null;
    }

    showToast('Loading comparison...', 'info');
    try {
        var a = await fetchApp(id1);
        var b = await fetchApp(id2);
        if (!a || !b) { showToast('Could not load applications', 'error'); return; }

        var fields = [
            { key: 'name', label: 'Full Name' },
            { key: 'dob', label: 'Date of Birth' },
            { key: 'idNumber', label: 'Aadhaar Number' },
            { key: 'panNumber', label: 'PAN Number' },
            { key: 'address', label: 'Address' },
            { key: 'mobile', label: 'Mobile' },
            { key: 'email', label: 'Email' },
            { key: 'ip', label: 'IP Address' },
            { key: 'device', label: 'Device' }
        ];

        var rows = fields.map(function(f) {
            var v1 = a[f.key] || '--';
            var v2 = b[f.key] || '--';
            var match = v1 === v2 && v1 !== '--';
            var bg = match ? 'rgba(220,38,38,0.06)' : '';
            var tag = match ? ' <span style="color:var(--danger);font-size:11px;font-weight:700">SAME</span>' : '';
            return '<tr style="background:' + bg + '">' +
                '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-weight:600;font-size:13px;color:var(--gray-700)">' + f.label + '</td>' +
                '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-size:13px">' + v1 + tag + '</td>' +
                '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-size:13px">' + v2 + tag + '</td>' +
            '</tr>';
        }).join('');

        var html =
            '<div style="padding:20px">' +
                '<h3 style="margin-bottom:16px;color:var(--gray-800)">&#128260; Duplicate Comparison</h3>' +
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">' +
                    '<div style="padding:12px;background:var(--gray-50);border-radius:8px;text-align:center">' +
                        '<div style="font-size:13px;color:var(--gray-500)">Application 1</div>' +
                        '<div style="font-weight:700;font-size:16px;color:var(--gray-800)">' + (a.name || 'Unknown') + '</div>' +
                        '<div style="font-size:12px;color:var(--gray-500)">ID: IOB-KYC-' + String(a.id).padStart(5, '0') + '</div>' +
                        '<div style="margin-top:4px"><span class="badge ' + (a.status === 'approved' ? 'badge-success' : a.status === 'rejected' ? 'badge-danger' : 'badge-warning') + '">' + (a.status || 'pending') + '</span></div>' +
                    '</div>' +
                    '<div style="padding:12px;background:var(--gray-50);border-radius:8px;text-align:center">' +
                        '<div style="font-size:13px;color:var(--gray-500)">Application 2</div>' +
                        '<div style="font-weight:700;font-size:16px;color:var(--gray-800)">' + (b.name || 'Unknown') + '</div>' +
                        '<div style="font-size:12px;color:var(--gray-500)">ID: IOB-KYC-' + String(b.id).padStart(5, '0') + '</div>' +
                        '<div style="margin-top:4px"><span class="badge ' + (b.status === 'approved' ? 'badge-success' : b.status === 'rejected' ? 'badge-danger' : 'badge-warning') + '">' + (b.status || 'pending') + '</span></div>' +
                    '</div>' +
                '</div>' +
                '<table style="width:100%;border-collapse:collapse;border:1px solid var(--gray-200);border-radius:8px;overflow:hidden">' +
                    '<thead><tr style="background:var(--gray-100)">' +
                        '<th style="padding:10px 12px;text-align:left;font-size:13px;color:var(--gray-600)">Field</th>' +
                        '<th style="padding:10px 12px;text-align:left;font-size:13px;color:var(--gray-600)">Application 1 (' + (a.name || 'Unknown') + ')</th>' +
                        '<th style="padding:10px 12px;text-align:left;font-size:13px;color:var(--gray-600)">Application 2 (' + (b.name || 'Unknown') + ')</th>' +
                    '</tr></thead>' +
                    '<tbody>' + rows + '</tbody>' +
                '</table>' +
                '<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px">' +
                    '<button class="btn btn-sm btn-outline" onclick="viewAppById(' + a.id + ')">&#128065; View App 1</button>' +
                    '<button class="btn btn-sm btn-outline" onclick="viewAppById(' + b.id + ')">&#128065; View App 2</button>' +
                    '<button class="btn btn-sm btn-outline" onclick="closeReviewModal()">Close</button>' +
                '</div>' +
            '</div>';

        var modal = document.getElementById('reviewModal');
        var content = document.getElementById('reviewModalContent');
        if (!modal || !content) return;
        content.innerHTML = html;
        var modalTitle = modal.querySelector('.modal-header h2');
        if (modalTitle) modalTitle.textContent = 'Duplicate Comparison';
        modal.classList.add('active');
    } catch(e) {
        showToast('Error loading comparison: ' + e.message, 'error');
    }
}

function renderDashboard() {
    var tbody = document.getElementById('kycTableBody');
    if (!tbody) return;

    var currentHash = dataHash(kycApplications);
    if (currentHash === lastDataHash && tbody.getAttribute('data-hash') === currentHash) {
        return;
    }
    lastDataHash = currentHash;

    var filter = document.getElementById('kycFilter');
    var filterVal = filter ? filter.value : 'all';

    var filtered = [].concat(kycApplications);
    if (filterVal === 'highrisk') filtered = filtered.filter(function(a) { return a.riskScore >= 70; });
    else if (filterVal === 'pending') filtered = filtered.filter(function(a) { return a.status === 'pending'; });
    else if (filterVal === 'approved') filtered = filtered.filter(function(a) { return a.status === 'approved'; });
    else if (filterVal === 'rejected') filtered = filtered.filter(function(a) { return a.status === 'rejected' || a.status === 'highrisk'; });
    else if (filterVal === 'rekyc') filtered = filtered.filter(function(a) { return a.applicationType === 'RE_KYC'; });

    var searchEl = document.getElementById('kycSearch');
    var searchVal = searchEl ? searchEl.value.trim().toLowerCase() : '';
    if (searchVal) {
        filtered = filtered.filter(function(a) {
            return (a.name && a.name.toLowerCase().indexOf(searchVal) > -1) ||
                (a.mobile && a.mobile.toLowerCase().indexOf(searchVal) > -1) ||
                (a.email && a.email.toLowerCase().indexOf(searchVal) > -1) ||
                (a.idNumber && a.idNumber.toLowerCase().indexOf(searchVal) > -1) ||
                (a.panNumber && a.panNumber.toLowerCase().indexOf(searchVal) > -1) ||
                (a.ip && a.ip.toLowerCase().indexOf(searchVal) > -1) ||
                (String(a.id).indexOf(searchVal) > -1);
        });
    }

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--gray-500)">No matching applications</td></tr>';
        tbody.setAttribute('data-hash', currentHash);
        return;
    }

    tbody.innerHTML = filtered.map(function(app) {
        var riskColor = app.riskScore < 30 ? 'var(--success)' : app.riskScore < 60 ? 'var(--warning)' : 'var(--danger)';
        var statusBadge = app.status === 'approved' ? 'badge-success'
            : app.status === 'rejected' ? 'bade-danger'
            : app.status === 'highrisk' ? 'bade-danger'
            : 'bade-warning';
        var statusLabel = app.status === 'highrisk' ? 'High Risk' : app.status.charAt(0).toUpperCase() + app.status.slice(1);

        var reKycBadge = app.applicationType === 'RE_KYC' ? ' <span class="badge badge-info" style="font-size:10px;padding:2px 8px;background:var(--primary,#3b82f6);color:white">Re-KYC</span>' : '';
        return '<tr>' +
            '<td style="cursor:pointer" onclick="viewApplication(' + app.id + ')"><strong>' + app.name + '</strong>' + reKycBadge + '<br><small style="color:var(--gray-500)">' + app.date + '</small></td>' +
            '<td style="cursor:pointer" onclick="viewApplication(' + app.id + ')"><small>' + (app.branchId || 'N/A') + '</small></td>' +
            '<td style="cursor:pointer" onclick="viewApplication(' + app.id + ')">' + app.docType + '</td>' +
            '<td style="cursor:pointer" onclick="viewApplication(' + app.id + ')">' +
                '<div class="risk-bar">' +
                    '<div class="risk-indicator">' +
                        '<div class="risk-fill-bar" style="width:' + app.riskScore + '%;background:' + riskColor + '"></div>' +
                    '</div>' +
                    '<span style="font-size:13px;font-weight:600;color:' + riskColor + '">' + app.riskScore + '</span>' +
                '</div>' +
            '</td>' +
            '<td style="cursor:pointer" onclick="viewApplication(' + app.id + ')"><span class="badge ' + statusBadge + '">' + statusLabel + '</span></td>' +
            '<td>' +
                ((function() { var u = getUser(); return u && u.role === 'admin'; })() ? '<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteKycApplication(' + app.id + ')" title="Delete Application">&#128465;</button>' : '') +
            '</td>' +
        '</tr>';
    }).join('');
    tbody.setAttribute('data-hash', currentHash);
}

// ====================== EXPORT CSV ======================
function exportCSV() {
    var headers = ['Application ID', 'Application Type', 'Name', 'Doc Type', 'ID Number', 'PAN', 'DOB', 'Address', 'Mobile', 'Email', 'Account Type', 'Risk Score', 'Status', 'Submitted Date', 'Device', 'IP', 'Location'];
    var rows = kycApplications.map(function(a) {
        var appType = a.applicationType === 'RE_KYC' ? 'Re-KYC' : 'KYC';
        var status = a.status.charAt(0).toUpperCase() + a.status.slice(1);
        return [
            'IOB-KYC-' + String(a.id).padStart(5, '0'),
            appType,
            '"' + (a.name || '').replace(/"/g, '""') + '"',
            a.docType,
            a.idNumber,
            a.panNumber,
            a.dob,
            '"' + (a.address || '').replace(/"/g, '""') + '"',
            a.mobile,
            a.email,
            a.accountType,
            a.riskScore,
            status,
            a.date,
            a.device,
            a.ip,
            a.location
        ].join(',');
    });
    var csv = '\uFEFF' + headers.join(',') + '\n' + rows.join('\n');
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'kyc_applications_' + new Date().toISOString().slice(0,10) + '.csv';
    link.click();
    showToast('CSV exported successfully!', 'success');
}



function filterKYC() { lastDataHash = ''; renderDashboard(); }

// ====================== VIEW APPLICATION (Full Details with Photos) ======================
function viewApplication(id) {
    var app = kycApplications.find(function(a) { return a.id === id; });
    if (!app) return;

    var modal = document.getElementById('reviewModal');
    var content = document.getElementById('reviewModalContent');
    if (!modal || !content) return;

    var riskColor = app.riskScore < 30 ? 'var(--success)' : app.riskScore < 60 ? 'var(--warning)' : 'var(--danger)';
    var statusBadgeClass = app.status === 'approved' ? 'badge-success' : app.status === 'rejected' ? 'badge-danger' : 'badge-warning';
    var statusLabel = app.status === 'highrisk' ? 'High Risk' : app.status.charAt(0).toUpperCase() + app.status.slice(1);

    if (app.applicationType === 'RE_KYC' && app.riskScore === 0) {
        var riskOldApp = kycApplications.find(function(a) {
            return a.status === 'approved' && a.applicationType !== 'RE_KYC' && a.name === app.name && a.riskScore > 0;
        });
        if (!riskOldApp) riskOldApp = kycApplications.find(function(a) {
            return a.status === 'approved' && a.name === app.name && a.riskScore > 0;
        });
        if (riskOldApp) {
            app = Object.assign({}, app, { riskScore: riskOldApp.riskScore, faceMatch: riskOldApp.faceMatch, livenessScore: riskOldApp.livenessScore });
            riskColor = app.riskScore < 30 ? 'var(--success)' : app.riskScore < 60 ? 'var(--warning)' : 'var(--danger)';
        }
    }

    var photoSvg = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" fill="%23e2e8f0"><circle cx="60" cy="60" r="60"/><text x="60" y="55" font-family="sans-serif" font-size="36" fill="%23a0aec0" text-anchor="middle">👤</text><text x="60" y="80" font-family="sans-serif" font-size="11" fill="%23a0aec0" text-anchor="middle">No Photo</text></svg>');
    var docNotUploaded = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="260" height="180" fill="%23e2e8f0"><rect width="260" height="180" rx="12"/><text x="130" y="90" font-family="sans-serif" font-size="14" fill="%23a0aec0" text-anchor="middle">Document</text><text x="130" y="112" font-family="sans-serif" font-size="14" fill="%23a0aec0" text-anchor="middle">Not Uploaded</text></svg>');

    var profileImgAppId = app.id;
    if (app.applicationType === 'RE_KYC' && !app.hasPhoto && !app.hasSelfie) {
        var profileOldApp = kycApplications.find(function(a) {
            return a.status === 'approved' && a.applicationType !== 'RE_KYC' && a.name === app.name && (a.hasPhoto || a.hasSelfie);
        });
        if (profileOldApp) profileImgAppId = profileOldApp.id;
    }
    var selfieUrl = ADMIN_API + '/applications/' + profileImgAppId + '/selfie?t=' + Date.now();
    var photoUrl = ADMIN_API + '/applications/' + profileImgAppId + '/photo?t=' + Date.now();

    var profileImg = (app.hasPhoto || (app.applicationType === 'RE_KYC' && profileImgAppId !== app.id))
        ? '<img src="' + photoUrl + '" onerror="this.src=\'' + selfieUrl + '\'" style="width:80px;height:80px;border-radius:50%;object-fit:cover;border:3px solid var(--primary)">'
        : '<img src="' + selfieUrl + '" onerror="this.src=\'' + photoSvg + '\'" style="width:80px;height:80px;border-radius:50%;object-fit:cover;border:3px solid var(--primary)">';

    function docSection(title, url, exists) {
        var img = '<img src="' + url + '" onerror="this.src=\'' + docNotUploaded + '\'" style="width:100%;max-width:320px;height:auto;max-height:200px;border-radius:8px;object-fit:contain;border:2px solid var(--gray-200);cursor:pointer;background:var(--gray-50)" onclick="window.open(this.src,\'_blank\')" title="Click to view full size">';
        return '<h4 style="margin-bottom:8px;color:var(--gray-700);font-size:14px">' + title + '</h4>' +
            '<div style="margin-bottom:16px;padding:12px;background:var(--gray-50,#f8fafc);border-radius:8px;text-align:center">' +
                img +
                '<p style="font-size:11px;color:var(--gray-500);margin-top:6px">' + (exists ? 'Click image to view full size' : 'No document uploaded') + '</p>' +
            '</div>';
    }

    var docSections = '';

    // For RE_KYC: if current app has no docs, find the old approved app's docs
    var docApp = app;
    if (app.applicationType === 'RE_KYC' && !app.hasAadhaarFront && !app.hasAadhaarBack && !app.hasPanCard && !app.hasDoc) {
    var oldApp = kycApplications.find(function(a) {
        return a.status === 'approved' && a.applicationType !== 'RE_KYC' && a.name === app.name && (a.hasAadhaarFront || a.hasPanCard || a.hasPhoto);
    });
    if (!oldApp) oldApp = kycApplications.find(function(a) {
        return a.status === 'approved' && a.name === app.name && (a.hasAadhaarFront || a.hasPanCard || a.hasPhoto);
    });
    if (!oldApp) oldApp = kycApplications.find(function(a) { return a.status === 'approved' && a.applicationType !== 'RE_KYC' && a.name === app.name; });
        if (!oldApp) oldApp = kycApplications.find(function(a) { return a.status === 'approved'; });
        if (oldApp) {
            docApp = {
                id: oldApp.id,
                hasAadhaarFront: oldApp.hasAadhaarFront,
                hasAadhaarBack: oldApp.hasAadhaarBack,
                hasPanCard: oldApp.hasPanCard,
                hasDoc: oldApp.hasDoc,
                docType: oldApp.docType
            };
        }
    }

    var docAppAadhaarFrontUrl = ADMIN_API + '/applications/' + docApp.id + '/aadhaar-front?t=' + Date.now();
    var docAppAadhaarBackUrl = ADMIN_API + '/applications/' + docApp.id + '/aadhaar-back?t=' + Date.now();
    var docAppPanCardUrl = ADMIN_API + '/applications/' + docApp.id + '/pan-card?t=' + Date.now();
    var docAppDocUrl = ADMIN_API + '/applications/' + docApp.id + '/document?t=' + Date.now();

    if (docApp.hasAadhaarFront) {
        docSections += docSection('&#128196; Aadhaar Front', docAppAadhaarFrontUrl, true);
    }
    if (docApp.hasAadhaarBack) {
        docSections += docSection('&#128196; Aadhaar Back', docAppAadhaarBackUrl, true);
    }
    if (docApp.hasPanCard) {
        docSections += docSection('&#128221; PAN Card', docAppPanCardUrl, true);
    }
    if (docApp.hasDoc && !docApp.hasAadhaarFront && !docApp.hasPanCard) {
        docSections += docSection('&#128196; ' + docApp.docType + ' Card', docAppDocUrl, true);
    }
    if (!docApp.hasDoc && !docApp.hasAadhaarFront && !docApp.hasAadhaarBack && !docApp.hasPanCard) {
        docSections += '<p style="text-align:center;color:var(--gray-500);padding:12px;font-size:13px">No documents uploaded</p>';
    }

    if (app.applicationType === 'RE_KYC' && docApp.id !== app.id) {
        docSections = '<p style="font-size:12px;color:var(--primary);margin-bottom:8px">&#128196; Showing documents from previous approved KYC (Ref: IOB-KYC-' + String(docApp.id).padStart(5, '0') + ')</p>' + docSections;
    }

    var selfieSection = '';
    if (app.hasSelfie) {
        selfieSection += '<img src="' + selfieUrl + '" onerror="this.src=\'' + photoSvg + '\'" style="width:100px;height:100px;border-radius:50%;object-fit:cover;border:3px solid var(--primary)">';
    }
    if (app.hasPhoto) {
        selfieSection += '<img src="' + photoUrl + '" onerror="this.style.display=\'none\'" style="width:100px;height:100px;border-radius:8px;object-fit:cover;border:2px solid var(--gray-200)">';
    }
    if (app.hasSelfie || app.hasPhoto) {
        selfieSection += '<div>' +
            '<p style="font-weight:600;font-size:14px">Face Match: ' + (app.faceMatch || 0) + '%</p>' +
            '<p style="font-size:12px;color:var(--gray-500)">Liveness Score: ' + (app.livenessScore || 0) + '%</p>' +
        '</div>';
    }
    if (!selfieSection) {
        selfieSection = '<p style="text-align:center;color:var(--gray-500);padding:12px;font-size:13px">No selfie or photo uploaded</p>';
    }

    content.innerHTML =
        '<div style="display:flex;gap:16px;align-items:center;margin-bottom:20px">' +
            profileImg +
            '<div>' +
                '<h3 style="color:var(--gray-800);margin-bottom:2px">' + app.name + '</h3>' +
                '<p style="color:var(--gray-500);font-size:13px">Application ID: #IOB-KYC-' + String(app.id).padStart(5, '0') + ' &bull; ' + app.date + '</p>' +
                '<span class="badge ' + statusBadgeClass + '">' + statusLabel + '</span>' +
                (app.applicationType === 'RE_KYC' ? ' <span style="background:var(--primary,#1a73e8);color:#fff;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:600">&#128260; Re-KYC</span>' : '') +
            '</div>' +
        '</div>' +

        docSections +

        '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128247; Selfie & Photo</h4>' +
        '<div style="margin-bottom:20px;display:flex;gap:16px;align-items:center;padding:12px;background:var(--gray-50,#f8fafc);border-radius:8px;flex-wrap:wrap">' +
            selfieSection +
        '</div>' +

        '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128196; Document Details</h4>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px;font-size:14px">' +
            '<div class="form-group"><label>Document Type</label><p style="font-weight:600">' + app.docType + ' Card</p></div>' +
            '<div class="form-group"><label>ID Number</label><p style="font-weight:600;font-size:13px">' + (app.idNumber || 'N/A') + '</p></div>' +
            '<div class="form-group"><label>PAN Number</label><p style="font-weight:600;font-size:13px;color:' + (app.panNumber && app.panNumber !== 'N/A' ? 'var(--success)' : 'var(--gray-500)') + '">' + (app.panNumber || 'N/A') + '</p></div>' +
            '<div class="form-group"><label>Date of Birth</label><p style="font-weight:600;font-size:13px">' + (app.dob || 'N/A') + '</p></div>' +
            '<div class="form-group" style="grid-column:1/-1"><label>Address</label><p style="font-weight:600;font-size:13px">' + (app.address || 'N/A') + '</p></div>' +
        '</div>' +

        '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128270; QR Code Verification</h4>' +
        '<div id="qrVerificationSection" style="margin-bottom:20px;padding:16px;background:var(--gray-50,#f8fafc);border-radius:8px;border:1px solid var(--gray-200)">' +
            '<div style="text-align:center;padding:12px"><div class="spinner" style="margin:0 auto 8px"></div><p style="font-size:13px;color:var(--gray-500)">Loading QR verification status...</p></div>' +
        '</div>' +

        (function() {
            var challengeHtml = '';
            var hasVideo = !!(app.challengeVideoBase64);
            var hasResults = !!(app.challengeResults);
            var hasQrFace = !!(app.qrFaceMatchStatus);

            if (!hasVideo && !hasResults && !hasQrFace) return '';

            challengeHtml += '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#127909; Challenge Response Verification</h4>';
            challengeHtml += '<div style="margin-bottom:20px;padding:16px;background:var(--gray-50,#f8fafc);border-radius:8px;border:1px solid var(--gray-200)">';

            // Verification timestamp (server stores UTC, append Z)
            if (app.verificationTimestamp) {
                var vtDate = '';
                try {
                    var tsStr = String(app.verificationTimestamp).trim();
                    if (tsStr.endsWith('Z') || tsStr.endsWith('+00:00')) {
                        var d = new Date(tsStr);
                        vtDate = d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true });
                    } else {
                        var d = new Date(tsStr + 'Z');
                        vtDate = d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: true });
                    }
                } catch(e) { vtDate = app.verificationTimestamp; }
                challengeHtml += '<p style="font-size:12px;color:var(--gray-500);margin:0 0 12px">Verified: ' + vtDate + '</p>';
            }

            // Challenge video player
            if (hasVideo) {
                var vid = app.challengeVideoBase64;
                var vidBlobUrl = null;
                if (vid && vid.indexOf('base64,') !== -1) {
                    try {
                        var parts = vid.split('base64,');
                        var mime = parts[0].replace('data:', '').replace(';', '');
                        var raw = atob(parts[1]);
                        var arr = new Uint8Array(raw.length);
                        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
                        vidBlobUrl = URL.createObjectURL(new Blob([arr], { type: mime }));
                    } catch(e) { vidBlobUrl = vid; }
                } else if (vid) {
                    vidBlobUrl = vid;
                }
                challengeHtml += '<div style="margin-bottom:16px">' +
                    '<p style="font-weight:600;font-size:13px;margin-bottom:8px">&#127909; Challenge Response Video</p>' +
                    '<video id="challengeVideoPlayer_' + app.id + '" controls style="width:100%;max-width:480px;border-radius:8px;border:2px solid var(--gray-200);background:#000" preload="metadata">' +
                        'Your browser does not support video playback.' +
                    '</video>' +
                '</div>';
                setTimeout(function(bUrl) {
                    return function() {
                        var vp = document.getElementById('challengeVideoPlayer_' + app.id);
                        if (vp && bUrl) {
                            vp.src = bUrl;
                        }
                    };
                }(vidBlobUrl), 200);
            }

            // Challenge completion results
            if (hasResults) {
                var results = [];
                try { results = JSON.parse(app.challengeResults); } catch(e) {}
                if (results.length > 0) {
                    challengeHtml += '<div style="margin-bottom:16px">' +
                        '<p style="font-weight:600;font-size:13px;margin-bottom:8px">&#9989; Challenge Completion</p>' +
                        '<div style="display:flex;flex-wrap:wrap;gap:8px">';
                    var challengeNames = { 'blink': 'Blink', 'open_mouth': 'Open Mouth', 'shake_head': 'Shake Head', 'look_left': 'Look Left', 'look_right': 'Look Right', 'look_up': 'Look Up', 'raise_one_hand': 'Raise One Hand', 'raise_both_hands': 'Raise Both Hands' };
                    for (var ci = 0; ci < results.length; ci++) {
                        var r = results[ci];
                        var chName = challengeNames[r.challenge] || r.challenge;
                        var chColor = r.passed ? 'var(--success)' : 'var(--danger)';
                        var chIcon = r.passed ? '&#9989;' : '&#10060;';
                        challengeHtml += '<div style="display:flex;align-items:center;gap:6px;padding:6px 12px;background:#fff;border-radius:6px;border:1px solid ' + chColor + '">' +
                            '<span>' + chIcon + '</span>' +
                            '<span style="font-size:12px;font-weight:600">' + chName + '</span>' +
                        '</div>';
                    }
                    challengeHtml += '</div></div>';
                }
            }

            // QR face match results
            if (hasQrFace) {
                var faceColor = app.qrFaceMatchStatus === 'MATCH' ? 'var(--success)' : (app.qrFaceMatchStatus === 'PARTIAL_MATCH' ? 'var(--warning)' : 'var(--danger)');
                challengeHtml += '<div style="margin-bottom:8px">' +
                    '<p style="font-weight:600;font-size:13px;margin-bottom:8px">&#128100; QR Face vs ID Card Face Comparison</p>' +
                    '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">' +
                        '<div style="padding:10px;background:#fff;border-radius:6px;text-align:center">' +
                            '<p style="font-size:11px;color:var(--gray-500);margin:0">Match Status</p>' +
                            '<p style="font-weight:700;font-size:14px;margin:4px 0 0;color:' + faceColor + '">' + (app.qrFaceMatchStatus || 'N/A') + '</p>' +
                        '</div>' +
                        '<div style="padding:10px;background:#fff;border-radius:6px;text-align:center">' +
                            '<p style="font-size:11px;color:var(--gray-500);margin:0">Match Score</p>' +
                            '<p style="font-weight:700;font-size:14px;margin:4px 0 0">' + (app.qrFaceMatchScore != null ? app.qrFaceMatchScore.toFixed(1) + '%' : 'N/A') + '</p>' +
                        '</div>' +
                        '<div style="padding:10px;background:#fff;border-radius:6px;text-align:center">' +
                            '<p style="font-size:11px;color:var(--gray-500);margin:0">Confidence</p>' +
                            '<p style="font-weight:700;font-size:14px;margin:4px 0 0">' + (app.qrFaceConfidence != null ? (app.qrFaceConfidence * 100).toFixed(1) + '%' : 'N/A') + '</p>' +
                        '</div>' +
                    '</div>' +
                '</div>';
            }

            challengeHtml += '</div>';
            return challengeHtml;
        })() +

        '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128100; Personal Details</h4>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px;font-size:14px">' +
            '<div class="form-group"><label>Mobile</label><p style="font-weight:600">' + (app.mobile || 'N/A') + '</p></div>' +
            '<div class="form-group"><label>Email</label><p style="font-weight:600;font-size:13px">' + (app.email || 'N/A') + '</p></div>' +
            '<div class="form-group"><label>Branch</label><p style="font-weight:600;font-size:13px;color:var(--primary)">' + (app.branchId || 'N/A') + '</p></div>' +
            '<div class="form-group"><label>Account Type</label><p style="font-weight:600;text-transform:capitalize">' + (app.accountType || 'savings') + '</p></div>' +
            '<div class="form-group"><label>Current Status</label><span class="badge ' + statusBadgeClass + '">' + statusLabel + '</span></div>' +
            '<div class="form-group"><label>Gender</label><p style="font-weight:600">' + (app.gender || 'N/A') + '</p></div>' +
        '</div>' +

        (app.rawStatus === 'REJECTED' && app.reviewNotes ? (
            '<div style="margin-bottom:20px;padding:16px;background:rgba(220,38,38,0.05);border:2px solid var(--danger,#dc2626);border-radius:12px">' +
                '<h4 style="margin:0 0 8px;color:var(--danger,#dc2626)">&#10060; Rejection Reason</h4>' +
                '<p style="margin:0;font-size:14px;color:var(--gray-700)">' + app.reviewNotes + '</p>' +
            '</div>'
        ) : '') +
        '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128200; AI Risk Assessment</h4>' +
        '<div class="risk-result-card" style="margin-bottom:20px">' +
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">' +
                '<div class="risk-meter" style="flex:1"><div class="risk-fill" style="width:' + app.riskScore + '%;background:' + riskColor + '"></div></div>' +
                '<span style="font-size:18px;font-weight:800;color:' + riskColor + '">' + app.riskScore + '/100</span>' +
            '</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px">' +
                '<span>IP Reputation:</span><span style="font-weight:600">' + Math.floor(app.riskScore * 0.25) + '/25</span>' +
                '<span>Geolocation Analysis:</span><span style="font-weight:600">' + Math.floor(app.riskScore * 0.2) + '/20</span>' +
                '<span>Face Match Confidence:</span><span style="font-weight:600">' + (app.faceMatch || 0) + '%</span>' +
                '<span>Liveness Score:</span><span style="font-weight:600">' + (app.livenessScore || 0) + '%</span>' +
            '</div>' +
        '</div>' +

        '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128274; Device & Session</h4>' +
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:20px;font-size:14px">' +
            '<div class="form-group"><label>Device</label><p style="font-weight:600;font-size:13px">' + app.device + '</p></div>' +
            '<div class="form-group"><label>IP Address</label><p style="font-weight:600;font-size:13px;color:' + (app.ip && app.ip !== 'N/A' && app.ip !== '0.0.0.0' ? 'var(--gray-800)' : 'var(--gray-500)') + '">' + (app.ip || 'N/A') + '</p></div>' +
            '<div class="form-group" style="grid-column:1/-1"><label>Geolocation</label><p style="font-weight:600;font-size:13px">' + app.location + '</p></div>' +
        '</div>' +

        '<div id="rejectionReasonSection" style="margin-bottom:12px;display:none">' +
            '<div class="form-group">' +
                '<label for="rejectionReason">Rejection Reason</label>' +
                '<textarea id="rejectionReason" rows="3" style="width:100%;padding:10px;border:2px solid var(--gray-300);border-radius:8px;font-size:14px;resize:vertical" placeholder="Enter the reason for rejection..."></textarea>' +
            '</div>' +
        '</div>' +
        '<div style="display:flex;gap:10px;justify-content:flex-end;border-top:1px solid var(--gray-200);padding-top:16px">' +
            (app.applicationType === 'RE_KYC' ? '<button class="btn btn-sm btn-outline" onclick="compareReKyc(' + app.id + ')" style="color:var(--warning);border-color:var(--warning)">&#128260; Compare</button>' : '') +
            ((function() { var u = getUser(); return u && (u.role === 'admin' || u.role === 'manager'); })() ? '<button class="btn btn-sm btn-danger" onclick="rejectApplication(' + app.id + ')">&#10060; Reject</button>' : '') +
            ((function() { var u = getUser(); return u && (u.role === 'admin' || u.role === 'manager'); })() ? '<button class="btn btn-sm btn-success" onclick="approveApplication(' + app.id + ')">&#9989; Approve</button>' : '') +
        '</div>';

    modal.classList.add('active');
    loadQrVerification(app.id);
    // Update modal title based on application type
    var modalTitle = modal.querySelector('.modal-header h2');
    if (modalTitle) {
        modalTitle.textContent = app.applicationType === 'RE_KYC' ? 'Re-KYC Application Details' : 'KYC Application Details';
    }
}

function closeReviewModal() {
    document.getElementById('reviewModal').classList.remove('active');
    var reasonSection = document.getElementById('rejectionReasonSection');
    var reasonField = document.getElementById('rejectionReason');
    if (reasonSection) reasonSection.style.display = 'none';
    if (reasonField) reasonField.value = '';
}

async function approveApplication(id) {
    try {
        const token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        const res = await fetch(ADMIN_API + '/applications/' + id + '/approve', {
            method: 'PUT',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (res.status === 403) { showToast('Access denied - insufficient permissions', 'error'); return; }
        if (res.ok) {
            var app = kycApplications.find(function(a) { return a.id === id; });
            if (app) { app.status = 'approved'; app.rawStatus = 'APPROVED'; }
            showToast('KYC approved', 'success');
        } else {
            showToast('Failed to approve', 'error');
        }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
    renderDashboard(); updateStats(); closeReviewModal();
}

async function rejectApplication(id) {
    var reasonSection = document.getElementById('rejectionReasonSection');
    var reasonField = document.getElementById('rejectionReason');
    if (reasonSection && reasonSection.style.display !== 'block') {
        reasonSection.style.display = 'block';
        if (reasonField) reasonField.focus();
        showToast('Enter a rejection reason and click Reject again', 'info');
        return;
    }
    var notes = (reasonField && reasonField.value.trim()) || 'Rejected by admin';
    try {
        const token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        const res = await fetch(ADMIN_API + '/applications/' + id + '/reject', {
            method: 'PUT',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: notes })
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (res.status === 403) { showToast('Access denied - insufficient permissions', 'error'); return; }
        if (res.ok) {
            var app = kycApplications.find(function(a) { return a.id === id; });
            if (app) { app.status = 'rejected'; app.rawStatus = 'REJECTED'; app.reviewNotes = notes; }
            showToast('KYC rejected', 'warning');
        } else {
            showToast('Failed to reject', 'error');
        }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
    renderDashboard(); updateStats(); closeReviewModal();
}

async function submitForReview(appId) {
    try {
        var token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        
        var res = await fetch(ADMIN_API + '/applications/' + appId + '/approve', {
            method: 'PUT',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        var data = await res.json();
        if (data.success) {
            showToast('Application submitted for review', 'success');
            closeReviewModal();
            loadApplicationsFromAPI();
        } else {
            showToast(data.message || 'Failed to submit', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

// ====================== STATS ======================
async function updateStats() {
    var total = kycApplications.length;
    var approved = kycApplications.filter(function(a) { return a.status === 'approved'; }).length;
    var pending = kycApplications.filter(function(a) { return a.status === 'pending'; }).length;
    var rejected = kycApplications.filter(function(a) { return a.status === 'rejected' || a.status === 'highrisk'; }).length;
    var highRisk = kycApplications.filter(function(a) { return a.riskScore >= 70; }).length;

    document.getElementById('totalApplications').textContent = total;
    document.getElementById('approvedCount').textContent = approved;
    document.getElementById('pendingCount').textContent = pending;
    document.getElementById('rejectedCount').textContent = rejected;
    if (document.getElementById('highRiskCount')) {
        document.getElementById('highRiskCount').textContent = highRisk;
    }
}

// ====================== CHART ======================
function renderChart() {
    var container = document.getElementById('chartContainer') || document.querySelector('.chart-container');
    if (!container) return;

    var periodEl = document.getElementById('chartPeriod');
    var period = periodEl ? periodEl.value : 'week';

    var now = new Date();
    var cutoff = new Date();
    if (period === 'all') {
        cutoff = null;
    } else if (period === 'day') {
        cutoff.setHours(0, 0, 0, 0);
    } else if (period === 'week') {
        cutoff.setDate(now.getDate() - now.getDay());
        cutoff.setHours(0, 0, 0, 0);
    } else {
        cutoff.setDate(1);
        cutoff.setHours(0, 0, 0, 0);
    }

    var periodApps = kycApplications.filter(function(a) {
        if (!a.date || a.date === 'N/A') return false;
        if (!cutoff) return true;
        try {
            var d = new Date(a.date);
            return d >= cutoff;
        } catch(e) { return false; }
    });

    var total = periodApps.length;
    var approved = periodApps.filter(function(a) { return a.status === 'approved'; }).length;
    var pending = periodApps.filter(function(a) { return a.status === 'pending'; }).length;
    var rejected = periodApps.filter(function(a) { return a.status === 'rejected'; }).length;

    var labels = ['Total', 'Approved', 'Pending', 'Rejected'];
    var data = [total, approved, pending, rejected];
    var colors = ['var(--primary, #3b82f6)', 'var(--success, #22c55e)', 'var(--warning, #f59e0b)', 'var(--danger, #ef4444)'];

    if (total === 0) {
        container.innerHTML = '<p style="text-align:center;color:var(--gray-500);padding:20px;font-size:13px">No data for this period</p>';
        return;
    }

    var maxVal = Math.max.apply(null, data);
    container.innerHTML = '<div style="display:flex;align-items:flex-end;gap:16px;justify-content:center;padding:20px 16px;height:300px">' +
        data.map(function(val, i) {
            var height = maxVal > 0 ? Math.max(20, (val / maxVal) * 260) : 20;
            return                 '<div style="display:flex;flex-direction:column;align-items:center;flex:1;max-width:100px">' +
                '<span style="font-size:14px;font-weight:700;color:var(--gray-700);margin-bottom:6px">' + val + '</span>' +
                '<div style="width:100%;height:' + height + 'px;background:' + colors[i] + ';border-radius:6px 6px 0 0;transition:height 0.3s"></div>' +
                '<span style="font-size:12px;color:var(--gray-500);margin-top:6px;text-align:center">' + labels[i] + '</span>' +
            '</div>';
        }).join('') +
    '</div>';
}

// ====================== REVIEW LIST ======================
function loadReviewList() {
    var container = document.getElementById('kycReviewList');
    if (!container) return;

    var pending = kycApplications.filter(function(a) { return a.status === 'pending' || a.status === 'highrisk'; });
    document.getElementById('pendingBadge').textContent = pending.length;

    if (pending.length === 0) {
        container.innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray-500)">No pending applications</p>';
        return;
    }

    container.innerHTML = pending.map(function(app) {
        var riskColor = app.riskScore < 30 ? 'var(--success)' : app.riskScore < 60 ? 'var(--warning)' : 'var(--danger)';
        var selfieUrl = ADMIN_API + '/applications/' + app.id + '/selfie';
        var defaultAvatar = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" fill="%23e2e8f0"><circle cx="24" cy="24" r="24"/><text x="24" y="30" font-family="sans-serif" font-size="20" fill="%23a0aec0" text-anchor="middle">👤</text></svg>');
        return '<div class="kyc-review-card">' +
            '<img src="' + selfieUrl + '" onerror="this.src=\'' + defaultAvatar + '\'" class="review-avatar" style="width:48px;height:48px;border-radius:50%;object-fit:cover;border:2px solid var(--primary)">' +
            '<div class="review-info">' +
                '<h4>' + app.name + '</h4>' +
                '<p>' + app.docType + ' &bull; ' + app.date + ' &bull; IP: ' + app.ip + '</p>' +
            '</div>' +
            '<div style="text-align:right;margin-right:12px">' +
                '<div style="font-size:20px;font-weight:700;color:' + riskColor + '">' + app.riskScore + '</div>' +
                '<small style="color:var(--gray-500)">Risk Score</small>' +
            '</div>' +
            '<div class="review-actions">' +
                ((function() { var u = getUser(); return u && (u.role === 'admin' || u.role === 'manager'); })() ? '<button class="btn btn-sm btn-success" onclick="quickApprove(' + app.id + ')">&#10003;</button>' : '') +
                '<button class="btn btn-sm btn-warning" onclick="viewApplication(' + app.id + ')">&#128065;</button>' +
                ((function() { var u = getUser(); return u && (u.role === 'admin' || u.role === 'manager'); })() ? '<button class="btn btn-sm btn-danger" onclick="quickReject(' + app.id + ')">&#10007;</button>' : '') +
            '</div>' +
        '</div>';
    }).join('');
}

async function quickApprove(id) {
    try {
        const token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        const res = await fetch(ADMIN_API + '/applications/' + id + '/approve', {
            method: 'PUT',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (res.status === 403) { showToast('Access denied - insufficient permissions', 'error'); return; }
        if (res.ok) {
            var app = kycApplications.find(function(a) { return a.id === id; });
            if (app) { app.status = 'approved'; app.rawStatus = 'APPROVED'; }
            showToast((app ? app.name : 'Application') + ' approved', 'success');
        } else {
            var err = await res.json().catch(function(){ return {}; });
            showToast('Approve failed: ' + (err.message || 'Unknown error'), 'error');
        }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
    loadReviewList(); updateStats();
}

async function quickReject(id) {
    var reason = prompt('Enter rejection reason:');
    if (reason === null) return;
    if (!reason.trim()) reason = 'Rejected by admin';
    try {
        const token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        const res = await fetch(ADMIN_API + '/applications/' + id + '/reject', {
            method: 'PUT',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: reason.trim() })
        });
        if (res.status === 401) { handleAuthError(); return; }
        if (res.status === 403) { showToast('Access denied - insufficient permissions', 'error'); return; }
        if (res.ok) {
            var app = kycApplications.find(function(a) { return a.id === id; });
            if (app) { app.status = 'rejected'; app.rawStatus = 'REJECTED'; app.reviewNotes = reason.trim(); }
            showToast((app ? app.name : 'Application') + ' rejected', 'info');
        } else {
            var err = await res.json().catch(function(){ return {}; });
            showToast('Reject failed: ' + (err.message || 'Unknown error'), 'error');
        }
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
    loadReviewList(); updateStats();
}

// Cleanup interval on page unload
window.addEventListener('beforeunload', function() {
    if (refreshInterval) clearInterval(refreshInterval);
});

// ====================== RE-KYC: DOWNLOAD PDF ======================
async function downloadAdminPdf(id) {
    var token = getAuthToken();
    if (!token) { checkAdminAuth(); return; }
    try {
        var res = await fetch(ADMIN_API + '/applications/' + id + '/pdf', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!res.ok) throw new Error('Download failed');
        var blob = await res.blob();
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'KYC_Application_' + id + '.pdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('PDF downloaded successfully', 'success');
    } catch (e) {
        showToast('Failed to download PDF: ' + e.message, 'error');
    }
}

// ====================== RE-KYC: COMPARE OLD VS NEW ======================
async function compareReKyc(id) {
    var token = getAuthToken();
    if (!token) { checkAdminAuth(); return; }

    var app = kycApplications.find(function(a) { return a.id === id; });
    if (!app || app.applicationType !== 'RE_KYC') {
        showToast('Comparison is only available for Re-KYC applications', 'info');
        return;
    }

    var oldApp = kycApplications.find(function(a) {
        return a.status === 'approved' && a.applicationType !== 'RE_KYC' && a.name === app.name && (a.hasAadhaarFront || a.hasPanCard || a.hasPhoto);
    });
    if (!oldApp) oldApp = kycApplications.find(function(a) {
        return a.status === 'approved' && a.name === app.name && (a.hasAadhaarFront || a.hasPanCard || a.hasPhoto);
    });
    if (!oldApp) oldApp = kycApplications.find(function(a) { return a.status === 'approved' && a.applicationType !== 'RE_KYC' && a.name === app.name; });
    if (!oldApp) oldApp = kycApplications.find(function(a) { return a.status === 'approved' && a.applicationType !== 'RE_KYC'; });
    if (!oldApp) {
        showToast('No approved application found to compare against', 'error');
        return;
    }

    showToast('Loading comparison...', 'info');

    try {
        var res = await fetch(ADMIN_API + '/applications/' + oldApp.id + '/compare/' + id, {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!res.ok) {
            showToast('Could not load comparison data', 'error');
            return;
        }
        var data = await res.json();
        var oldData = data.old;
        var newData = data.new;
        var changes = data.changes;

        if (!oldData.mobile && oldApp.mobile && oldApp.mobile !== 'N/A') oldData.mobile = oldApp.mobile;
        if (!oldData.email && oldApp.email && oldApp.email !== 'N/A') oldData.email = oldApp.email;
        if (!newData.mobile && app.mobile && app.mobile !== 'N/A') newData.mobile = app.mobile;
        if (!newData.email && app.email && app.email !== 'N/A') newData.email = app.email;

        changes.mobile = (oldData.mobile || '') !== (newData.mobile || '');
        changes.email = (oldData.email || '') !== (newData.email || '');
        changes.hasChanges = changes.name || changes.dob || changes.idNumber || changes.panNumber || changes.address || changes.mobile || changes.email;

        var fields = [
            { key: 'ocrName', label: 'Full Name' },
            { key: 'ocrDob', label: 'Date of Birth' },
            { key: 'ocrIdNumber', label: 'Aadhaar Number' },
            { key: 'ocrPanNumber', label: 'PAN Number' },
            { key: 'ocrAddress', label: 'Address' },
            { key: 'mobile', label: 'Mobile' },
            { key: 'email', label: 'Email' }
        ];

        var changeMap = { ocrName: changes.name, ocrDob: changes.dob, ocrIdNumber: changes.idNumber, ocrPanNumber: changes.panNumber, ocrAddress: changes.address, mobile: changes.mobile, email: changes.email };

        var fmtDate = function(v) {
            if (!v) return '--';
            try { var d = new Date(v); return d.toLocaleDateString('en-IN', {day:'2-digit',month:'short',year:'numeric'}); } catch(e) { return v; }
        };

        var rows = fields.map(function(f) {
            var oldVal = f.key === 'ocrDob' ? fmtDate(oldData[f.key]) : (oldData[f.key] || '--');
            var newVal = f.key === 'ocrDob' ? fmtDate(newData[f.key]) : (newData[f.key] || '--');
            if (oldVal === '--' && newVal !== '--') oldVal = '<span style="color:var(--gray-400);font-style:italic">empty</span>';
            if (newVal === '--' && oldVal !== '--') newVal = '<span style="color:var(--gray-400);font-style:italic">empty</span>';
            var changed = changeMap[f.key];
            var bg = changed ? 'rgba(245,158,11,0.08)' : '';
            var mark = changed ? ' <span style="color:var(--warning);font-size:11px;font-weight:700">CHANGED</span>' : '';
            return '<tr style="background:' + bg + '">' +
                '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-weight:600;font-size:13px;color:var(--gray-700)">' + f.label + '</td>' +
                '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-size:13px">' + oldVal + '</td>' +
                '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-size:13px">' + newVal + mark + '</td>' +
            '</tr>';
        }).join('');

        var modal = document.getElementById('reviewModal');
        var content = document.getElementById('reviewModalContent');
        if (!modal || !content) return;

        var changedCount = Object.keys(changeMap).filter(function(k){return changeMap[k];}).length;
        var totalFields = fields.length;

        var oldImgBase = ADMIN_API + '/applications/' + oldApp.id;
        var newImgBase = ADMIN_API + '/applications/' + id;
        var noImgSvg = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="140" fill="%23e2e8f0"><rect width="200" height="140" rx="8"/><text x="100" y="75" font-family="sans-serif" font-size="13" fill="%23a0aec0" text-anchor="middle">No Document</text></svg>');

        var docTypes = [
            { key: 'aadhaarFront', label: 'Aadhaar Front', api: 'aadhaar-front' },
            { key: 'panCard', label: 'PAN Card', api: 'pan-card' },
            { key: 'photo', label: 'Photo', api: 'photo' }
        ];

        var docCompareHtml = '<div style="margin-top:20px">' +
            '<h4 style="margin-bottom:12px;color:var(--gray-700)">&#128196; Document Comparison</h4>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">';

        docTypes.forEach(function(dt) {
            var oldHasField = 'has' + dt.key.charAt(0).toUpperCase() + dt.key.slice(1);
            var oldUrl = oldImgBase + '/' + dt.api + '?t=' + Date.now();
            var newUrl = newImgBase + '/' + dt.api + '?t=' + Date.now();
            docCompareHtml +=
                '<div style="border:1px solid var(--gray-200);border-radius:8px;overflow:hidden">' +
                    '<div style="padding:6px 10px;background:var(--gray-50);border-bottom:1px solid var(--gray-200);font-size:12px;font-weight:600;color:var(--gray-600)">' + dt.label + '</div>' +
                    '<div style="display:grid;grid-template-columns:1fr 1fr">' +
                        '<div style="padding:8px;text-align:center;border-right:1px solid var(--gray-200)">' +
                            '<small style="color:var(--gray-500);font-size:10px;display:block;margin-bottom:4px">Previous</small>' +
                            '<img src="' + oldUrl + '" onerror="this.src=\'' + noImgSvg + '\'" style="max-width:100%;max-height:120px;border-radius:4px;object-fit:contain;cursor:pointer" onclick="window.open(this.src,\'_blank\')" title="Click to view full size">' +
                        '</div>' +
                        '<div style="padding:8px;text-align:center">' +
                            '<small style="color:var(--gray-500);font-size:10px;display:block;margin-bottom:4px">Updated</small>' +
                            '<img src="' + newUrl + '" onerror="this.src=\'' + noImgSvg + '\'" style="max-width:100%;max-height:120px;border-radius:4px;object-fit:contain;cursor:pointer" onclick="window.open(this.src,\'_blank\')" title="Click to view full size">' +
                        '</div>' +
                    '</div>' +
                '</div>';
        });

        docCompareHtml += '</div></div>';

        // Modal title
        var modalTitle = modal.querySelector('.modal-header h2');
        if (modalTitle) modalTitle.textContent = 'Re-KYC Comparison';

        content.innerHTML =
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">' +
                '<div style="font-size:28px">&#128260;</div>' +
                '<div>' +
                    '<h3 style="margin:0;color:var(--gray-800)">Re-KYC Comparison</h3>' +
                    '<p style="color:var(--gray-500);font-size:13px;margin:2px 0 0">Old: IOB-KYC-' + String(oldApp.id).padStart(5, '0') + ' &rarr; New: IOB-KYC-' + String(id).padStart(5, '0') + '</p>' +
                '</div>' +
            '</div>' +
            '<div style="margin-bottom:16px;padding:12px;border-radius:8px;background:' + (changes.hasChanges ? 'rgba(245,158,11,0.1)' : 'rgba(16,185,129,0.1)') + ';border:1px solid ' + (changes.hasChanges ? 'rgba(245,158,11,0.3)' : 'rgba(16,185,129,0.3)') + '">' +
                '<strong style="color:' + (changes.hasChanges ? 'var(--warning)' : 'var(--success)') + '">' +
                    (changes.hasChanges ? '&#9888; Changes detected in ' + changedCount + ' of ' + totalFields + ' field(s)' : '&#9989; No changes detected') +
                '</strong>' +
            '</div>' +
            '<h4 style="margin-bottom:8px;color:var(--gray-700)">&#128196; Personal Details</h4>' +
            '<div style="overflow-x:auto">' +
                '<table style="width:100%;border-collapse:collapse;font-size:14px">' +
                    '<thead><tr style="background:var(--gray-100,#f1f5f9)">' +
                        '<th style="padding:10px 12px;text-align:left;border-bottom:2px solid var(--gray-300);font-size:12px;color:var(--gray-600);width:25%">Field</th>' +
                        '<th style="padding:10px 12px;text-align:left;border-bottom:2px solid var(--gray-300);font-size:12px;color:var(--gray-600);width:37.5%">Previous Value</th>' +
                        '<th style="padding:10px 12px;text-align:left;border-bottom:2px solid var(--gray-300);font-size:12px;color:var(--gray-600);width:37.5%">Updated Value</th>' +
                    '</tr></thead>' +
                    '<tbody>' + rows + '</tbody>' +
                '</table>' +
            '</div>' +
            docCompareHtml +
            '<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px;padding-top:16px;border-top:1px solid var(--gray-200)">' +
                '<button class="btn btn-sm btn-outline" onclick="closeReviewModal()">Close</button>' +
            '</div>';

        modal.classList.add('active');
    } catch (e) {
        showToast('Error loading comparison: ' + e.message, 'error');
    }
}

function showCreateAccountModal() {
    document.getElementById('createAccountModal').classList.add('active');
}

function closeCreateAccountModal() {
    document.getElementById('createAccountModal').classList.remove('active');
    document.getElementById('caFirstName').value = '';
    document.getElementById('caLastName').value = '';
    document.getElementById('caEmail').value = '';
    document.getElementById('caPhone').value = '';
    document.getElementById('caPassword').value = '';
}

async function createEmployeeAccount() {
    var firstName = document.getElementById('caFirstName').value.trim();
    var lastName = document.getElementById('caLastName').value.trim();
    var email = document.getElementById('caEmail').value.trim();
    var phone = document.getElementById('caPhone').value.trim();
    var role = document.getElementById('caRole').value;
    var branchId = document.getElementById('caBranchId').value.trim();
    var password = document.getElementById('caPassword').value;

    if (!firstName || !email || !password) {
        showToast('First name, email, and password are required', 'error');
        return;
    }
    if (password.length < 8) {
        showToast('Password must be at least 8 characters', 'error');
        return;
    }

    try {
        var token = getAuthToken();
        var res = await fetch(ADMIN_API + '/create-account', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify({ firstName: firstName, lastName: lastName, email: email, phone: phone, role: role, branchId: branchId, password: password })
        });
        var data = await res.json();
        if (data.success) {
            showToast(role + ' account created! Employee ID: ' + data.employeeId, 'success');
            closeCreateAccountModal();
        } else {
            showToast(data.message || 'Failed to create account', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

// ====================== QR CODE VERIFICATION ======================
async function loadQrVerification(appId) {
    var container = document.getElementById('qrVerificationSection');
    if (!container) return;

    try {
        var token = getAuthToken();
        if (!token) return;

        var res = await fetch(ADMIN_API + '/applications/' + appId + '/qr-verify', {
            headers: { 'Authorization': 'Bearer ' + token }
        });

        if (!res.ok) {
            container.innerHTML = renderQrNotPerformed(appId);
            return;
        }

        var data = await res.json();
        if (data.results && data.verificationStatus) {
            container.innerHTML = renderQrResult(data, appId);
        } else if (data.verificationStatus === 'SKIPPED') {
            container.innerHTML = renderQrResult(data, appId);
        } else {
            container.innerHTML = '<div style="text-align:center;padding:16px"><div class="spinner" style="margin:0 auto 8px"></div><p style="font-size:13px;color:var(--gray-500)">Scanning QR code and comparing fields...</p></div>';
            triggerQrVerification(appId);
        }
    } catch (e) {
        triggerQrVerification(appId);
    }
}

function renderQrNotPerformed(appId) {
    return '<div style="text-align:center;padding:12px">' +
        '<p style="font-size:14px;color:var(--gray-600);margin-bottom:12px">&#9888; QR verification has not been performed yet</p>' +
        '<button class="btn btn-sm btn-primary" onclick="triggerQrVerification(' + appId + ')" id="qrVerifyBtn_' + appId + '" style="padding:8px 16px;border-radius:6px;font-size:13px;cursor:pointer">' +
            '&#128270; Run QR Verification' +
        '</button>' +
        '<p style="font-size:11px;color:var(--gray-500);margin-top:8px">This will scan the document QR code and compare with OCR data</p>' +
    '</div>';
}

function renderQrResult(data, appId) {
    var status = data.verificationStatus || 'SKIPPED';
    var isDetected = data.qrDetected || false;
    var matchPct = data.matchPercentage || 0;

    var statusColors = {
        'PASSED': { bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.3)', text: 'var(--success)', icon: '&#9989;' },
        'FAILED': { bg: 'rgba(220,38,38,0.1)', border: 'rgba(220,38,38,0.3)', text: 'var(--danger)', icon: '&#10060;' },
        'SKIPPED': { bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.3)', text: 'var(--warning)', icon: '&#9888;' }
    };
    var sc = statusColors[status] || statusColors['SKIPPED'];

    var statusLabel = status === 'PASSED' ? 'QR Verification Passed' : status === 'FAILED' ? 'QR Verification Failed' : 'QR Verification Skipped';

    var detectionBadge = isDetected
        ? '<span style="background:rgba(16,185,129,0.15);color:var(--success);padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600">&#9989; Detected</span>'
        : '<span style="background:rgba(245,158,11,0.15);color:var(--warning);padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600">&#9888; Not Detected</span>';

    var headerHtml = '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">' +
        '<div style="display:flex;align-items:center;gap:10px">' +
            '<span style="font-size:20px">' + sc.icon + '</span>' +
            '<div>' +
                '<div style="font-weight:700;font-size:15px;color:' + sc.text + '">' + statusLabel + '</div>' +
                '<div style="font-size:12px;color:var(--gray-500)">QR Detection: ' + detectionBadge + ' &bull; Match: ' + matchPct + '%</div>' +
            '</div>' +
        '</div>' +
        '<button class="btn btn-sm btn-outline" onclick="triggerQrVerification(' + appId + ')" id="qrVerifyBtn_' + appId + '" style="font-size:12px;padding:6px 12px;border-radius:6px;cursor:pointer">&#128260; Re-run</button>' +
    '</div>';

    var results = data.results || {};
    var fieldRows = '';

    var fieldConfig = [
        { key: 'name', label: 'Name' },
        { key: 'dob', label: 'Date of Birth' }
    ];
    var docType = (data.documentType || '').toLowerCase();
    fieldConfig.push({ key: 'aadhaar_number', label: 'Aadhaar Number' });
    fieldConfig.push({ key: 'pan_number', label: 'PAN Number' });

    for (var i = 0; i < fieldConfig.length; i++) {
        var f = fieldConfig[i];
        var r = results[f.key] || {};
        var ocrVal = r.ocr || '--';
        var qrVal = r.qr || '--';
        if (f.key === 'dob') {
            if (ocrVal && ocrVal !== '--') ocrVal = ocrVal.replace(/T\d{2}:\d{2}(:\d{2})?$/, '').substring(0, 10);
            if (qrVal && qrVal !== '--') qrVal = qrVal.replace(/T\d{2}:\d{2}(:\d{2})?$/, '').substring(0, 10);
        }
        var match = r.match || false;
        var matchIcon = match ? '<span style="color:var(--success);font-weight:700">&#10004; Yes</span>' : '<span style="color:var(--danger);font-weight:700">&#10008; No</span>';
        var rowBg = match ? '' : 'background:rgba(220,38,38,0.03)';

        fieldRows += '<tr style="' + rowBg + '">' +
            '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-weight:600;font-size:13px;color:var(--gray-700);width:25%">' + f.label + '</td>' +
            '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-size:13px;color:var(--gray-600)">' + ocrVal + '</td>' +
            '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);font-size:13px;color:var(--gray-600)">' + qrVal + '</td>' +
            '<td style="padding:10px 12px;border-bottom:1px solid var(--gray-200);text-align:center">' + matchIcon + '</td>' +
        '</tr>';
    }

    var fieldTable = '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px">' +
        '<thead><tr style="background:var(--gray-100,#f1f5f9)">' +
            '<th style="padding:8px 12px;text-align:left;font-size:12px;color:var(--gray-600);font-weight:600">Field</th>' +
            '<th style="padding:8px 12px;text-align:left;font-size:12px;color:var(--gray-600);font-weight:600">OCR Value</th>' +
            '<th style="padding:8px 12px;text-align:left;font-size:12px;color:var(--gray-600);font-weight:600">QR Value</th>' +
            '<th style="padding:8px 12px;text-align:center;font-size:12px;color:var(--gray-600);font-weight:600">Match</th>' +
        '</tr></thead>' +
        '<tbody>' + fieldRows + '</tbody>' +
    '</table>';

    var timestamp = '';
    if (data.verifiedAt) {
        try {
            var dtStr = String(data.verifiedAt).trim();
            var dt = new Date(dtStr.endsWith('Z') || dtStr.endsWith('+00:00') ? dtStr : dtStr + 'Z');
            timestamp = dt.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true });
        } catch(e) { timestamp = data.verifiedAt; }
    }

    var timestampHtml = timestamp ? '<p style="font-size:11px;color:var(--gray-500);margin:0">Verified at: ' + timestamp + '</p>' : '';

    var rawDataHtml = '';
    if (data.qrRawData) {
        rawDataHtml = '<details style="margin-top:8px"><summary style="font-size:11px;color:var(--gray-500);cursor:pointer">QR Raw Data (first 500 chars)</summary>' +
            '<pre style="font-size:10px;color:var(--gray-600);background:var(--gray-100,#f1f5f9);padding:8px;border-radius:4px;margin-top:4px;white-space:pre-wrap;word-break:break-all;max-height:120px;overflow:auto">' + (data.qrRawData || '').replace(/</g, '&lt;') + '</pre></details>';
    }

    return '<div style="padding:4px">' +
        headerHtml +
        '<div style="padding:12px;border:1px solid ' + sc.border + ';border-radius:8px;background:' + sc.bg + ';margin-bottom:12px">' +
            fieldTable +
        '</div>' +
        timestampHtml +
        rawDataHtml +
    '</div>';
}

async function triggerQrVerification(appId) {
    var btn = document.getElementById('qrVerifyBtn_' + appId);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '&#8987; Verifying...';
    }

    var container = document.getElementById('qrVerificationSection');
    if (container) {
        container.innerHTML = '<div style="text-align:center;padding:16px"><div class="spinner" style="margin:0 auto 8px"></div><p style="font-size:13px;color:var(--gray-500)">Scanning QR code and comparing fields...</p></div>';
    }

    try {
        var token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }

        var res = await fetch(ADMIN_API + '/applications/' + appId + '/qr-verify', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token }
        });

        var data = await res.json();
        if (data.success) {
            lastDataHash = '';
            await loadApplicationsFromAPI();
            if (data.results && data.verificationStatus) {
                if (container) {
                    container.innerHTML = renderQrResult(data, appId);
                }
                showToast('QR verification completed: ' + (data.verificationStatus || 'Unknown'), data.verificationStatus === 'PASSED' ? 'success' : data.verificationStatus === 'FAILED' ? 'error' : 'info');
            } else {
                var getRes = await fetch(ADMIN_API + '/applications/' + appId + '/qr-verify', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (getRes.ok) {
                    var getResult = await getRes.json();
                    if (getResult.results && getResult.verificationStatus) {
                        if (container) {
                            container.innerHTML = renderQrResult(getResult, appId);
                        }
                        showToast('QR verification completed: ' + (getResult.verificationStatus || 'Unknown'), getResult.verificationStatus === 'PASSED' ? 'success' : getResult.verificationStatus === 'FAILED' ? 'error' : 'info');
                        return;
                    }
                }
                var status = data.status || 'Unknown';
                if (container) {
                    container.innerHTML = '<div style="text-align:center;padding:12px"><p style="font-size:13px;color:var(--success)">QR verification completed: ' + status + '</p>' +
                        '<button class="btn btn-sm btn-outline" onclick="loadQrVerification(' + appId + ')" style="margin-top:8px;font-size:12px;padding:6px 12px;cursor:pointer">&#128260; Refresh</button></div>';
                }
                showToast('QR verification completed: ' + status, status === 'PASSED' ? 'success' : status === 'FAILED' ? 'error' : 'info');
            }
        } else {
            if (container) {
                container.innerHTML = '<div style="text-align:center;padding:12px"><p style="font-size:13px;color:var(--danger)">&#10060; ' + (data.message || 'Verification failed') + '</p>' +
                    '<button class="btn btn-sm btn-outline" onclick="triggerQrVerification(' + appId + ')" style="margin-top:8px;font-size:12px;padding:6px 12px;cursor:pointer">&#128260; Retry</button></div>';
            }
            showToast('QR verification failed', 'error');
        }
    } catch (e) {
        if (container) {
            container.innerHTML = '<div style="text-align:center;padding:12px"><p style="font-size:13px;color:var(--danger)">&#10060; Error: ' + e.message + '</p>' +
                '<button class="btn btn-sm btn-outline" onclick="triggerQrVerification(' + appId + ')" style="margin-top:8px;font-size:12px;padding:6px 12px;cursor:pointer">&#128260; Retry</button></div>';
        }
        showToast('QR verification error: ' + e.message, 'error');
    }
}

// ====================== RESET PASSWORD ======================
function showResetPasswordModal() {
    var modal = document.getElementById('resetPasswordModal');
    if (modal) {
        modal.classList.add('active');
        loadEmployeesForReset();
    }
}

function closeResetPasswordModal() {
    var modal = document.getElementById('resetPasswordModal');
    if (modal) modal.classList.remove('active');
}

async function loadEmployeesForReset() {
    var select = document.getElementById('rpEmployeeId');
    if (!select) return;
    try {
        var token = getAuthToken();
        if (!token) return;
        var res = await fetch(ADMIN_API + '/employees', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (!res.ok) return;
        var employees = await res.json();
        select.innerHTML = '<option value="">-- Select Employee --</option>' +
            employees.filter(function(e) { return e.isActive !== false; }).map(function(e) {
                return '<option value="' + e.employeeId + '">' + e.employeeId + ' - ' + e.name + ' (' + (e.role || '').toLowerCase() + ')</option>';
            }).join('');
    } catch (e) {
        select.innerHTML = '<option value="">Failed to load employees</option>';
    }
}

async function resetEmployeePassword() {
    var employeeId = document.getElementById('rpEmployeeId').value;
    var newPassword = document.getElementById('rpNewPassword').value;
    var confirmPassword = document.getElementById('rpConfirmPassword').value;

    if (!employeeId) { showToast('Select an employee', 'error'); return; }
    if (!newPassword || newPassword.length < 12) { showToast('Password must be at least 12 characters', 'error'); return; }
    if (newPassword !== confirmPassword) { showToast('Passwords do not match', 'error'); return; }

    try {
        var token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }
        var res = await fetch(ADMIN_API + '/reset-password', {
            method: 'PUT',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify({ employeeId: employeeId, newPassword: newPassword })
        });
        var data = await res.json();
        if (res.ok && data.success) {
            showToast('Password reset successfully for ' + employeeId, 'success');
            closeResetPasswordModal();
            document.getElementById('rpNewPassword').value = '';
            document.getElementById('rpConfirmPassword').value = '';
        } else {
            showToast(data.message || 'Failed to reset password', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

async function deleteAllKycData() {
    if (!confirm('WARNING: This will permanently delete ALL KYC applications, QR verification results, fraud alerts, and uploaded files. This cannot be undone.\n\nAre you sure you want to continue?')) return;
    if (!confirm('This is your LAST CHANCE. All data will be permanently deleted. Continue?')) return;

    try {
        var token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }

        showToast('Deleting all KYC data...', 'info');
        var res = await fetch(ADMIN_API + '/delete-all-kyc', {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        var data = await res.json();
        if (res.ok && data.success) {
            showToast('All KYC data deleted: ' + data.deletedApplications + ' applications, ' + data.deletedQrResults + ' QR results, ' + data.deletedFraudAlerts + ' fraud alerts', 'success');
            kycApplications = [];
            loadReviewList();
            refreshDashboard();
        } else {
            showToast(data.message || 'Failed to delete data', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

async function deleteKycApplication(id) {
    var app = kycApplications.find(function(a) { return a.id === id; });
    var appName = app ? app.name : 'this application';
    if (!confirm('Delete application for "' + appName + '" (ID: IOB-KYC-' + String(id).padStart(5, '0') + ')?\n\nThis will permanently remove all data and uploaded files. This cannot be undone.')) return;

    try {
        var token = getAuthToken();
        if (!token) { checkAdminAuth(); return; }

        showToast('Deleting application...', 'info');
        var res = await fetch(ADMIN_API + '/applications/' + id, {
            method: 'DELETE',
            headers: { 'Authorization': 'Bearer ' + token }
        });
        var data = await res.json();
        if (res.ok && data.success) {
            showToast('Application deleted successfully', 'success');
            kycApplications = kycApplications.filter(function(a) { return a.id !== id; });
            renderDashboard();
            refreshDashboard();
        } else {
            showToast(data.message || 'Failed to delete application', 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
}

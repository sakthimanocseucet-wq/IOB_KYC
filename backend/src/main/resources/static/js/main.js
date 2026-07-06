// ====================== AUTH STORAGE (Tab-Isolated) ======================
// Uses sessionStorage as primary (isolated per tab) with localStorage backup
// for persistence across browser close/reopen. This prevents one tab from
// destroying another tab's auth state.

function setAuthData(token, userObj) {
    sessionStorage.setItem('authToken', token);
    sessionStorage.setItem('user', JSON.stringify(userObj));
    localStorage.setItem('authTokenBackup', token);
    localStorage.setItem('userBackup', JSON.stringify(userObj));
}

function getAuthToken() {
    var t = sessionStorage.getItem('authToken');
    if (t) return t;
    var backup = localStorage.getItem('authTokenBackup');
    if (backup) {
        sessionStorage.setItem('authToken', backup);
        return backup;
    }
    return null;
}

function getUser() {
    var u = sessionStorage.getItem('user');
    if (u) {
        try { return JSON.parse(u); } catch(e) { return null; }
    }
    var backup = localStorage.getItem('userBackup');
    if (backup) {
        try {
            var parsed = JSON.parse(backup);
            sessionStorage.setItem('user', backup);
            return parsed;
        } catch(e) { return null; }
    }
    return null;
}

function clearAuthData() {
    sessionStorage.removeItem('authToken');
    sessionStorage.removeItem('user');
    localStorage.removeItem('authTokenBackup');
    localStorage.removeItem('userBackup');
}

function isLoggedIn() {
    return !!getAuthToken();
}

// ====================== TOAST ======================
function showToast(message, type) {
    type = type || 'success';
    var container = document.getElementById('toastContainer');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    var icons = { success: '\u2713', error: '\u2717', warning: '\u26A0', info: '\u2139' };
    var titles = { success: 'Success', error: 'Error', warning: 'Warning', info: 'Info' };
    toast.innerHTML =
        '<div class="toast-icon">' + (icons[type] || '') + '</div>' +
        '<div class="toast-body">' +
            '<div class="toast-title">' + (titles[type] || 'Notification') + '</div>' +
            '<div class="toast-message">' + message + '</div>' +
        '</div>' +
        '<button class="toast-close" onclick="dismissToast(this.parentElement)">&times;</button>' +
        '<div class="toast-progress"></div>';
    container.appendChild(toast);
    setTimeout(function() { dismissToast(toast); }, 4000);
}
function dismissToast(toast) {
    if (!toast || toast.classList.contains('toast-exit')) return;
    toast.classList.add('toast-exit');
    setTimeout(function() { toast.remove(); }, 300);
}

// Loading state
function setLoading(btnId, spinnerId, textId, loading) {
    var btn = document.getElementById(btnId);
    var spinner = document.getElementById(spinnerId);
    var text = document.getElementById(textId);
    if (!btn) return;
    btn.disabled = loading;
    if (spinner) spinner.style.display = loading ? 'block' : 'none';
    if (text) text.style.display = loading ? 'none' : 'inline';
}

// Toggle password visibility
function togglePassword(id) {
    var input = document.getElementById(id);
    if (input) input.type = input.type === 'password' ? 'text' : 'password';
}

// Mobile menu toggle
function toggleMobileMenu() {
    var nav = document.getElementById('navLinks');
    var navRight = nav ? nav.parentElement : null;
    if (navRight && navRight.classList.contains('nav-right')) {
        navRight.classList.toggle('active');
    } else if (nav) {
        nav.classList.toggle('active');
    }
}

// Session timeout (24 hours) — only affects THIS tab
var sessionTimer;
var SESSION_TIMEOUT = 24 * 60 * 60 * 1000;
function resetSessionTimer() {
    clearTimeout(sessionTimer);
    sessionTimer = setTimeout(function() {
        clearAuthData();
        var loginPath = window.location.pathname.includes('/admin/') ? '../admin/login.html' : '../user/login.html';
        window.location.href = loginPath;
    }, SESSION_TIMEOUT);
}
resetSessionTimer();
document.addEventListener('click', resetSessionTimer);
document.addEventListener('keypress', resetSessionTimer);
document.addEventListener('mousemove', resetSessionTimer);
document.addEventListener('scroll', resetSessionTimer);
document.addEventListener('touchstart', resetSessionTimer);

// Dark mode toggle
function toggleDarkMode() {
    document.body.classList.toggle('dark-mode');
    var isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem('darkMode', isDark);
}

// Load dark mode preference
(function() {
    if (localStorage.getItem('darkMode') === 'true') {
        document.body.classList.add('dark-mode');
    }
})();

// Animate counters on scroll
function animateCounter(el) {
    var target = parseInt(el.getAttribute('data-target'));
    if (!target) return;
    var current = 0;
    var increment = Math.ceil(target / 60);
    var timer = setInterval(function() {
        current += increment;
        if (current >= target) { current = target; clearInterval(timer); }
        el.textContent = current + (target === 99.9 ? '%' : '+');
    }, 25);
}

// Intersection Observer for animations
var observerOptions = { threshold: 0.05, rootMargin: '0px 0px -20px 0px' };
var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
        if (entry.isIntersecting) {
            entry.target.classList.add('animate-visible');
            if (entry.target.classList.contains('stat-number')) animateCounter(entry.target);
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.fade-in, .slide-up, .scale-in').forEach(function(el) {
        el.classList.add('animate-ready');
        observer.observe(el);
    });
    document.querySelectorAll('.stat-number').forEach(function(el) { observer.observe(el); });
});

// Format date
function formatDate(date) {
    return new Date(date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

// Get initial for avatar
function getInitial(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
}

// ====================== SWIPE NAVIGATION ======================
(function() {
    var userPages = ['dashboard.html', 'kyc.html', 'kyc-status.html'];
    var adminPages = ['dashboard.html', 'kyc-review.html', 'account-details.html'];
    var SWIPE_THRESHOLD = 80;
    var SWIPE_MAX_Y = 60;
    var startX = 0, startY = 0, swiping = false;

    function getPageList() {
        var path = window.location.pathname;
        if (path.includes('/admin/')) return adminPages;
        if (path.includes('/user/')) return userPages;
        return null;
    }

    function getCurrentPage() {
        var path = window.location.pathname;
        return path.split('/').pop() || 'index.html';
    }

    function getBasePath() {
        var path = window.location.pathname;
        if (path.includes('/admin/')) return path.substring(0, path.indexOf('/admin/') + 7);
        if (path.includes('/user/')) return path.substring(0, path.indexOf('/user/') + 6);
        return path.substring(0, path.lastIndexOf('/') + 1);
    }

    function navigateTo(page) {
        var base = getBasePath();
        window.location.href = base + page;
    }

    document.addEventListener('touchstart', function(e) {
        if (e.touches.length !== 1) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        swiping = true;
    }, { passive: true });

    document.addEventListener('touchend', function(e) {
        if (!swiping) return;
        swiping = false;
        var endX = e.changedTouches[0].clientX;
        var endY = e.changedTouches[0].clientY;
        var diffX = endX - startX;
        var diffY = Math.abs(endY - startY);
        if (Math.abs(diffX) < SWIPE_THRESHOLD || diffY > SWIPE_MAX_Y) return;

        var pages = getPageList();
        if (!pages) return;
        var current = getCurrentPage();
        var idx = pages.indexOf(current);
        if (idx === -1) return;

        if (diffX < 0 && idx < pages.length - 1) {
            navigateTo(pages[idx + 1]);
        } else if (diffX > 0 && idx > 0) {
            navigateTo(pages[idx - 1]);
        }
    }, { passive: true });
})();

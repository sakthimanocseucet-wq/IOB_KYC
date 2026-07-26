// Forgot Password - Fully self-contained
let resetOtp = null;
let resetOtpTimer = null;
let resetIdentifier = '';
let fpOtpMethod = 'email';
let fpFirebaseConfirmation = null;
let fpFirebaseInitialized = false;
let fpFirebaseApp = null;
let fpRecaptchaVerifier = null;
let isEmployeePage = (function() {
    if (document.body && document.body.getAttribute('data-role') === 'employee') return true;
    var path = window.location.pathname.toLowerCase();
    if (path.indexOf('/admin/') !== -1) return true;
    if (path.indexOf('employee') !== -1) return true;
    return false;
})();

async function initFpFirebase() {
    if (fpFirebaseInitialized) return;
    try {
        var existingApp = firebase.apps.find(function(app) { return app.name === 'fpFirebase'; });
        if (existingApp) { fpFirebaseApp = existingApp; fpFirebaseInitialized = true; return; }
        var res = await fetch('/api/config/firebase');
        var cfg = await res.json();
        if (cfg.apiKey && cfg.projectId) {
            fpFirebaseApp = firebase.initializeApp({ apiKey: cfg.apiKey, authDomain: cfg.authDomain, projectId: cfg.projectId }, 'fpFirebase');
            fpFirebaseInitialized = true;
        }
    } catch (e) {
        console.warn('[Firebase] FP init failed:', e);
    }
}

function setFpOtpMethod(method) {
    fpOtpMethod = method;
    var emailBtn = document.getElementById('fpOtpMethodEmail');
    var smsBtn = document.getElementById('fpOtpMethodSms');
    var emailGroup = document.getElementById('fpEmailGroup');
    var phoneGroup = document.getElementById('fpPhoneGroup');
    if (method === 'email') {
        emailBtn.className = 'btn btn-sm btn-primary';
        emailBtn.style.border = '2px solid #2563eb';
        smsBtn.className = 'btn btn-sm btn-outline';
        smsBtn.style.border = '';
        if (emailGroup) emailGroup.style.display = '';
        if (phoneGroup) phoneGroup.style.display = 'none';
    } else {
        smsBtn.className = 'btn btn-sm btn-primary';
        smsBtn.style.border = '2px solid #2563eb';
        emailBtn.className = 'btn btn-sm btn-outline';
        emailBtn.style.border = '';
        if (emailGroup) emailGroup.style.display = 'none';
        if (phoneGroup) phoneGroup.style.display = '';
    }
}

function fpShowAlert(message, type) {
    type = type || 'error';
    var c = document.getElementById('alertContainer');
    if (!c) return;
    if (!message) { c.innerHTML = ''; return; }
    c.innerHTML = '<div class="alert alert-' + type + '">' + message + '</div>';
    c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function fpShowToast(message, type) {
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
        '<button class="toast-close" onclick="fpDismissToast(this.parentElement)">&times;</button>' +
        '<div class="toast-progress"></div>';
    container.appendChild(toast);
    setTimeout(function() { fpDismissToast(toast); }, 4000);
}
function fpDismissToast(toast) {
    if (!toast || toast.classList.contains('toast-exit')) return;
    toast.classList.add('toast-exit');
    setTimeout(function() { toast.remove(); }, 300);
}

function fpSetLoading(formId, loading) {
    var form = document.getElementById(formId);
    if (!form) return;
    var btn = form.querySelector('button[type="submit"]');
    var spans = btn ? btn.querySelectorAll('span') : [];
    if (btn) btn.disabled = loading;
    spans.forEach(function(s) {
        if (s.classList.contains('spinner')) s.style.display = loading ? 'block' : 'none';
        else s.style.display = loading ? 'none' : 'inline';
    });
}

function togglePassword(id) {
    var el = document.getElementById(id);
    if (el) el.type = el.type === 'password' ? 'text' : 'password';
}

function fpTogglePassword(id) {
    togglePassword(id);
}

function validateFpEmail(input) {
    var errEl = document.getElementById('fpEmailError');
    var val = input.value.trim();
    if (!val) {
        errEl.textContent = 'Email address is required';
        errEl.style.display = 'block';
        input.style.borderColor = 'var(--danger)';
        return false;
    }
    var emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(val)) {
        errEl.textContent = 'Invalid email format (e.g. user@example.com)';
        errEl.style.display = 'block';
        input.style.borderColor = 'var(--danger)';
        return false;
    }
    errEl.style.display = 'none';
    input.style.borderColor = '';
    return true;
}

function goToStep(step) {
    document.querySelectorAll('.forgot-step').forEach(function(el) { el.style.display = 'none'; });
    document.getElementById('step' + step).style.display = 'block';
    var subtitles = {
        1: 'Enter your registered email or phone number',
        2: 'We sent a verification code to your ' + (fpOtpMethod === 'sms' ? 'phone' : 'email'),
        3: 'Create a strong new password for your account',
        4: ''
    };
    var subtitleEl = document.getElementById('stepSubtitle');
    if (subtitleEl) subtitleEl.textContent = subtitles[step] || '';
    var loginLink = document.getElementById('loginLink');
    if (loginLink) loginLink.style.display = step === 4 ? 'none' : '';
}

// Step 1
async function handleSendResetOtp(event) {
    event.preventDefault();
    var identifier;
    if (fpOtpMethod === 'sms') {
        identifier = (document.getElementById('resetPhone') || {}).value || '';
    } else {
        identifier = (document.getElementById('resetEmail') || {}).value || '';
    }
    identifier = identifier.trim();

    if (!identifier) {
        fpShowAlert(fpOtpMethod === 'sms' ? 'Please enter your mobile number' : 'Please enter your email address');
        return;
    }

    if (fpOtpMethod === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identifier)) {
        fpShowAlert('Please enter a valid email address');
        return;
    }

    if (fpOtpMethod === 'sms' && !/^\+[0-9]/.test(identifier)) {
        fpShowAlert('Mobile must start with country code (e.g., +91)');
        return;
    }

    fpSetLoading('forgotForm', true);
    fpShowAlert('', '');

    var checkUrl = isEmployeePage ? '/api/auth/admin/forgot-password/check' : '/api/auth/forgot-password/check';

    if (fpOtpMethod === 'email') {
        try {
            var res = await fetch(checkUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ identifier: identifier })
            });
            var text = await res.text();
            var result;
            try { result = JSON.parse(text); } catch (e) { result = { success: false, message: 'Invalid server response' }; }
            if (!res.ok || !result.success) {
                fpShowAlert(result.message || 'No account found with this email address');
                fpSetLoading('forgotForm', false);
                return;
            }
        } catch (e) {
            fpShowAlert('Cannot reach server. Please try again later.');
            fpSetLoading('forgotForm', false);
            return;
        }

        try {
            var otpUrl = '/api/auth/otp/generate';
            var fpRes = await fetch(otpUrl + '?identifier=' + encodeURIComponent(identifier) + '&purpose=PASSWORD_RESET', { method: 'POST' });
            var fpData = await fpRes.json();
        } catch (e) {}
    } else {
        await initFpFirebase();
        if (!fpFirebaseInitialized) {
            fpShowAlert('Firebase not configured. Use email OTP.');
            fpSetLoading('forgotForm', false);
            return;
        }
        try {
            var app = fpFirebaseApp || firebase.app();
            if (fpRecaptchaVerifier) { fpRecaptchaVerifier.clear(); fpRecaptchaVerifier = null; }
            var oldContainer = document.getElementById('fp-recaptcha-container');
            if (oldContainer) oldContainer.remove();
            var container = document.createElement('div');
            container.id = 'fp-recaptcha-container';
            container.style.display = 'none';
            document.body.appendChild(container);
            fpRecaptchaVerifier = new firebase.auth.RecaptchaVerifier('fp-recaptcha-container', { size: 'invisible' }, app);
            fpFirebaseConfirmation = await app.auth().signInWithPhoneNumber(identifier, fpRecaptchaVerifier);
        } catch (e) {
            fpShowAlert('Failed to send SMS: ' + e.message);
            fpSetLoading('forgotForm', false);
            return;
        }
    }

    resetOtp = null;
    resetIdentifier = identifier;

    fpSetLoading('forgotForm', false);
    goToStep(2);
    fpShowToast('OTP sent to ' + identifier, 'success');
    startOtpTimer();
    document.getElementById('resetOtp').focus();
}

function startOtpTimer() {
    var seconds = 30;
    var timerEl = document.getElementById('otpTimer');
    timerEl.textContent = 'Resend OTP in ' + seconds + 's';
    if (resetOtpTimer) clearInterval(resetOtpTimer);
    resetOtpTimer = setInterval(function() {
        seconds--;
        timerEl.textContent = seconds > 0 ? 'Resend OTP in ' + seconds + 's' : '';
        if (seconds <= 0) {
            clearInterval(resetOtpTimer);
            timerEl.innerHTML = '<button type="button" class="btn-link" onclick="resendResetOtp()">Resend OTP</button>';
        }
    }, 1000);
}

function resendResetOtp() {
    if (fpOtpMethod === 'sms') {
        initFpFirebase().then(function() {
            if (!fpFirebaseInitialized) { fpShowAlert('Firebase not configured.'); return; }
            var app = fpFirebaseApp || firebase.app();
            if (fpRecaptchaVerifier) { fpRecaptchaVerifier.clear(); fpRecaptchaVerifier = null; }
            var oldContainer2 = document.getElementById('fp-recaptcha-container-resend');
            if (oldContainer2) oldContainer2.remove();
            var container = document.createElement('div');
            container.id = 'fp-recaptcha-container-resend';
            container.style.display = 'none';
            document.body.appendChild(container);
            fpRecaptchaVerifier = new firebase.auth.RecaptchaVerifier('fp-recaptcha-container-resend', { size: 'invisible' }, app);
            fpFirebaseConfirmation = app.auth().signInWithPhoneNumber(resetIdentifier, fpRecaptchaVerifier)
                .then(function() { fpShowToast('OTP resent to ' + resetIdentifier, 'success'); startOtpTimer(); })
                .catch(function(e) { fpShowAlert('Failed to resend SMS: ' + e.message); });
        });
    } else {
        fetch('/api/auth/otp/generate?identifier=' + encodeURIComponent(resetIdentifier) + '&purpose=PASSWORD_RESET', { method: 'POST' }).catch(function() {});
        fpShowToast('OTP resent to ' + resetIdentifier, 'success');
        startOtpTimer();
    }
}

// Step 2
async function autoVerifyFpOtp() {
    var otp = document.getElementById('resetOtp').value.trim();
    if (otp.length !== 6 || !/^[0-9]{6}$/.test(otp)) return;

    var tick = document.getElementById('fpOtpTick');
    fpSetLoading('otpForm', true);

    try {
        if (fpOtpMethod === 'sms') {
            if (!fpFirebaseConfirmation) { fpSetLoading('otpForm', false); fpShowAlert('Send OTP first'); return; }
            await fpFirebaseConfirmation.confirm(otp);
        } else {
            var res = await fetch('/api/auth/otp/verify?identifier=' + encodeURIComponent(resetIdentifier) + '&otp=' + otp + '&purpose=PASSWORD_RESET', { method: 'POST' });
            var result = await res.json();
            if (!result.success) {
                fpSetLoading('otpForm', false);
                tick.style.display = 'none';
                document.getElementById('resetOtp').style.borderColor = '#dc2626';
                fpShowAlert(result.message || 'Invalid OTP');
                return;
            }
        }
        fpSetLoading('otpForm', false);
        tick.style.display = 'inline';
        document.getElementById('resetOtp').style.borderColor = '#16a34a';
        if (resetOtpTimer) clearInterval(resetOtpTimer);
        fpShowToast('OTP verified!', 'success');
        setTimeout(function() { goToStep(3); document.getElementById('newPassword').focus(); }, 600);
    } catch (e) {
        fpSetLoading('otpForm', false);
        tick.style.display = 'none';
        document.getElementById('resetOtp').style.borderColor = '#dc2626';
        fpShowAlert('Verification failed. Please try again.');
    }
}

async function handleVerifyResetOtp(event) {
    event.preventDefault();
    var otp = document.getElementById('resetOtp').value.trim();
    if (!otp || otp.length !== 6) {
        fpShowAlert('Please enter the 6-digit OTP');
        return;
    }
    if (!/^[0-9]{6}$/.test(otp)) {
        fpShowAlert('OTP must be exactly 6 digits');
        return;
    }

    fpSetLoading('otpForm', true);

    try {
        if (fpOtpMethod === 'sms') {
            if (!fpFirebaseConfirmation) {
                fpSetLoading('otpForm', false);
                fpShowAlert('Please send OTP first');
                return;
            }
            await fpFirebaseConfirmation.confirm(otp);
        } else {
            var purpose = 'PASSWORD_RESET';
            var res = await fetch('/api/auth/otp/verify?identifier=' + encodeURIComponent(resetIdentifier) + '&otp=' + otp + '&purpose=' + purpose, { method: 'POST' });
            var result = await res.json();
            if (!result.success) {
                fpSetLoading('otpForm', false);
                fpShowAlert(result.message || 'Invalid OTP. Please try again.');
                return;
            }
        }
    } catch (e) {
        fpSetLoading('otpForm', false);
        fpShowAlert('Verification failed. Please try again.');
        return;
    }

    fpSetLoading('otpForm', false);

    if (resetOtpTimer) clearInterval(resetOtpTimer);
    fpShowToast('OTP verified!', 'success');
    goToStep(3);
    document.getElementById('newPassword').focus();
}

// Step 3
async function handleResetPassword(event) {
    event.preventDefault();
    var newPass = document.getElementById('newPassword').value;
    var confirmPass = document.getElementById('confirmPassword').value;

    if (!newPass || newPass.length < (isEmployeePage ? 12 : 8)) { fpShowAlert('Password must be at least ' + (isEmployeePage ? '12' : '8') + ' characters'); return; }
    if (newPass !== confirmPass) { fpShowAlert('Passwords do not match'); return; }
    if (!/[A-Z]/.test(newPass)) { fpShowAlert('Password must contain at least one uppercase letter'); return; }
    if (!/[a-z]/.test(newPass)) { fpShowAlert('Password must contain at least one lowercase letter'); return; }
    if (!/[0-9]/.test(newPass)) { fpShowAlert('Password must contain at least one number'); return; }
    if (!/[^A-Za-z0-9]/.test(newPass)) { fpShowAlert('Password must contain at least one special character'); return; }
    if (isEmployeePage && /password/i.test(newPass)) { fpShowAlert('Password must not contain the word "password"'); return; }
    if (isEmployeePage && /iob/i.test(newPass)) { fpShowAlert('Password must not contain the bank name'); return; }

    fpSetLoading('resetForm', true);

    try {
        var resetUrl = isEmployeePage ? '/api/auth/admin/forgot-password/reset' : '/api/auth/forgot-password/reset';
        var res = await fetch(resetUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: resetIdentifier, newPassword: newPass })
        });
        var result = await res.json();
        if (!result.success) {
            fpShowAlert(result.message || 'Failed to reset password');
            fpSetLoading('resetForm', false);
            return;
        }
    } catch (e) {
        fpShowAlert('Network error. Please try again.');
        fpSetLoading('resetForm', false);
        return;
    }

    fpSetLoading('resetForm', false);
    fpShowToast('Password reset successful!', 'success');
    goToStep(4);
}

// Password strength
document.addEventListener('DOMContentLoaded', function() {
    var input = document.getElementById('newPassword');
    if (!input) return;
    input.addEventListener('input', function() {
        var val = this.value;
        var s = document.getElementById('passwordStrength');
        if (!val) { s.innerHTML = ''; return; }
        var score = 0;
        if (val.length >= 8) score++;
        if (val.length >= 12) score++;
        if (/[A-Z]/.test(val)) score++;
        if (/[a-z]/.test(val)) score++;
        if (/[0-9]/.test(val)) score++;
        if (/[^A-Za-z0-9]/.test(val)) score++;
        var levels = [
            { w: '16%', c: '#ef4444', t: 'Very Weak' },
            { w: '33%', c: '#f97316', t: 'Weak' },
            { w: '50%', c: '#eab308', t: 'Fair' },
            { w: '66%', c: '#22c55e', t: 'Strong' },
            { w: '83%', c: '#16a34a', t: 'Very Strong' },
            { w: '100%', c: '#0d9488', t: 'Excellent' }
        ];
        var l = levels[Math.min(score, levels.length - 1)];
        s.innerHTML = '<div style="height:4px;background:var(--gray-200);border-radius:2px;overflow:hidden;margin-bottom:4px"><div style="height:100%;width:' + l.w + ';background:' + l.c + ';border-radius:2px;transition:all 0.3s"></div></div><small style="color:' + l.c + ';font-weight:500">' + l.t + '</small>';
    });
});

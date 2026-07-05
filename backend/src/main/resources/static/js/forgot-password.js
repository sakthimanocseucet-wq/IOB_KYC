// Forgot Password - Fully self-contained
let resetOtp = null;
let resetOtpTimer = null;
let resetIdentifier = '';
let isEmployeePage = (function() {
    if (document.body && document.body.getAttribute('data-role') === 'employee') return true;
    var path = window.location.pathname.toLowerCase();
    if (path.indexOf('/admin/') !== -1) return true;
    if (path.indexOf('employee') !== -1) return true;
    return false;
})();

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
        1: 'Enter your registered email address',
        2: 'We sent a verification code to your email',
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
    var identifier = (document.getElementById('resetEmail') || {}).value || '';
    identifier = identifier.trim();

    if (!identifier) {
        fpShowAlert('Please enter your email address');
        return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identifier)) {
        fpShowAlert('Please enter a valid email address');
        return;
    }

    fpSetLoading('forgotForm', true);
    fpShowAlert('', '');

    try {
        var checkUrl = isEmployeePage ? '/api/auth/admin/forgot-password/check' : '/api/auth/forgot-password/check';
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
        var otpUrl = isEmployeePage ? '/api/auth/otp/generate' : '/api/auth/otp/generate';
        var purpose = isEmployeePage ? 'PASSWORD_RESET' : 'PASSWORD_RESET';
        await fetch(otpUrl + '?identifier=' + encodeURIComponent(identifier) + '&purpose=' + purpose, { method: 'POST' });
    } catch (e) {}

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
    fetch('/api/auth/otp/generate?identifier=' + encodeURIComponent(resetIdentifier) + '&purpose=PASSWORD_RESET', { method: 'POST' }).catch(function() {});
    fpShowToast('OTP resent to ' + resetIdentifier, 'success');
    startOtpTimer();
}

// Step 2
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
        var purpose = isEmployeePage ? 'PASSWORD_RESET' : 'PASSWORD_RESET';
        var res = await fetch('/api/auth/otp/verify?identifier=' + encodeURIComponent(resetIdentifier) + '&otp=' + otp + '&purpose=' + purpose, { method: 'POST' });
        var result = await res.json();
    } catch (e) {
        fpSetLoading('otpForm', false);
        fpShowAlert('Verification failed. Please try again.');
        return;
    }

    fpSetLoading('otpForm', false);

    if (!result.success) {
        fpShowAlert(result.message || 'Invalid OTP. Please try again.');
        return;
    }

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

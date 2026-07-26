// ====================== GLOBAL FORM SUBMIT BLOCKER (runs FIRST) ======================
// Prevents browser password manager from auto-submitting forms as application/x-www-form-urlencoded
(function() {
    document.addEventListener('submit', function(e) {
        if (e.target && (e.target.id === 'registerForm' || e.target.id === 'employeeRegisterForm' || e.target.id === 'otpForm' || e.target.id === 'resetForm' || e.target.id === 'forgotForm')) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        return false;
    }, true);
})();

// ====================== AUTH STATE ======================
const AUTH_API = '/api/auth';

// ====================== INLINE FIELD ERRORS ======================
function clearFieldError(errorId) {
    var el = document.getElementById(errorId);
    if (el) { el.textContent = ''; el.style.display = 'none'; }
}

function showFieldError(errorId, message) {
    var el = document.getElementById(errorId);
    if (el) { el.textContent = message; el.style.display = 'block'; }
}

// ====================== OTP METHOD ======================
let otpMethod = 'email';
let regFirebaseConfirmation = null;
let regFirebaseInitialized = false;
let regFirebaseApp = null;
let regRecaptchaVerifier = null;
let emailOtpVerified = false;
let smsOtpVerified = false;
let otpTimerInterval = null;
let otpVerifying = false;

async function initRegFirebase() {
    if (regFirebaseInitialized) return;
    try {
        var existingApp = firebase.apps.find(function(app) { return app.name === 'regFirebase'; });
        if (existingApp) { regFirebaseApp = existingApp; regFirebaseInitialized = true; return; }
        var res = await fetch('/api/config/firebase');
        var cfg = await res.json();
        if (cfg.apiKey && cfg.projectId) {
            regFirebaseApp = firebase.initializeApp({ apiKey: cfg.apiKey, authDomain: cfg.authDomain, projectId: cfg.projectId }, 'regFirebase');
            regFirebaseInitialized = true;
        }
    } catch (e) {
        console.warn('[Firebase] Reg init failed:', e);
    }
}

function setOtpMethod(method) {
    otpMethod = method;
    var emailBtn = document.getElementById('otpMethodEmail');
    var smsBtn = document.getElementById('otpMethodSms');
    var emailRow = document.getElementById('otpEmailRow');
    var smsRow = document.getElementById('otpSmsRow');
    var tick = document.getElementById('regOtpTick');

    if (method === 'email') {
        emailBtn.className = 'btn btn-sm btn-primary';
        emailBtn.style.border = '2px solid #2563eb';
        smsBtn.className = 'btn btn-sm btn-outline';
        smsBtn.style.border = '';
        emailRow.style.display = '';
        smsRow.style.display = 'none';
    } else {
        smsBtn.className = 'btn btn-sm btn-primary';
        smsBtn.style.border = '2px solid #2563eb';
        emailBtn.className = 'btn btn-sm btn-outline';
        emailBtn.style.border = '';
        emailRow.style.display = 'none';
        smsRow.style.display = '';
    }

    tick.style.display = 'none';
    document.getElementById('regOtpInput').value = '';
    document.getElementById('regOtpInput').style.borderColor = '';
    otpVerifying = false;
    clearFieldError('otpError');
}

async function sendRegOtp() {
    clearFieldError('otpError');
    var tick = document.getElementById('regOtpTick');
    tick.style.display = 'none';
    otpVerifying = false;

    if (otpMethod === 'email') {
        var email = document.getElementById('email').value.trim();
        if (!email) { showFieldError('emailError', 'Enter email first'); return; }
        emailOtpVerified = false;

        var btn = document.getElementById('sendRegOtpBtn');
        btn.disabled = true;
        try {
            var res = await fetch(AUTH_API + '/otp/generate?identifier=' + encodeURIComponent(email) + '&purpose=REGISTER', { method: 'POST' });
            var data = await res.json();
            if (data.success) {
                showToast('OTP sent to ' + email, 'success');
                var spamHint = document.getElementById('otpSpamHint');
                if (spamHint) spamHint.style.display = 'block';
            } else {
                showFieldError('otpError', data.message || 'Failed to send OTP');
                btn.disabled = false;
                return;
            }
        } catch (err) {
            showFieldError('otpError', 'Failed to send OTP');
            btn.disabled = false;
            return;
        }
        startOtpTimer(btn);
    } else {
        var phone = document.getElementById('phone').value.trim();
        if (!phone) { showFieldError('phoneError', 'Enter phone number first'); return; }
        if (!/^\+[0-9]/.test(phone)) { showFieldError('phoneError', 'Phone must start with country code (e.g., +91)'); return; }
        smsOtpVerified = false;

        await initRegFirebase();
        if (!regFirebaseInitialized) { showFieldError('otpError', 'Firebase not configured. Use email OTP.'); return; }

        var btn = document.getElementById('sendRegOtpBtn');
        btn.disabled = true;
        try {
            var app = regFirebaseApp || firebase.app();
            if (regRecaptchaVerifier) { regRecaptchaVerifier.clear(); regRecaptchaVerifier = null; }
            var oldContainer = document.getElementById('reg-recaptcha-container');
            if (oldContainer) oldContainer.remove();
            var container = document.createElement('div');
            container.id = 'reg-recaptcha-container';
            container.style.display = 'none';
            document.body.appendChild(container);
            regRecaptchaVerifier = new firebase.auth.RecaptchaVerifier('reg-recaptcha-container', { size: 'invisible' }, app);
            regFirebaseConfirmation = await app.auth().signInWithPhoneNumber(phone, regRecaptchaVerifier);
            showToast('OTP sent to ' + phone, 'success');
        } catch (e) {
            showFieldError('otpError', 'Failed to send SMS: ' + e.message);
            btn.disabled = false;
            return;
        }
        startOtpTimer(btn);
    }
}

function startOtpTimer(btn) {
    var seconds = 30;
    var timerEl = document.getElementById('otpTimer');
    timerEl.textContent = 'Resend in ' + seconds + 's';
    if (otpTimerInterval) clearInterval(otpTimerInterval);
    otpTimerInterval = setInterval(function() {
        seconds--;
        timerEl.textContent = 'Resend in ' + seconds + 's';
        if (seconds <= 0) {
            clearInterval(otpTimerInterval);
            btn.disabled = false;
            btn.textContent = 'Resend OTP';
            timerEl.textContent = '';
        }
    }, 1000);
}

async function autoVerifyOtp() {
    var otp = document.getElementById('regOtpInput').value.trim();
    if (otp.length !== 6 || !/^[0-9]{6}$/.test(otp)) return;
    if (otpVerifying || emailOtpVerified || smsOtpVerified) return;
    otpVerifying = true;

    var tick = document.getElementById('regOtpTick');
    clearFieldError('otpError');

    if (otpMethod === 'email') {
        var email = document.getElementById('email').value.trim();
        if (!email) { showFieldError('otpError', 'Enter email first'); otpVerifying = false; return; }
        try {
            var res = await fetch(AUTH_API + '/otp/verify?identifier=' + encodeURIComponent(email) + '&otp=' + otp + '&purpose=REGISTER', { method: 'POST' });
            var data = await res.json();
            if (data.success) {
                emailOtpVerified = true;
                tick.style.display = 'inline';
                document.getElementById('regOtpInput').style.borderColor = '#16a34a';
                showToast('Email verified!', 'success');
            } else {
                emailOtpVerified = false;
                otpVerifying = false;
                tick.style.display = 'none';
                document.getElementById('regOtpInput').style.borderColor = '#dc2626';
                showFieldError('otpError', data.message || 'Invalid OTP');
            }
        } catch (err) {
            otpVerifying = false;
            showFieldError('otpError', 'Verification failed');
        }
    } else {
        if (!regFirebaseConfirmation) { showFieldError('otpError', 'Send OTP first'); otpVerifying = false; return; }
        try {
            await regFirebaseConfirmation.confirm(otp);
            smsOtpVerified = true;
            tick.style.display = 'inline';
            document.getElementById('regOtpInput').style.borderColor = '#16a34a';
            showToast('Phone verified!', 'success');
        } catch (err) {
            smsOtpVerified = false;
            otpVerifying = false;
            tick.style.display = 'none';
            document.getElementById('regOtpInput').style.borderColor = '#dc2626';
            showFieldError('otpError', 'Invalid OTP: ' + err.message);
        }
    }
}

async function sendRegOTP() { sendRegOtp(); }
async function verifyRegOTP() { return otpMethod === 'sms' ? smsOtpVerified : emailOtpVerified; }

// ====================== PASSWORD VALIDATION ======================
function validateUserPassword(password) {
    if (password.length < 8) return 'Password must be at least 8 characters long';
    if (!/[A-Z]/.test(password)) return 'Password must contain at least one uppercase letter';
    if (!/[a-z]/.test(password)) return 'Password must contain at least one lowercase letter';
    if (!/[0-9]/.test(password)) return 'Password must contain at least one number';
    if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) return 'Password must contain at least one special character (!@#$%^&*...)';
    return null;
}

function validateEmployeePassword(password) {
    if (password.length < 12) return 'Employee password must be at least 12 characters long';
    if (!/[A-Z]/.test(password)) return 'Password must contain at least one uppercase letter';
    if (!/[a-z]/.test(password)) return 'Password must contain at least one lowercase letter';
    if (!/[0-9]/.test(password)) return 'Password must contain at least one number';
    if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)) return 'Password must contain at least one special character (!@#$%^&*...)';
    if (/password/i.test(password)) return 'Password must not contain the word "password"';
    if (/iob/i.test(password)) return 'Password must not contain the bank name';
    return null;
}

function getPasswordStrength(password) {
    var score = 0;
    if (password.length >= 8) score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[a-z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;
    return score;
}

function renderPasswordStrength(containerId, password) {
    var el = document.getElementById(containerId);
    if (!el) return;
    if (!password) { el.innerHTML = ''; return; }
    var score = getPasswordStrength(password);
    var levels = [
        { width: '16%', color: '#ef4444', text: 'Very Weak' },
        { width: '33%', color: '#f97316', text: 'Weak' },
        { width: '50%', color: '#eab308', text: 'Fair' },
        { width: '66%', color: '#22c55e', text: 'Strong' },
        { width: '83%', color: '#16a34a', text: 'Very Strong' },
        { width: '100%', color: '#0d9488', text: 'Excellent' }
    ];
    var level = levels[Math.min(score, levels.length - 1)];
    el.innerHTML =
        '<div style="height:4px;background:var(--gray-200);border-radius:2px;overflow:hidden;margin-top:6px">' +
            '<div style="height:100%;width:' + level.width + ';background:' + level.color + ';border-radius:2px;transition:all 0.3s"></div>' +
        '</div>' +
        '<small style="color:' + level.color + ';font-weight:500">' + level.text + '</small>';
}

// getAuthToken, getUser, isLoggedIn, clearAuthData, setAuthData are defined in main.js

// ====================== LOGIN LOCK (prevents browser autofill infinite loop) ======================
let _loginLocked = false;

// ====================== USER LOGIN ======================
async function handleLogin(event) {
    if (event) event.preventDefault();
    if (_loginLocked) return;
    _loginLocked = true;

    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    clearFieldError('emailError');
    clearFieldError('passwordError');
    if (!email) { showFieldError('emailError', 'Email is required'); _loginLocked = false; return; }
    if (!password) { showFieldError('passwordError', 'Password is required'); _loginLocked = false; return; }

    setLoading('loginForm', 'btnSpinner', 'btnText', true);

    try {
        const res = await fetch(AUTH_API + '/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (data.success) {
            var userData = data.data || {};
            var userName = userData.name || email.split('@')[0];
            setAuthData(userData.token || '', {
                id: userData.userId || null,
                name: userName,
                email: userData.email || email,
                role: 'user'
            });
            showToast('Login successful!', 'success');
            setTimeout(() => window.location.href = 'dashboard.html', 500);
        } else {
            showFieldError('passwordError', data.message || 'Invalid credentials. Please try again.');
            _loginLocked = false;
        }
    } catch (err) {
        showAlert('Login failed. Please try again.', 'error');
        _loginLocked = false;
    } finally {
        setLoading('loginForm', 'btnSpinner', 'btnText', false);
    }
}

// ====================== FORGOT PASSWORD ======================
function handleForgotPassword() {
    const email = prompt('Enter your registered email address:');
    if (!email) return;
    showToast('If an account exists with ' + email + ', a password reset link has been sent.', 'success');
}

async function handleRegister(event) {
    event.preventDefault();
    const firstName = document.getElementById('firstName').value;
    const lastName = document.getElementById('lastName').value;
    const email = document.getElementById('email').value;
    const phone = document.getElementById('phone').value;
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const terms = document.getElementById('terms').checked;

    ['firstNameError','lastNameError','emailError','phoneError','passwordError','confirmPasswordError','termsError','otpError'].forEach(clearFieldError);

    if (!firstName) { showFieldError('firstNameError', 'First name is required'); return; }
    if (!lastName) { showFieldError('lastNameError', 'Last name is required'); return; }
    if (!email) { showFieldError('emailError', 'Email is required'); return; }
    if (!phone) { showFieldError('phoneError', 'Phone number is required'); return; }
    if (!password) { showFieldError('passwordError', 'Password is required'); return; }
    if (!confirmPassword) { showFieldError('confirmPasswordError', 'Please confirm your password'); return; }

    if (password !== confirmPassword) {
        showFieldError('confirmPasswordError', 'Passwords do not match');
        return;
    }

    var passwordError = validateUserPassword(password);
    if (passwordError) {
        showFieldError('passwordError', passwordError);
        return;
    }

    if (!terms) {
        showFieldError('termsError', 'Please accept the Terms of Service');
        return;
    }

    if (!emailOtpVerified && !smsOtpVerified) {
        showFieldError('otpError', 'Please verify with OTP');
        return;
    }

    setLoading('registerForm', 'btnSpinner', 'btnText', true);

    try {
        const res = await fetch(AUTH_API + '/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ firstName, lastName, email, phone, password, role: 'USER' })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Account created successfully! Please login.', 'success');
            setTimeout(() => window.location.href = 'login.html', 1000);
        } else {
            showAlert(data.message || 'Registration failed.', 'error');
        }
    } catch (err) {
        showAlert('Registration failed. Please try again.', 'error');
    } finally {
        setLoading('registerForm', 'btnSpinner', 'btnText', false);
    }
}

// ====================== ADMIN LOGIN ======================
let _adminLoginLocked = false;
async function handleAdminLogin(event) {
    if (event) event.preventDefault();
    if (_adminLoginLocked) return;
    _adminLoginLocked = true;

    const empId = document.getElementById('employeeId').value;
    const password = document.getElementById('password').value;

    if (!empId || !password) {
        showAlert('Please enter Employee ID and Password', 'error');
        _adminLoginLocked = false;
        return;
    }

    setLoading('adminLoginForm', 'btnSpinner', 'btnText', true);

    try {
        const res = await fetch(AUTH_API + '/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employeeId: empId, password })
        });
        const data = await res.json();
        if (data.success) {
            var userData = data.data || {};
            var empName = (userData.firstName || '') + ' ' + (userData.lastName || '');
            empName = empName.trim() || userData.role || 'Admin';
            setAuthData(userData.token || '', {
                id: userData.userId || null,
                name: empName,
                email: userData.email || '',
                role: (userData.role || 'ADMIN').toLowerCase(),
                employeeId: empId
            });
            showToast('Welcome back!', 'success');
            setTimeout(() => window.location.href = 'dashboard.html', 500);
        } else {
            showAlert(data.message || 'Invalid credentials', 'error');
            _adminLoginLocked = false;
        }
    } catch (err) {
        showAlert('Login failed. Please try again.', 'error');
        _adminLoginLocked = false;
    } finally {
        setLoading('adminLoginForm', 'btnSpinner', 'btnText', false);
    }
}

// ====================== LOGOUT ======================
function handleLogout() {
    clearAuthData();
    showToast('Logged out successfully', 'info');
    setTimeout(() => { window.location.href = '../user/login.html'; }, 500);
}

function handleAdminLogout() {
    clearAuthData();
    showToast('Logged out successfully', 'info');
    setTimeout(() => { window.location.href = '../admin/login.html'; }, 500);
}

// ====================== EMPLOYEE REGISTER ======================
async function handleEmployeeRegister(event) {
    event.preventDefault();
    const firstName = document.getElementById('firstName').value;
    const lastName = document.getElementById('lastName').value;
    const employeeId = document.getElementById('employeeId').value;
    const role = document.getElementById('role').value;
    const email = document.getElementById('email').value;
    const phone = document.getElementById('phone').value;
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const terms = document.getElementById('terms').checked;

    if (!firstName || !lastName || !employeeId || !role || !email || !phone || !password || !confirmPassword) {
        showAlert('Please fill in all fields', 'error');
        return;
    }

    if (password !== confirmPassword) {
        showAlert('Passwords do not match', 'error');
        return;
    }

    var passwordError = validateEmployeePassword(password);
    if (passwordError) {
        showAlert(passwordError, 'error');
        return;
    }

    if (!terms) {
        showAlert('Please accept the Terms of Service', 'error');
        return;
    }

    if (!emailOtpVerified && !smsOtpVerified) {
        showFieldError('otpError', 'Please verify with OTP');
        return;
    }

    setLoading('employeeRegisterForm', 'btnSpinner', 'btnText', true);

    try {
        const res = await fetch(AUTH_API + '/admin/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ firstName, lastName, email, phone, password, role, employeeId })
        });
        const data = await res.json();
        if (data.success) {
            showToast('Employee account created successfully! Please login.', 'success');
            setTimeout(() => window.location.href = 'login.html', 1000);
        } else {
            showAlert(data.message || 'Registration failed.', 'error');
        }
    } catch (err) {
        showAlert('Registration failed. Please try again.', 'error');
    } finally {
        setLoading('employeeRegisterForm', 'btnSpinner', 'btnText', false);
    }
}

// ====================== HELPERS ======================
function showAlert(message, type = 'error') {
    const container = document.getElementById('alertContainer');
    if (!container) return;
    container.innerHTML = '<div class="alert alert-' + type + '">' + message + '</div>';
}

function simulateDelay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function setLoading(btnId, spinnerId, textId, loading) {
    const btn = document.getElementById(btnId);
    const spinner = document.getElementById(spinnerId);
    const text = document.getElementById(textId);
    if (!btn) return;
    btn.disabled = loading;
    if (spinner) spinner.style.display = loading ? 'block' : 'none';
    if (text) text.style.display = loading ? 'none' : 'inline';
}

// Auth redirect check
(function() {
    const token = getAuthToken();
    const user = getUser();
    if (token && user) {
        const nameEl = document.getElementById('userName');
        const emailEl = document.getElementById('userEmail');
        const holderEl = document.getElementById('accountHolder');
        if (nameEl) nameEl.textContent = user.name || 'User';
        if (emailEl) emailEl.textContent = user.email || '';
        if (holderEl) holderEl.textContent = user.name || '--';
    }
})();

// Prevent native form submissions for non-auth forms (stops browser autofill auto-submit)
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('form').forEach(function(form) {
        if (form.id !== 'registerForm' && form.id !== 'employeeRegisterForm' && form.id !== 'otpForm' && form.id !== 'resetForm' && form.id !== 'forgotForm') {
            form.addEventListener('submit', function(e) { e.preventDefault(); });
        }
    });
});

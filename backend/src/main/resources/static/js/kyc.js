const KYC_API = '/api/kyc';
const AI_API = '/api/ai';

window.addEventListener('error', function (e) {
    console.groupCollapsed('[Global Error] ' + e.message);
    console.error('ErrorEvent:', e);
    if (e.error && e.error.stack) console.error('Stack:', e.error.stack);
    console.groupEnd();
});
window.addEventListener('unhandledrejection', function (e) {
    console.groupCollapsed('[Unhandled Promise] ' + e.reason);
    console.error('Reason:', e.reason);
    if (e.reason && e.reason.stack) console.error('Stack:', e.reason.stack);
    console.groupEnd();
});
let kycData = {
    aadhaarFile: null,
    panFile: null,
    profilePhoto: null,
    ocrData: null,
    selfieImage: null,
    faceMatchPercent: 0,
    riskScore: 15,
    mobile: '',
    email: '',
    accountType: 'savings',
    emailOtpVerified: false
};
let currentStep = 1;
let webcamStream = null;
let ocrInProgress = false;

let challengeData = null;
let challengeFrames = [];
let challengeActive = false;
let challengeInterval = null;
let challengeTimerInterval = null;
const CHALLENGE_FRAME_INTERVAL = 120;
const CHALLENGE_STEP_TIMEOUT = 5000; // 5 seconds per challenge

// Sequential 4-challenge session state
let challengeSessionId = null;
let challengeCurrentIndex = 0;
let challengeTotalCount = 4;
let challengeResults = [];
const CHALLENGE_FRAMES_PER_STEP = 15;

function goToStep(step) {
    currentStep = step;
    document.querySelectorAll('.kyc-step').forEach(el => el.style.display = 'none');
    const target = document.querySelector('.kyc-step[data-step="' + step + '"]');
    if (target) target.style.display = 'block';
    if (step === 3) {
        challengeData = null;
        challengeFrames = [];
        challengeActive = false;
        challengeSessionId = null;
        challengeCurrentIndex = 0;
        challengeResults = [];
        window.__finalChallengeResult = null;
        window.__localChallenges = null;
        if (challengeInterval) { clearInterval(challengeInterval); challengeInterval = null; }
        if (challengeTimerInterval) { clearInterval(challengeTimerInterval); challengeTimerInterval = null; }
        kycData.selfieImage = null;
        const faceResult = document.getElementById('faceResult');
        if (faceResult) faceResult.style.display = 'none';
        const submitBtn = document.getElementById('submitKycBtn');
        if (submitBtn) submitBtn.disabled = true;
        const startBtn = document.getElementById('startChallengeBtn');
        if (startBtn) {
            startBtn.style.display = '';
            startBtn.disabled = false;
            startBtn.textContent = '\u{1F50D} Start Live Verification';
        }
        const instruction = document.getElementById('challengeInstruction');
        if (instruction) instruction.style.display = 'none';
        const actionStatus = document.getElementById('challengeActionStatus');
        if (actionStatus) actionStatus.style.display = 'none';
        const seqProgress = document.getElementById('challengeSequenceProgress');
        if (seqProgress) seqProgress.style.display = 'none';
        const sidebar = document.getElementById('challengeRightPanel');
        if (sidebar) sidebar.style.display = 'none';
        const leftPanel = document.getElementById('challengeLeftPanel');
        if (leftPanel) {
            leftPanel.querySelector('.panel-icon').textContent = '\u{1F441}\uFE0F';
            leftPanel.querySelector('.panel-instructions').innerHTML = '<strong>Position your face</strong> within the guide. Complete 4 challenges to prove you are live.';
            leftPanel.querySelectorAll('.step-item').forEach(function(el, i) {
                el.className = 'step-item';
                el.querySelector('.step-num').textContent = (i + 1);
                el.lastChild.textContent = 'Challenge ' + (i + 1);
            });
        }
        // Reset liveness check icons
        var checkIds = ['livenessBlink', 'livenessSpoof', 'livenessDeepfake', 'livenessChallenge', 'livenessDepth'];
        checkIds.forEach(function(id) {
            var el = document.getElementById(id);
            if (el) { el.innerHTML = '&#10060;'; el.style.color = ''; }
        });
        // Reset 4-Step Challenge label
        var cItem2 = document.getElementById('livenessChallenge');
        if (cItem2 && cItem2.parentElement) {
            var cParent2 = cItem2.parentElement;
            cParent2.innerHTML = '<span id="livenessChallenge">&#10060;</span> 4-Step Challenge';
            cParent2.style.color = '';
        }
        var matchText2 = document.getElementById('faceMatchText');
        if (matchText2) { matchText2.textContent = 'Running enhanced AI verification...'; matchText2.style.color = ''; }
        var matchPct2 = document.getElementById('faceMatchPercent');
        if (matchPct2) matchPct2.textContent = '0%';
        var debugPnl = document.getElementById('debugPanel');
        if (debugPnl) debugPnl.style.display = 'none';
        var retryBtn2 = document.getElementById('retryFaceBtn');
        if (retryBtn2) retryBtn2.style.display = 'none';
        // Restart webcam only if not already running
        if (!webcamStream) {
            // Start webcam async — disable button until ready
        if (startBtn) { startBtn.disabled = true; startBtn.textContent = 'Starting camera...'; }
        startWebcam().then(function() {
            if (startBtn) { startBtn.disabled = false; startBtn.textContent = '\u{1F50D} Start Live Verification'; }
        }).catch(function() {
            if (startBtn) { startBtn.disabled = false; startBtn.textContent = '\u{1F50D} Start Live Verification'; }
        });
        }
    } else {
        stopWebcam();
    }
    if (step === 4) {
        calculateFinalRiskScore();
    }
}

function saveKycProgress() {
    var savedAppId = localStorage.getItem('kycAppId');
    localStorage.setItem('kycSubmitted', 'true');
    localStorage.setItem('kycData', JSON.stringify({
        ocrName: kycData.ocrData ? kycData.ocrData.name : '',
        ocrDob: kycData.ocrData ? kycData.ocrData.dob : '',
        ocrIdNumber: kycData.ocrData ? kycData.ocrData.idNumber : '',
        ocrPanNumber: kycData.ocrData ? kycData.ocrData.panNumber : '',
        ocrAddress: kycData.ocrData ? kycData.ocrData.address : '',
        branch: kycData.ocrData ? kycData.ocrData.branch : '',
        mobile: kycData.mobile || '',
        email: kycData.email || '',
        accountType: kycData.accountType || '',
        hasDoc: !!(kycData.aadhaarFile || kycData.panFile),
        hasDetails: !!kycData.emailOtpVerified,
        hasFace: !!kycData.selfieImage,
        riskScore: kycData.riskScore,
        faceMatch: kycData.faceMatchPercent,
        status: 'PENDING',
        appId: savedAppId || 1
    }));
}

function nextStep(current) {
    if (current === 1) {
        if (!kycData.aadhaarFile && !kycData.panFile) {
            showAlert('Please upload at least one identity document (Aadhaar or PAN)', 'error');
            return;
        }
        kycData.ocrData = null;
        goToStep(2);
        populateOCRForm();
        return;
    }
    if (current === 3) {
        saveKycProgress();
    }
    goToStep(current + 1);
}
function goBackFromFace() {
    var isReKyc = !!(window.__rekycMode || kycData.reKyc || kycData.reKycAppId || new URLSearchParams(window.location.search).get('rekyc') === '1');
    if (isReKyc) {
        stopWebcam();
        window.location.href = 'rekyc.html';
    } else {
        prevStep(3);
    }
}

function prevStep(current) {
    if (current === 2) {
        ocrInProgress = false;
    }
    if (current === 3) {
        kycData.ocrData = null;
    }
    goToStep(current - 1);
    if (current === 3) {
        populateOCRForm();
    }
}

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'application/pdf'];

function handleDocSelect(input, type) {
    try {
        var file = input.files[0];
        if (!file) return;
        if (file.size > 5 * 1024 * 1024) {
            alert('File size must be under 5MB');
            input.value = '';
            return;
        }

        var uploadId, fileNameId, removeId;
        if (type === 'aadhaar') {
            kycData.aadhaarFile = file;
            kycData.ocrData = null;
            uploadId = 'aadhaarUpload';
            fileNameId = 'aadhaarFileName';
            removeId = 'aadhaarRemove';
        } else if (type === 'pan') {
            kycData.panFile = file;
            kycData.ocrData = null;
            uploadId = 'panUpload';
            fileNameId = 'panFileName';
            removeId = 'panRemove';
        } else if (type === 'photo') {
            kycData.profilePhoto = file;
            uploadId = 'photoUpload';
            fileNameId = 'photoFileName';
            removeId = 'photoRemove';
        }

        var uploadEl = document.getElementById(uploadId);
        var fileNameEl = document.getElementById(fileNameId);
        var removeEl = document.getElementById(removeId);

        if (fileNameEl) fileNameEl.textContent = '\u2705 ' + file.name;
        if (removeEl) removeEl.style.display = 'inline-block';
        if (uploadEl) uploadEl.classList.add('uploaded');

        input.style.display = 'none';
        checkUploadReady();
        if (typeof showToast === 'function') showToast(file.name + ' selected', 'success');
    } catch (e) {
        console.error('[KYC] handleDocSelect error:', e);
    }
}

function resetUploadEl(el) {
    if (!el) return;
    el.classList.remove('uploaded');
    el.style.borderColor = '';
    el.style.background = '';
    var icon = el.querySelector('.upload-icon');
    var p = el.querySelector('p');
    var sm = el.querySelector('small');
    var fn = el.querySelector('.file-name');
    if (icon) icon.style.display = '';
    if (p) p.style.display = '';
    if (sm) sm.style.display = '';
    if (fn) { fn.textContent = ''; fn.style.display = 'none'; }
}

function removeFile(type) {
    var uploadEl, fileNameEl, removeEl, inputEl;
    if (type === 'aadhaar') {
        kycData.aadhaarFile = null;
        inputEl = document.getElementById('aadhaarFile');
        uploadEl = document.getElementById('aadhaarUpload');
        fileNameEl = document.getElementById('aadhaarFileName');
        removeEl = document.getElementById('aadhaarRemove');
    } else if (type === 'pan') {
        kycData.panFile = null;
        inputEl = document.getElementById('panFile');
        uploadEl = document.getElementById('panUpload');
        fileNameEl = document.getElementById('panFileName');
        removeEl = document.getElementById('panRemove');
    } else if (type === 'photo') {
        kycData.profilePhoto = null;
        inputEl = document.getElementById('profilePhoto');
        uploadEl = document.getElementById('photoUpload');
        fileNameEl = document.getElementById('photoFileName');
        removeEl = document.getElementById('photoRemove');
    }
    if (inputEl) { inputEl.value = ''; inputEl.style.display = ''; }
    if (fileNameEl) { fileNameEl.textContent = ''; fileNameEl.innerHTML = ''; fileNameEl.style.display = 'none'; }
    if (removeEl) removeEl.style.display = 'none';
    resetUploadEl(uploadEl);
    if (uploadEl) {
        var preview = uploadEl.querySelector('.file-preview');
        if (preview) preview.remove();
    }
    checkUploadReady();
    showToast('File removed', 'info');
}

function checkUploadReady() {
    const btn = document.getElementById('uploadContinueBtn');
    if (btn && (kycData.aadhaarFile || kycData.panFile)) {
        btn.disabled = false;
    } else if (btn) {
        btn.disabled = true;
    }
}

// ====================== OCR ======================
function populateOCRForm() {
    ocrInProgress = false;
    var ocrStatus = document.getElementById('ocrStatus');
    var ocrForm = document.getElementById('ocrForm');
    if (!ocrStatus || !ocrForm) return;

    if (kycData.ocrData) {
        ocrStatus.style.display = 'none';
        ocrForm.style.display = 'block';
        document.getElementById('ocrName').value = kycData.ocrData.name || '';
        document.getElementById('ocrDob').value = kycData.ocrData.dob || '';
        document.getElementById('ocrIdNumber').value = kycData.ocrData.idNumber || '';
        document.getElementById('ocrPanNumber').value = kycData.ocrData.panNumber || '';
        document.getElementById('ocrAddress').value = kycData.ocrData.address || '';
        var savedBranch = kycData.ocrData.branch || '';
        var branchSelect = document.getElementById('ocrBranch');
        var branchManual = document.getElementById('ocrBranchManual');
        var matchFound = false;
        if (branchSelect) {
            for (var i = 0; i < branchSelect.options.length; i++) {
                if (branchSelect.options[i].value === savedBranch) {
                    branchSelect.value = savedBranch;
                    matchFound = true;
                    break;
                }
            }
            if (!matchFound && savedBranch) {
                branchSelect.value = 'other';
                if (branchManual) {
                    branchManual.style.display = 'block';
                    branchManual.value = savedBranch;
                }
            }
        }
        if (kycData.mobile) document.getElementById('kycMobile').value = kycData.mobile;
        if (kycData.email) document.getElementById('kycEmail').value = kycData.email;
    } else {
        startOCR();
    }
}

function manualEntryFallback() {
    const ocrStatus = document.getElementById('ocrStatus');
    const ocrForm = document.getElementById('ocrForm');
    if (ocrStatus) ocrStatus.style.display = 'none';
    if (ocrForm) ocrForm.style.display = 'block';
    kycData.ocrData = { name: '', dob: '', idNumber: '', panNumber: '', address: '', branch: '' };
    document.getElementById('ocrName').value = '';
    document.getElementById('ocrDob').value = '';
    document.getElementById('ocrIdNumber').value = '';
    document.getElementById('ocrPanNumber').value = '';
    document.getElementById('ocrAddress').value = '';
    document.getElementById('ocrBranch').value = '';
    showToast('Please enter your details manually', 'info');
}

async function runOCR(imageFile, docType) {
    if (!imageFile) { return { success: false, error: 'No file' }; }
    const formData = new FormData();
    formData.append('image', imageFile);
    formData.append('doc_type', docType);
    try {
        var headers = {};
        var tkn = (typeof getAuthToken === 'function') ? getAuthToken() : null;
        if (tkn) headers['Authorization'] = 'Bearer ' + tkn;
        const res = await fetch(AI_API + '/ocr', { method: 'POST', headers: headers, body: formData });
        var result;
        try { result = await res.json(); } catch(e) { return { success: false, error: 'OCR server returned invalid response (status ' + res.status + ')' }; }
        if (!result.success) return { success: false, error: result.error || 'OCR extraction failed' };
        return { success: true, data: result.data };
    } catch (e) {
        return { success: false, error: e.message || 'Network error' };
    }
}

async function startOCR() {
    if (ocrInProgress) return;
    ocrInProgress = true;
    const ocrStatus = document.getElementById('ocrStatus');
    const ocrForm = document.getElementById('ocrForm');
    if (!ocrStatus || !ocrForm) return;
    ocrStatus.style.display = 'block';
    ocrForm.style.display = 'none';
    ocrStatus.innerHTML = '<div class="spinner"></div><p>Connecting to OCR server...</p>';

    try {
        const healthRes = await fetch('/api/ai/healthz');
        if (!healthRes.ok) throw new Error('AI server not reachable');
    } catch {
        ocrStatus.innerHTML = '<p>OCR server not running.</p><p style="font-size:12px;color:var(--gray-500);margin-top:4px">Start it with: <code>python api_server.py</code> in the ai-ml folder</p><button class="btn btn-primary" style="margin-top:12px" onclick="manualEntryFallback()">Enter Details Manually</button>';
        ocrInProgress = false;
        return;
    }

    ocrStatus.innerHTML = '<div class="spinner"></div><p>Scanning document...</p>';

    var docResult = { success: false, data: {} };
    if (kycData.aadhaarFile) {
        docResult = await runOCR(kycData.aadhaarFile, 'AADHAAR');
    }
    if (kycData.panFile) {
        var panResult = await runOCR(kycData.panFile, 'PAN');
        if (panResult.success && panResult.data) {
            if (!docResult.success) {
                docResult = panResult;
                if (docResult.data.id_number) docResult.data.pan_number = docResult.data.id_number;
            } else {
                if (panResult.data.id_number) docResult.data.pan_number = panResult.data.id_number;
                if (panResult.data.name && !docResult.data.name) docResult.data.name = panResult.data.name;
                if (panResult.data.dob && !docResult.data.dob) docResult.data.dob = panResult.data.dob;
                if (panResult.data.address && !docResult.data.address) docResult.data.address = panResult.data.address;
            }
        }
    }

    if (!ocrInProgress) return;
    if (!docResult.success) {
        ocrStatus.innerHTML = '<p>OCR failed: ' + docResult.error + '</p><button class="btn btn-primary" style="margin-top:12px" onclick="manualEntryFallback()">Enter Details Manually</button>';
        ocrInProgress = false;
        return;
    }

    ocrInProgress = false;
    ocrStatus.innerHTML = '<div class="spinner"></div><p>Extracting personal details...</p>';
    await new Promise(r => setTimeout(r, 300));

    ocrStatus.style.display = 'none';
    ocrForm.style.display = 'block';

    const data = docResult.data || {};
    let dob = data.dob || '';
    if (dob && dob.includes('/')) {
        const parts = dob.split('/');
        dob = parts[2] + '-' + parts[1] + '-' + parts[0];
    }

    kycData.ocrData = {
        name: data.name || '',
        dob: dob,
        idNumber: data.id_number || '',
        panNumber: data.pan_number || '',
        address: data.address || '',
        addressComponents: data.address_components || null,
        branch: data.branch || ''
    };
    document.getElementById('ocrName').value = kycData.ocrData.name;
    document.getElementById('ocrDob').value = kycData.ocrData.dob;
    var idField = document.getElementById('ocrIdNumber');
    idField.value = kycData.ocrData.idNumber;
    if (kycData.ocrData.panNumber) document.getElementById('ocrPanNumber').value = kycData.ocrData.panNumber;
    document.getElementById('ocrAddress').value = kycData.ocrData.address;
    document.getElementById('ocrBranch').value = kycData.ocrData.branch;

    const user = getUser();
    if (user) {
        if (user.phone) document.getElementById('kycMobile').value = user.phone;
        if (user.email) document.getElementById('kycEmail').value = user.email;
    }

    if (kycData.ocrData.name || kycData.ocrData.idNumber) {
        showToast('Document scanned! Verify extracted details', 'success');
    } else {
        showToast('Could not auto-extract. Enter details manually', 'info');
    }
    document.getElementById('ocrName').focus();
}

// ====================== EMAIL OTP ======================
let kycEmailOtpTimer = null;

async function sendEmailOTP() {
    const email = document.getElementById('kycEmail').value;
    if (!email) {
        showAlert('Please enter your email first', 'error');
        return;
    }
    kycData.emailOtpVerified = false;
    const btn = document.getElementById('sendEmailOtpBtn');
    btn.disabled = true;

    try {
        const otpRes = await fetch('/api/auth/otp/generate?identifier=' + encodeURIComponent(email) + '&purpose=KYC', { method: 'POST' });
        const otpData = await otpRes.json();
        if (otpData.success) {
            showToast('OTP sent to ' + email, 'success');
        } else {
            showToast(otpData.message || 'Failed to send OTP', 'error');
            btn.disabled = false;
            return;
        }
    } catch (err) {
        showToast('Failed to send OTP. Please try again.', 'error');
        btn.disabled = false;
        return;
    }

    let seconds = 30;
    const timerEl = document.getElementById('emailOtpTimer');
    timerEl.textContent = 'Resend OTP in ' + seconds + 's';
    if (kycEmailOtpTimer) clearInterval(kycEmailOtpTimer);
    kycEmailOtpTimer = setInterval(() => {
        seconds--;
        timerEl.textContent = 'Resend OTP in ' + seconds + 's';
        if (seconds <= 0) {
            clearInterval(kycEmailOtpTimer);
            btn.disabled = false;
            btn.textContent = 'Resend OTP';
            timerEl.textContent = '';
        }
    }, 1000);
}

async function verifyDetails() {
    const name = document.getElementById('ocrName').value.trim();
    const dob = document.getElementById('ocrDob').value;
    const id = document.getElementById('ocrIdNumber').value.trim();
    const addr = document.getElementById('ocrAddress').value.trim();
    const mobile = document.getElementById('kycMobile').value.trim();
    const email = document.getElementById('kycEmail').value.trim();
    const emailOtp = document.getElementById('emailOtp').value.trim();
    const accountType = document.querySelector('input[name="accountType"]:checked').value;
    var branchVal = document.getElementById('ocrBranch') ? document.getElementById('ocrBranch').value.trim() : '';
    if (branchVal === 'other') {
        branchVal = document.getElementById('ocrBranchManual') ? document.getElementById('ocrBranchManual').value.trim() : '';
    }

    if (!name) { showAlert('Please enter your full name', 'error'); return; }
    if (!dob) { showAlert('Please enter your date of birth', 'error'); return; }
    if (!id || id.length < 12) { showAlert('Please enter a valid 12-digit Aadhaar number', 'error'); return; }
    var panVal = document.getElementById('ocrPanNumber') ? document.getElementById('ocrPanNumber').value.trim().toUpperCase() : '';
    if (panVal && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(panVal)) { showAlert('Please enter a valid PAN number (e.g., ABCDE1234F)', 'error'); return; }
    if (!branchVal) { showAlert('Please select your branch', 'error'); return; }
    if (!addr) { showAlert('Please enter your address', 'error'); return; }
    if (!mobile || mobile.length < 10) { showAlert('Please enter a valid mobile number with country code (e.g., +91 9876543210)', 'error'); return; }
    if (!/^\+[0-9]/.test(mobile)) { showAlert('Mobile number must start with country code (e.g., +91)', 'error'); return; }
    if (!email) { showAlert('Please enter your email address', 'error'); return; }
    if (!emailOtp || emailOtp.length !== 6) { showAlert('Please enter the 6-digit OTP sent to your email', 'error'); return; }

    try {
        var otpRes = await fetch('/api/auth/otp/verify?identifier=' + encodeURIComponent(email) + '&otp=' + emailOtp + '&purpose=KYC', { method: 'POST' });
        var otpResult = await otpRes.json();
        if (!otpResult.success) {
            showAlert(otpResult.message || 'Invalid email OTP. Please try again.', 'error');
            return;
        }
    } catch (err) {
        showAlert('OTP verification failed. Please try again.', 'error');
        return;
    }

    kycData.emailOtpVerified = true;
    kycData.mobile = mobile;
    kycData.email = email;
    kycData.accountType = accountType;
    var genderVal = document.getElementById('ocrGender') ? document.getElementById('ocrGender').value : '';
    kycData.ocrData = { name, dob, idNumber: id, panNumber: panVal, address: addr, branch: branchVal, gender: genderVal };
    document.getElementById('emailOtp').value = '';
    saveKycProgress();
    showToast('Email verified! Proceeding to face verification.', 'success');
    goToStep(3);
}

// ====================== WEBCAM / FACE VERIFICATION ======================
async function startWebcam() {
    const video = document.getElementById('webcam');
    if (!video) return;
    try {
        webcamStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: 640, height: 480 } });
        video.srcObject = webcamStream;
        await new Promise((resolve) => {
            video.onloadedmetadata = () => {
                video.play();
                resolve();
            };
        });
    } catch (err) {
        showAlert('Camera access denied. Please allow camera access to continue.', 'error');
    }
}

function stopWebcam() {
    if (webcamStream) {
        webcamStream.getTracks().forEach(track => track.stop());
        webcamStream = null;
    }
}

function retryFaceVerification() {
    try {
    // Reset all challenge state
    challengeData = null;
    challengeFrames = [];
    challengeActive = false;
    challengeSessionId = null;
    challengeCurrentIndex = 0;
    challengeResults = [];
    window.__finalChallengeResult = null;
    window.__localChallenges = null;
    if (challengeInterval) { clearInterval(challengeInterval); challengeInterval = null; }
    if (challengeTimerInterval) { clearInterval(challengeTimerInterval); challengeTimerInterval = null; }
    kycData.selfieImage = null;
    kycData.faceMatchPercent = 0;

    // Reset face result
    var faceResult = document.getElementById('faceResult');
    if (faceResult) {
        faceResult.style.display = 'none';
        var checks = ['livenessBlink', 'livenessSpoof', 'livenessDeepfake', 'livenessDepth'];
        checks.forEach(function(id) {
            var el = document.getElementById(id);
            if (el) { el.innerHTML = '&#10060;'; el.style.color = ''; }
        });
        var cItem = document.getElementById('livenessChallenge');
        if (cItem && cItem.parentElement) {
            var cParent = cItem.parentElement;
            cParent.innerHTML = '<span id="livenessChallenge">&#10060;</span> 4-Step Challenge';
            cParent.style.color = '';
        }
        var matchText = document.getElementById('faceMatchText');
        if (matchText) { matchText.textContent = 'Running enhanced AI verification...'; matchText.style.color = ''; }
        var matchPct = document.getElementById('faceMatchPercent');
        if (matchPct) matchPct.textContent = '0%';
    }

    // Hide score details
    var scoreDetails = document.getElementById('scoreDetails');
    if (scoreDetails) { scoreDetails.style.display = 'none'; scoreDetails.innerHTML = ''; }

    // Show start button, hide others
    var submitBtn = document.getElementById('submitKycBtn');
    if (submitBtn) submitBtn.disabled = true;
    var retryBtn = document.getElementById('retryFaceBtn');
    if (retryBtn) retryBtn.style.display = 'none';
    var startBtn = document.getElementById('startChallengeBtn');
    if (startBtn) {
        startBtn.style.display = '';
        startBtn.disabled = false;
        startBtn.textContent = '\u{1F50D} Start Live Verification';
    }
    var instruction = document.getElementById('challengeInstruction');
    if (instruction) instruction.style.display = 'none';
    var actionStatus = document.getElementById('challengeActionStatus');
    if (actionStatus) actionStatus.style.display = 'none';
    var seqProgress = document.getElementById('challengeSequenceProgress');
    if (seqProgress) seqProgress.style.display = 'none';
    var sidebar = document.getElementById('challengeRightPanel');
    if (sidebar) sidebar.style.display = 'none';
    var debugPanel = document.getElementById('debugPanel');
    if (debugPanel) debugPanel.style.display = 'none';
    var frameCount = document.getElementById('challengeFrameCount');
    if (frameCount) frameCount.style.display = 'none';

    // Reset left panel
    var leftPanel = document.getElementById('challengeLeftPanel');
    if (leftPanel) {
        var panelIcon = leftPanel.querySelector('.panel-icon');
        if (panelIcon) panelIcon.textContent = '\u{1F441}\uFE0F';
        var panelInstr = leftPanel.querySelector('.panel-instructions');
        if (panelInstr) panelInstr.innerHTML = '<strong>Position your face</strong> within the guide. Complete 4 challenges to prove you are live.';
        leftPanel.querySelectorAll('.step-item').forEach(function(el, i) {
            el.className = 'step-item';
            var stepNum = el.querySelector('.step-num');
            if (stepNum) stepNum.textContent = (i + 1);
            if (el.lastChild) el.lastChild.textContent = 'Challenge ' + (i + 1);
        });
    }
    var seqSteps = document.getElementById('sequenceSteps');
    if (seqSteps) seqSteps.innerHTML = '';
    var timerFill = document.getElementById('challengeTimerFill');
    if (timerFill) { timerFill.style.transition = 'none'; timerFill.style.width = '0%'; timerFill.className = 'challenge-timer-fill'; }

    // Ensure webcam is running — start if needed, disable button until ready
    if (!webcamStream) {
        var sb = document.getElementById('startChallengeBtn');
        if (sb) { sb.disabled = true; sb.textContent = 'Starting camera...'; }
        startWebcam().then(function() {
            if (sb) { sb.disabled = false; sb.textContent = '\u{1F50D} Start Live Verification'; }
        }).catch(function() {
            if (sb) { sb.disabled = false; sb.textContent = '\u{1F50D} Start Live Verification'; }
        });
    }
    } catch (e) {
        console.error('retryFaceVerification error:', e);
    }
}

function captureSelfie() {
    const video = document.getElementById('webcam');
    if (!video || !video.videoWidth) {
        showAlert('Camera not available. Please allow camera access.', 'error');
        return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    kycData.selfieImage = canvas.toDataURL('image/jpeg', 0.8);
    showToast('Selfie captured!', 'success');
    performFaceVerification();
}

function captureFrame() {
    const video = document.getElementById('webcam');
    if (!video || !video.videoWidth) return null;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.8);
}

function getChallengePrompt(type) {
    const prompts = {
        'blink':       { icon: '\u{1F440}', text: 'Blink both eyes', tip: 'Close and open both eyes naturally' },
        'open_mouth':  { icon: '\u{1F62E}', text: 'Open your mouth', tip: 'Open your mouth as if saying "Ah"' },
        'shake_head':  { icon: '\u{1F645}', text: 'Shake your head no', tip: 'Turn head left then right, like saying "no"' },
        'look_left':   { icon: '\u{1F448}', text: 'Look to your left', tip: 'Look left without turning your head fully' },
        'look_right':  { icon: '\u{1F449}', text: 'Look to your right', tip: 'Look right without turning your head fully' },
        'look_up':     { icon: '\u{1F446}', text: 'Look up', tip: 'Tilt your head up, then back to center' }
    };
    return prompts[type] || { icon: '\u{1F3AF}', text: type, tip: '' };
}

async function startLivenessChallenge() {
    const startBtn = document.getElementById('startChallengeBtn');
    startBtn.disabled = true;
    startBtn.textContent = 'Initializing...';
    challengeFrames = [];
    challengeActive = false;
    challengeSessionId = null;
    challengeCurrentIndex = 0;
    challengeResults = [];

    const video = document.getElementById('webcam');
    if (!video || !webcamStream) {
        showToast('Camera not available. Please allow camera access and try again.', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '\u{1F50D} Start Live Verification';
        return;
    }

    try {
        const rs = video.readyState;
        if (rs < 2 || video.videoWidth === 0) {
            await new Promise((resolve) => {
                let waited = 0;
                const check = setInterval(() => {
                    waited += 200;
                    if ((video.readyState >= 2 && video.videoWidth > 0) || waited > 5000) {
                        clearInterval(check);
                        resolve();
                    }
                }, 200);
            });
        }
    } catch (e) { }

    if (!video || video.readyState < 2 || video.videoWidth === 0) {
        showToast('Camera not ready. Please allow camera access and retry.', 'error');
        startBtn.disabled = false;
        startBtn.textContent = '\u{1F50D} Start Live Verification';
        return;
    }

    // Step 1: Fetch challenge session from server
    try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 15000);
        const res = await fetch(AI_API + '/liveness/challenge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (typeof getAuthToken === 'function' ? getAuthToken() : '') },
            body: JSON.stringify({}),
            signal: controller.signal
        });
        clearTimeout(t);
        const result = await res.json();
        if (!result.success) throw new Error(result.error || 'Failed to generate challenge');
        challengeSessionId = result.data.session_id;
        challengeTotalCount = result.data.total_challenges || 4;
        challengeData = result.data.challenge;
    } catch (err) {
        // Offline fallback — generate 4 local random challenges
        var allTypes = ['blink', 'open_mouth', 'shake_head', 'look_left', 'look_right', 'look_up'];
        var shuffled = allTypes.sort(() => Math.random() - 0.5).slice(0, 4);
        challengeSessionId = 'local-' + Date.now();
        challengeTotalCount = 4;
        challengeCurrentIndex = 0;
        challengeData = {
            challenge_type: shuffled[0],
            challenge_sequence: [shuffled[0]],
            prompt: getChallengePrompt(shuffled[0]).text,
        };
        // Store remaining challenges in a local "session"
        window.__localChallenges = shuffled;
    }

    if (startBtn) startBtn.style.display = 'none';

    // Build challenges array for step list updates
    var challenges = [];
    if (challengeData && challengeData.challenge_sequence) {
        challenges = challengeData.challenge_sequence.slice();
    } else if (window.__localChallenges) {
        challenges = window.__localChallenges.map(function(t) {
            return { challenge_type: t, challenge_sequence: [t] };
        });
    }
    // Ensure array has entries for all steps (server sends one-at-a-time)
    while (challenges.length < challengeTotalCount) {
        challenges.push(null);
    }

    const instruction = document.getElementById('challengeInstruction');
    const icon = document.getElementById('challengeIcon');
    const text = document.getElementById('challengeText');
    const frameCount = document.getElementById('challengeFrameCount');
    const seqProgress = document.getElementById('challengeSequenceProgress');
    const seqSteps = document.getElementById('sequenceSteps');
    const actionStatus = document.getElementById('challengeActionStatus');
    const actionRingFill = document.getElementById('actionRingFill');
    const actionPercent = document.getElementById('actionPercent');
    const actionLabel = document.getElementById('actionLabel');
    const timerFill = document.getElementById('challengeTimerFill');
    const timerText = document.getElementById('challengeTimerText');

    // Build 4-step progress indicator
    function buildStepIndicators() {
        seqSteps.innerHTML = '';
        for (let i = 0; i < challengeTotalCount; i++) {
            if (i > 0) {
                const arrow = document.createElement('span');
                arrow.className = 'sequence-arrow';
                arrow.textContent = '\u2192';
                seqSteps.appendChild(arrow);
            }
            const el = document.createElement('span');
            el.className = 'sequence-step';
            el.id = 'seqStep' + i;
            el.textContent = (i + 1);
            seqSteps.appendChild(el);
        }
    }

    function updateStepUI(index, currentChallenge) {
        const cp = getChallengePrompt(currentChallenge.challenge_type);
        icon.textContent = cp.icon;
        text.textContent = cp.text;
        actionLabel.textContent = cp.tip || 'Follow the instruction';

        // Update header
        var stepLabel = document.getElementById('challengeStepLabel');
        var stepCounter = document.getElementById('challengeStepCounter');
        var tipEl = document.getElementById('challengeTip');
        if (stepLabel) stepLabel.textContent = 'Challenge';
        if (stepCounter) stepCounter.textContent = (index + 1) + ' / ' + challengeTotalCount;
        if (tipEl) tipEl.textContent = cp.tip || '';

        // Update left panel step list
        var leftPanel = document.getElementById('challengeLeftPanel');
        if (leftPanel) {
            var steps = leftPanel.querySelectorAll('.step-item');
            steps.forEach(function(el, i) {
                if (i < index) {
                    var prevResult = challengeResults[i];
                    if (prevResult && prevResult.passed) {
                        el.className = 'step-item done';
                        el.querySelector('.step-num').textContent = '\u2713';
                        if (challenges[i]) {
                            var ch = challenges[i];
                            var chType = (typeof ch === 'string') ? ch : (ch.challenge_type || '');
                            el.lastChild.textContent = (chType ? getChallengePrompt(chType).text : 'Completed') + ' \u2713';
                        }
                    } else {
                        el.className = 'step-item failed';
                        el.querySelector('.step-num').textContent = '\u2717';
                        if (challenges[i]) {
                            var chF = challenges[i];
                            var chTypeF = (typeof chF === 'string') ? chF : (chF.challenge_type || '');
                            el.lastChild.textContent = (chTypeF ? getChallengePrompt(chTypeF).text : 'Challenge ' + (i + 1)) + ' \u2717';
                        }
                    }
                } else if (i === index) {
                    el.className = 'step-item active';
                    el.querySelector('.step-num').textContent = (i + 1);
                    el.lastChild.textContent = cp.text;
                } else {
                    el.className = 'step-item';
                    el.querySelector('.step-num').textContent = (i + 1);
                    el.lastChild.textContent = 'Challenge ' + (i + 1);
                }
            });
        }

        // Update step indicators
        for (let i = 0; i < challengeTotalCount; i++) {
            const el = document.getElementById('seqStep' + i);
            if (!el) continue;
            if (i < index) {
                var seqResult = challengeResults[i];
                if (seqResult && seqResult.passed) {
                    el.className = 'sequence-step done';
                    el.textContent = '\u2713';
                } else {
                    el.className = 'sequence-step failed';
                    el.textContent = '\u2717';
                }
            } else if (i === index) {
                el.className = 'sequence-step active';
                el.textContent = (i + 1);
            } else {
                el.className = 'sequence-step';
                el.textContent = (i + 1);
            }
        }

        actionPercent.textContent = '5s';
        if (typeof timerText !== 'undefined' && timerText) timerText.textContent = '5s';
        frameCount.textContent = 'Capturing...';
        actionRingFill.setAttribute('stroke-dasharray', '0, 100');
        if (typeof timerFill !== 'undefined' && timerFill) {
            timerFill.style.transition = 'none';
            timerFill.style.width = '100%';
            timerFill.style.background = 'linear-gradient(90deg, #22c55e, #4ade80)';
            timerFill.className = 'challenge-timer-fill';
        }
    }

    // Show UI
    const sidebar = document.getElementById('challengeRightPanel');
    if (sidebar) sidebar.style.display = 'flex';
    const leftPanel = document.getElementById('challengeLeftPanel');
    if (leftPanel) {
        leftPanel.querySelector('.panel-icon').textContent = '\u{1F3AC}';
        leftPanel.querySelector('.panel-instructions').innerHTML = '<strong>Follow each challenge</strong> as shown on the right. Keep your face centered.';
    }
    if (instruction) instruction.style.display = 'flex';
    if (frameCount) frameCount.style.display = 'block';
    if (seqProgress) seqProgress.style.display = 'block';
    if (actionStatus) actionStatus.style.display = 'flex';
    buildStepIndicators();
    updateStepUI(0, challengeData);

    // Run through all 4 challenges sequentially
    let currentChallenge = challengeData;
    let maxRetries = 0;
    let lastChallengeFrames = [];
    let allCapturedFrames = [];

    for (let idx = 0; idx < challengeTotalCount; idx++) {
        challengeCurrentIndex = idx;
        if (idx > 0 && window.__localChallenges) {
            currentChallenge = {
                challenge_type: window.__localChallenges[idx],
                challenge_sequence: [window.__localChallenges[idx]]
            };
        }
        updateStepUI(idx, currentChallenge);

        challengeActive = true;
        let capturedFrames = [];
        let retries = 0;
        let stepPassed = false;

        // Show debug panel
        const debugPanel = document.getElementById('debugPanel');
        const debugContent = document.getElementById('debugContent');
        if (debugPanel) debugPanel.style.display = 'block';

        function updateDebug(msg) {
            if (debugContent) {
                debugContent.innerHTML = msg;
            }
            console.log('[DEBUG]', msg.replace(/<br>/g, ' | ').replace(/<[^>]*>/g, ''));
        }

        while (!stepPassed && retries <= maxRetries) {
            // 5-second continuous capture window
            capturedFrames = [];
            const captureStart = Date.now();
            const videoEl = document.getElementById('webcam');

            // Reset and start timer bar animation
            if (timerFill) {
                timerFill.style.transition = 'none';
                timerFill.style.width = '100%';
                timerFill.style.background = 'linear-gradient(90deg, #22c55e, #4ade80)';
                void timerFill.offsetWidth;
                timerFill.style.transition = 'width 5s linear, background 0.5s ease';
                timerFill.style.width = '0%';
            }

            actionLabel.textContent = 'Performing action...';

            updateDebug(
                '<b>Challenge:</b> ' + currentChallenge.challenge_type + '<br>' +
                '<b>Video:</b> ' + (videoEl ? videoEl.videoWidth + 'x' + videoEl.videoHeight + ' readyState=' + videoEl.readyState : 'null') + '<br>' +
                '<b>Stream:</b> ' + (webcamStream ? 'active' : 'null') + '<br>' +
                'Capturing frames...'
            );

            while (Date.now() - captureStart < CHALLENGE_STEP_TIMEOUT) {
                if (!challengeActive) break;
                await sleep(CHALLENGE_FRAME_INTERVAL);
                const frame = captureFrame();
                if (frame) capturedFrames.push(frame);

                const remaining = Math.max(0, Math.ceil((CHALLENGE_STEP_TIMEOUT - (Date.now() - captureStart)) / 1000));
                if (typeof timerText !== 'undefined' && timerText) timerText.textContent = remaining + 's';
                actionPercent.textContent = remaining + 's';
                frameCount.textContent = capturedFrames.length + ' frames captured';
                const pct = Math.min(100, Math.round((capturedFrames.length / 15) * 100));
                actionRingFill.setAttribute('stroke-dasharray', pct + ', 100');

                // Timer color: green > 4s, yellow > 2s, red <= 2s
                if (typeof timerFill !== 'undefined' && timerFill) {
                    timerFill.style.transition = 'width 0.3s linear';
                    timerFill.style.width = (remaining / 5 * 100) + '%';
                    if (remaining <= 1) {
                        timerFill.className = 'challenge-timer-fill danger';
                    } else if (remaining <= 3) {
                        timerFill.className = 'challenge-timer-fill warning';
                    } else {
                        timerFill.className = 'challenge-timer-fill';
                    }
                }

                // Update debug every 5 frames
                if (capturedFrames.length % 5 === 0 && capturedFrames.length > 0) {
                    const lastFrame = capturedFrames[capturedFrames.length - 1];
                    const frameSizeKB = Math.round(lastFrame.length / 1024);
                    updateDebug(
                        '<b>Challenge:</b> ' + currentChallenge.challenge_type + '<br>' +
                        '<b>Frames:</b> ' + capturedFrames.length + ' | Size: ~' + frameSizeKB + 'KB each<br>' +
                        '<b>Video:</b> ' + videoEl.videoWidth + 'x' + videoEl.videoHeight + '<br>' +
                        '<b>Time left:</b> ' + remaining + 's<br>' +
                        '<b>Last frame prefix:</b> ' + lastFrame.substring(0, 50) + '...'
                    );
                }
            }

            lastChallengeFrames = capturedFrames;
            // Accumulate all frames for best selfie selection
            allCapturedFrames = allCapturedFrames.concat(capturedFrames);

            if (!challengeActive) break;

            if (capturedFrames.length < 6) {
                retries++;
                if (retries <= maxRetries) {
                    showToast('Not enough frames. Please try again.', 'warning');
                    updateDebug('<b style="color:#ff4444">ERROR:</b> Only ' + capturedFrames.length + ' frames captured (need 6+). Retrying...');
                    await sleep(800);
                    continue;
                } else {
                    challengeResults.push({
                        challenge: currentChallenge.challenge_type,
                        passed: false,
                        reason: 'Insufficient frames captured',
                    });
                    updateDebug('<b style="color:#ff4444">FAILED:</b> Insufficient frames after retries');
                    break;
                }
            }

            actionLabel.textContent = 'Verifying...';

            // Send for verification
            if (challengeSessionId && challengeSessionId.startsWith('local-')) {
                // Offline: always pass local challenges
                stepPassed = true;
                updateDebug('<b style="color:#00ff88">OFFLINE PASS:</b> Local challenge session');
                await sleep(300);
            } else {
                const totalSizeKB = Math.round(capturedFrames.reduce((s, f) => s + f.length, 0) / 1024);
                updateDebug('<b>Sending to server...</b><br>' +
                    'Frames: ' + capturedFrames.length + '<br>' +
                    'Total payload: ~' + totalSizeKB + 'KB<br>' +
                    'Challenge: ' + currentChallenge.challenge_type);
                try {
                    const reqStart = Date.now();
                    const verifyRes = await fetch(AI_API + '/liveness/verify-challenge', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (typeof getAuthToken === 'function' ? getAuthToken() : '') },
                        body: JSON.stringify({
                            session_id: challengeSessionId,
                            challenge: currentChallenge,
                            frames: capturedFrames,
                        })
                    });
                    const reqTime = Date.now() - reqStart;
                    const verifyResult = await verifyRes.json();
                    if (!verifyResult.success) throw new Error(verifyResult.error || 'Verify failed');

                    const data = verifyResult.data;
                    var stepPassing = data.passed || data.challengePassed;
                    updateDebug(
                        '<b>Server Response (' + reqTime + 'ms):</b><br>' +
                        'Status: ' + verifyRes.status + '<br>' +
                        'Passed: ' + stepPassing + '<br>' +
                        'Confidence: ' + (data.livenessScore || data.confidence || '--') + '<br>' +
                        'Reason: ' + (data.reason || 'none') + '<br>' +
                        'Challenge: ' + currentChallenge.challenge_type
                    );

                    if (stepPassing) {
                        stepPassed = true;
                        challengeResults.push({
                            challenge: currentChallenge.challenge_type,
                            passed: true,
                        });
                        // Track completed challenge for left panel
                        challenges[idx] = { challenge_type: currentChallenge.challenge_type };

                        if (data.next_challenge) {
                            currentChallenge = data.next_challenge;
                            // Also store next challenge so it shows correct name when marked done
                            if (idx + 1 < challengeTotalCount) {
                                challenges[idx + 1] = { challenge_type: currentChallenge.challenge_type };
                            }
                        }

                        // On last step, store final verdict data
                        if (idx === challengeTotalCount - 1 && data.verdict) {
                            window.__finalChallengeResult = data;
                        }
                    } else {
                        retries++;
                        updateDebug(
                            '<div style="color:#f87171;font-weight:600;margin-bottom:4px">Challenge Failed</div>' +
                            '<div style="color:#94a3b8;font-size:10px">' + (data.reason || 'Unknown error') + '</div>' +
                            '<div style="color:#64748b;font-size:10px;margin-top:4px">Retry ' + retries + '/' + maxRetries + '</div>'
                        );
                        if (retries <= maxRetries) {
                            showToast('Try again — ' + (data.reason || 'challenge failed'), 'warning');
                            await sleep(800);
                        } else {
                            challengeResults.push({
                                challenge: currentChallenge.challenge_type,
                                passed: false,
                                reason: data.reason || 'Failed after retries',
                            });
                            updateDebug('<div style="color:#f87171;font-weight:600">Max retries reached</div><div style="color:#64748b;font-size:10px">' + (data.reason || '') + '</div>');
                            break;
                        }
                    }
                } catch (err) {
                    retries++;
                    updateDebug('<b style="color:#ff4444">NETWORK ERROR:</b> ' + err.message);
                    if (retries > maxRetries) {
                        showToast('Verification error: ' + err.message, 'error');
                        break;
                    }
                    await sleep(500);
                }
            }
        }

        if (!stepPassed) {
            const failEl = document.getElementById('seqStep' + idx);
            if (failEl) { failEl.className = 'sequence-step failed'; failEl.textContent = '\u2717'; }
        }
    }

    // Build final challenge result from accumulated results (even if some failed)
    if (!window.__finalChallengeResult) {
        var completedCount = challengeResults.length;
        var passedCount = challengeResults.filter(function(r) { return r.passed; }).length;
        window.__finalChallengeResult = {
            challengePassed: passedCount >= 3,
            challengeCount: passedCount,
            livenessScore: passedCount / Math.max(completedCount, 1),
        };
    }

    challengeActive = false;
    if (challengeTimerInterval) { clearInterval(challengeTimerInterval); challengeTimerInterval = null; }

    actionLabel.textContent = 'Completed!';
    actionRingFill.setAttribute('stroke-dasharray', '100, 100');
    actionPercent.textContent = '100%';

    // Pick the best selfie frame from ALL challenges
    // Use frame from early in the first challenge — user is centered and still
    if (allCapturedFrames.length > 0) {
        // Pick frame ~3 captures in (about 450ms) — user is centered before moving
        var bestIdx = Math.min(3, Math.floor(allCapturedFrames.length / 2));
        kycData.selfieImage = allCapturedFrames[bestIdx];
    }

    setTimeout(() => {
        if (instruction) instruction.style.display = 'none';
        if (actionStatus) actionStatus.style.display = 'none';
        if (seqProgress) seqProgress.style.display = 'none';
        const sb = document.getElementById('challengeRightPanel');
        if (sb) sb.style.display = 'none';
        const lp = document.getElementById('challengeLeftPanel');
        if (lp) {
            lp.querySelector('.panel-icon').textContent = '\u{2705}';
            lp.querySelector('.panel-instructions').innerHTML = '<strong>Verification complete</strong>';
            lp.querySelectorAll('.step-item').forEach(function(el, i) {
                var res = challengeResults[i];
                if (res && res.passed) {
                    el.className = 'step-item done';
                    el.querySelector('.step-num').textContent = '\u2713';
                    if (challenges[i]) {
                        var ch = challenges[i];
                        var chType = (typeof ch === 'string') ? ch : (ch.challenge_type || '');
                        if (chType) el.lastChild.textContent = getChallengePrompt(chType).text + ' \u2713';
                    }
                } else {
                    el.className = 'step-item failed';
                    el.querySelector('.step-num').textContent = '\u2717';
                    if (challenges[i]) {
                        var chF = challenges[i];
                        var chTypeF = (typeof chF === 'string') ? chF : (chF.challenge_type || '');
                        if (chTypeF) el.lastChild.textContent = getChallengePrompt(chTypeF).text + ' \u2717';
                    }
                }
            });
        }
        performFaceVerification();
    }, 600);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function performFaceVerification() {
    const faceResult = document.getElementById('faceResult');
    const submitBtn = document.getElementById('submitKycBtn');
    if (!faceResult) return;
    faceResult.style.display = 'block';
    document.getElementById('faceMatchText').textContent = 'Running AI verification (face match, liveness, anti-spoofing, deepfake)...';
    document.getElementById('faceMatchPercent').textContent = '0%';
    const blinkEl = document.getElementById('livenessBlink');
    const spoofEl = document.getElementById('livenessSpoof');
    const deepfakeEl = document.getElementById('livenessDeepfake');
    const challengeEl = document.getElementById('livenessChallenge');
    const depthEl = document.getElementById('livenessDepth');
    if (blinkEl) { blinkEl.innerHTML = '&#10060;'; blinkEl.style.color = ''; }
    if (spoofEl) { spoofEl.innerHTML = '&#10060;'; spoofEl.style.color = ''; }
    if (deepfakeEl) { deepfakeEl.innerHTML = '&#10060;'; deepfakeEl.style.color = ''; }
    if (challengeEl) { challengeEl.innerHTML = '&#10060;'; challengeEl.style.color = ''; }
    if (depthEl) { depthEl.innerHTML = '&#10060;'; depthEl.style.color = ''; }
    submitBtn.disabled = true;

    if (!kycData.selfieImage) {
        document.getElementById('faceMatchText').textContent = 'No selfie captured.';
        document.getElementById('faceMatchText').style.color = 'var(--danger)';
        return;
    }

    var isReKyc = !!kycData.reKycAppId;
    if (!isReKyc) {
        var urlCheck = new URLSearchParams(window.location.search);
        var wrd = window.__rekycData;
        if (!wrd) { try { var r = localStorage.getItem('rekycData') || localStorage.getItem('reKycData'); wrd = r ? JSON.parse(r) : null; } catch(e) {} }
        if (urlCheck.get('rekyc') === '1' || kycData.reKyc || wrd) {
            isReKyc = true;
            if (wrd && wrd.appId) kycData.reKycAppId = wrd.appId;
            if (wrd && wrd.id) kycData.reKycAppId = kycData.reKycAppId || wrd.id;
            kycData.reKyc = true;
        }
    }
    var reKycAppId = kycData.reKycAppId;
    if (!reKycAppId) {
        try { var kd = JSON.parse(localStorage.getItem('kycData') || '{}'); reKycAppId = kd.appId || kd.id; } catch(e) {}
    }
    const idFile = kycData.aadhaarFile || kycData.panFile;
    if (!idFile && !isReKyc) {
        document.getElementById('faceMatchText').textContent = 'No ID document available for comparison.';
        document.getElementById('faceMatchText').style.color = 'var(--danger)';
        return;
    }

    try {
        let idBase64;
        let profilePhotoBase64;
        var idLoaded = false;

        // KYC: Read uploaded document
        if (idFile) {
            idBase64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(idFile);
            });
            idLoaded = true;
        }

        // Read profile photo if uploaded
        if (kycData.profilePhoto) {
            profilePhotoBase64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = reject;
                reader.readAsDataURL(kycData.profilePhoto);
            });
        }

        // Re-KYC: Fetch stored documents from the old approved application
        if (isReKyc && reKycAppId) {
            const token = getAuthToken();
            console.log('[ReKYC] Fetching old approved app docs, appId:', reKycAppId);

            // 1. Fetch profile photo FIRST — best source for face comparison (headshot)
            if (!profilePhotoBase64) {
                try {
                    const photoResp = await fetch('/api/kyc/' + reKycAppId + '/photo', {
                        headers: { 'Authorization': 'Bearer ' + token }
                    });
                    if (photoResp.ok) {
                        const photoBlob = await photoResp.blob();
                        if (photoBlob.size > 500) {
                            profilePhotoBase64 = await new Promise((resolve) => {
                                const reader = new FileReader();
                                reader.onload = () => resolve(reader.result);
                                reader.readAsDataURL(photoBlob);
                            });
                            console.log('[ReKYC] Loaded profile photo, size:', photoBlob.size);
                        }
                    }
                } catch (_) { }
            }

            // 2. Use profile photo as id_face (headshot = reliable face detection)
            if (profilePhotoBase64) {
                idBase64 = profilePhotoBase64;
                idLoaded = true;
                console.log('[ReKYC] Using profile photo for face match');
            }

            // 3. Try Aadhaar/PAN as fallback id_face if no profile photo
            if (!idLoaded) {
                const idEndpoints = [
                    '/api/kyc/' + reKycAppId + '/aadhaar-front',
                    '/api/kyc/' + reKycAppId + '/pan-card',
                    '/api/kyc/' + reKycAppId + '/document'
                ];
                for (const url of idEndpoints) {
                    try {
                        const resp = await fetch(url, { headers: { 'Authorization': 'Bearer ' + token } });
                        if (resp.ok) {
                            const blob = await resp.blob();
                            if (blob.size > 500) {
                                idBase64 = await new Promise((resolve) => {
                                    const reader = new FileReader();
                                    reader.onload = () => resolve(reader.result);
                                    reader.readAsDataURL(blob);
                                });
                                idLoaded = true;
                                console.log('[ReKYC] Loaded ID doc from:', url, 'size:', blob.size);
                                break;
                            }
                        }
                    } catch (e) { console.warn('[ReKYC] ID fetch failed:', url, e); }
                }
            }

            if (!idLoaded) {
                console.error('[ReKYC] FAILED: No documents found for appId:', reKycAppId);
            }
        }

        // Merge session-based sequential challenge results
        var sessionFinal = window.__finalChallengeResult;
        var challengePassed = sessionFinal ? sessionFinal.challengePassed : false;
        var challengeCount = sessionFinal ? sessionFinal.challengeCount : 0;
        var livenessScore = sessionFinal ? sessionFinal.livenessScore : 0;

        // Build payload
        var payload = { selfie: kycData.selfieImage };
        if (idBase64) {
            payload.id_face = idBase64;
        }
        if (profilePhotoBase64) {
            payload.profile_photo = profilePhotoBase64;
        }
        if (isReKyc) {
            payload.rekyc = true;
        }
        if (sessionFinal) {
            payload.session_result = { challengePassed: sessionFinal.challengePassed, livenessScore: sessionFinal.livenessScore };
            // Pass session_id so server can look up full session data
            if (challengeSessionId && !challengeSessionId.startsWith('local-')) {
                payload.session_id = challengeSessionId;
            }
        }

        let data = null;
        try {
            const ctrl = new AbortController();
            const tm = setTimeout(() => ctrl.abort(), 120000);
            const response = await fetch(AI_API + '/detailed-verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (typeof getAuthToken === 'function' ? getAuthToken() : '') },
                body: JSON.stringify(payload),
                signal: ctrl.signal
            });
            clearTimeout(tm);
            const result = await response.json();
            if (result && result.success) data = result.data;
            else throw new Error((result && result.error) ? result.error : 'Verification failed');
        } catch (e) {
            try {
                const ctrl2 = new AbortController();
                const tm2 = setTimeout(() => ctrl2.abort(), 60000);
                const res2 = await fetch(AI_API + '/liveness/combined', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (typeof getAuthToken === 'function' ? getAuthToken() : '') },
                    body: JSON.stringify(payload), signal: ctrl2.signal
                });
                clearTimeout(tm2);
                const r2 = await res2.json();
                if (r2 && r2.success) data = r2.data;
                else throw new Error(r2.error || 'Combined verification failed');
            } catch (e2) {
                throw new Error('Face verification service unavailable');
            }
        }

        if (!data || typeof data !== 'object') {
            throw new Error('Invalid response from verification service');
        }

        var fm = Math.round(((data.confidence && data.confidence.face_similarity !== undefined) ? data.confidence.face_similarity : (data.face_match_score || 0)) * 100) || 0;
        var lv = Math.round(((data.confidence && data.confidence.liveness !== undefined) ? data.confidence.liveness : (data.liveness_score || 0)) * 100) || 0;
        var sl = Math.round(((data.confidence && data.confidence.spoof !== undefined) ? data.confidence.spoof : (data.spoof_risk_score || 0)) * 100) || 0;
        var df = Math.round(((data.confidence && data.confidence.deepfake !== undefined) ? data.confidence.deepfake : 0) * 100) || 0;
        var status = data.status || data.verdict || 'REJECTED';

        // Trust backend verdict — no frontend override
        // Backend enforces: faceMatchPassed AND livenessPassed AND NOT spoofDetected AND NOT deepfakeDetected
        var serverLivenessConfirmed = data.sessionLivenessConfirmed || false;

        var sLivenessPassed = (challengePassed || serverLivenessConfirmed) || (lv >= 60);
        var sAntiSpoofPassed = data.spoofDetected ? false : (sl > 0 || lv > 20);
        var sDeepfake = (data.deepfakeDetected !== undefined) ? data.deepfakeDetected : (df > 50);
        var isReKycResponse = data.rekyc === true;
        var sFaceMatchPassed = isReKycResponse ? (fm >= 40) : (fm >= 60);
        var fs = data.final_score || Math.round((fm * 0.3 + lv * 0.3 + (100 - (data.spoofDetected ? 100 : sl)) * 0.2 + (100 - df) * 0.2));

        animateMatchPercent(fm);

        function icon(pass) { return pass ? '&#9989;' : '&#10060;'; }
        function col(pass) { return pass ? 'var(--success)' : 'var(--danger)'; }

        if (blinkEl) { blinkEl.innerHTML = icon(sLivenessPassed); blinkEl.style.color = col(sLivenessPassed); }
        if (spoofEl) { spoofEl.innerHTML = icon(sAntiSpoofPassed); spoofEl.style.color = col(sAntiSpoofPassed); }
        if (deepfakeEl) { deepfakeEl.innerHTML = icon(!sDeepfake); deepfakeEl.style.color = col(!sDeepfake); }
        if (challengeEl) { challengeEl.innerHTML = icon(challengePassed); challengeEl.style.color = col(challengePassed); }
        if (challengeCount > 0) {
            var cItem = document.getElementById('livenessChallenge');
            if (cItem && cItem.parentElement) {
                var cParent = cItem.parentElement;
                cParent.innerHTML = '<span id="livenessChallenge">' + icon(challengePassed) + '</span> ' + challengeCount + '-Step Challenge';
                cParent.style.color = col(challengePassed);
            }
        }
        if (depthEl) {
            depthEl.innerHTML = icon(sFaceMatchPassed);
            depthEl.style.color = col(sFaceMatchPassed);
        }

        kycData.faceMatchPercent = fm;

        var scoreDetails = document.getElementById('scoreDetails');
        if (scoreDetails) {
            var challengeInfo = challengeCount > 0 ? '<div class="score-row"><span>Challenges Passed:</span><strong>' + challengeCount + '/4</strong></div>' : '';
            var faceSection = '';
            if (data.face_three_way) {
                var ftw = data.face_three_way;
                var fmt = function(v) { return (v * 100).toFixed(1) + '%'; };
                var ficon = function(p) { return p ? '&#9989;' : '&#10060;'; };
                faceSection =
                    '<div class="score-row" style="font-weight:600;color:var(--primary,#1a73e8)"><span>Face Match (3-way):</span></div>' +
                    '<div class="score-row" style="padding-left:16px"><span>ID vs Selfie:</span><strong>' + ficon(ftw.id_vs_selfie.passed) + ' ' + fmt(ftw.id_vs_selfie.similarity) + '</strong></div>' +
                    '<div class="score-row" style="padding-left:16px"><span>ID vs Photo:</span><strong>' + ficon(ftw.id_vs_photo.passed) + ' ' + fmt(ftw.id_vs_photo.similarity) + '</strong></div>' +
                    '<div class="score-row" style="padding-left:16px"><span>Photo vs Selfie:</span><strong>' + ficon(ftw.photo_vs_selfie.passed) + ' ' + fmt(ftw.photo_vs_selfie.similarity) + '</strong></div>';
            } else {
                faceSection = '<div class="score-row"><span>Face Match:</span><strong>' + fm + '%</strong></div>';
            }
            scoreDetails.innerHTML =
                faceSection +
                '<div class="score-row"><span>Liveness:</span><strong>' + lv + '%</strong></div>' +
                '<div class="score-row"><span>Anti-Spoof:</span><strong>' + (data.spoofDetected ? 'FAIL' : sl + '%') + '</strong></div>' +
                '<div class="score-row"><span>Deepfake:</span><strong>' + (data.deepfakeDetected ? 'DETECTED' : df + '%') + '</strong></div>' +
                challengeInfo +
                '<hr style="margin:8px 0;opacity:0.3">' +
                '<div class="score-row final"><span>Overall:</span><strong>' + fs + '%</strong></div>';
            scoreDetails.style.display = 'block';
        }

        if (status === 'VERIFIED' || status === 'APPROVED') {
            if (isReKycResponse) {
                document.getElementById('faceMatchText').textContent = 'RE-KYC VERIFIED | Face: ' + fm + '% | Liveness: ' + lv + '% | Final Score: ' + fs + '%';
            } else {
                document.getElementById('faceMatchText').textContent = 'VERIFIED | Face: ' + fm + '% | Final Score: ' + fs + '%';
            }
            document.getElementById('faceMatchText').style.color = 'var(--success)';
            submitBtn.disabled = false;
            showToast('Face verification successful!', 'success');
        } else {
            var reasons = data.rejection_reasons || data.reasons || [];
            var reason = reasons.length > 0 ? reasons.join('; ') : ('Verification rejected');
            document.getElementById('faceMatchText').textContent = 'REJECTED: ' + reason;
            document.getElementById('faceMatchText').style.color = 'var(--danger)';
            showToast('Face verification rejected: ' + reason, 'error');
        }
    } catch (err) {
        console.error('Face verification error:', err);
        document.getElementById('faceMatchText').textContent = 'Verification error: ' + err.message;
        document.getElementById('faceMatchText').style.color = 'var(--danger)';
        showToast('Face verification failed: ' + err.message, 'error');
    } finally {
        challengeData = null;
        challengeFrames = [];
        const retryBtn = document.getElementById('retryFaceBtn');
        if (retryBtn) retryBtn.style.display = 'inline-block';
    }
}

function animateMatchPercent(target) {
    let current = 0;
    const el = document.getElementById('faceMatchPercent');
    const interval = setInterval(() => {
        current += Math.max(1, Math.floor((target - current) / 5));
        if (current >= target) { current = target; clearInterval(interval); }
        el.textContent = current + '%';
    }, 80);
}

async function calculateFinalRiskScore() {
    let riskScore = 15;
    try {
        const response = await fetch(AI_API + '/risk-score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (typeof getAuthToken === 'function' ? getAuthToken() : '') },
            body: JSON.stringify({
                face_data: { match_percent: kycData.faceMatchPercent, face_detected: kycData.faceMatchPercent > 0 },
                device_data: { user_agent: navigator.userAgent, platform: navigator.platform }
            })
        });
        const result = await response.json();
        if (result.success && result.data) riskScore = result.data.risk_score || 15;
    } catch (err) {
        riskScore = kycData.faceMatchPercent < 85 ? 25 : 10;
    }
    kycData.riskScore = riskScore;
    const fill = document.getElementById('riskScoreFill');
    const scoreEl = document.getElementById('finalRiskScore');
    const labelEl = document.getElementById('finalRiskLabel');
    if (fill) {
        fill.style.width = kycData.riskScore + '%';
        fill.style.background = kycData.riskScore < 30 ? 'var(--success)' : kycData.riskScore < 60 ? 'var(--warning)' : 'var(--danger)';
    }
    if (scoreEl) scoreEl.textContent = kycData.riskScore + '/100';
    if (labelEl) {
        if (kycData.riskScore < 30) { labelEl.textContent = 'Low Risk'; labelEl.className = 'badge badge-success'; }
        else if (kycData.riskScore < 60) { labelEl.textContent = 'Medium Risk'; labelEl.className = 'badge badge-warning'; }
        else { labelEl.textContent = 'High Risk'; labelEl.className = 'badge badge-danger'; }
    }
}

function getClientIP() {
    // Return stored IP or try to fetch it
    if (window.__clientIP) return window.__clientIP;
    // Try fetching real IP (non-blocking)
    fetch('https://api.ipify.org?format=json')
        .then(function(r) { return r.json(); })
        .then(function(d) { if (d && d.ip) window.__clientIP = d.ip; })
        .catch(function() {});
    return '0.0.0.0';
}

// Pre-fetch IP on page load
getClientIP();

async function submitKYCApplication(showLoading) {
    const token = getAuthToken();
    if (!token) { showToast('Please login first', 'error'); return false; }
    if (showLoading) showToast('Submitting KYC application...', 'info');
    const ocr = kycData.ocrData || {};
    try {
        const submitRes = await fetch(KYC_API + '/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
            body: JSON.stringify({
                docType: kycData.aadhaarFile ? 'AADHAAR' : 'PAN',
                ocrName: ocr.name || '',
                ocrDob: ocr.dob || '',
                ocrIdNumber: ocr.idNumber || '',
                ocrPanNumber: ocr.panNumber || '',
                ocrAddress: ocr.address || '',
                gender: ocr.gender || '',
                mobile: kycData.mobile || '',
                email: kycData.email || '',
                accountType: kycData.accountType || 'savings',
                riskScore: kycData.riskScore,
                faceMatchPercent: kycData.faceMatchPercent,
                ipAddress: getClientIP(),
                applicationType: kycData.reKyc ? 'RE_KYC' : 'NORMAL'
            })
        });
        const submitResult = await submitRes.json();
        if (!submitResult.success || !submitResult.data) {
            showToast(submitResult.message || 'KYC submission failed', 'error');
            return false;
        }
        const appId = submitResult.data.applicationId;
        const appRef = submitResult.data.applicationRef;
        localStorage.setItem('kycAppId', appId);
        localStorage.setItem('kycAppRef', appRef);

        if (kycData.aadhaarFile && appId) {
            const fd = new FormData();
            fd.append('file', kycData.aadhaarFile);
            await fetch(KYC_API + '/' + appId + '/aadhaar-front', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token }, body: fd });
        }
        if (kycData.panFile && appId) {
            const fd = new FormData();
            fd.append('file', kycData.panFile);
            await fetch(KYC_API + '/' + appId + '/pan-card', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token }, body: fd });
        }
        if (kycData.profilePhoto && appId) {
            const fd = new FormData();
            fd.append('photo', kycData.profilePhoto);
            await fetch(KYC_API + '/' + appId + '/photo', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token }, body: fd });
        }
        if (kycData.selfieImage && appId) {
            const fd = new FormData();
            const blob = await fetch(kycData.selfieImage).then(r => r.blob());
            fd.append('selfie', blob, 'selfie.jpg');
            await fetch(KYC_API + '/' + appId + '/selfie', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token }, body: fd });
        }

        localStorage.setItem('kycData', JSON.stringify({
            status: 'PENDING',
            appId: appId,
            appRef: appRef,
            ocrName: kycData.ocrData ? kycData.ocrData.name : '',
            ocrDob: kycData.ocrData ? kycData.ocrData.dob : '',
            ocrIdNumber: kycData.ocrData ? kycData.ocrData.idNumber : '',
            ocrPanNumber: kycData.ocrData ? kycData.ocrData.panNumber : '',
            ocrAddress: kycData.ocrData ? kycData.ocrData.address : '',
            branch: kycData.ocrData ? kycData.ocrData.branch : '',
            mobile: kycData.mobile || '',
            email: kycData.email || '',
            accountType: kycData.accountType || '',
            riskScore: kycData.riskScore,
            faceMatch: kycData.faceMatchPercent
        }));
        localStorage.removeItem('kycStatusHtml');
        showToast('KYC submitted successfully!', 'success');
        return true;
    } catch (err) {
        console.error('KYC submit error:', err);
        showToast('KYC submission failed. Please try again.', 'error');
        return false;
    }
}

async function handleFinalSubmit() {
    var btn = document.getElementById('submitKycBtn');
    var isReKyc = !!(window.__rekycMode || kycData.reKyc || kycData.reKycAppId || new URLSearchParams(window.location.search).get('rekyc') === '1');
    if (btn) { btn.disabled = true; btn.textContent = 'Submitting...'; }
    if (isReKyc) {
        kycData.reKyc = true;
        if (kycData.profilePhoto && kycData.profilePhoto instanceof File) {
            var photoDataUrl = await new Promise(function(resolve) {
                var r = new FileReader();
                r.onload = function(e) { resolve(e.target.result); };
                r.onerror = function() { resolve(null); };
                r.readAsDataURL(kycData.profilePhoto);
            });
            if (photoDataUrl) {
                try {
                    var existing = JSON.parse(localStorage.getItem('kycData') || '{}');
                    existing.profilePhotoBase64 = photoDataUrl;
                    localStorage.setItem('kycData', JSON.stringify(existing));
                } catch(ex) {}
            }
        }
        localStorage.removeItem('rekycData');
        localStorage.removeItem('reKycData');
        window.location.href = 'rekyc-review.html';
        return;
    }
    var ok = await submitKYCApplication(true);
    if (ok) {
        window.location.href = 'kyc-status.html';
    } else {
        if (btn) { btn.disabled = false; btn.textContent = 'Submit KYC \u2192'; }
    }
}

        document.addEventListener('DOMContentLoaded', function() {
            var reKycData = window.__rekycData;
            if (!reKycData) {
                try {
                    var raw = localStorage.getItem('rekycData') || localStorage.getItem('reKycData');
                    reKycData = raw ? JSON.parse(raw) : null;
                } catch(e) { reKycData = null; }
            }
            var urlParams = new URLSearchParams(window.location.search);
            var isReKyc = !!(window.__rekycMode || (urlParams.get('rekyc') === '1' && reKycData));
            if (isReKyc && reKycData) {
                isReKyc = true;
                kycData.reKyc = true;
                if (reKycData.appId) kycData.reKycAppId = reKycData.appId;
                if (reKycData.name) kycData.ocrData = kycData.ocrData || {};
                if (reKycData.name) kycData.ocrData.name = reKycData.name;
                if (reKycData.dob) {
                    kycData.ocrData = kycData.ocrData || {};
                    var d = reKycData.dob;
                    if (d.indexOf('T') > 0) {
                        kycData.ocrData.dob = d.substring(0, 10);
                    } else if (d.indexOf('/') > 0) {
                        var parts = d.split('/');
                        kycData.ocrData.dob = parts[2] + '-' + parts[1] + '-' + parts[0];
                    } else {
                        kycData.ocrData.dob = d;
                    }
                }
                if (reKycData.idNumber) { kycData.ocrData = kycData.ocrData || {}; kycData.ocrData.idNumber = reKycData.idNumber; }
                if (reKycData.panNumber) { kycData.ocrData = kycData.ocrData || {}; kycData.ocrData.panNumber = reKycData.panNumber; }
                if (reKycData.address) { kycData.ocrData = kycData.ocrData || {}; kycData.ocrData.address = reKycData.address; }
                if (document.getElementById('appTypeIndicator')) {
                    document.getElementById('appTypeIndicator').textContent = 'Re-KYC Application';
                    document.getElementById('appTypeIndicator').style.display = 'inline-block';
                }
                var submitBtn = document.getElementById('submitKycBtn');
                if (submitBtn) submitBtn.textContent = 'Submit Re-KYC \u2192';
            }

            if (isReKyc) {
                if (typeof goToStep === 'function') {
                    goToStep(3);
                } else {
                    document.querySelectorAll('.kyc-step').forEach(function(el) { el.style.display = 'none'; });
                    var s3 = document.querySelector('.kyc-step[data-step="3"]');
                    if (s3) s3.style.display = 'block';
                }
            } else {
                localStorage.removeItem('rekycData');
                localStorage.removeItem('reKycData');
                goToStep(1);
            }
            populateOCRForm();

            var branchSelect = document.getElementById('ocrBranch');
            var branchManual = document.getElementById('ocrBranchManual');
            if (branchSelect) {
                fetch('/api/kyc/branches')
                    .then(function(r) { return r.json(); })
                    .then(function(resp) {
                        var branches = resp.data || resp || [];
                        branchSelect.innerHTML = '<option value="">Select your branch</option>';
                        var grouped = {};
                        branches.forEach(function(b) {
                            var state = b.branchState || 'Other';
                            if (!grouped[state]) grouped[state] = [];
                            grouped[state].push(b);
                        });
                        Object.keys(grouped).sort().forEach(function(state) {
                            var group = document.createElement('optgroup');
                            group.label = state;
                            grouped[state].forEach(function(b) {
                                var opt = document.createElement('option');
                                opt.value = b.branchName;
                                opt.textContent = b.branchName;
                                group.appendChild(opt);
                            });
                            branchSelect.appendChild(group);
                        });
                    })
                    .catch(function() {
                        branchSelect.innerHTML = '<option value="">Failed to load branches</option>';
                    });
                branchSelect.addEventListener('change', function() {
                    if (this.value === 'other') {
                        branchManual.style.display = 'block';
                    } else {
                        branchManual.style.display = 'none';
                    }
                });
            }
        });

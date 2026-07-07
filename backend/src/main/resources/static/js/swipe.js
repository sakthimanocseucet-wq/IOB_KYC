(function() {
    var userPages = ['dashboard.html', 'kyc.html', 'kyc-status.html'];
    var adminPages = ['dashboard.html', 'kyc-review.html', 'account-details.html'];
    var THRESHOLD = 100;
    var MAX_TIME = 400;

    var p = window.location.pathname;
    var pages = null;
    if (p.indexOf('/admin/') !== -1) pages = adminPages;
    else if (p.indexOf('/user/') !== -1) pages = userPages;
    if (!pages) return;

    var cur = p.split('/').pop() || 'index.html';
    var idx = pages.indexOf(cur);
    if (idx === -1) return;

    var base = '';
    if (p.indexOf('/admin/') !== -1) base = p.substring(0, p.indexOf('/admin/') + 7);
    else if (p.indexOf('/user/') !== -1) base = p.substring(0, p.indexOf('/user/') + 6);
    else base = p.substring(0, p.lastIndexOf('/') + 1);

    function goNext() { if (idx < pages.length - 1) window.location.href = base + pages[idx + 1]; }
    function goPrev() { if (idx > 0) window.location.href = base + pages[idx - 1]; }

    var sx = 0, sy = 0, startTime = 0, tracking = false, moved = false;

    function isInteractive(el) {
        while (el && el !== document.body) {
            var tag = el.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' ||
                tag === 'A' || tag === 'LABEL' || tag === 'VIDEO' || tag === 'AUDIO' ||
                tag === 'CANVAS' || tag === 'SVG' || tag === 'IFRAME' ||
                tag === 'PRE' || tag === 'CODE' ||
                el.contentEditable === 'true' || el.getAttribute('role') === 'textbox' ||
                el.closest && (el.closest('.modal-overlay') || el.closest('.navbar') ||
                el.closest('.table-container') || el.closest('.chatbot-widget') ||
                el.closest('.nav-links') || el.closest('.hamburger'))) {
                return true;
            }
            el = el.parentElement;
        }
        return false;
    }

    document.addEventListener('touchstart', function(e) {
        if (e.touches.length !== 1) return;
        var el = document.elementFromPoint(e.touches[0].clientX, e.touches[0].clientY);
        if (isInteractive(el)) { tracking = false; return; }
        sx = e.touches[0].clientX;
        sy = e.touches[0].clientY;
        startTime = Date.now();
        tracking = true;
        moved = false;
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
        if (!tracking || e.touches.length !== 1) return;
        var elapsed = Date.now() - startTime;
        if (elapsed > MAX_TIME) { tracking = false; return; }
        var dx = e.touches[0].clientX - sx;
        var dy = Math.abs(e.touches[0].clientY - sy);
        if (dy > 50) { tracking = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            moved = true;
            e.preventDefault();
            tracking = false;
            if (dx < 0) goNext(); else goPrev();
        }
    }, { passive: false });

    document.addEventListener('touchend', function() { tracking = false; }, { passive: true });

    document.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        if (isInteractive(e.target)) { tracking = false; return; }
        sx = e.clientX;
        sy = e.clientY;
        startTime = Date.now();
        tracking = true;
        moved = false;
    });

    document.addEventListener('mousemove', function(e) {
        if (!tracking) return;
        var elapsed = Date.now() - startTime;
        if (elapsed > MAX_TIME) { tracking = false; return; }
        var dx = e.clientX - sx;
        var dy = Math.abs(e.clientY - sy);
        if (dy > 50) { tracking = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            moved = true;
            e.preventDefault();
            tracking = false;
            if (dx < 0) goNext(); else goPrev();
        }
    });

    document.addEventListener('mouseup', function() { tracking = false; });
})();

(function() {
    var userPages = ['dashboard.html', 'kyc.html', 'kyc-status.html'];
    var adminPages = ['dashboard.html', 'kyc-review.html', 'account-details.html'];
    var THRESHOLD = 80;

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

    var sx1 = 0, sx2 = 0, sy1 = 0, sy2 = 0, tracking = false;

    document.addEventListener('touchstart', function(e) {
        if (e.touches.length === 2) {
            sx1 = e.touches[0].clientX;
            sy1 = e.touches[0].clientY;
            sx2 = e.touches[1].clientX;
            sy2 = e.touches[1].clientY;
            tracking = true;
        } else {
            tracking = false;
        }
    }, { passive: true });

    document.addEventListener('touchmove', function(e) {
        if (!tracking || e.touches.length !== 2) return;
        var mx1 = e.touches[0].clientX - sx1;
        var my1 = Math.abs(e.touches[0].clientY - sy1);
        var mx2 = e.touches[1].clientX - sx2;
        var my2 = Math.abs(e.touches[1].clientY - sy2);
        var avgDx = (mx1 + mx2) / 2;
        var avgDy = (my1 + my2) / 2;
        if (avgDy > 60) { tracking = false; return; }
        if (Math.abs(avgDx) > THRESHOLD) {
            e.preventDefault();
            tracking = false;
            if (avgDx < 0) goNext(); else goPrev();
        }
    }, { passive: false });

    document.addEventListener('touchend', function() { tracking = false; }, { passive: true });

    var mx = 0, my = 0, mtracking = false;
    document.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        mx = e.clientX;
        my = e.clientY;
        mtracking = true;
    });
    document.addEventListener('mousemove', function(e) {
        if (!mtracking) return;
        var dx = e.clientX - mx;
        var dy = Math.abs(e.clientY - my);
        if (dy > 60) { mtracking = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            e.preventDefault();
            mtracking = false;
            if (dx < 0) goNext(); else goPrev();
        }
    });
    document.addEventListener('mouseup', function() { mtracking = false; });
})();

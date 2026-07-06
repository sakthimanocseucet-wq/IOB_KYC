(function() {
    var userPages = ['dashboard.html', 'kyc.html', 'kyc-status.html'];
    var adminPages = ['dashboard.html', 'kyc-review.html', 'account-details.html'];
    var THRESHOLD = 50;

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

    var sx = 0, sy = 0, moved = false;

    window.addEventListener('touchstart', function(e) {
        if (e.touches.length === 1) {
            sx = e.touches[0].clientX;
            sy = e.touches[0].clientY;
            moved = true;
        }
    }, { passive: true, capture: true });

    window.addEventListener('touchmove', function(e) {
        if (!moved) return;
        var dx = e.touches[0].clientX - sx;
        var dy = Math.abs(e.touches[0].clientY - sy);
        if (dy > 50) { moved = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            moved = false;
            if (dx < 0) goNext(); else goPrev();
        }
    }, { passive: true, capture: true });

    window.addEventListener('touchend', function() { moved = false; }, { passive: true, capture: true });

    window.addEventListener('mousedown', function(e) { sx = e.clientX; sy = e.clientY; moved = true; }, { capture: true });
    window.addEventListener('mousemove', function(e) {
        if (!moved) return;
        var dx = e.clientX - sx;
        var dy = Math.abs(e.clientY - sy);
        if (dy > 50) { moved = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            moved = false;
            if (dx < 0) goNext(); else goPrev();
        }
    }, { capture: true });
    window.addEventListener('mouseup', function() { moved = false; }, { capture: true });
})();

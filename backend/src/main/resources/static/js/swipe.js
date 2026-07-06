(function() {
    var userPages = ['dashboard.html', 'kyc.html', 'kyc-status.html'];
    var adminPages = ['dashboard.html', 'kyc-review.html', 'account-details.html'];
    var THRESHOLD = 30;

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

    var html = '';
    if (idx > 0) html += '<div id="swipePrev" style="position:fixed;left:0;top:0;bottom:0;width:40px;z-index:99999;cursor:pointer;background:linear-gradient(to right,rgba(0,71,171,0.08),transparent);display:flex;align-items:center;justify-content:center;font-size:18px;color:rgba(0,71,171,0.4)">&#9664;</div>';
    if (idx < pages.length - 1) html += '<div id="swipeNext" style="position:fixed;right:0;top:0;bottom:0;width:40px;z-index:99999;cursor:pointer;background:linear-gradient(to left,rgba(0,71,171,0.08),transparent);display:flex;align-items:center;justify-content:center;font-size:18px;color:rgba(0,71,171,0.4)">&#9654;</div>';
    document.body.insertAdjacentHTML('beforeend', html);

    var prevEl = document.getElementById('swipePrev');
    var nextEl = document.getElementById('swipeNext');

    if (prevEl) {
        prevEl.addEventListener('click', goPrev);
        prevEl.addEventListener('touchend', function(e) { e.preventDefault(); goPrev(); });
    }
    if (nextEl) {
        nextEl.addEventListener('click', goNext);
        nextEl.addEventListener('touchend', function(e) { e.preventDefault(); goNext(); });
    }

    var sx = 0, sy = 0, active = false;
    document.addEventListener('touchstart', function(e) {
        if (e.touches.length === 1) {
            sx = e.touches[0].clientX;
            sy = e.touches[0].clientY;
            active = true;
        }
    }, false);
    document.addEventListener('touchmove', function(e) {
        if (!active) return;
        var dx = e.touches[0].clientX - sx;
        var dy = Math.abs(e.touches[0].clientY - sy);
        if (dy > 40) { active = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            active = false;
            if (dx < 0) goNext(); else goPrev();
        }
    }, false);
    document.addEventListener('touchend', function() { active = false; }, false);

    document.addEventListener('mousedown', function(e) { sx = e.clientX; sy = e.clientY; active = true; });
    document.addEventListener('mousemove', function(e) {
        if (!active) return;
        var dx = e.clientX - sx;
        var dy = Math.abs(e.clientY - sy);
        if (dy > 40) { active = false; return; }
        if (Math.abs(dx) > THRESHOLD) {
            active = false;
            if (dx < 0) goNext(); else goPrev();
        }
    });
    document.addEventListener('mouseup', function() { active = false; });
})();

// прогрес-бар
(function () {
    const p = document.getElementById('progress');
    if (!p) return;
    const update = () => {
        const h = document.documentElement;
        const s = h.scrollTop || document.body.scrollTop;
        const t = h.scrollHeight - h.clientHeight;
        p.style.width = (t > 0 ? (s / t) * 100 : 0) + '%';
    };
    window.addEventListener('scroll', update, { passive: true });
    update();
})();

// fade-in
(function () {
    const els = document.querySelectorAll('.fade-in');
    if (!('IntersectionObserver' in window) || !els.length) {
        els.forEach(el => el.classList.add('in'));
        return;
    }
    const io = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (e.isIntersecting) e.target.classList.add('in');
        });
    }, { threshold: 0.12 });
    els.forEach(el => io.observe(el));
})();

// картки сегментів
(function () {
    const segCards = document.querySelectorAll('.segment-card');
    const segDetails = document.querySelectorAll('.segment-details');
    if (!segCards.length || !segDetails.length) return;

    segCards.forEach(card => {
        card.addEventListener('click', () => {
            const targetId = card.getAttribute('data-target');
            if (!targetId) return;
            const next = document.getElementById(targetId);
            if (!next || next.classList.contains('active')) return;

            segCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');

            segDetails.forEach(d => d.classList.remove('active'));
            next.classList.add('active');
        });
    });
})();

// дропдаун "Трейдерам"
(function () {
    const drop = document.querySelector('.menu-dropdown');
    if (!drop) return;
    const btn = drop.querySelector('.menu-dropbtn');
    const box = drop.querySelector('.menu-dropcontent');

    btn.addEventListener('click', () => {
        box.style.display = box.style.display === 'block' ? 'none' : 'block';
    });

    document.addEventListener('click', (e) => {
        if (!drop.contains(e.target)) box.style.display = 'none';
    });
})();

// мови
/*(function () {
    const buttons = document.querySelectorAll('.lang-btn');
    if (!buttons.length) return;
    const apply = (lang) => {
        document.documentElement.lang = lang;
        buttons.forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
        localStorage.setItem('telwha-lang', lang);
    };
    buttons.forEach(btn => btn.addEventListener('click', () => apply(btn.dataset.lang)));
    apply(localStorage.getItem('telwha-lang') || 'uk');
})();*/

// parallax hero
(function () {
    const hero = document.querySelector('.hero-inner');
    if (!hero) return;

    const onScroll = () => {
        const rect = hero.getBoundingClientRect();
        const vh = window.innerHeight || document.documentElement.clientHeight;
        const center = (rect.top + rect.height / 2 - vh / 2) / vh;
        const shift = Math.max(-0.5, Math.min(0.5, center));
        hero.style.transform = `translateY(${shift * -12}px)`;
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
})();

// тема
(function () {
    const root = document.documentElement;
    const saved = localStorage.getItem('telwha-theme');
    const fallback = root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    const initial = saved === 'light' || saved === 'dark' ? saved : fallback;
    root.setAttribute('data-theme', initial);
})();

(function () {
    const root = document.documentElement;
    const btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const current = root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
        const next = current === 'light' ? 'dark' : 'light';
        root.setAttribute('data-theme', next);
        localStorage.setItem('telwha-theme', next);
    });
})();

// переходы по data-href вместо inline onclick
(function () {
    const navButtons = document.querySelectorAll('[data-href]');
    if (!navButtons.length) return;

    navButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const href = button.getAttribute('data-href');
            if (!href) return;
            window.location.href = href;
        });
    });
})();

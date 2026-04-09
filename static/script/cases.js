(function () {
    const caseDetails = {
        trading1: '...',
        trading2: '...',
        personal1: '...',
        personal2: '...',
        business1: '...',
        business2: '...'
    };

    const tabs = document.querySelectorAll('.case-tab');
    const cards = document.querySelectorAll('.case-card');
    const backdrop = document.getElementById('caseModalBackdrop');
    const modalContent = document.getElementById('modalContent');
    const modalClose = backdrop?.querySelector('.modal-close');

    if (!tabs.length || !cards.length || !backdrop || !modalContent || !modalClose) return;

    tabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            const filter = tab.getAttribute('data-filter');
            tabs.forEach((currentTab) => currentTab.classList.remove('active'));
            tab.classList.add('active');

            cards.forEach((card) => {
                const category = card.getAttribute('data-category');
                card.style.display = filter === 'all' || filter === category ? '' : 'none';
            });
        });
    });

    cards.forEach((card) => {
        card.addEventListener('click', () => {
            const id = card.getAttribute('data-id');
            const html = caseDetails[id];
            if (!html) return;
            modalContent.innerHTML = html;
            backdrop.classList.add('active');
            backdrop.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
        });
    });

    const closeModal = () => {
        backdrop.classList.remove('active');
        backdrop.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
    };

    modalClose.addEventListener('click', closeModal);
    backdrop.addEventListener('click', (event) => {
        if (event.target === backdrop) closeModal();
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && backdrop.classList.contains('active')) {
            closeModal();
        }
    });
})();

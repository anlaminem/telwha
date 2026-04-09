(function () {
    const chips = document.querySelectorAll('.filter-chip');
    const cards = document.querySelectorAll('.article-card');
    if (!chips.length || !cards.length) return;

    const applyFilter = (filter) => {
        cards.forEach((card) => {
            const tag = card.getAttribute('data-tag');
            const show = filter === 'all' || tag === filter;
            card.classList.toggle('hidden', !show);
        });
    };

    chips.forEach((chip) => {
        chip.addEventListener('click', () => {
            const filter = chip.getAttribute('data-filter');
            chips.forEach((currentChip) => currentChip.classList.remove('active'));
            chip.classList.add('active');
            applyFilter(filter);
        });
    });

    applyFilter('all');
})();

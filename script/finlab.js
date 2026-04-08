(function () {
    const tabButtons = document.querySelectorAll('.tabs-nav button');
    const tabPanels = document.querySelectorAll('.tabs-panel');

    tabButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const target = button.getAttribute('data-tab');
            tabButtons.forEach((currentButton) => {
                currentButton.setAttribute('data-active', currentButton === button ? 'true' : 'false');
            });
            tabPanels.forEach((panel) => {
                panel.setAttribute('data-active', panel.getAttribute('data-panel') === target ? 'true' : 'false');
            });
        });
    });

    const accordionHeaders = document.querySelectorAll('.acc-header');
    accordionHeaders.forEach((header) => {
        header.addEventListener('click', () => {
            const item = header.parentElement;
            const isOpen = item?.getAttribute('data-open') === 'true';
            item?.setAttribute('data-open', isOpen ? 'false' : 'true');
        });
    });

    const totalUsersEl = document.getElementById('total-users');
    const readyPercentEl = document.getElementById('ready-percent');
    if (!totalUsersEl || !readyPercentEl) return;

    const baseUsers = 1248;
    const basePercent = 68;
    const jitter = () => {
        const users = baseUsers + Math.floor(Math.random() * 12) - 6;
        const percent = basePercent + Math.floor(Math.random() * 4) - 2;
        totalUsersEl.textContent = users.toLocaleString('uk-UA');
        readyPercentEl.textContent = `${percent}%`;
    };

    jitter();
    window.setInterval(jitter, 9000);
})();

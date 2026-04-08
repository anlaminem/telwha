(function () {
    const tabs = document.querySelectorAll('.telwha-tab');
    const panels = document.querySelectorAll('.telwha-panel');
    if (!tabs.length || !panels.length) return;

    tabs.forEach((tab) => {
        tab.addEventListener('click', () => {
            const id = tab.dataset.tab;
            tabs.forEach((currentTab) => currentTab.classList.toggle('active', currentTab === tab));
            panels.forEach((panel) => panel.classList.toggle('active', panel.dataset.panel === id));
        });
    });
})();

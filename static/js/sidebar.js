document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;

    const STORAGE_KEY = 'ndmu-sidebar-collapsed';
    const layout = sidebar.parentElement;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sidebar-toggle';
    button.setAttribute('aria-label', 'Collapse sidebar');
    button.setAttribute('title', 'Collapse sidebar');
    button.innerHTML = '<span aria-hidden="true">‹</span><b>Collapse</b>';
    sidebar.insertBefore(button, sidebar.firstChild);

    const setCollapsed = (collapsed) => {
        layout.classList.toggle('sidebar-collapsed', collapsed);
        button.classList.toggle('is-collapsed', collapsed);
        button.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        button.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
        button.innerHTML = `<span aria-hidden="true">${collapsed ? '›' : '‹'}</span><b>${collapsed ? 'Expand' : 'Collapse'}</b>`;
        localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
    };

    setCollapsed(localStorage.getItem(STORAGE_KEY) === '1');

    button.addEventListener('click', () => {
        setCollapsed(!layout.classList.contains('sidebar-collapsed'));
    });
});

const GNS3_URL_KEY = 'gns3_webui_url';

document.addEventListener('DOMContentLoaded', () => {
    const saved = localStorage.getItem(GNS3_URL_KEY);
    if (saved) document.getElementById('gns3-url').value = saved;
    applyStoredTheme();
});

function openGns3() {
    const url = document.getElementById('gns3-url').value.trim();
    if (!url) return;
    localStorage.setItem(GNS3_URL_KEY, url);
    window.open(url, '_blank');
}

function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('theme-icon');
    const isDark = html.getAttribute('data-theme') === 'dark';
    html.setAttribute('data-theme', isDark ? 'light' : 'dark');
    icon.className = isDark ? 'bi bi-moon-fill' : 'bi bi-sun-fill';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
}

function applyStoredTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.className = saved === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
}
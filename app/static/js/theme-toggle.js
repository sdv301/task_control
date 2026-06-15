/**
 * Theme Switcher for Smart Control
 * Toggles between dark and light themes.
 * Persists choice in localStorage.
 */
(function() {
    const STORAGE_KEY = 'smartcontrol-theme';

    function getPreferredTheme() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) return stored;
        return 'dark'; // default
    }

    function applyTheme(theme) {
        const html = document.documentElement;
        if (theme === 'light') {
            html.classList.remove('dark');
            html.classList.add('light');
        } else {
            html.classList.remove('light');
            html.classList.add('dark');
        }
        localStorage.setItem(STORAGE_KEY, theme);

        // Update toggle button state if exists
        const btn = document.getElementById('theme-toggle-btn');
        if (btn) {
            const sunIcon = btn.querySelector('.icon-sun');
            const moonIcon = btn.querySelector('.icon-moon');
            if (sunIcon && moonIcon) {
                if (theme === 'light') {
                    sunIcon.style.display = 'none';
                    moonIcon.style.display = 'block';
                } else {
                    sunIcon.style.display = 'block';
                    moonIcon.style.display = 'none';
                }
            }
        }
    }

    function toggleTheme() {
        const current = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
    }

    // Apply on load (before DOMContentLoaded to prevent flash)
    applyTheme(getPreferredTheme());

    // Expose globally
    window.toggleTheme = toggleTheme;
    window.applyTheme = applyTheme;

    // Create toggle button and inject into page after DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        // Create floating toggle button
        const btn = document.createElement('button');
        btn.id = 'theme-toggle-btn';
        btn.title = 'Переключить тему';
        btn.onclick = toggleTheme;
        btn.innerHTML = `
            <span class="icon-sun" style="display:none">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="5"/>
                    <line x1="12" y1="1" x2="12" y2="3"/>
                    <line x1="12" y1="21" x2="12" y2="23"/>
                    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                    <line x1="1" y1="12" x2="3" y2="12"/>
                    <line x1="21" y1="12" x2="23" y2="12"/>
                    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                </svg>
            </span>
            <span class="icon-moon" style="display:none">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
                </svg>
            </span>
        `;

        // Style
        Object.assign(btn.style, {
            position: 'fixed',
            bottom: '20px',
            left: '20px',
            zIndex: '9999',
            width: '44px',
            height: '44px',
            borderRadius: '12px',
            border: '1px solid rgba(148,163,184,0.2)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.3s ease',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            backdropFilter: 'blur(10px)',
        });

        document.body.appendChild(btn);

        // Apply theme-specific button styling
        function updateBtnStyle() {
            const isDark = document.documentElement.classList.contains('dark');
            btn.style.background = isDark ? 'rgba(30,41,59,0.9)' : 'rgba(255,255,255,0.9)';
            btn.style.color = isDark ? '#e2e8f0' : '#1e293b';
        }

        // Initial update
        applyTheme(getPreferredTheme());
        updateBtnStyle();

        // Watch for theme changes
        const observer = new MutationObserver(updateBtnStyle);
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    });
})();

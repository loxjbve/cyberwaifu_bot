import { qs } from './dom.js';
import { refreshIcons } from './icons.js';

function initClock() {
    const clock = qs('#digital-clock');
    if (!clock) {
        return;
    }

    const formatterTime = new Intl.DateTimeFormat('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });

    const formatterDate = new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        weekday: 'short',
    });

    const updateClock = () => {
        const now = new Date();
        clock.innerHTML = `
            <span class="time">${formatterTime.format(now)}</span>
            <span class="date">${formatterDate.format(now)}</span>
        `;
    };

    updateClock();
    window.setInterval(updateClock, 1000);
}

function initSidebar() {
    const sidebar = qs('.sidebar');
    const toggle = qs('.sidebar-toggle');
    const overlay = qs('.shell-overlay');
    if (!sidebar || !toggle) {
        return;
    }

    const syncLayout = () => {
        if (window.innerWidth <= 992) {
            document.body.classList.remove('sidebar-collapsed');
        }
    };

    toggle.addEventListener('click', () => {
        if (window.innerWidth <= 992) {
            document.body.classList.toggle('sidebar-open');
            overlay?.classList.toggle('is-visible', document.body.classList.contains('sidebar-open'));
        } else {
            document.body.classList.toggle('sidebar-collapsed');
        }
    });

    overlay?.addEventListener('click', () => {
        document.body.classList.remove('sidebar-open');
        overlay.classList.remove('is-visible');
    });

    window.addEventListener('resize', syncLayout);
    syncLayout();
}

function initKeyboardMode() {
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Tab') {
            document.body.classList.add('user-is-tabbing');
        }
    });

    document.addEventListener('mousedown', () => {
        document.body.classList.remove('user-is-tabbing');
    });
}

export function initAppShell() {
    initClock();
    initSidebar();
    initKeyboardMode();
    refreshIcons();
}

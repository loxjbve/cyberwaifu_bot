import { initAppShell } from './core/app-shell.js';
import { initModalSystem } from './core/modal.js';
import { initCollapsibles } from './core/collapsible.js';
import { initCustomSelects } from './core/select.js';
import { refreshIcons } from './core/icons.js';
import { showToast } from './core/toast.js';

document.addEventListener('DOMContentLoaded', () => {
    initAppShell();
    initModalSystem();
    initCollapsibles();
    initCustomSelects();
    refreshIcons();
    window.showToast = showToast;
});

import { createElementFromHtml, escapeHtml } from './dom.js';

let toastStack;

function getToastIcon(type) {
    const icons = {
        success: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"></path></svg>',
        error: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18"></path><path d="M6 6l12 12"></path></svg>',
        info: '<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path></svg>',
    };
    return icons[type] || icons.info;
}

function ensureToastStack() {
    if (!toastStack) {
        toastStack = document.createElement('div');
        toastStack.className = 'toast-stack';
        toastStack.setAttribute('aria-live', 'polite');
        toastStack.setAttribute('aria-atomic', 'true');
        document.body.appendChild(toastStack);
    }

    return toastStack;
}

export function showToast(message, type = 'info', options = {}) {
    const { duration = 3200 } = options;
    const stack = ensureToastStack();
    const toast = createElementFromHtml(`
        <div class="toast-notification" data-type="${escapeHtml(type)}" role="status">
            ${getToastIcon(type)}
            <div class="toast-copy">${escapeHtml(message)}</div>
            <button type="button" class="toast-close" aria-label="关闭提示">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18"></path>
                    <path d="M6 6l12 12"></path>
                </svg>
            </button>
        </div>
    `);

    const closeToast = () => {
        toast.classList.remove('is-visible');
        window.setTimeout(() => {
            toast.remove();
        }, 240);
    };

    toast.querySelector('.toast-close')?.addEventListener('click', closeToast);
    stack.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('is-visible');
    });

    if (duration > 0) {
        window.setTimeout(closeToast, duration);
    }

    return toast;
}

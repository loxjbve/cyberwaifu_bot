import { qsa } from './dom.js';

let activeModal = null;
let previouslyFocused = null;

function getFocusableElements(modal) {
    return qsa(
        'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])',
        modal,
    ).filter((element) => !element.hasAttribute('hidden'));
}

function trapFocus(event) {
    if (!activeModal || event.key !== 'Tab') {
        return;
    }

    const focusable = getFocusableElements(activeModal);
    if (!focusable.length) {
        return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
}

export function openModal(target) {
    const modal = typeof target === 'string' ? document.getElementById(target) : target;
    if (!modal) {
        return null;
    }

    previouslyFocused = document.activeElement;
    modal.classList.add('is-open');
    modal.classList.add('active');
    modal.classList.add('show');
    modal.classList.add('visible');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('is-scroll-locked');
    activeModal = modal;

    const firstFocusable = getFocusableElements(modal)[0];
    firstFocusable?.focus();
    return modal;
}

export function closeModal(target = activeModal) {
    const modal = typeof target === 'string' ? document.getElementById(target) : target;
    if (!modal) {
        return;
    }

    modal.classList.remove('is-open', 'active', 'show', 'visible');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('is-scroll-locked');
    activeModal = null;

    if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
        previouslyFocused.focus();
    }
}

export function initModalSystem() {
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && activeModal) {
            closeModal(activeModal);
        }

        trapFocus(event);
    });

    qsa('.modal-overlay').forEach((modal) => {
        modal.setAttribute('aria-hidden', modal.classList.contains('is-open') ? 'false' : 'true');
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeModal(modal);
            }
        });
    });

    document.addEventListener('click', (event) => {
        const closeTrigger = event.target.closest('[data-modal-close], .modal-close, .modal-close-btn, .btn-close');
        if (closeTrigger && activeModal) {
            closeModal(activeModal);
        }
    });
}

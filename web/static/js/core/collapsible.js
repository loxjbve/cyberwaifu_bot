import { delegate, qsa } from './dom.js';

function toggleCard(card, forceExpanded = null) {
    const shouldExpand = forceExpanded ?? card.classList.contains('collapsed');
    card.classList.toggle('collapsed', !shouldExpand);
    const header = card.querySelector('.collapsible-header');
    header?.setAttribute('aria-expanded', shouldExpand ? 'true' : 'false');
}

export function initCollapsibles(root = document) {
    qsa('.collapsible-card', root).forEach((card) => {
        const header = card.querySelector('.collapsible-header');
        if (header) {
            header.setAttribute('role', 'button');
            header.setAttribute('tabindex', '0');
            header.setAttribute('aria-expanded', card.classList.contains('collapsed') ? 'false' : 'true');
        }
    });

    delegate(root, 'click', '.collapsible-card .collapsible-header', (event, header) => {
        if (event.target.closest('button, a, input, textarea, select')) {
            return;
        }

        const card = header.closest('.collapsible-card');
        if (card) {
            toggleCard(card);
        }
    });

    delegate(root, 'keydown', '.collapsible-card .collapsible-header', (event, header) => {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }

        event.preventDefault();
        const card = header.closest('.collapsible-card');
        if (card) {
            toggleCard(card);
        }
    });

    delegate(root, 'click', '.collapse-toggle, .toggle-summary-btn', (event, button) => {
        event.preventDefault();
        event.stopPropagation();
        const card = button.closest('.collapsible-card, .collapsible-summary, .message-meta-container');
        if (card) {
            card.classList.toggle('collapsed');
        }
    });
}

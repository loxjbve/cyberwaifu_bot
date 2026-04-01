import { delegate } from '../core/dom.js';
import { closeModal, openModal } from '../core/modal.js';
import { qs, qsa } from '../core/dom.js';

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="database"]');
    if (!pageRoot) {
        return;
    }

    const modal = qs('#cellDataModal');
    const modalTitle = qs('#cellDataModalTitle');
    const modalContent = qs('#cellDataModalContent');
    const headers = qsa('.table.excel-style thead th', pageRoot);

    delegate(pageRoot, 'click', '.expandable-cell', (_event, cell) => {
        const contentWrapper = cell.querySelector('.cell-content-wrapper');
        if (!contentWrapper || contentWrapper.offsetWidth >= contentWrapper.scrollWidth) {
            return;
        }

        const headerText = headers[cell.cellIndex]?.textContent?.trim() || '单元格内容';
        modalTitle.textContent = headerText;
        modalContent.textContent = cell.dataset.fullText || cell.textContent || '';
        openModal(modal);
    });

    delegate(pageRoot, 'click', '[data-action="close-cell-modal"]', () => {
        closeModal(modal);
    });
});

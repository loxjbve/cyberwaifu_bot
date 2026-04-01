import { qs, delegate } from '../core/dom.js';
import { copyText } from '../core/clipboard.js';
import { openModal } from '../core/modal.js';
import { showToast } from '../core/toast.js';

async function copyForwardCommand(groupId, messageId) {
    const command = `/fw ${groupId} ${messageId}`;
    try {
        await copyText(command);
        showToast('转发命令已复制。', 'success');
    } catch (_error) {
        showToast('复制失败，请手动复制。', 'error');
    }
}

function highlightHashTarget() {
    const targetId = window.location.hash.replace('#', '');
    if (!targetId) {
        return;
    }

    const target = document.getElementById(targetId);
    if (!target) {
        return;
    }

    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('is-highlighted');
    window.setTimeout(() => target.classList.remove('is-highlighted'), 2500);
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="group-dialogs"][data-group-id]');
    if (!pageRoot) {
        return;
    }

    const groupId = pageRoot.dataset.groupId;
    const searchMode = pageRoot.dataset.searchMode === 'true';

    delegate(pageRoot, 'click', '.forward-btn', async (event, button) => {
        event.stopPropagation();
        const container = button.closest('.message-bubble-container');
        if (container) {
            await copyForwardCommand(groupId, container.dataset.dialogId);
        }
    });

    delegate(pageRoot, 'click', '.message-bubble', (_event, bubble) => {
        const container = bubble.closest('.message-bubble-container');
        if (!container) {
            return;
        }

        if (searchMode) {
            const url = new URL(window.location.href);
            url.searchParams.delete('search');
            url.searchParams.set('page', container.dataset.originalPage || '1');
            url.hash = container.id;
            window.location.href = url.toString();
            return;
        }

        qs('#modal-sender').textContent = container.dataset.userName || '';
        qs('#modal-role').textContent = container.dataset.role === 'user' ? '用户' : 'AI';
        qs('#modal-turn').textContent = container.dataset.turn || '';
        qs('#modal-time').textContent = container.dataset.time || '';
        qs('#modal-msg-id').textContent = container.dataset.msgId || 'N/A';
        qs('#modal-raw-content').textContent = container.dataset.rawContent || '';
        qs('#modal-processed-content').textContent = container.dataset.processedContent || '';
        openModal('messageDetailModal');
    });

    highlightHashTarget();
});

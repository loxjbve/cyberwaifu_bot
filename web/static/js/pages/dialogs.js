import { escapeHtml, qs, delegate } from '../core/dom.js';
import { requestJson } from '../core/http.js';
import { openModal, closeModal } from '../core/modal.js';
import { showToast } from '../core/toast.js';

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

function renderMessageDetail(container) {
    qs('#modal-role').textContent = container.dataset.role === 'user' ? '用户' : 'AI';
    qs('#modal-turn').textContent = container.dataset.turn || '';
    qs('#modal-time').textContent = container.dataset.time || '';
    qs('#modal-msg-id').textContent = container.dataset.msgId || 'N/A';
    qs('#modal-raw-content').textContent = container.dataset.rawContent || '';
}

function openEditor(container) {
    const textarea = qs('#edit-content');
    textarea.value = container.dataset.processedContent || '';
    textarea.dataset.dialogId = container.dataset.dialogId || '';
    openModal('editMessageModal');
    textarea.focus();
}

async function exportConversation(conversationId) {
    try {
        const result = await requestJson(`/api/export_dialogs/${conversationId}`);
        const blob = new Blob([JSON.stringify({
            conversation: result.conversation,
            dialogs: result.dialogs,
        }, null, 2)], { type: 'application/json' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `conversation_${conversationId}_${new Date().toISOString().slice(0, 10)}.json`;
        link.click();
        URL.revokeObjectURL(link.href);
        showToast(`成功导出 ${result.dialogs.length} 条对话记录。`, 'success');
    } catch (error) {
        showToast(`导出失败：${error.message}`, 'error');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="dialogs"][data-conversation-id]');
    if (!pageRoot) {
        return;
    }

    const conversationId = pageRoot.dataset.conversationId;
    const messageDetailModal = qs('#messageDetailModal');
    const editModal = qs('#editMessageModal');

    delegate(pageRoot, 'click', '.edit-btn', (event, button) => {
        event.stopPropagation();
        const container = button.closest('.message-bubble-container');
        if (container) {
            openEditor(container);
        }
    });

    delegate(pageRoot, 'click', '.message-bubble', (_event, bubble) => {
        const container = bubble.closest('.message-bubble-container');
        if (!container) {
            return;
        }

        renderMessageDetail(container);
        const editButton = qs('#editMessageDetailBtn');
        if (editButton) {
            editButton.dataset.dialogId = container.dataset.dialogId || '';
            editButton.dataset.processedContent = container.dataset.processedContent || '';
        }
        openModal(messageDetailModal);
    });

    qs('#editMessageDetailBtn')?.addEventListener('click', () => {
        const dialogId = qs('#editMessageDetailBtn')?.dataset.dialogId;
        const container = qs(`.message-bubble-container[data-dialog-id="${dialogId}"]`);
        if (container) {
            closeModal(messageDetailModal);
            openEditor(container);
        }
    });

    qs('#saveEditBtn')?.addEventListener('click', async () => {
        const textarea = qs('#edit-content');
        const dialogId = textarea.dataset.dialogId;
        if (!dialogId) {
            return;
        }

        const saveButton = qs('#saveEditBtn');
        const originalMarkup = saveButton.innerHTML;
        saveButton.disabled = true;
        saveButton.innerHTML = '<span class="loading-spinner-small"></span><span>保存中</span>';

        try {
            await requestJson('/api/edit_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    dialog_id: dialogId,
                    content: textarea.value,
                    conv_id: conversationId,
                }),
            });

            const container = qs(`.message-bubble-container[data-dialog-id="${dialogId}"]`);
            if (container) {
                container.dataset.processedContent = textarea.value;
                container.querySelector('.message-content').innerHTML = escapeHtml(textarea.value).replace(/\n/g, '<br>');
            }

            closeModal(editModal);
            showToast('消息已更新。', 'success');
        } catch (error) {
            showToast(`保存失败：${error.message}`, 'error');
        } finally {
            saveButton.disabled = false;
            saveButton.innerHTML = originalMarkup;
        }
    });

    qs('#exportBtn')?.addEventListener('click', () => {
        exportConversation(conversationId);
    });

    highlightHashTarget();
});

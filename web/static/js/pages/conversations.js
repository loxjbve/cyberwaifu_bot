import { delegate } from '../core/dom.js';
import { requestJson } from '../core/http.js';
import { showToast } from '../core/toast.js';

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="conversations"]');
    if (!pageRoot) {
        return;
    }

    delegate(pageRoot, 'click', '.generate-summary-btn', async (event, button) => {
        event.preventDefault();
        if (button.disabled) {
            return;
        }

        const conversationId = button.dataset.convId;
        const originalMarkup = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner-small"></span><span>生成中</span>';

        try {
            const result = await requestJson('/api/generate_summary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_id: conversationId }),
            });

            const summaryCell = button.closest('tr')?.querySelector('.summary-preview');
            if (summaryCell) {
                const text = result.summary || '';
                summaryCell.textContent = text.length > 30 ? `${text.slice(0, 30)}...` : text;
                summaryCell.title = text;
            }

            showToast('摘要生成成功。', 'success');
        } catch (error) {
            showToast(`摘要生成失败：${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalMarkup;
        }
    });
});

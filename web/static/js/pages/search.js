import { delegate, escapeHtml, qsa } from '../core/dom.js';
import { copyText } from '../core/clipboard.js';
import { requestJson } from '../core/http.js';
import { showToast } from '../core/toast.js';

function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightText(text, term) {
    const source = String(text || '');
    if (!term) {
        return escapeHtml(source);
    }

    const regex = new RegExp(escapeRegExp(term), 'gi');
    let cursor = 0;
    let highlighted = '';

    for (const match of source.matchAll(regex)) {
        const index = match.index ?? 0;
        highlighted += escapeHtml(source.slice(cursor, index));
        highlighted += `<mark>${escapeHtml(match[0])}</mark>`;
        cursor = index + match[0].length;
    }

    highlighted += escapeHtml(source.slice(cursor));
    return highlighted;
}

function toggleSearchCard(card) {
    const body = card.querySelector('.collapse');
    if (!body) {
        return;
    }

    const collapsed = !card.classList.contains('collapsed');
    card.classList.toggle('collapsed', collapsed);
    body.classList.toggle('show', !collapsed);
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="search"]');
    if (!pageRoot) {
        return;
    }

    const searchInput = pageRoot.querySelector('#searchQuery');
    if (searchInput && !searchInput.value) {
        searchInput.focus();
    }

    qsa('.collapsible-card', pageRoot).forEach((card) => {
        const body = card.querySelector('.collapse');
        if (body && !body.classList.contains('show')) {
            card.classList.add('collapsed');
        }
    });

    delegate(pageRoot, 'click', '.collapsible-card .card-header', (event, header) => {
        if (event.target.closest('button, a')) {
            return;
        }

        const card = header.closest('.collapsible-card');
        if (card) {
            toggleSearchCard(card);
        }
    });

    delegate(pageRoot, 'click', '.collapse-toggle', (event, button) => {
        event.preventDefault();
        event.stopPropagation();
        const card = button.closest('.collapsible-card');
        if (card) {
            toggleSearchCard(card);
        }
    });

    delegate(pageRoot, 'click', '.toggle-text', (event, button) => {
        event.preventDefault();
        const wrapper = button.closest('.collapsible-text');
        if (!wrapper) {
            return;
        }
        const expanded = !wrapper.classList.contains('is-expanded');
        wrapper.classList.toggle('is-expanded', expanded);
        button.textContent = expanded ? '收起' : '展开';
    });

    delegate(pageRoot, 'click', '.generate-summary-btn', async (event, button) => {
        event.preventDefault();
        const conversationId = button.dataset.convId;
        const originalMarkup = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner-small"></span>';

        try {
            const result = await requestJson('/api/generate_summary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ conversation_id: conversationId }),
            });

            const summaryCell = button.closest('tr')?.querySelector('.summary-cell');
            const query = searchInput?.value || '';
            if (summaryCell) {
                const summary = result.summary || '';
                const preview = summary.length > 50 ? `${summary.slice(0, 50)}...` : summary;
                summaryCell.innerHTML = `
                    <div class="collapsible-text">
                        <div class="text-preview">${highlightText(preview, query)}</div>
                        <div class="text-full">${highlightText(summary, query)}</div>
                        <button class="btn-glass btn-text btn-sm toggle-text">展开</button>
                    </div>
                `;
            }

            showToast('摘要生成成功。', 'success');
        } catch (error) {
            showToast(`摘要生成失败：${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalMarkup;
        }
    });

    delegate(pageRoot, 'click', '[data-action="copy-forward-command"]', async (_event, button) => {
        const command = `/fw ${button.dataset.targetId} ${button.dataset.msgId}`;
        try {
            await copyText(command);
            showToast(`已复制：${command}`, 'success');
        } catch (error) {
            showToast('复制失败，请手动复制。', 'error');
        }
    });

    delegate(pageRoot, 'click', '[data-action="jump-group-message"]', async (_event, button) => {
        const groupId = button.dataset.groupId;
        const msgId = button.dataset.msgId;

        try {
            const result = await requestJson(`/api/message_page/${groupId}/${msgId}`);
            window.location.href = `/admin/group_dialogs/${groupId}?page=${result.page}#msg-${msgId}`;
        } catch (_error) {
            window.location.href = `/admin/group_dialogs/${groupId}#msg-${msgId}`;
        }
    });
});

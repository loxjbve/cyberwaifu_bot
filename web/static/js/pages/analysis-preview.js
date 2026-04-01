import { requestJson } from '../core/http.js';
import { closeModal, openModal } from '../core/modal.js';
import { createElementFromHtml, delegate, escapeHtml, qs } from '../core/dom.js';
import { showToast } from '../core/toast.js';

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="analysis-preview"][data-page-number]');
    if (!pageRoot) {
        return;
    }

    const modal = qs('#analysis-modal');
    const modalImage = qs('#modal-image');
    const modalText = qs('#modal-text');
    const modalUser = qs('#modal-user');
    const modalTime = qs('#modal-time');
    const grid = qs('.analysis-grid', pageRoot);
    const loading = qs('#loading-indicator', pageRoot);
    let page = Number(pageRoot.dataset.pageNumber || '1');
    let hasNext = pageRoot.dataset.hasNext === 'true';
    let pending = false;

    const fillModal = (card) => {
        modalImage.src = card.dataset.imageUrl || '';
        modalImage.alt = card.dataset.user || '分析图片';
        modalText.textContent = card.dataset.content || '';
        modalUser.textContent = card.dataset.user || '';
        modalTime.textContent = card.dataset.time || '';
    };

    delegate(pageRoot, 'click', '.analysis-card', (_event, card) => {
        fillModal(card);
        openModal(modal);
    });

    delegate(pageRoot, 'click', '[data-action="close-analysis-modal"]', () => {
        closeModal(modal);
    });

    async function loadNextPage() {
        if (!hasNext || pending) {
            return;
        }

        pending = true;
        loading.hidden = false;
        const nextPage = page + 1;

        try {
            const payload = await requestJson(`/api/analysis_previews?page=${nextPage}`);
            page = nextPage;
            hasNext = payload.has_next;

            payload.items.forEach((item) => {
                grid.appendChild(createElementFromHtml(`
                    <div class="analysis-card"
                        data-image-url="${escapeHtml(item.image_url || '')}"
                        data-content="${escapeHtml(item.content || '')}"
                        data-user="${escapeHtml(item.user_name || '')}"
                        data-time="${escapeHtml(item.date_time || '')}">
                        <div class="analysis-image-wrapper">
                            <img src="${escapeHtml(item.image_url || '')}" alt="分析图片" loading="lazy">
                        </div>
                        <div class="analysis-content"><pre>${escapeHtml(item.content || '')}</pre></div>
                        <div class="analysis-footer"><span>${escapeHtml(item.user_name || '')}</span><span>${escapeHtml(item.date_time || '')}</span></div>
                    </div>
                `));
            });
        } catch (error) {
            hasNext = false;
            showToast(`加载更多失败：${error.message}`, 'error');
        } finally {
            pending = false;
            loading.hidden = true;
        }
    }

    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 120) {
            loadNextPage();
        }
    });
});

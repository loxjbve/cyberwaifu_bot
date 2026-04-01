import { createElementFromHtml, delegate, qsa } from './dom.js';

export function syncCustomSelect(originalSelect) {
    const wrapper = originalSelect.closest('.custom-select-wrapper');
    if (!wrapper) {
        return;
    }

    const triggerText = wrapper.querySelector('.custom-select-trigger span');
    const options = qsa('.custom-option', wrapper);
    const selectedOption = originalSelect.selectedOptions[0];

    if (triggerText) {
        triggerText.textContent = selectedOption ? selectedOption.textContent : '请选择';
    }

    options.forEach((option) => {
        option.classList.toggle('selected', option.dataset.value === originalSelect.value);
    });
}

export function initCustomSelects(root = document) {
    qsa('.custom-select-wrapper', root).forEach((wrapper) => {
        const originalSelect = wrapper.querySelector('.original-select');
        if (!originalSelect) {
            return;
        }

        if (!wrapper.querySelector('.custom-select')) {
            const optionsMarkup = Array.from(originalSelect.options)
                .map((option) => `
                    <div class="custom-option" data-value="${option.value}">
                        <span>${option.textContent}</span>
                    </div>
                `)
                .join('');

            wrapper.appendChild(createElementFromHtml(`
                <div class="custom-select">
                    <button type="button" class="custom-select-trigger" aria-haspopup="listbox" aria-expanded="false">
                        <span></span>
                        <div class="arrow-container">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                        </div>
                    </button>
                    <div class="custom-options" role="listbox">
                        ${optionsMarkup}
                    </div>
                </div>
            `));
        }

        syncCustomSelect(originalSelect);
    });

    delegate(root, 'click', '.custom-select-trigger', (event, trigger) => {
        event.preventDefault();
        const customSelect = trigger.closest('.custom-select');
        const willOpen = !customSelect.classList.contains('open');

        qsa('.custom-select.open').forEach((select) => {
            select.classList.remove('open');
            select.querySelector('.custom-select-trigger')?.setAttribute('aria-expanded', 'false');
        });

        customSelect.classList.toggle('open', willOpen);
        trigger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });

    delegate(root, 'click', '.custom-option', (event, option) => {
        const wrapper = option.closest('.custom-select-wrapper');
        const originalSelect = wrapper?.querySelector('.original-select');
        if (!originalSelect) {
            return;
        }

        originalSelect.value = option.dataset.value || '';
        originalSelect.dispatchEvent(new Event('change', { bubbles: true }));
        syncCustomSelect(originalSelect);

        const customSelect = option.closest('.custom-select');
        customSelect?.classList.remove('open');
        customSelect?.querySelector('.custom-select-trigger')?.setAttribute('aria-expanded', 'false');
    });

    document.addEventListener('click', (event) => {
        if (!event.target.closest('.custom-select-wrapper')) {
            qsa('.custom-select.open').forEach((select) => {
                select.classList.remove('open');
                select.querySelector('.custom-select-trigger')?.setAttribute('aria-expanded', 'false');
            });
        }
    });
}

import { createElementFromHtml, delegate, escapeHtml, qs } from '../core/dom.js';
import { requestJson } from '../core/http.js';
import { showToast } from '../core/toast.js';

const API_ENDPOINTS = {
    load: '/api/system-config',
    save: '/api/system-config',
};

let pageState = null;
let sensitiveVisible = false;

function deepGet(source, path, fallback = '') {
    let value = source;
    for (const part of path.split('.')) {
        if (value && typeof value === 'object' && part in value) {
            value = value[part];
        } else {
            return fallback;
        }
    }
    return value;
}

function deepSet(target, path, value) {
    const parts = path.split('.');
    let cursor = target;
    for (const part of parts.slice(0, -1)) {
        if (!cursor[part] || typeof cursor[part] !== 'object') {
            cursor[part] = {};
        }
        cursor = cursor[part];
    }
    cursor[parts.at(-1)] = value;
}

function setLoading(isLoading) {
    const loading = qs('#systemConfigLoading');
    const form = qs('#systemConfigForm');
    const error = qs('#systemConfigError');

    if (loading) {
        loading.hidden = !isLoading;
    }
    if (form && isLoading) {
        form.hidden = true;
    }
    if (error && isLoading) {
        error.hidden = true;
    }
}

function showError(message) {
    const loading = qs('#systemConfigLoading');
    const form = qs('#systemConfigForm');
    const error = qs('#systemConfigError');
    const text = qs('#systemConfigErrorText');

    if (loading) {
        loading.hidden = true;
    }
    if (form) {
        form.hidden = true;
    }
    if (error) {
        error.hidden = false;
    }
    if (text) {
        text.textContent = message;
    }
}

function optionMarkup(value, label, selected = false) {
    return `<option value="${escapeHtml(value)}"${selected ? ' selected' : ''}>${escapeHtml(label)}</option>`;
}

function populateSelect(select, options, currentValue = '') {
    if (!select) {
        return;
    }

    const source = select.dataset.optionSource || '';
    if (source === 'presets') {
        select.innerHTML = options.map((item) => optionMarkup(item.name, item.display, item.name === currentValue)).join('');
        return;
    }

    select.innerHTML = options.map((item) => optionMarkup(item, item, item === currentValue)).join('');
}

function populateOptionFields(config, options) {
    document.querySelectorAll('[data-option-source]').forEach((select) => {
        const sourceName = select.dataset.optionSource;
        const sourceOptions = options?.[sourceName] || [];
        populateSelect(select, sourceOptions, deepGet(config, select.dataset.configPath || '', ''));
    });
}

function formatAdminIds(value) {
    if (!Array.isArray(value)) {
        return '';
    }
    return value.join(', ');
}

function parseAdminIds(rawValue) {
    return rawValue
        .split(/[\s,]+/)
        .map((item) => item.trim())
        .filter(Boolean)
        .map((item) => Number(item));
}

function fillBasicFields(config) {
    document.querySelectorAll('#systemConfigForm [data-config-path]').forEach((field) => {
        if (field.closest('.api-list')) {
            return;
        }

        const path = field.dataset.configPath || '';
        const value = deepGet(config, path, field.type === 'checkbox' ? false : '');
        if (field.dataset.format === 'admin-ids') {
            field.value = formatAdminIds(value);
            return;
        }
        if (field.type === 'checkbox') {
            field.checked = Boolean(value);
            return;
        }
        field.value = value ?? '';
    });
}

function renderRestartNotice(payload) {
    const notice = qs('#restartFieldsNotice');
    const labels = payload?.restart_required_labels || {};
    const values = Array.isArray(payload?.restart_required_fields) ? payload.restart_required_fields : [];
    if (!notice) {
        return;
    }
    const labelList = values.map((key) => labels[key] || key);
    notice.textContent = labelList.length
        ? labelList.join(' | ')
        : '褰撳墠鎵€鏈夎皟鏁撮兘鍙姩鎬佺敓鏁堛€?';
}

function renderApiItem(item = {}) {
    const type = sensitiveVisible ? 'text' : 'password';
    return createElementFromHtml(`
        <div class="api-item" data-api-item>
            <div class="api-item-grid">
                <div class="form-group">
                    <label class="form-label">name</label>
                    <input class="form-input" data-api-field="name" value="${escapeHtml(item.name || '')}">
                </div>
                <div class="form-group">
                    <label class="form-label">key</label>
                    <input class="form-input api-key-input" data-api-field="key" data-sensitive="true" type="${type}" value="${escapeHtml(item.key || '')}">
                </div>
                <div class="form-group">
                    <label class="form-label">url</label>
                    <input class="form-input" data-api-field="url" value="${escapeHtml(item.url || '')}">
                </div>
                <div class="form-group">
                    <label class="form-label">model</label>
                    <input class="form-input" data-api-field="model" value="${escapeHtml(item.model || '')}">
                </div>
                <div class="form-group">
                    <label class="form-label">group</label>
                    <input class="form-input" data-api-field="group" data-cast="int" type="number" value="${escapeHtml(item.group ?? 0)}">
                </div>
                <div class="form-group">
                    <label class="form-label">multiple</label>
                    <input class="form-input" data-api-field="multiple" data-cast="int" type="number" min="1" value="${escapeHtml(item.multiple ?? 1)}">
                </div>
            </div>
            <div class="api-item-actions">
                <button type="button" class="btn-danger btn-sm" data-action="remove-api-item">鍒犻櫎</button>
            </div>
        </div>
    `);
}

function renderApiList(apiList = []) {
    const container = qs('#apiList');
    if (!container) {
        return;
    }

    container.innerHTML = '';
    apiList.forEach((item) => {
        container.appendChild(renderApiItem(item));
    });
    if (!apiList.length) {
        container.appendChild(renderApiItem());
    }
}

function collectApiList() {
    return Array.from(document.querySelectorAll('[data-api-item]')).map((item) => {
        const payload = {};
        item.querySelectorAll('[data-api-field]').forEach((field) => {
            const cast = field.dataset.cast || '';
            let value = field.value ?? '';
            if (cast === 'int') {
                value = Number(value || 0);
            }
            payload[field.dataset.apiField] = value;
        });
        return payload;
    }).filter((item) => Object.values(item).some((value) => String(value ?? '').trim() !== ''));
}

function syncApiNameOptionsFromForm() {
    const config = collectFormPayload();
    const apiNames = collectApiList()
        .map((item) => String(item.name || '').trim())
        .filter(Boolean);

    const mergedApiNames = Array.from(new Set([
        ...apiNames,
        deepGet(config, 'api.default_api', ''),
        deepGet(config, 'analysis.default_api', ''),
        config.fuck_or_not_api || '',
        config.q_command_api || '',
    ].filter(Boolean))).sort();

    document.querySelectorAll('[data-option-source="api_names"]').forEach((select) => {
        populateSelect(select, mergedApiNames, select.value);
    });
}

function collectFieldValue(field) {
    if (field.dataset.format === 'admin-ids') {
        return parseAdminIds(field.value || '');
    }
    if (field.type === 'checkbox') {
        return field.checked;
    }
    if (field.dataset.cast === 'int') {
        return Number(field.value || 0);
    }
    if (field.dataset.cast === 'float') {
        return Number(field.value || 0);
    }
    return field.value ?? '';
}

function collectFormPayload() {
    const payload = {};
    document.querySelectorAll('#systemConfigForm [data-config-path]').forEach((field) => {
        if (field.closest('.api-list')) {
            return;
        }
        deepSet(payload, field.dataset.configPath, collectFieldValue(field));
    });
    payload.api_list = collectApiList();
    return payload;
}

function setSensitiveVisibility(nextVisible) {
    sensitiveVisible = Boolean(nextVisible);
    document.querySelectorAll('[data-sensitive="true"]').forEach((field) => {
        if (field.tagName === 'INPUT') {
            field.type = sensitiveVisible ? 'text' : 'password';
        }
    });
    const toggleButton = qs('#toggleSensitiveBtn');
    if (toggleButton) {
        toggleButton.textContent = sensitiveVisible ? '闅愯棌鏁忔劅瀛楁' : '鏄剧ず鏁忔劅瀛楁';
    }
}

function applyPayload(payload) {
    pageState = payload;
    populateOptionFields(payload.config, payload.options);
    fillBasicFields(payload.config);
    renderApiList(payload.config.api_list || []);
    renderRestartNotice(payload);
    setSensitiveVisibility(false);

    const loading = qs('#systemConfigLoading');
    const form = qs('#systemConfigForm');
    const error = qs('#systemConfigError');
    const configLocalPathText = qs('#configLocalPathText');

    if (loading) {
        loading.hidden = true;
    }
    if (form) {
        form.hidden = false;
    }
    if (error) {
        error.hidden = true;
    }
    if (configLocalPathText) {
        configLocalPathText.textContent = `褰撳墠鍐欏叆鏂囦欢: ${payload.config_local_path}`;
    }
}

async function loadSystemConfig() {
    setLoading(true);
    try {
        const payload = await requestJson(API_ENDPOINTS.load);
        applyPayload(payload);
    } catch (error) {
        showError(error.message);
    }
}

async function saveSystemConfig(button) {
    const originalMarkup = button?.innerHTML || '';
    if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner-small"></span><span>淇濆瓨涓?/span>';
    }

    try {
        const payload = collectFormPayload();
        const result = await requestJson(API_ENDPOINTS.save, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (result.restart_required && Array.isArray(result.restart_required_fields)) {
            const labels = result.restart_required_fields
                .map((key) => result.restart_required_labels?.[key] || key)
                .join(' | ');
            showToast(`閰嶇疆宸蹭繚瀛橈紝浣嗕互涓嬮」闇€瑕侀噸鍚敓鏁? ${labels}`, 'info');
        } else {
            showToast('绯荤粺閰嶇疆宸蹭繚瀛樺埌 config_local.json', 'success');
        }
        await loadSystemConfig();
    } catch (error) {
        showToast(`淇濆瓨澶辫触锛?${error.message}`, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = originalMarkup;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="system-config"]');
    if (!pageRoot) {
        return;
    }

    delegate(pageRoot, 'click', '[data-action="toggle-sensitive"]', () => {
        setSensitiveVisibility(!sensitiveVisible);
    });

    delegate(pageRoot, 'click', '[data-action="save-system-config"]', async (_event, button) => {
        await saveSystemConfig(button);
    });

    delegate(pageRoot, 'click', '[data-action="add-api-item"]', () => {
        const container = qs('#apiList');
        container?.appendChild(renderApiItem());
        syncApiNameOptionsFromForm();
        setSensitiveVisibility(sensitiveVisible);
    });

    delegate(pageRoot, 'click', '[data-action="remove-api-item"]', (_event, button) => {
        const item = button.closest('[data-api-item]');
        item?.remove();
        if (!document.querySelector('[data-api-item]')) {
            qs('#apiList')?.appendChild(renderApiItem());
        }
        syncApiNameOptionsFromForm();
    });

    delegate(pageRoot, 'input', '[data-api-field="name"]', () => {
        syncApiNameOptionsFromForm();
    });

    loadSystemConfig();
});

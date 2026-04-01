import { createElementFromHtml, delegate, escapeHtml, qs } from '../core/dom.js';
import { requestJson } from '../core/http.js';
import { closeModal, openModal } from '../core/modal.js';
import { showToast } from '../core/toast.js';

const CATEGORY_ORDER = ['characters', 'config', 'prompts', 'agent_docs'];
const CATEGORY_LABELS = {
    characters: '角色配置',
    config: '系统配置',
    prompts: '提示词',
    agent_docs: '智能体文档',
};

const API_ENDPOINTS = {
    list: '/api/config/list',
    read: '/api/config/read',
    save: '/api/config/save',
    create: '/api/config/create',
    delete: '/api/config/delete',
};

let codeEditor;
let jsonEditor;
let currentFile = null;
let currentMode = 'visual';
let isDirty = false;
let isSyncingEditors = false;

function formatFileSize(bytes) {
    const size = Number(bytes || 0);
    if (size >= 1024 * 1024) {
        return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    }
    if (size >= 1024) {
        return `${(size / 1024).toFixed(1)} KB`;
    }
    return `${size} B`;
}

function formatDateTime(value) {
    if (!value) {
        return '未知';
    }

    const date = new Date(Number(value) * 1000);
    if (Number.isNaN(date.getTime())) {
        return '未知';
    }

    return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    }).format(date);
}

function setDirty(nextDirty) {
    isDirty = Boolean(nextDirty);
    const saveButton = qs('#saveBtn');
    if (saveButton) {
        saveButton.disabled = !currentFile || !isDirty;
    }
}

function updateToolbar(file = null) {
    const nameEl = qs('#currentFileName');
    const infoEl = qs('#currentFileInfo');
    const deleteButton = qs('#deleteBtn');

    if (!file) {
        nameEl.textContent = '请选择一个文件进行编辑';
        infoEl.textContent = '';
        deleteButton.disabled = true;
        setDirty(false);
        return;
    }

    nameEl.textContent = file.name || '未命名文件';
    infoEl.textContent = `路径: ${file.path}`;
    deleteButton.disabled = false;
}

function setEditorsContent(content) {
    isSyncingEditors = true;
    const normalizedContent = content ?? {};
    const jsonText = JSON.stringify(normalizedContent, null, 2);
    codeEditor.setValue(jsonText);
    jsonEditor.set(normalizedContent);
    isSyncingEditors = false;
    setDirty(false);
}

function clearEditors() {
    currentFile = null;
    setEditorsContent({});
    updateToolbar(null);
}

function syncFromVisualToCode() {
    const content = jsonEditor.get();
    isSyncingEditors = true;
    codeEditor.setValue(JSON.stringify(content, null, 2));
    isSyncingEditors = false;
}

function syncFromCodeToVisual() {
    const content = JSON.parse(codeEditor.getValue() || '{}');
    isSyncingEditors = true;
    jsonEditor.set(content);
    isSyncingEditors = false;
}

function setEditorMode(nextMode) {
    if (nextMode === currentMode) {
        return;
    }

    try {
        if (nextMode === 'visual') {
            syncFromCodeToVisual();
        } else {
            syncFromVisualToCode();
        }
    } catch (error) {
        showToast(`无法切换编辑模式：${error.message}`, 'error');
        return;
    }

    currentMode = nextMode;

    document.querySelectorAll('#editorModeTabs .tab-btn').forEach((button) => {
        button.classList.toggle('active', button.dataset.mode === nextMode);
    });

    document.querySelectorAll('.editor-pane').forEach((pane) => {
        pane.classList.toggle('active', pane.id === `${nextMode}-editor`);
    });

    if (nextMode === 'code') {
        window.setTimeout(() => codeEditor.refresh(), 0);
    }
}

function getActiveEditorContent() {
    if (currentMode === 'visual') {
        return jsonEditor.get();
    }

    return JSON.parse(codeEditor.getValue() || '{}');
}

function getTemplateContent(template, filename = '') {
    const lowerName = filename.toLowerCase();
    switch (template) {
    case 'character':
        return {
            name: '',
            description: '',
        };
    case 'config':
        return {
            api: {
                default_api: '',
                max_tokens: 8000,
            },
            user: {
                default_char: '',
                default_preset: '',
                default_stream: 'no',
            },
        };
    case 'prompt':
        return {
            prompt_set_list: [],
            prompts: [],
        };
    case 'agent_docs':
        if (lowerName.includes('exp')) {
            return [];
        }
        return {};
    case 'empty':
    default:
        return {};
    }
}

function buildFileItem(file) {
    const hasError = Boolean(file.error);
    const title = hasError
        ? `错误: ${file.error}`
        : `大小: ${formatFileSize(file.size)}, 修改时间: ${formatDateTime(file.modified)}`;

    return createElementFromHtml(`
        <button
            type="button"
            class="file-item${hasError ? ' error' : ''}"
            data-action="load-config-file"
            data-path="${escapeHtml(file.path || '')}"
            title="${escapeHtml(title)}"
            ${hasError ? 'disabled' : ''}
        >
            <span class="file-icon" aria-hidden="true">${hasError ? '!' : '{ }'}</span>
            <span class="file-item-copy">
                <span class="file-item-name">${escapeHtml(file.name || '未命名文件')}</span>
                <span class="file-item-meta">${hasError ? 'JSON 无法解析' : `${formatFileSize(file.size)} · ${formatDateTime(file.modified)}`}</span>
            </span>
            ${hasError ? '<span class="file-item-status">异常</span>' : ''}
        </button>
    `);
}

function renderFileList(data) {
    const fileList = qs('#fileList');
    if (!fileList) {
        return;
    }

    fileList.innerHTML = '';

    CATEGORY_ORDER.forEach((category) => {
        const files = Array.isArray(data?.[category]) ? [...data[category]] : [];
        files.sort((left, right) => (left.name || '').localeCompare(right.name || '', 'zh-CN'));

        const section = document.createElement('section');
        section.className = 'file-list-section';
        section.appendChild(createElementFromHtml(`
            <div class="category-header">${escapeHtml(CATEGORY_LABELS[category] || category)}</div>
        `));

        if (!files.length) {
            section.appendChild(createElementFromHtml(`
                <div class="empty-file-category">暂无文件</div>
            `));
        } else {
            files.forEach((file) => {
                const element = buildFileItem(file);
                if (currentFile && currentFile.path === file.path) {
                    element.classList.add('active');
                }
                section.appendChild(element);
            });
        }

        fileList.appendChild(section);
    });
}

function renderFileListLoading() {
    const fileList = qs('#fileList');
    if (!fileList) {
        return;
    }

    fileList.innerHTML = `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <span>正在加载配置文件...</span>
        </div>
    `;
}

function renderFileListError(message) {
    const fileList = qs('#fileList');
    if (!fileList) {
        return;
    }

    fileList.innerHTML = `
        <div class="error-state">
            <h3>配置列表加载失败</h3>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

async function refreshFileList(options = {}) {
    const { preserveSelection = true } = options;
    renderFileListLoading();

    try {
        const data = await requestJson(API_ENDPOINTS.list);
        if (!preserveSelection) {
            currentFile = null;
        }
        renderFileList(data);
    } catch (error) {
        renderFileListError(error.message);
        showToast(`加载文件列表失败：${error.message}`, 'error');
    }
}

function selectFileItem(path) {
    document.querySelectorAll('#fileList .file-item').forEach((item) => {
        item.classList.toggle('active', item.dataset.path === path);
    });
}

function confirmDiscardChanges() {
    if (!isDirty) {
        return true;
    }

    return window.confirm('当前文件有未保存修改，确定放弃这些更改吗？');
}

async function loadFile(filePath) {
    if (!filePath) {
        return;
    }

    if (currentFile?.path !== filePath && !confirmDiscardChanges()) {
        return;
    }

    updateToolbar({
        name: '正在加载...',
        path: filePath,
    });

    try {
        const payload = await requestJson(`${API_ENDPOINTS.read}?path=${encodeURIComponent(filePath)}`);
        currentFile = payload;
        setEditorsContent(payload.content);
        updateToolbar(payload);
        selectFileItem(filePath);
        if (currentMode === 'code') {
            window.setTimeout(() => codeEditor.refresh(), 0);
        }
    } catch (error) {
        updateToolbar(currentFile);
        showToast(`加载文件失败：${error.message}`, 'error');
    }
}

async function saveCurrentFile() {
    if (!currentFile) {
        showToast('请先选择一个文件。', 'info');
        return;
    }

    const saveButton = qs('#saveBtn');
    const originalMarkup = saveButton.innerHTML;
    saveButton.disabled = true;
    saveButton.innerHTML = '<span class="loading-spinner-small"></span><span>保存中</span>';

    try {
        const content = getActiveEditorContent();
        await requestJson(API_ENDPOINTS.save, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: currentFile.path,
                content,
            }),
        });

        currentFile.content = content;
        setDirty(false);
        await refreshFileList();
        selectFileItem(currentFile.path);
        showToast('配置文件已保存。', 'success');
    } catch (error) {
        showToast(`保存失败：${error.message}`, 'error');
    } finally {
        saveButton.disabled = !currentFile || !isDirty;
        saveButton.innerHTML = originalMarkup;
    }
}

async function deleteCurrentFile() {
    if (!currentFile) {
        showToast('请先选择一个文件。', 'info');
        return;
    }

    const confirmed = window.confirm(`确认删除 ${currentFile.name} 吗？系统会保留备份文件。`);
    if (!confirmed) {
        return;
    }

    const deleteButton = qs('#deleteBtn');
    const originalMarkup = deleteButton.innerHTML;
    deleteButton.disabled = true;
    deleteButton.innerHTML = '<span class="loading-spinner-small"></span><span>删除中</span>';

    try {
        await requestJson(API_ENDPOINTS.delete, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentFile.path }),
        });

        clearEditors();
        await refreshFileList({ preserveSelection: false });
        showToast('文件已删除，备份已保留。', 'success');
    } catch (error) {
        showToast(`删除失败：${error.message}`, 'error');
        updateToolbar(currentFile);
        deleteButton.disabled = false;
    } finally {
        deleteButton.innerHTML = originalMarkup;
    }
}

function openCreateFileModal() {
    const form = qs('#createFileForm');
    form?.reset();
    openModal('createFileModal');
    qs('#fileName')?.focus();
}

async function createFile() {
    const category = qs('#fileCategory')?.value || '';
    const fileNameInput = qs('#fileName');
    const template = qs('#fileTemplate')?.value || 'empty';
    const rawName = (fileNameInput?.value || '').trim();

    if (!category || !rawName) {
        showToast('请填写文件分类和文件名。', 'error');
        return;
    }

    const createButton = qs('#createFileBtn');
    const originalMarkup = createButton.innerHTML;
    createButton.disabled = true;
    createButton.innerHTML = '<span class="loading-spinner-small"></span><span>创建中</span>';

    try {
        const content = getTemplateContent(template, rawName);
        const payload = await requestJson(API_ENDPOINTS.create, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                category,
                filename: rawName,
                content,
            }),
        });

        closeModal('createFileModal');
        await refreshFileList();
        await loadFile(payload.path);
        showToast('新配置文件已创建。', 'success');
    } catch (error) {
        showToast(`创建失败：${error.message}`, 'error');
    } finally {
        createButton.disabled = false;
        createButton.innerHTML = originalMarkup;
    }
}

function initEditors() {
    if (!window.CodeMirror || !window.JSONEditor) {
        showToast('编辑器资源加载失败，请刷新页面重试。', 'error');
        return false;
    }

    codeEditor = window.CodeMirror.fromTextArea(qs('#codeEditor'), {
        mode: 'application/json',
        theme: 'monokai',
        lineNumbers: true,
        matchBrackets: true,
        autoCloseBrackets: true,
        foldGutter: true,
        gutters: ['CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
        indentUnit: 2,
        tabSize: 2,
    });

    jsonEditor = new window.JSONEditor(qs('#jsoneditor'), {
        mode: 'tree',
        modes: ['tree', 'view', 'form', 'code', 'text'],
        search: true,
        history: true,
        mainMenuBar: true,
        onChange() {
            if (!isSyncingEditors && currentFile) {
                setDirty(true);
            }
        },
    });

    codeEditor.on('change', () => {
        if (!isSyncingEditors && currentFile) {
            setDirty(true);
        }
    });

    setEditorsContent({});
    updateToolbar(null);
    return true;
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="config"]');
    if (!pageRoot) {
        return;
    }

    if (!initEditors()) {
        return;
    }

    delegate(pageRoot, 'click', '[data-action="load-config-file"]', async (_event, item) => {
        await loadFile(item.dataset.path);
    });

    delegate(pageRoot, 'click', '#editorModeTabs .tab-btn', (event, button) => {
        event.preventDefault();
        setEditorMode(button.dataset.mode || 'visual');
    });

    qs('[data-action="open-create-file-modal"]')?.addEventListener('click', openCreateFileModal);
    qs('[data-action="refresh-config-files"]')?.addEventListener('click', () => {
        if (!confirmDiscardChanges()) {
            return;
        }
        refreshFileList();
    });
    qs('[data-action="save-config-file"]')?.addEventListener('click', saveCurrentFile);
    qs('[data-action="delete-config-file"]')?.addEventListener('click', deleteCurrentFile);
    qs('[data-action="create-config-file"]')?.addEventListener('click', createFile);

    qs('#createFileForm')?.addEventListener('submit', (event) => {
        event.preventDefault();
        createFile();
    });

    window.addEventListener('beforeunload', (event) => {
        if (!isDirty) {
            return;
        }

        event.preventDefault();
        event.returnValue = '';
    });

    refreshFileList();
});

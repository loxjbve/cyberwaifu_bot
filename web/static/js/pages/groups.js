import { qs, delegate, escapeHtml } from '../core/dom.js';
import { requestJson } from '../core/http.js';
import { openModal, closeModal } from '../core/modal.js';
import { showToast } from '../core/toast.js';
import { syncCustomSelect } from '../core/select.js';

function formatDateTime(dateString) {
    if (!dateString) {
        return '未知';
    }

    return new Intl.DateTimeFormat('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    }).format(new Date(dateString));
}

function buildBadgeList(text, type = 'secondary') {
    if (!text) {
        return '<span class="text-muted">无</span>';
    }

    return text.split(',').map((item) => `<span class="badge ${type}">${escapeHtml(item.trim())}</span>`).join(' ');
}

function buildGroupDetailHtml(group) {
    return `
        <div class="user-detail-grid">
            <div class="detail-card">
                <h4 class="card-title">基本信息</h4>
                <div class="profile-body">
                    <div class="info-item"><span class="info-label">群组 ID</span><span class="info-value">#${escapeHtml(group.group_id)}</span></div>
                    <div class="info-item"><span class="info-label">群组名称</span><span class="info-value">${escapeHtml(group.group_name || '未命名')}</span></div>
                    <div class="info-item"><span class="info-label">状态</span><span class="info-value">${group.active ? '<span class="badge success">活跃</span>' : '<span class="badge danger">非活跃</span>'}</span></div>
                    <div class="info-item"><span class="info-label">更新时间</span><span class="info-value">${escapeHtml(formatDateTime(group.update_time))}</span></div>
                </div>
            </div>
            <div class="detail-card">
                <h4 class="card-title">核心统计</h4>
                <div class="stats-grid">
                    <div class="stat-item"><span class="stat-value">${Number(group.call_count || 0).toLocaleString('zh-CN')}</span><span class="stat-label">调用次数</span></div>
                    <div class="stat-item"><span class="stat-value">${((Number(group.rate || 0)) * 100).toFixed(1)}%</span><span class="stat-label">触发几率</span></div>
                </div>
            </div>
            <div class="detail-card">
                <h4 class="card-title">配置与规则</h4>
                <div class="config-grid">
                    <div class="config-item"><span class="config-label">角色</span><span class="config-value">${escapeHtml(group.char || '未设置')}</span></div>
                    <div class="config-item"><span class="config-label">API</span><span class="config-value">${escapeHtml(group.api || '默认')}</span></div>
                    <div class="config-item"><span class="config-label">预设</span><span class="config-value">${escapeHtml(group.preset || '默认')}</span></div>
                </div>
                <div class="config-item" style="margin-top: 1rem;"><span class="config-label">关键词</span><div class="config-value-box">${buildBadgeList(group.keywords)}</div></div>
                <div class="config-item" style="margin-top: 1rem;"><span class="config-label">禁用话题</span><div class="config-value-box">${buildBadgeList(group.disabled_topics, 'danger')}</div></div>
            </div>
        </div>
    `;
}

function populateEditForm(group) {
    const setValue = (id, value) => {
        const element = qs(`#${id}`);
        if (element) {
            element.value = value ?? '';
        }
    };

    setValue('editGroupId', group.group_id);
    setValue('editGroupName', group.group_name);
    setValue('editActive', group.active ? '1' : '0');
    setValue('editRate', group.rate ?? 0);
    setValue('editChar', group.char);
    setValue('editApi', group.api);
    setValue('editPreset', group.preset);
    setValue('editKeywords', group.keywords);
    setValue('editDisabledTopics', group.disabled_topics);
    syncCustomSelect(qs('#editActive'));
}

function updateGroupRow(groupId, group) {
    const row = qs(`[data-group-row][data-group-id="${groupId}"]`);
    if (!row) {
        return;
    }

    row.querySelector('[data-group-field="name"]').textContent = group.group_name || '未命名群组';
    row.querySelector('[data-group-field="call-count"]').textContent = `${Number(group.call_count || 0).toLocaleString('zh-CN')} 次`;
    row.querySelector('[data-group-field="char"]').textContent = group.char || '未设置';
    row.querySelector('[data-group-field="api"]').textContent = group.api || '默认';
    row.querySelector('[data-group-field="rate-fill"]').style.width = `${(Number(group.rate || 0) * 100).toFixed(1)}%`;
    row.querySelector('[data-group-field="rate-text"]').textContent = `${(Number(group.rate || 0) * 100).toFixed(1)}%`;
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="groups"]');
    if (!pageRoot) {
        return;
    }

    const detailModal = qs('#groupDetailModal');
    const editModal = qs('#groupEditModal');
    const profileModal = qs('#groupProfileModal');
    const detailContent = qs('#groupDetailContent');
    const profileContent = qs('#groupProfileContent');
    const dialogsBtn = qs('#viewGroupDialogsBtn');

    delegate(pageRoot, 'click', '[data-action="view-group"]', async (_event, button) => {
        const groupId = button.dataset.groupId;
        openModal(detailModal);
        detailContent.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><span>加载中...</span></div>';

        try {
            const group = await requestJson(`/api/groups/${groupId}`);
            detailContent.innerHTML = buildGroupDetailHtml(group);
            if (dialogsBtn) {
                dialogsBtn.href = `/admin/group_dialogs/${groupId}`;
            }
        } catch (error) {
            detailContent.innerHTML = `<div class="error-state"><h3>无法加载群组数据</h3><p>${escapeHtml(error.message)}</p></div>`;
        }
    });

    delegate(pageRoot, 'click', '[data-action="edit-group"]', async (_event, button) => {
        const groupId = button.dataset.groupId;
        openModal(editModal);

        try {
            const group = await requestJson(`/api/groups/${groupId}`);
            populateEditForm(group);
        } catch (error) {
            closeModal(editModal);
            showToast(`加载群组失败：${error.message}`, 'error');
        }
    });

    delegate(pageRoot, 'click', '[data-action="view-group-profile"]', async (_event, button) => {
        const groupId = button.dataset.groupId;
        openModal(profileModal);
        profileContent.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><span>加载中...</span></div>';

        try {
            const profiles = await requestJson(`/api/groups/${groupId}/profiles`);
            if (!profiles.length) {
                profileContent.innerHTML = '<div class="empty-state"><h3 class="empty-state-title">暂无用户画像</h3><p class="empty-state-description">该群组还没有生成任何用户画像。</p></div>';
                return;
            }

            profileContent.innerHTML = `
                <div class="profile-list">
                    ${profiles.map((profile) => `
                        <div class="profile-item" data-profile-card data-user-id="${profile.user_id}">
                            <div class="profile-item-header">
                                <span class="profile-user-name">${escapeHtml(((profile.first_name || '') + ' ' + (profile.last_name || '')).trim() || profile.user_name || `用户 ${profile.user_id}`)}</span>
                                <span class="profile-user-id">ID: ${escapeHtml(profile.user_id)}</span>
                            </div>
                            <div class="profile-item-body">
                                <textarea class="profile-json" readonly>${escapeHtml(profile.profile_json || '')}</textarea>
                            </div>
                            <div class="profile-footer">
                                <button type="button" class="btn-glass btn-sm" data-action="edit-profile">编辑</button>
                                <button type="button" class="btn-primary btn-sm" data-action="save-profile" hidden>保存</button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;

            profileContent.dataset.groupId = groupId;
        } catch (error) {
            profileContent.innerHTML = `<div class="error-state"><h3>无法加载用户画像</h3><p>${escapeHtml(error.message)}</p></div>`;
        }
    });

    delegate(document, 'click', '[data-action="save-group"]', async (_event, button) => {
        const groupId = qs('#editGroupId')?.value;
        const form = qs('#groupEditForm');
        if (!form || !groupId) {
            return;
        }

        const formData = Object.fromEntries(new FormData(form).entries());
        formData.active = Number(formData.active || 0);
        formData.rate = Number(formData.rate || 0);
        const originalMarkup = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner-small"></span><span>保存中</span>';

        try {
            await requestJson(`/api/groups/${groupId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            });

            const group = await requestJson(`/api/groups/${groupId}`);
            updateGroupRow(groupId, group);
            closeModal(editModal);
            showToast('群组信息已更新。', 'success');
        } catch (error) {
            showToast(`保存失败：${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalMarkup;
        }
    });

    delegate(document, 'click', '[data-action="edit-profile"]', (_event, button) => {
        const card = button.closest('[data-profile-card]');
        const textarea = card?.querySelector('.profile-json');
        if (!textarea) {
            return;
        }
        textarea.readOnly = false;
        textarea.focus();
        button.hidden = true;
        card.querySelector('[data-action="save-profile"]').hidden = false;
    });

    delegate(document, 'click', '[data-action="save-profile"]', async (_event, button) => {
        const card = button.closest('[data-profile-card]');
        const textarea = card?.querySelector('.profile-json');
        const groupId = profileContent.dataset.groupId;
        if (!card || !textarea || !groupId) {
            return;
        }

        const originalMarkup = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner-small"></span><span>保存中</span>';

        try {
            await requestJson(`/api/groups/${groupId}/profiles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: card.dataset.userId,
                    profile_json: textarea.value,
                }),
            });

            textarea.readOnly = true;
            button.hidden = true;
            card.querySelector('[data-action="edit-profile"]').hidden = false;
            showToast('画像已保存。', 'success');
        } catch (error) {
            showToast(`画像保存失败：${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalMarkup;
        }
    });
});

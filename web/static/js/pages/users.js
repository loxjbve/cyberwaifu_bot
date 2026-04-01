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

function formatCompactNumber(value) {
    const num = Number(value || 0);
    if (num >= 1000000) {
        return `${(num / 1000000).toFixed(2)}M`;
    }
    if (num >= 1000) {
        return `${(num / 1000).toFixed(1)}K`;
    }
    return `${num}`;
}

function getTierMarkup(tier) {
    if (Number(tier) === 1) {
        return '<span class="badge warning">VIP</span>';
    }
    if (Number(tier) === 2) {
        return '<span class="badge danger">SVIP</span>';
    }
    return '<span class="badge secondary">普通</span>';
}

function buildUserDetailHtml(payload) {
    const user = payload.user || {};
    const config = payload.config || {};
    const profiles = payload.profiles || [];
    const displayName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.user_name || '未设置';

    const profilesHtml = profiles.length ? `
        <div class="detail-card-full-width user-profiles-card">
            <h5 class="card-title">用户画像</h5>
            <div class="profiles-content">
                ${profiles.map((profile) => `
                    <div class="profile-item">
                        <div class="profile-item-header">
                            <span class="badge secondary">群组: ${escapeHtml(profile.group_id)}</span>
                        </div>
                        <div class="profile-item-body">${escapeHtml(profile.user_profile || '')}</div>
                    </div>
                `).join('')}
            </div>
        </div>
    ` : '';

    return `
        <div class="user-detail-grid">
            <div class="detail-card">
                <div class="profile-header">
                    <div class="profile-avatar">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                            <circle cx="12" cy="7" r="4"></circle>
                        </svg>
                    </div>
                    <div class="profile-info">
                        <h4 class="profile-name">${escapeHtml(displayName)}</h4>
                        <p class="profile-username">@${escapeHtml(user.user_name || 'N/A')}</p>
                    </div>
                    <div class="profile-tier">${getTierMarkup(user.account_tier)}</div>
                </div>
                <div class="profile-body">
                    <div class="info-item"><span class="info-label">用户 ID</span><span class="info-value">${escapeHtml(user.uid)}</span></div>
                    <div class="info-item"><span class="info-label">昵称</span><span class="info-value">${escapeHtml(config.nick || '未设置')}</span></div>
                    <div class="info-item"><span class="info-label">注册于</span><span class="info-value">${escapeHtml(formatDateTime(user.create_at))}</span></div>
                </div>
            </div>
            <div class="detail-card">
                <h5 class="card-title">账户统计</h5>
                <div class="stats-grid">
                    <div class="stat-item"><span class="stat-value">¥${Number(user.balance || 0).toFixed(2)}</span><span class="stat-label">余额</span></div>
                    <div class="stat-item"><span class="stat-value">${formatCompactNumber(user.remain_frequency)}</span><span class="stat-label">剩余额度</span></div>
                    <div class="stat-item"><span class="stat-value">${formatCompactNumber(user.conversations)}</span><span class="stat-label">总对话</span></div>
                    <div class="stat-item"><span class="stat-value">${formatCompactNumber(user.dialog_turns)}</span><span class="stat-label">总轮数</span></div>
                    <div class="stat-item"><span class="stat-value">${formatCompactNumber(user.input_tokens)}</span><span class="stat-label">输入 Tokens</span></div>
                    <div class="stat-item"><span class="stat-value">${formatCompactNumber(user.output_tokens)}</span><span class="stat-label">输出 Tokens</span></div>
                </div>
            </div>
            <div class="detail-card">
                <h5 class="card-title">高级配置</h5>
                <div class="config-grid">
                    <div class="config-item"><span class="config-label">角色</span><span class="config-value">${escapeHtml(config.char || '默认')}</span></div>
                    <div class="config-item"><span class="config-label">预设</span><span class="config-value">${escapeHtml(config.preset || '默认')}</span></div>
                    <div class="config-item"><span class="config-label">API</span><span class="config-value">${escapeHtml(config.api || '默认')}</span></div>
                    <div class="config-item"><span class="config-label">流式传输</span><span class="config-value">${escapeHtml(config.stream ?? '默认')}</span></div>
                </div>
            </div>
            ${profilesHtml}
        </div>
    `;
}

function populateEditForm(payload) {
    const user = payload.user || {};
    const config = payload.config || {};
    const setValue = (id, value) => {
        const element = qs(`#${id}`);
        if (element) {
            element.value = value ?? '';
        }
    };

    setValue('editUserId', user.uid);
    setValue('editUserName', user.user_name);
    setValue('editFirstName', user.first_name);
    setValue('editLastName', user.last_name);
    setValue('editNick', config.nick);
    setValue('editRemainFrequency', user.remain_frequency ?? 0);
    setValue('editBalance', Number(user.balance || 0).toFixed(2));
    setValue('editChar', config.char);
    setValue('editPreset', config.preset);
    setValue('editApi', config.api);
    setValue('editStream', config.stream);
    setValue('editAccountTier', user.account_tier ?? 0);
    syncCustomSelect(qs('#editAccountTier'));
}

function updateUserRow(userId, payload) {
    const row = qs(`[data-user-row][data-user-id="${userId}"]`);
    if (!row) {
        return;
    }

    const user = payload.user || {};
    const displayName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.user_name || '未设置';
    row.querySelector('[data-user-field="display-name"]').textContent = displayName;
    row.querySelector('[data-user-field="username"]').textContent = `@${user.user_name || 'N/A'}`;
    row.querySelector('[data-user-field="tier"]').innerHTML = getTierMarkup(user.account_tier);
    row.querySelector('[data-user-field="balance"]').textContent = `¥${Number(user.balance || 0).toFixed(2)}`;
    row.querySelector('[data-user-field="conversations"]').textContent = user.conversations || 0;
    row.querySelector('[data-user-field="dialog-turns"]').textContent = user.dialog_turns || 0;
    row.querySelector('[data-user-field="input-tokens"]').textContent = formatCompactNumber(user.input_tokens);
    row.querySelector('[data-user-field="output-tokens"]').textContent = formatCompactNumber(user.output_tokens);
}

document.addEventListener('DOMContentLoaded', () => {
    const pageRoot = document.querySelector('[data-page="users"]');
    if (!pageRoot) {
        return;
    }

    const detailModal = qs('#userDetailModal');
    const editModal = qs('#userEditModal');
    const detailContent = qs('#userDetailContent');

    delegate(pageRoot, 'click', '[data-action="view-user"]', async (event, button) => {
        event.preventDefault();
        const userId = button.dataset.uid;
        openModal(detailModal);
        detailContent.innerHTML = '<div class="loading-state"><div class="loading-spinner"></div><span>加载中...</span></div>';

        try {
            const payload = await requestJson(`/api/user/${userId}`);
            detailContent.innerHTML = buildUserDetailHtml(payload);
        } catch (error) {
            detailContent.innerHTML = `<div class="error-state"><h3>无法加载用户数据</h3><p>${escapeHtml(error.message)}</p></div>`;
        }
    });

    delegate(pageRoot, 'click', '[data-action="edit-user"]', async (event, button) => {
        event.preventDefault();
        const userId = button.dataset.uid;
        openModal(editModal);

        try {
            const payload = await requestJson(`/api/user/${userId}`);
            populateEditForm(payload);
        } catch (error) {
            closeModal(editModal);
            showToast(`加载用户失败：${error.message}`, 'error');
        }
    });

    delegate(document, 'click', '[data-action="save-user"]', async (event, button) => {
        event.preventDefault();
        const form = qs('#userEditForm');
        if (!form) {
            return;
        }

        const userId = qs('#editUserId')?.value;
        const payload = {
            user_id: userId,
            user_name: qs('#editUserName')?.value || '',
            first_name: qs('#editFirstName')?.value || '',
            last_name: qs('#editLastName')?.value || '',
            nick: qs('#editNick')?.value || '',
            account_tier: Number(qs('#editAccountTier')?.value || 0),
            remain_frequency: Number(qs('#editRemainFrequency')?.value || 0),
            balance: Number(qs('#editBalance')?.value || 0),
            config: {
                char: qs('#editChar')?.value || '',
                preset: qs('#editPreset')?.value || '',
                api: qs('#editApi')?.value || '',
                stream: qs('#editStream')?.value || '',
                nick: qs('#editNick')?.value || '',
            },
        };

        const originalMarkup = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="loading-spinner-small"></span><span>保存中</span>';

        try {
            await requestJson(`/api/user/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            const refreshed = await requestJson(`/api/user/${userId}`);
            updateUserRow(userId, refreshed);
            closeModal(editModal);
            showToast('用户信息已更新。', 'success');
        } catch (error) {
            showToast(`保存失败：${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalMarkup;
        }
    });
});

import { parseJsonDataset, qs } from '../core/dom.js';
import { showToast } from '../core/toast.js';

function buildLineChart(context, label, labels, values, color) {
    return new window.Chart(context, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label,
                data: values,
                borderColor: color,
                backgroundColor: `${color}22`,
                tension: 0.35,
                fill: true,
                pointRadius: 3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-soft'),
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted') },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted') },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                },
            },
        },
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const analytics = qs('[data-dashboard-analytics]');
    if (!analytics) {
        return;
    }

    qs('[data-action="refresh-dashboard"]')?.addEventListener('click', () => {
        window.location.reload();
    });

    analytics.querySelectorAll('.period-btn').forEach((button) => {
        button.addEventListener('click', () => {
            const period = button.dataset.period;
            const url = new URL(window.location.href);
            url.searchParams.set('time_range', period);
            window.location.href = url.toString();
        });
    });

    if (!window.Chart) {
        showToast('图表库未加载，已跳过趋势渲染。', 'error');
        return;
    }

    const userGrowth = parseJsonDataset(analytics.dataset.userGrowth, []);
    const dialogTrend = parseJsonDataset(analytics.dataset.dialogTrend, []);
    const groupTrend = parseJsonDataset(analytics.dataset.groupTrend, []);
    const tokenTrend = parseJsonDataset(analytics.dataset.tokenTrend, []);

    buildLineChart(
        qs('#userGrowthChart'),
        '新增用户',
        userGrowth.map((item) => item[0]),
        userGrowth.map((item) => item[1]),
        '#6fb6ff',
    );

    buildLineChart(
        qs('#conversationChart'),
        '对话量',
        dialogTrend.map((item) => item[0]),
        dialogTrend.map((item) => item[1]),
        '#3ed1b2',
    );

    buildLineChart(
        qs('#tokenUsageChart'),
        'Token',
        tokenTrend.map((item) => item[0]),
        tokenTrend.map((item) => item[1]),
        '#9d7cff',
    );

    buildLineChart(
        qs('#activityChart'),
        '群聊活跃度',
        groupTrend.map((item) => item[0]),
        groupTrend.map((item) => item[1]),
        '#f6c35d',
    );
});

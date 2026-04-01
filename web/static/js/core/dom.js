export function qs(selector, root = document) {
    return root.querySelector(selector);
}

export function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
}

export function delegate(root, eventName, selector, handler) {
    root.addEventListener(eventName, (event) => {
        const match = event.target.closest(selector);
        if (match && root.contains(match)) {
            handler(event, match);
        }
    });
}

export function escapeHtml(value = '') {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function createElementFromHtml(html) {
    const template = document.createElement('template');
    template.innerHTML = html.trim();
    return template.content.firstElementChild;
}

export function parseJsonDataset(value, fallback = null) {
    if (!value) {
        return fallback;
    }

    try {
        return JSON.parse(value);
    } catch (error) {
        console.warn('Failed to parse dataset JSON:', error);
        return fallback;
    }
}

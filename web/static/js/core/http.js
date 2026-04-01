export async function requestJson(url, options = {}) {
    const config = {
        headers: {
            Accept: 'application/json',
            ...(options.headers || {}),
        },
        ...options,
    };

    const response = await fetch(url, config);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
        ? await response.json()
        : await response.text();

    if (!response.ok) {
        const message = typeof payload === 'object'
            ? payload.error || payload.message || response.statusText
            : payload || response.statusText;
        throw new Error(message);
    }

    return payload;
}

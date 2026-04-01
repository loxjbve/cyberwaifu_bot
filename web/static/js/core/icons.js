export function refreshIcons() {
    if (window.feather) {
        window.feather.replace({
            'stroke-width': 1.8,
            width: 16,
            height: 16,
        });
    }
}

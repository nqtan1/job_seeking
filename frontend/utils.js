/**
 * RecruitAI Console Client - Global Helper Utilities
 */

export function showNotification(msg) {
    const div = document.createElement('div');
    div.className = 'fixed bottom-4 right-4 z-50 bg-slate-900 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 text-xs font-semibold animate-slide-in';
    div.innerHTML = `<i class="fa-solid fa-circle-check text-emerald-400 text-sm"></i> <span>${msg}</span>`;
    document.body.appendChild(div);
    setTimeout(() => {
        div.classList.add('opacity-0', 'transition-opacity', 'duration-300');
        setTimeout(() => div.remove(), 300);
    }, 3000);
}

export function showError(msg) {
    const div = document.createElement('div');
    div.className = 'fixed bottom-4 right-4 z-50 bg-slate-900 border border-rose-500/30 text-rose-400 px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 text-xs font-semibold animate-slide-in';
    div.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-rose-400 text-sm"></i> <span>${msg}</span>`;
    document.body.appendChild(div);
    setTimeout(() => {
        div.classList.add('opacity-0', 'transition-opacity', 'duration-300');
        setTimeout(() => div.remove(), 300);
    }, 4500);
}

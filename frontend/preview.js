/**
 * RecruitAI Console Client - Local Document Preview Rendering Engines
 */
import { state } from './state.js';

export function renderCVPreview() {
    const card = document.getElementById('cv-preview-card');
    const iframe = document.getElementById('cv-preview-iframe');
    const img = document.getElementById('cv-preview-img');
    const txt = document.getElementById('cv-preview-txt');
    const fallback = document.getElementById('cv-preview-fallback');

    // Hide everything inside
    [iframe, img, txt, fallback].forEach(el => el.classList.add('hidden'));

    if (!state.cvFile) {
        card.classList.add('hidden');
        return;
    }

    card.classList.remove('hidden');
    const ext = state.cvFile.name.substring(state.cvFile.name.lastIndexOf('.')).toLowerCase();

    try {
        if (ext === '.pdf') {
            iframe.src = URL.createObjectURL(state.cvFile);
            iframe.classList.remove('hidden');
        } else if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)) {
            img.src = URL.createObjectURL(state.cvFile);
            img.classList.remove('hidden');
        } else if (ext === '.txt') {
            const reader = new FileReader();
            reader.onload = function(e) {
                txt.textContent = e.target.result;
                txt.classList.remove('hidden');
            };
            reader.readAsText(state.cvFile);
        } else {
            fallback.classList.remove('hidden');
        }
    } catch (err) {
        console.error("CV Preview render failed:", err);
        fallback.classList.remove('hidden');
    }
}

export function renderJDPreview() {
    const card = document.getElementById('jd-preview-card');
    const iframe = document.getElementById('jd-preview-iframe');
    const img = document.getElementById('jd-preview-img');
    const txt = document.getElementById('jd-preview-txt');
    const fallback = document.getElementById('jd-preview-fallback');

    // Hide everything inside
    [iframe, img, txt, fallback].forEach(el => el.classList.add('hidden'));

    if (!state.jdFile || state.jdInputType !== 'file') {
        card.classList.add('hidden');
        return;
    }

    card.classList.remove('hidden');
    const ext = state.jdFile.name.substring(state.jdFile.name.lastIndexOf('.')).toLowerCase();

    try {
        if (ext === '.pdf') {
            iframe.src = URL.createObjectURL(state.jdFile);
            iframe.classList.remove('hidden');
        } else if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)) {
            img.src = URL.createObjectURL(state.jdFile);
            img.classList.remove('hidden');
        } else if (ext === '.txt') {
            const reader = new FileReader();
            reader.onload = function(e) {
                txt.textContent = e.target.result;
                txt.classList.remove('hidden');
            };
            reader.readAsText(state.jdFile);
        } else {
            fallback.classList.remove('hidden');
        }
    } catch (err) {
        console.error("JD Preview render failed:", err);
        fallback.classList.remove('hidden');
    }
}

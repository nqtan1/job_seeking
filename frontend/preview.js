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
            const newUrl = URL.createObjectURL(state.cvFile);
            
            // Re-create/clone the iframe element to bypass standard browser PDF caching/refresh issues
            const newIframe = iframe.cloneNode(true);
            newIframe.src = newUrl;
            iframe.parentElement.replaceChild(newIframe, iframe);
            
            newIframe.classList.remove('hidden');
        } else if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)) {
            img.src = URL.createObjectURL(state.cvFile);
            img.classList.remove('hidden');
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

    if (!state.jdFile || (state.jdInputType !== 'file' && state.jdInputType !== 'search')) {
        card.classList.add('hidden');
        return;
    }

    card.classList.remove('hidden');
    const ext = state.jdFile.name.substring(state.jdFile.name.lastIndexOf('.')).toLowerCase();

    try {
        if (ext === '.pdf') {
            const newUrl = URL.createObjectURL(state.jdFile);
            
            // Re-create/clone the iframe element to bypass standard browser PDF caching/refresh issues
            const newIframe = iframe.cloneNode(true);
            newIframe.src = newUrl;
            iframe.parentElement.replaceChild(newIframe, iframe);
            
            newIframe.classList.remove('hidden');
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

export function zoomDocument(type) {
    const file = type === 'cv' ? state.cvFile : state.jdFile;
    if (!file) return;

    const modal = document.getElementById('zoom-modal');
    const iframe = document.getElementById('zoom-iframe');
    const img = document.getElementById('zoom-img');
    const txt = document.getElementById('zoom-txt');
    const title = document.getElementById('zoom-modal-title');

    // Hide everything inside
    [iframe, img, txt].forEach(el => el.classList.add('hidden'));

    title.textContent = `${type === 'cv' ? 'Candidate Resume' : 'Job Description Requirements'} - ${file.name}`;
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

    try {
        if (ext === '.pdf') {
            const newUrl = URL.createObjectURL(file);
            
            // Re-create/clone the iframe element to bypass standard browser PDF caching/refresh issues
            const newIframe = iframe.cloneNode(true);
            newIframe.src = newUrl;
            iframe.parentElement.replaceChild(newIframe, iframe);
            
            newIframe.classList.remove('hidden');
        } else if (['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'].includes(ext)) {
            img.src = URL.createObjectURL(file);
            img.classList.remove('hidden');
        } else {
            if (type === 'jd') {
                const reader = new FileReader();
                reader.onload = function(e) {
                    txt.textContent = e.target.result;
                    txt.classList.remove('hidden');
                };
                reader.readAsText(file);
            }
        }

        // Show Modal with beautiful smooth transition
        modal.classList.remove('hidden');
        setTimeout(() => {
            modal.classList.remove('opacity-0', 'scale-95');
            modal.classList.add('opacity-100', 'scale-100');
        }, 10);

    } catch (err) {
        console.error("Zoom preview failed:", err);
    }
}

export function closeZoomModal() {
    const modal = document.getElementById('zoom-modal');
    modal.classList.remove('opacity-100', 'scale-100');
    modal.classList.add('opacity-0', 'scale-95');
    setTimeout(() => {
        modal.classList.add('hidden');
        document.getElementById('zoom-iframe').src = '';
        document.getElementById('zoom-img').src = '';
        document.getElementById('zoom-txt').textContent = '';
    }, 300);
}

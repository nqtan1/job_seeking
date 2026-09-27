/**
 * RecruitAI Console Client - Career Chat Coach Logic Module
 */
import { state } from './state.js';
import { sendCareerChatMessage as postCareerChatMessage } from './api.js';
import { showError } from './utils.js';

function appendMessageBubble(role, content) {
    const container = document.getElementById('career-chat-messages');
    if (!container) return null;

    const bubble = document.createElement('div');
    bubble.className = role === 'user'
        ? 'self-end bg-emerald-500/10 border border-emerald-500/20 text-emerald-100 rounded-lg px-3 py-2 text-xs max-w-[85%]'
        : 'self-start bg-slate-950 border border-slate-850 text-slate-200 rounded-lg px-3 py-2 text-xs max-w-[85%]';
    bubble.style.whiteSpace = 'pre-wrap';
    bubble.textContent = content; // textContent only: this is user- and LLM-generated free text
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
    return bubble;
}

export function renderCareerChat() {
    const container = document.getElementById('career-chat-messages');
    if (!container) return;
    container.innerHTML = '';
    state.careerChatHistory.forEach(turn => appendMessageBubble(turn.role, turn.content));
}

export function clearCareerChat() {
    state.careerChatHistory = [];
    renderCareerChat();
}

export async function sendCareerChatMessage() {
    const input = document.getElementById('career-chat-input');
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    if (!state.cvData) {
        showError('Load or extract a CV first to chat with the Career Coach.');
        return;
    }

    const sendBtn = document.getElementById('career-chat-send-btn');
    input.value = '';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    const historyBeforeThisTurn = state.careerChatHistory.slice();
    state.careerChatHistory.push({ role: 'user', content: message });
    appendMessageBubble('user', message);
    const thinkingBubble = appendMessageBubble('assistant', 'Thinking...');

    try {
        const payload = {
            candidate_cv: state.cvData,
            job_information: state.jobPosition || null,
            fit_check: state.fitCheck || null,
            interview_kit: state.interviewKit || null,
            message: message,
            history: historyBeforeThisTurn
        };
        const result = await postCareerChatMessage(payload, state.tenantId);

        if (thinkingBubble) thinkingBubble.remove();
        state.careerChatHistory.push({ role: 'assistant', content: result.reply });
        appendMessageBubble('assistant', result.reply);
    } catch (e) {
        console.error('Career chat failed:', e);
        if (thinkingBubble) thinkingBubble.remove();
        showError(`Career Coach error: ${e.message}`);
    } finally {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        input.focus();
    }
}

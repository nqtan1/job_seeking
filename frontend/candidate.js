/**
 * RecruitAI Console Client - Candidate Sandbox Logic Module
 */
import { state } from './state.js';
import { extractCV, extractJob, analyzeFit, generateLetter } from './api.js';
import { showNotification, showError } from './utils.js';
import { renderCVPreview, renderJDPreview } from './preview.js';

export async function runCandidateAnalysis() {
    if (!state.cvFile) {
        showError('Please upload a candidate resume file first!');
        return;
    }

    const jdText = document.getElementById('jd-text').value.trim();
    if (state.jdInputType === 'text' && !jdText) {
        showError('Please provide a Job Description to match against!');
        return;
    }
    if (state.jdInputType === 'file' && !state.jdFile) {
        showError('Please upload a Job Description document first!');
        return;
    }

    showCandidateLoader(true);

    try {
        // Step 1: CV Extraction
        const cvResult = await extractCV(state.cvFile, state.tenantId);
        state.cvData = cvResult.data;
        state.candidateId = cvResult.candidate_id;
        console.log("Parsed CV successfully:", state.cvData);

        // Step 2: Job Description Extraction
        const jobResult = await extractJob(state.jdInputType, state.jdFile, jdText, state.tenantId);
        state.jobPosition = jobResult.data || jobResult.extracted_data || jobResult;
        console.log("Parsed Job description successfully:", state.jobPosition);

        // Step 3: Fit Analysis & Interview Kit Generation
        const customContext = document.getElementById('fit-custom-context').value.trim();
        const fitResult = await analyzeFit(state.cvData, state.jobPosition, state.companyType, customContext, state.tenantId);
        
        state.fitCheck = fitResult.fit_check;
        state.interviewKit = fitResult.interview_kit;
        console.log("Analyzed Fit successfully:", state.fitCheck);
        console.log("Generated Interview Kit successfully:", state.interviewKit);

        // Render Outputs in DOM
        renderCandidateOutput();
        showNotification("Fit Analysis & Application Optimization complete!");

    } catch (err) {
        console.error("Full pipeline crash:", err);
        showError(`AI Engine Error: ${err.message}. Check your terminal logs or .env setup.`);
        showCandidateLoader(false);
    }
}

export function renderCandidateOutput() {
    showCandidateLoader(false);
    document.getElementById('candidate-placeholder').classList.add('hidden');
    document.getElementById('candidate-output').classList.remove('hidden');

    // Profile Details
    const name = state.cvData?.personal_info?.name || "Jane Doe";
    const email = state.cvData?.personal_info?.email || "unknown@email.com";
    const phone = state.cvData?.personal_info?.phone || "+1-555-0100";
    
    document.getElementById('profile-name').textContent = name;
    document.getElementById('profile-email-phone').textContent = `${email} | ${phone}`;

    // Score Ring and Badge
    const score = state.fitCheck?.fit_score ?? 75;
    const ring = document.getElementById('score-ring');
    const text = document.getElementById('score-text');
    const badge = document.getElementById('recommendation-badge');

    // SVG dashoffset calculation. Total dasharray is 175.9 for r=28.
    const maxOffset = 175.9;
    const offset = maxOffset - (score / 100) * maxOffset;
    ring.setAttribute('stroke-dashoffset', offset);
    text.textContent = `${score}%`;

    // Colors threshold
    if (score >= 80) {
        ring.setAttribute('stroke', '#10b981'); // Emerald
        badge.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider';
    } else if (score >= 50) {
        ring.setAttribute('stroke', '#f59e0b'); // Amber
        badge.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider';
    } else {
        ring.setAttribute('stroke', '#f43f5e'); // Rose
        badge.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 uppercase tracking-wider';
    }
    
    badge.textContent = state.fitCheck?.recommendation?.toUpperCase().replace('_', ' ') || 'MAYBE';

    // Summary
    document.getElementById('score-voice-summary').textContent = state.fitCheck?.summary || "A highly aligned fit matching primary requirements.";
    document.getElementById('analysis-confidence').textContent = state.fitCheck?.confidence ? `${Math.round(state.fitCheck.confidence * 100)}%` : '90%';

    // Strengths
    const strengthsUl = document.getElementById('strengths-list');
    strengthsUl.innerHTML = '';
    const strengths = state.fitCheck?.strengths || ["Highly skilled Python backend development background."];
    strengths.forEach(st => {
        const li = document.createElement('li');
        li.className = 'flex items-start gap-2 leading-relaxed';
        li.innerHTML = `<i class="fa-solid fa-chevron-right text-emerald-500 text-[10px] mt-1 shrink-0"></i> <span>${st}</span>`;
        strengthsUl.appendChild(li);
    });

    // Gaps
    const gapsUl = document.getElementById('gaps-list');
    gapsUl.innerHTML = '';
    const gaps = state.fitCheck?.gaps || ["Minor experience containerization gaps shown on paper."];
    gaps.forEach(gp => {
        const li = document.createElement('li');
        li.className = 'flex items-start gap-2 leading-relaxed';
        li.innerHTML = `<i class="fa-solid fa-circle-minus text-rose-400 text-[10px] mt-1 shrink-0"></i> <span>${gp}</span>`;
        gapsUl.appendChild(li);
    });

    // Constructive Feedback
    document.getElementById('constructive-feedback').textContent = state.fitCheck?.constructive_feedback || "Optimize your summary line to highlight containerized architectures, Docker experience, or microservices deployment grids matching requirements.";

    // Show/Hide Mock Interview Preparation Kit
    const kitCard = document.getElementById('interview-kit-card');
    const rec = (state.fitCheck?.recommendation || '').toLowerCase();
    if ((rec === 'go' || rec === 'maybe') && state.interviewKit) {
        kitCard.classList.remove('hidden');
        renderInterviewKit();
    } else {
        kitCard.classList.add('hidden');
    }

    // Hide any previous motivation letters
    document.getElementById('ml-output-container').classList.add('hidden');
    document.getElementById('ml-text-output').value = '';
}

export async function generateMotivationLetter() {
    if (!state.cvData || !state.jobPosition) {
        showError('Run fit analysis on your resume first!');
        return;
    }

    const btnGenerate = document.getElementById('btn-generate-ml');
    btnGenerate.disabled = true;
    btnGenerate.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> Drafting...`;

    try {
        const language = document.getElementById('ml-language').value;
        const tone = document.getElementById('ml-tone').value;
        const format = document.getElementById('ml-format').value;

        const result = await generateLetter(state.cvData, state.jobPosition, state.companyType, language, tone, format, state.tenantId);
        state.motivationLetter = result;

        // Display results
        const container = document.getElementById('ml-output-container');
        const textarea = document.getElementById('ml-text-output');
        
        container.classList.remove('hidden');
        textarea.value = result.content;
        
        showNotification("Motivation Letter drafted successfully!");

    } catch (err) {
        console.error(err);
        showError(`Letter Error: ${err.message}`);
    } finally {
        btnGenerate.disabled = false;
        btnGenerate.innerHTML = `<i class="fa-solid fa-feather-pointed"></i> Draft`;
    }
}

export function copyMotivationLetter() {
    const textarea = document.getElementById('ml-text-output');
    if (!textarea.value) return;
    
    navigator.clipboard.writeText(textarea.value);
    const btn = document.getElementById('btn-copy-ml');
    btn.innerHTML = `<i class="fa-solid fa-check text-emerald-400"></i> Copied!`;
    setTimeout(() => {
        btn.innerHTML = `<i class="fa-regular fa-copy"></i> Copy Letter`;
    }, 2000);
}

export function switchKitTab(tab) {
    state.activeKitTab = tab;
    const btnTech = document.getElementById('btn-kit-tech');
    const btnBeh = document.getElementById('btn-kit-beh');
    const btnSim = document.getElementById('btn-kit-sim');

    const panelTech = document.getElementById('kit-panel-tech');
    const panelBeh = document.getElementById('kit-panel-beh');
    const panelSim = document.getElementById('kit-panel-sim');

    // Reset button styles
    [btnTech, btnBeh, btnSim].forEach(btn => {
        btn.className = 'flex-1 py-1 rounded text-[10px] font-bold text-slate-400 hover:text-slate-100 transition-colors uppercase tracking-wider';
    });

    // Hide panels
    [panelTech, panelBeh, panelSim].forEach(panel => panel.classList.add('hidden'));

    if (tab === 'tech') {
        btnTech.className = 'flex-1 py-1 rounded text-[10px] font-bold bg-slate-800 text-slate-100 transition-colors uppercase tracking-wider shadow';
        panelTech.classList.remove('hidden');
    } else if (tab === 'beh') {
        btnBeh.className = 'flex-1 py-1 rounded text-[10px] font-bold bg-slate-800 text-slate-100 transition-colors uppercase tracking-wider shadow';
        panelBeh.classList.remove('hidden');
    } else {
        btnSim.className = 'flex-1 py-1 rounded text-[10px] font-bold bg-slate-800 text-slate-100 transition-colors uppercase tracking-wider shadow';
        panelSim.classList.remove('hidden');
    }
}

export function renderInterviewKit() {
    if (!state.interviewKit) return;

    // Render Technical Questions
    const techContainer = document.getElementById('tech-questions-container');
    techContainer.innerHTML = '';
    const techQs = state.interviewKit.technical_questions || [];
    techQs.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'flex flex-col gap-1.5 border-b border-slate-850/60 pb-3 last:border-0';
        div.innerHTML = `
            <div class="font-bold text-slate-200 text-xs flex gap-2">
                <span class="text-emerald-400 font-mono">Q${index + 1}:</span>
                <span>${item.question}</span>
            </div>
            <div class="text-[11px] text-slate-300 bg-slate-950/60 p-2.5 rounded border border-slate-900/60 leading-relaxed">
                <span class="font-bold text-emerald-400/80 uppercase text-[8px] tracking-wider block mb-1">Expected Answer guidelines:</span>
                ${item.expected_answer}
            </div>
            <div class="text-[10px] text-slate-500 italic px-1">
                <span class="font-bold text-slate-400 uppercase text-[8px] tracking-wider">Evaluation Focus:</span> ${item.reasoning}
            </div>
        `;
        techContainer.appendChild(div);
    });

    // Render Behavioral Questions
    const behContainer = document.getElementById('beh-questions-container');
    behContainer.innerHTML = '';
    const behQs = state.interviewKit.behavioral_questions || [];
    behQs.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'flex flex-col gap-1.5 border-b border-slate-850/60 pb-3 last:border-0';
        div.innerHTML = `
            <div class="font-bold text-slate-200 text-xs flex gap-2">
                <span class="text-emerald-400 font-mono">Q${index + 1}:</span>
                <span>${item.question}</span>
            </div>
            <div class="text-[11px] text-slate-300 bg-slate-950/60 p-2.5 rounded border border-slate-900/60 leading-relaxed">
                <span class="font-bold text-emerald-400/80 uppercase text-[8px] tracking-wider block mb-1">Star Method Alignment:</span>
                ${item.expected_answer}
            </div>
            <div class="text-[10px] text-slate-500 italic px-1">
                <span class="font-bold text-slate-400 uppercase text-[8px] tracking-wider">Evaluation Focus:</span> ${item.reasoning}
            </div>
        `;
        behContainer.appendChild(div);
    });

    // Render Simulation Prompt
    document.getElementById('sim-prompt-text').value = state.interviewKit.simulation_prompt || '';

    // Reset to technical tab
    switchKitTab('tech');
}

export function copySimulationPrompt() {
    const text = document.getElementById('sim-prompt-text');
    if (!text.value) return;

    navigator.clipboard.writeText(text.value);
    const btn = document.getElementById('btn-copy-sim');
    btn.innerHTML = `<i class="fa-solid fa-check text-emerald-400"></i> Copied!`;
    setTimeout(() => {
        btn.innerHTML = `<i class="fa-regular fa-copy"></i> Copy Prompt`;
    }, 2000);
}

export function resetOutputs() {
    document.getElementById('candidate-output').classList.add('hidden');
    document.getElementById('candidate-placeholder').classList.remove('hidden');
}

export function clearCV() {
    state.cvFile = null;
    state.cvFileName = '';
    state.cvData = null;
    state.candidateId = null;

    document.getElementById('cv-file').value = '';
    document.getElementById('cv-upload-info').classList.add('hidden');
    document.getElementById('cv-dropzone').classList.remove('hidden');
    
    const statusBadge = document.getElementById('cv-status');
    statusBadge.textContent = 'Empty';
    statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-slate-950 border border-slate-850 text-slate-500 uppercase tracking-wider';
    
    resetOutputs();
    renderCVPreview();
}

export function showCandidateLoader(show) {
    const placeholder = document.getElementById('candidate-placeholder');
    const loader = document.getElementById('candidate-loader');
    const output = document.getElementById('candidate-output');

    if (show) {
        placeholder.classList.add('hidden');
        output.classList.add('hidden');
        loader.classList.remove('hidden');
    } else {
        loader.classList.add('hidden');
    }
}

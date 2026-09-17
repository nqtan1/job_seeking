/**
 * RecruitAI Console Client - Candidate Sandbox Logic Module
 */
import { state } from './state.js';
import { extractCV, extractJob, analyzeFit, generateLetter, listCandidates, searchJobs, getJobDetail, getCandidateFile, generateTempPDF } from './api.js';
import { showNotification, showError } from './utils.js';
import { renderCVPreview, renderJDPreview } from './preview.js';

export async function runCandidateAnalysis() {
    let cvData = state.cvData;
    let candidateId = state.candidateId;

    if (!cvData) {
        if (!state.cvFile) {
            showError('Please upload a candidate resume file or select an existing saved profile first!');
            return;
        }
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
    if (state.jdInputType === 'search' && !state.jobPosition) {
        showError('Please search and select a job from the search engine first!');
        return;
    }

    showCandidateLoader(true);
    updateLoaderBubble("Initializing AI Sandbox... 🤖");

    try {
        // Step 1: CV Extraction (skip if already loaded)
        if (!cvData) {
            updateLoaderBubble("Extracting candidate CV profile... 🔍");
            console.log("Extracting CV document...");
            const cvResult = await extractCV(state.cvFile, state.tenantId);
            cvData = cvResult.data;
            candidateId = cvResult.candidate_id;
            state.cvData = cvData;
            state.candidateId = candidateId;
            console.log("Parsed CV successfully:", state.cvData);

            // Refresh DB candidates list immediately, which will auto-select the newly added CV!
            if (window.populateDbCandidates) {
                await window.populateDbCandidates();
            }
        } else {
            console.log("Reusing cached candidate CV data.");
        }

        // Step 2: Job Description Extraction (skip if already selected via search)
        let jobPosition = state.jobPosition;
        if (state.jdInputType !== 'search' || !jobPosition) {
            updateLoaderBubble("Parsing Job Description requirements... 📑");
            console.log("Extracting Job description...");
            const jobResult = await extractJob(state.jdInputType, state.jdFile, jdText, state.tenantId);
            jobPosition = jobResult.data || jobResult.extracted_data || jobResult;
            state.jobPosition = jobPosition;
            console.log("Parsed Job description successfully:", state.jobPosition);
        } else {
            console.log("Reusing selected job posting detail:", jobPosition);
        }

        // Step 3: Fit Analysis & Interview Kit Generation
        updateLoaderBubble("Analyzing profile alignment and skills... 🧠");
        const customContext = document.getElementById('fit-custom-context').value.trim();
        const fitResult = await analyzeFit(cvData, jobPosition, state.companyType, customContext, state.tenantId);
        
        state.fitCheck = fitResult.fit_check;
        state.interviewKit = fitResult.interview_kit;
        console.log("Analyzed Fit successfully:", state.fitCheck);
        console.log("Generated Interview Kit successfully:", state.interviewKit);

        updateLoaderBubble("Ah! Your result is almost done! 🚀");
        await new Promise(resolve => setTimeout(resolve, 800));

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
    btnGenerate.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> Drafting & Compiling...`;

    try {
        const language = document.getElementById('ml-language').value;
        const tone = document.getElementById('ml-tone').value;
        const format = document.getElementById('ml-format').value;

        // Compile and typeset cover letter PDF
        const result = await generateTempPDF(state.cvData, state.jobPosition, state.companyType, language, tone, 'txt', state.tenantId);
        state.motivationLetter = result;

        // Display results
        const container = document.getElementById('ml-output-container');
        const textarea = document.getElementById('ml-text-output');
        const pdfContainer = document.getElementById('ml-pdf-container');
        const pdfPreview = document.getElementById('ml-pdf-preview');
        
        container.classList.remove('hidden');
        textarea.value = result.content;

        if (pdfPreview && result.pdf_url) {
            pdfPreview.src = result.pdf_url;
            pdfContainer.classList.remove('hidden');
        } else if (pdfContainer) {
            pdfContainer.classList.add('hidden');
        }
        
        showNotification("Motivation Letter drafted and typeset PDF compiled successfully!");

    } catch (err) {
        console.error(err);
        showError(`Letter Error: ${err.message}`);
    } finally {
        btnGenerate.disabled = false;
        btnGenerate.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Generate AI Draft (PDF)`;
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

    const selectEl = document.getElementById('select-db-candidate');
    if (selectEl) selectEl.value = '';

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

export function updateLoaderBubble(text) {
    const el = document.getElementById('candidate-loader-bubble-text');
    if (el) el.textContent = text;
}

export async function loadDbCandidate(candidateId) {
    if (!candidateId) {
        clearCV();
        return;
    }

    const candidate = state.dbCandidates.find(c => String(c.candidate_id) === String(candidateId));
    if (!candidate) {
        showError("Profile not found in database.");
        return;
    }

    try {
        let extractedData = candidate.extracted_data;
        if (typeof extractedData === 'string') {
            extractedData = JSON.parse(extractedData);
        }

        state.cvData = extractedData;
        state.candidateId = candidate.candidate_id;

        document.getElementById('cv-filename').textContent = `${candidate.name} (Saved Profile)`;
        document.getElementById('cv-upload-info').classList.remove('hidden');
        document.getElementById('cv-dropzone').classList.add('hidden');

        const statusBadge = document.getElementById('cv-status');
        statusBadge.textContent = 'Loaded (DB)';
        statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider';

        try {
            // Retrieve actual raw file (PDF/Image) from database/server
            const fileBlob = await getCandidateFile(candidate.candidate_id, state.tenantId);
            
            // Extract the correct file extension from candidate's file path if available, or fall back to response content-type
            let ext = '.pdf';
            if (candidate.file_path) {
                const dotIdx = candidate.file_path.lastIndexOf('.');
                if (dotIdx !== -1) {
                    ext = candidate.file_path.substring(dotIdx).toLowerCase();
                }
            } else {
                const mimeType = fileBlob.type || 'application/pdf';
                if (mimeType.includes('png')) ext = '.png';
                else if (mimeType.includes('jpeg') || mimeType.includes('jpg')) ext = '.jpg';
                else if (mimeType.includes('plain') || mimeType.includes('text')) ext = '.txt';
            }

            const mimeType = fileBlob.type || (ext === '.png' ? 'image/png' : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' : 'application/pdf');
            const originalName = `${candidate.name.replace(/\s+/g, '_')}_resume${ext}`;

            state.cvFile = new File([fileBlob], originalName, { type: mimeType });
            state.cvFileName = originalName;
            console.log(`Loaded original CV document preview: ${originalName} (${mimeType})`);
        } catch (fileErr) {
            console.warn("Could not retrieve original document file from backend, falling back to text summary:", fileErr);
            
            // Generate fallback dynamic mock file in-memory for preview rendering
            const skillsList = extractedData.skills ? extractedData.skills.map(s => typeof s === 'string' ? s : s.name).join(', ') : '';
            const expList = extractedData.experiences ? extractedData.experiences.map(e => `- ${e.job_title} at ${e.company} (${e.start_date || 'N/A'} - ${e.end_date || 'N/A'}): ${e.description || ''}`).join('\n') : '';
            const eduList = extractedData.formations ? extractedData.formations.map(e => `- ${e.degree} in ${e.field} from ${e.institution}`).join('\n') : '';

            const summaryTxt = `CANDIDATE SAVED PROFILE:\nName: ${candidate.name}\nEmail: ${candidate.email}\nPhone: ${candidate.phone}\n\nSKILLS:\n${skillsList}\n\nEXPERIENCE:\n${expList}\n\nEDUCATION:\n${eduList}`;
            
            state.cvFile = new File([summaryTxt], `${candidate.name.replace(/\s+/g, '_')}_profile.txt`, {type: "text/plain"});
            state.cvFileName = `${candidate.name}_profile.txt`;
        }
        
        renderCVPreview();
        resetOutputs();
        showNotification(`Profile for ${candidate.name} loaded successfully!`);
    } catch (e) {
        console.error("Failed to parse extracted data:", e);
        showError("Corrupted profile data in database.");
    }
}


export async function triggerJobSearch() {
    const btn = document.getElementById('btn-search-jobs');
    const resultsContainer = document.getElementById('search-results-list');
    
    const query = document.getElementById('search-query').value.trim();
    const department = document.getElementById('search-dept').value.trim();
    const contract = document.getElementById('search-contract').value;

    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner animate-spin text-xs"></i> Searching...`;
    
    try {
        const result = await searchJobs(state.searchProvider, query, department, contract, state.tenantId);
        state.searchResults = result.jobs || result.results || [];
        
        resultsContainer.innerHTML = '';
        resultsContainer.classList.remove('hidden');

        if (state.searchResults.length === 0) {
            resultsContainer.innerHTML = `<p class="text-[10px] text-slate-500 italic text-center py-3">No jobs found matching criteria.</p>`;
            return;
        }

        state.searchResults.forEach(job => {
            const div = document.createElement('div');
            div.className = 'p-2 rounded bg-slate-900 border border-slate-850 hover:border-emerald-500/40 cursor-pointer transition-all flex flex-col gap-1';
            div.onclick = () => selectSearchJob(job.id);
            div.innerHTML = `
                <div class="flex items-center justify-between gap-1.5 min-w-0">
                    <span class="text-xs font-bold text-slate-200 truncate hover:text-emerald-400 transition-colors">${job.title}</span>
                    <span class="text-[9px] font-mono font-bold bg-slate-950 text-slate-400 px-1 py-0.5 rounded shrink-0 border border-slate-850">${job.contract_type}</span>
                </div>
                <div class="flex items-center justify-between text-[9px] text-slate-400 font-medium">
                    <span class="truncate">${job.company}</span>
                    <span class="shrink-0"><i class="fa-solid fa-location-dot text-[8px] mr-0.5 text-emerald-400/80"></i>${job.location}</span>
                </div>
            `;
            resultsContainer.appendChild(div);
        });

        showNotification(`Found ${state.searchResults.length} job postings!`);

    } catch (e) {
        console.error("Job search failed:", e);
        showError(`Search failed: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-magnifying-glass text-xs"></i> Search Job Postings`;
    }
}

export async function selectSearchJob(jobId) {
    const resultsContainer = document.getElementById('search-results-list');
    showNotification(`Retrieving detailed job posting information...`);
    try {
        const result = await getJobDetail(state.searchProvider, jobId, state.tenantId);
        const positionData = result.job_position_data;
        
        state.jobPosition = positionData;
        state.selectedSearchJob = result;

        // Auto fill pasted text as backup
        document.getElementById('jd-text').value = positionData.job_description_text || '';

        // Render card
        document.getElementById('selected-job-title').textContent = positionData.job_title;
        document.getElementById('selected-job-meta').textContent = `${positionData.company} | ${positionData.location} | ${positionData.contract_type}`;
        document.getElementById('selected-job-snippet').textContent = (positionData.job_description_text || '').substring(0, 120) + '...';
        
        document.getElementById('selected-job-info').classList.remove('hidden');
        resultsContainer.classList.add('hidden');

        const statusBadge = document.getElementById('jd-status');
        statusBadge.textContent = 'Linked';
        statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 uppercase tracking-wider';

        // Set up local file preview in-memory for detail recheck zoom
        const rawText = positionData.job_description_text || '';
        state.jdFile = new File([rawText], `job_posting_${jobId}.txt`, {type: "text/plain"});
        renderJDPreview();

        showNotification(`Job detail retrieved and linked to evaluation context successfully!`);

    } catch (e) {
        console.error("Failed to load job details:", e);
        showError(`Detail retrieve failed: ${e.message}`);
    }
}

export function clearSelectedSearchJob() {
    state.jobPosition = null;
    state.selectedSearchJob = null;
    state.jdFile = null;

    document.getElementById('selected-job-info').classList.add('hidden');
    document.getElementById('jd-text').value = '';
    
    const statusBadge = document.getElementById('jd-status');
    statusBadge.textContent = 'Empty';
    statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-slate-950 border border-slate-850 text-slate-500 uppercase tracking-wider';
    
    renderJDPreview();
}

export function applyDomainFilter(keywords) {
    if (!keywords) return;
    document.getElementById('search-query').value = keywords;
    triggerJobSearch();
}

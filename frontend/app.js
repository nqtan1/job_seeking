/**
 * RecruitAI Console Client - Application Bootstrapper & Orchestrator
 */
import { state } from './state.js';
import { renderCVPreview, renderJDPreview } from './preview.js';
import { 
    runCandidateAnalysis, 
    generateMotivationLetter, 
    copyMotivationLetter, 
    switchKitTab, 
    copySimulationPrompt, 
    clearCV,
    resetOutputs 
} from './candidate.js';
import { 
    runBatchScreening, 
    clearBulkGroup, 
    viewCandidateOutreach, 
    copyOutreachEmail, 
    renderBulkList 
} from './recruiter.js';
import { showNotification, showError } from './utils.js';

// Initialize App Immediately (ES6 Modules are deferred by default, meaning DOM is guaranteed to be parsed)
initTenantSelector();
initCVDropzone();
initJDDropzone();
initBulkDropzone();
initCompanyTypes();

// Bind public window functions for HTML access
window.switchTab = switchTab;
window.switchJDInputType = switchJDInputType;
window.updateJDTextStatus = updateJDTextStatus;
window.setCompanyType = setCompanyType;
window.runCandidateAnalysis = runCandidateAnalysis;
window.generateMotivationLetter = generateMotivationLetter;
window.copyMotivationLetter = copyMotivationLetter;
window.switchKitTab = switchKitTab;
window.copySimulationPrompt = copySimulationPrompt;
window.clearCV = clearCV;
window.clearJDFile = clearJDFile;

window.runBatchScreening = runBatchScreening;
window.clearBulkGroup = clearBulkGroup;
window.viewCandidateOutreach = viewCandidateOutreach;
window.copyOutreachEmail = copyOutreachEmail;

// ==========================================
// 1. Navigation & Configurations
// ==========================================
function switchTab(tab) {
    const btnCandidate = document.getElementById('tab-candidate');
    const btnRecruiter = document.getElementById('tab-recruiter');
    const viewCandidate = document.getElementById('view-candidate');
    const viewRecruiter = document.getElementById('view-recruiter');

    if (tab === 'candidate') {
        btnCandidate.className = 'flex-1 py-2 px-4 rounded-lg font-semibold text-sm transition-all duration-150 flex items-center justify-center gap-2 text-slate-100 bg-slate-800 shadow shadow-slate-950';
        btnRecruiter.className = 'flex-1 py-2 px-4 rounded-lg font-semibold text-sm transition-all duration-150 flex items-center justify-center gap-2 text-slate-400 hover:text-slate-100';
        viewCandidate.classList.remove('hidden');
        viewRecruiter.classList.add('hidden');
    } else {
        btnRecruiter.className = 'flex-1 py-2 px-4 rounded-lg font-semibold text-sm transition-all duration-150 flex items-center justify-center gap-2 text-slate-100 bg-slate-800 shadow shadow-slate-950';
        btnCandidate.className = 'flex-1 py-2 px-4 rounded-lg font-semibold text-sm transition-all duration-150 flex items-center justify-center gap-2 text-slate-400 hover:text-slate-100';
        viewRecruiter.classList.remove('hidden');
        viewCandidate.classList.add('hidden');
        renderBulkList();
    }
}

function initTenantSelector() {
    const input = document.getElementById('tenant-id');
    input.addEventListener('change', (e) => {
        state.tenantId = e.target.value.trim() || 'default-tenant';
        console.log(`Switched X-Tenant-ID context to: ${state.tenantId}`);
        showNotification(`Tenant switched to: ${state.tenantId}`);
    });
}

function initCompanyTypes() {
    setCompanyType('corporation');
}

function setCompanyType(type) {
    state.companyType = type;
    const btnStartup = document.getElementById('btn-comp-startup');
    const btnPhd = document.getElementById('btn-comp-phd');
    const btnCorp = document.getElementById('btn-comp-corporation');

    // Reset styles
    [btnStartup, btnPhd, btnCorp].forEach(btn => {
        btn.className = 'py-2 px-3 border border-slate-850 rounded-lg text-xs font-semibold bg-slate-950 text-slate-400 transition-colors';
    });

    // Set active style
    if (type === 'startup') {
        btnStartup.className = 'py-2 px-3 border border-emerald-500/20 rounded-lg text-xs font-semibold bg-slate-950 text-emerald-400 shadow shadow-emerald-950/20';
    } else if (type === 'phd') {
        btnPhd.className = 'py-2 px-3 border border-emerald-500/20 rounded-lg text-xs font-semibold bg-slate-950 text-emerald-400 shadow shadow-emerald-950/20';
    } else {
        btnCorp.className = 'py-2 px-3 border border-emerald-500/20 rounded-lg text-xs font-semibold bg-slate-950 text-emerald-400 shadow shadow-emerald-950/20';
    }
}

// ==========================================
// 2. Local Document Ingestion Listeners
// ==========================================
function initCVDropzone() {
    const dropzone = document.getElementById('cv-dropzone');
    const fileInput = document.getElementById('cv-file');

    dropzone.addEventListener('click', () => fileInput.click());
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('border-emerald-500/80', 'bg-slate-900/40');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('border-emerald-500/80', 'bg-slate-900/40');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('border-emerald-500/80', 'bg-slate-900/40');
        if (e.dataTransfer.files.length > 0) {
            handleCVSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleCVSelect(e.target.files[0]);
        }
    });
}

function handleCVSelect(file) {
    state.cvFile = file;
    state.cvFileName = file.name;
    
    document.getElementById('cv-filename').textContent = file.name;
    document.getElementById('cv-upload-info').classList.remove('hidden');
    document.getElementById('cv-dropzone').classList.add('hidden');
    
    const statusBadge = document.getElementById('cv-status');
    statusBadge.textContent = 'Selected';
    statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider';
    
    renderCVPreview();
}

function switchJDInputType(type) {
    state.jdInputType = type;
    const btnText = document.getElementById('btn-jd-type-text');
    const btnFile = document.getElementById('btn-jd-type-file');
    const containerText = document.getElementById('jd-text-container');
    const containerFile = document.getElementById('jd-file-container');

    if (type === 'text') {
        btnText.className = 'flex-1 py-1.5 px-3 rounded-md font-semibold text-xs transition-colors bg-slate-800 text-slate-100 shadow shadow-slate-950';
        btnFile.className = 'flex-1 py-1.5 px-3 rounded-md font-semibold text-xs transition-colors text-slate-400 hover:text-slate-100';
        containerText.classList.remove('hidden');
        containerFile.classList.add('hidden');
    } else {
        btnFile.className = 'flex-1 py-1.5 px-3 rounded-md font-semibold text-xs transition-colors bg-slate-800 text-slate-100 shadow shadow-slate-950';
        btnText.className = 'flex-1 py-1.5 px-3 rounded-md font-semibold text-xs transition-colors text-slate-400 hover:text-slate-100';
        containerFile.classList.remove('hidden');
        containerText.classList.add('hidden');
    }
    
    if (type === 'text') {
        updateJDTextStatus();
    } else {
        const statusBadge = document.getElementById('jd-status');
        if (state.jdFile) {
            statusBadge.textContent = 'Selected';
            statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider';
        } else {
            statusBadge.textContent = 'Empty';
            statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-slate-950 border border-slate-850 text-slate-500 uppercase tracking-wider';
        }
    }
    
    renderJDPreview();
}

function initJDDropzone() {
    const dropzone = document.getElementById('jd-dropzone');
    const fileInput = document.getElementById('jd-file');

    dropzone.addEventListener('click', () => fileInput.click());
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('border-emerald-500/80', 'bg-slate-900/40');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('border-emerald-500/80', 'bg-slate-900/40');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('border-emerald-500/80', 'bg-slate-900/40');
        if (e.dataTransfer.files.length > 0) {
            handleJDSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleJDSelect(e.target.files[0]);
        }
    });
}

function handleJDSelect(file) {
    state.jdFile = file;
    state.jdFileName = file.name;
    
    document.getElementById('jd-filename').textContent = file.name;
    document.getElementById('jd-upload-info').classList.remove('hidden');
    document.getElementById('jd-dropzone').classList.add('hidden');
    
    const statusBadge = document.getElementById('jd-status');
    statusBadge.textContent = 'Selected';
    statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider';
    
    renderJDPreview();
}

function clearJDFile() {
    state.jdFile = null;
    state.jdFileName = '';
    
    document.getElementById('jd-file').value = '';
    document.getElementById('jd-upload-info').classList.add('hidden');
    document.getElementById('jd-dropzone').classList.remove('hidden');
    
    const statusBadge = document.getElementById('jd-status');
    statusBadge.textContent = 'Empty';
    statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-slate-950 border border-slate-850 text-slate-500 uppercase tracking-wider';
    
    renderJDPreview();
}

function updateJDTextStatus() {
    const text = document.getElementById('jd-text').value.trim();
    const statusBadge = document.getElementById('jd-status');
    if (text) {
        statusBadge.textContent = 'Pasted';
        statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase tracking-wider';
    } else {
        statusBadge.textContent = 'Empty';
        statusBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-slate-950 border border-slate-850 text-slate-500 uppercase tracking-wider';
    }
}

// ==========================================
// 3. Recruiter Ingestion Setup
// ==========================================
function initBulkDropzone() {
    const dropzone = document.getElementById('bulk-dropzone');
    const fileInput = document.getElementById('bulk-file-input');

    dropzone.addEventListener('click', () => fileInput.click());
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('border-emerald-500/85', 'bg-slate-900/40');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('border-emerald-500/85', 'bg-slate-900/40');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('border-emerald-500/85', 'bg-slate-900/40');
        if (e.dataTransfer.files.length > 0) {
            handleBulkSelect(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleBulkSelect(e.target.files);
        }
    });
}

function handleBulkSelect(files) {
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const randomId = "c" + Math.floor(Math.random() * 1000);
        state.recruiterCandidates.push({
            candidate_id: randomId,
            name: file.name.replace(/\.[^/.]+$/, "").replace(/_/g, " "),
            email: `${randomId}@firm-candidate.com`,
            phone: "+33-6-00-11-22-33",
            skills: ["Python", "FastAPI", "PostgreSQL", "Docker"]
        });
    }
    
    renderBulkList();
    showNotification(`Added ${files.length} resume(s) to the screening group pool!`);
}

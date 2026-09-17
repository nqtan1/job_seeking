import { state } from './state.js';
import { 
    createApplication, 
    getApplications, 
    updateApplication, 
    deleteApplication, 
    uploadApplicationFile,
    uploadSpecialDocuments,
    listCandidates
} from './api.js';
import { showNotification, showError } from './utils.js';

/**
 * Initialize Tracker View (setup defaults)
 */
export function initTracker() {
    // Set up default date in input to today's date
    const dateInput = document.getElementById('form-applied-date');
    if (dateInput) {
        dateInput.value = new Date().toISOString().split('T')[0];
    }

    // Expose functions to window so they are globally accessible from HTML onclick/onsubmit attributes
    window.openNewApplicationModal = openNewApplicationModal;
    window.closeApplicationModal = closeApplicationModal;
    window.saveApplication = saveApplication;
    window.editApplication = editApplication;
    window.deleteApplicationCard = deleteApplicationCard;
    window.applyTrackerFilters = applyTrackerFilters;
    window.uploadCVFile = uploadCVFile;
    window.uploadCLFile = uploadCLFile;

    // Decision Flow functions
    window.triggerApplyFlow = triggerApplyFlow;
    window.closeDecisionFlowModal = closeDecisionFlowModal;
    window.toggleCVDocSource = toggleCVDocSource;
    window.toggleLetterDocSource = toggleLetterDocSource;
    window.toggleSpecialDocsSource = toggleSpecialDocsSource;
    window.stageDecisionFlowApplication = stageDecisionFlowApplication;
    window.markAsApplied = markAsApplied;
}

/**
 * Fetch and render all job applications in the pipeline
 */
export async function renderTracker() {
    try {
        const tenantId = state.tenantId || 'default-tenant';
        
        // Fetch applications from backend
        const apps = await getApplications(state.trackerFilters, tenantId);
        state.applications = apps;

        // Render pipeline board
        renderPipelineBoard(apps);
    } catch (err) {
        console.error("Failed to render tracker:", err);
        showError("Failed to load job tracker board.");
    }
}

/**
 * Render the kanban pipeline boards and update badges
 */
function renderPipelineBoard(apps) {
    const statuses = ['to_apply', 'applied', 'in_review', 'interview', 'offer', 'rejected', 'ghosted'];
    
    // Initialize columns containers and counts
    const columns = {};
    const counts = {};
    
    statuses.forEach(status => {
        columns[status] = document.getElementById(`col-${status}`);
        counts[status] = 0;
        if (columns[status]) {
            columns[status].innerHTML = ''; // Clear existing cards
        }
    });

    // Populate columns and increment counts
    apps.forEach(app => {
        const status = app.status || 'to_apply';
        counts[status]++;
        
        const col = columns[status];
        if (col) {
            const card = createApplicationCard(app);
            col.appendChild(card);
        }
    });

    // Update status column badge counts in DOM
    statuses.forEach(status => {
        const badge = document.getElementById(`count-${status}`);
        if (badge) {
            badge.innerText = counts[status];
        }
    });
}

/**
 * Helper to generate a single Application Card DOM element
 */
function createApplicationCard(app) {
    const card = document.createElement('div');
    card.className = 'bg-slate-900 border border-slate-800 rounded-lg p-3.5 flex flex-col gap-2.5 shadow hover:shadow-md hover:border-slate-700/60 transition-all duration-150';
    
    const formattedDate = app.applied_date ? app.applied_date : 'N/A';
    const sourceLabel = getSourceLabel(app.source);

    // Build files buttons html
    let filesHtml = '';
    if (app.cv_file || app.cover_letter_file || app.special_documents) {
        filesHtml = `<div class="flex flex-wrap gap-1.5 pt-1.5 border-t border-slate-850/60 mt-1">`;
        if (app.cv_file) {
            filesHtml += `
                <a href="${app.cv_file}" target="_blank" class="text-[9px] font-extrabold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1 hover:bg-emerald-500/20 transition-all">
                    <i class="fa-solid fa-file-pdf"></i> CV
                </a>`;
        }
        if (app.cover_letter_file) {
            filesHtml += `
                <a href="${app.cover_letter_file}" target="_blank" class="text-[9px] font-extrabold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center gap-1 hover:bg-blue-500/20 transition-all">
                    <i class="fa-solid fa-file-lines"></i> Letter
                </a>`;
        }
        if (app.special_documents) {
            try {
                const specDocs = JSON.parse(app.special_documents);
                if (specDocs && specDocs.length > 0) {
                    specDocs.forEach((doc, idx) => {
                        filesHtml += `
                            <a href="${doc}" target="_blank" class="text-[9px] font-extrabold px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center gap-1 hover:bg-purple-500/20 transition-all" title="View Special Doc">
                                <i class="fa-solid fa-paperclip"></i> Doc ${idx + 1}
                            </a>`;
                    });
                }
            } catch (e) {
                // If it was stored as a single url string fallback
                filesHtml += `
                    <a href="${app.special_documents}" target="_blank" class="text-[9px] font-extrabold px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center gap-1 hover:bg-purple-500/20 transition-all">
                        <i class="fa-solid fa-paperclip"></i> Special
                    </a>`;
            }
        }
        filesHtml += `</div>`;
    }

    // Step 3 Mark as Applied Checkbox
    let markAppliedHtml = '';
    if (app.status === 'to_apply') {
        markAppliedHtml = `
            <div class="flex items-center gap-1.5 pt-2 border-t border-slate-850/50 mt-1">
                <input type="checkbox" id="mark-applied-${app.application_id}" onchange="markAsApplied('${app.application_id}')" class="accent-emerald-500 h-3 w-3 rounded cursor-pointer">
                <label for="mark-applied-${app.application_id}" class="text-[9px] font-bold uppercase tracking-wider text-emerald-400 cursor-pointer hover:text-emerald-300">Mark as Applied</label>
            </div>
        `;
    }

    card.innerHTML = `
        <div class="flex items-start justify-between gap-1">
            <h4 class="font-bold text-xs text-slate-200 truncate pr-1" title="${app.company_name}">${app.company_name}</h4>
            <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-slate-950 text-slate-400 border border-slate-850 whitespace-nowrap uppercase tracking-wider">${sourceLabel}</span>
        </div>
        
        <p class="text-[10px] text-slate-400 flex items-center gap-1">
            <i class="fa-regular fa-calendar text-[9px]"></i> ${formattedDate}
        </p>

        ${app.jd_summary ? `
        <p class="text-[10px] text-slate-300 bg-slate-950/40 p-1.5 rounded border border-slate-850/40 truncate max-w-full italic" title="${app.jd_summary}">
            ${app.jd_summary}
        </p>` : ''}

        ${app.recruiter_response ? `
        <p class="text-[10px] text-amber-400/90 bg-amber-500/5 p-1.5 rounded border border-amber-500/10 truncate max-w-full" title="${app.recruiter_response}">
            <i class="fa-solid fa-reply text-[9px]"></i> ${app.recruiter_response}
        </p>` : ''}

        ${filesHtml}
        ${markAppliedHtml}

        <div class="flex items-center justify-end gap-1.5 pt-2 border-t border-slate-850/50 mt-1">
            <button onclick="editApplication('${app.application_id}')" class="h-6 w-6 rounded bg-slate-950 hover:bg-slate-800 border border-slate-850/80 flex items-center justify-center text-slate-400 hover:text-slate-100 transition-colors text-[10px]" title="Edit Application">
                <i class="fa-solid fa-pen-to-square"></i>
            </button>
            <button onclick="deleteApplicationCard('${app.application_id}')" class="h-6 w-6 rounded bg-slate-950 hover:bg-rose-950/40 border border-slate-850/80 hover:border-rose-900/50 flex items-center justify-center text-slate-400 hover:text-rose-400 transition-colors text-[10px]" title="Delete Application">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        </div>
    `;

    return card;
}

/**
 * Return friendly uppercase display labels for source values
 */
function getSourceLabel(source) {
    const labels = {
        linkedin: 'LinkedIn',
        indeed: 'Indeed',
        referral: 'Referral',
        company_site: 'Website',
        other: 'Other'
    };
    return labels[source] || source || 'Other';
}

/**
 * Open manual form modal for creating a new application
 */
export function openNewApplicationModal() {
    document.getElementById('app-modal-title').innerText = "Add Job Application";
    document.getElementById('form-app-id').value = '';
    
    // Clear and reset form fields
    const form = document.getElementById('app-tracker-form');
    form.reset();
    
    // Pre-fill applied date with today
    document.getElementById('form-applied-date').value = new Date().toISOString().split('T')[0];
    
    // Hide file upload section (uploads are only allowed during edit mode)
    document.getElementById('file-upload-section').classList.add('hidden');

    // Show modal
    const modal = document.getElementById('application-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

/**
 * Close the add/edit application modal
 */
export function closeApplicationModal() {
    const modal = document.getElementById('application-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

/**
 * Save manual form input to create or update an application
 */
export async function saveApplication(event) {
    event.preventDefault();
    
    const appId = document.getElementById('form-app-id').value;
    const tenantId = state.tenantId || 'default-tenant';

    const payload = {
        company_name: document.getElementById('form-company').value.trim(),
        source: document.getElementById('form-source').value,
        applied_date: document.getElementById('form-applied-date').value,
        status: document.getElementById('form-status').value,
        jd_summary: document.getElementById('form-jd-summary').value.trim() || null,
        recruiter_response: document.getElementById('form-response').value.trim() || null
    };

    try {
        if (appId) {
            // Update existing application
            // Retrieve existing file references to preserve them if not changed
            const existing = state.applications.find(a => a.application_id === appId);
            if (existing) {
                payload.cv_file = existing.cv_file;
                payload.cover_letter_file = existing.cover_letter_file;
                payload.special_documents = existing.special_documents;
                payload.document_prep_completed_at = existing.document_prep_completed_at;
                payload.applied_confirmed_at = existing.applied_confirmed_at;
            }
            await updateApplication(appId, payload, tenantId);
            showNotification(`Application at ${payload.company_name} updated successfully.`);
        } else {
            // Create new application
            await createApplication(payload, tenantId);
            showNotification(`Application at ${payload.company_name} added to pipeline.`);
        }
        
        closeApplicationModal();
        renderTracker();
    } catch (err) {
        console.error("Failed to save application:", err);
        showError("Failed to save job application.");
    }
}

/**
 * Load application details, prefill modal form, and enable file uploads
 */
export function editApplication(appId) {
    const app = state.applications.find(a => a.application_id === appId);
    if (!app) {
        showError("Application not found.");
        return;
    }

    document.getElementById('app-modal-title').innerText = "Edit Job Application";
    document.getElementById('form-app-id').value = appId;

    // Prefill form
    document.getElementById('form-company').value = app.company_name;
    document.getElementById('form-source').value = app.source || 'linkedin';
    document.getElementById('form-applied-date').value = app.applied_date;
    document.getElementById('form-status').value = app.status || 'to_apply';
    document.getElementById('form-jd-summary').value = app.jd_summary || '';
    document.getElementById('form-response').value = app.recruiter_response || '';

    // Prefill upload file labels
    const cvLabel = app.cv_file ? app.cv_file.split('/').pop() : 'None';
    const clLabel = app.cover_letter_file ? app.cover_letter_file.split('/').pop() : 'None';
    
    document.getElementById('form-cv-file-label').innerText = cvLabel;
    document.getElementById('form-cl-file-label').innerText = clLabel;

    // Enable file uploads (only when editing)
    document.getElementById('file-upload-section').classList.remove('hidden');

    // Show modal
    const modal = document.getElementById('application-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

/**
 * Handle confirmation and deletion of a job application card
 */
export async function deleteApplicationCard(appId) {
    const app = state.applications.find(a => a.application_id === appId);
    if (!app) return;

    if (!confirm(`Are you sure you want to delete your application for ${app.company_name}? This will permanently remove all file links and logs.`)) {
        return;
    }

    try {
        const tenantId = state.tenantId || 'default-tenant';
        await deleteApplication(appId, tenantId);
        showNotification("Application removed from tracker.");
        renderTracker();
    } catch (err) {
        console.error("Failed to delete application:", err);
        showError("Failed to delete job application.");
    }
}

/**
 * Fetch filters values from DOM, update state filters, and trigger re-render
 */
export function applyTrackerFilters() {
    state.trackerFilters.status = document.getElementById('tracker-filter-status').value;
    state.trackerFilters.source = document.getElementById('tracker-filter-source').value;
    state.trackerFilters.sort_by_date = document.getElementById('tracker-sort-date').value;

    renderTracker();
}

/**
 * Asynchronously upload CV file and attach to editing application
 */
export async function uploadCVFile() {
    const appId = document.getElementById('form-app-id').value;
    const fileInput = document.getElementById('form-cv-file');
    const tenantId = state.tenantId || 'default-tenant';

    if (!appId || !fileInput.files || fileInput.files.length === 0) return;

    const file = fileInput.files[0];
    document.getElementById('form-cv-file-label').innerText = "Uploading...";

    try {
        const updated = await uploadApplicationFile(appId, 'cv', file, tenantId);
        
        // Update local state store cache
        const index = state.applications.findIndex(a => a.application_id === appId);
        if (index !== -1) {
            state.applications[index] = updated;
        }

        const cvLabel = updated.cv_file ? updated.cv_file.split('/').pop() : 'None';
        document.getElementById('form-cv-file-label').innerText = cvLabel;
        showNotification("CV Document uploaded successfully.");
    } catch (err) {
        console.error("CV upload failed:", err);
        document.getElementById('form-cv-file-label').innerText = "Upload Failed";
        showError("Failed to upload CV document.");
    }
}

/**
 * Asynchronously upload Cover Letter file and attach to editing application
 */
export async function uploadCLFile() {
    const appId = document.getElementById('form-app-id').value;
    const fileInput = document.getElementById('form-cl-file');
    const tenantId = state.tenantId || 'default-tenant';

    if (!appId || !fileInput.files || fileInput.files.length === 0) return;

    const file = fileInput.files[0];
    document.getElementById('form-cl-file-label').innerText = "Uploading...";

    try {
        const updated = await uploadApplicationFile(appId, 'cover_letter', file, tenantId);
        
        // Update local state store cache
        const index = state.applications.findIndex(a => a.application_id === appId);
        if (index !== -1) {
            state.applications[index] = updated;
        }

        const clLabel = updated.cover_letter_file ? updated.cover_letter_file.split('/').pop() : 'None';
        document.getElementById('form-cl-file-label').innerText = clLabel;
        showNotification("Cover Letter uploaded successfully.");
    } catch (err) {
        console.error("Cover letter upload failed:", err);
        document.getElementById('form-cl-file-label').innerText = "Upload Failed";
        showError("Failed to upload Cover Letter.");
    }
}


// =========================================================================
// =========================================================================
// FEATURE: APPLY DECISION FLOW (STEP 1, 2, 3)
// =========================================================================
// =========================================================================

/**
 * Triggered by clicking "Apply" on an analyzed job. Opens selection flow.
 */
export async function triggerApplyFlow() {
    if (!state.fitCheck) {
        showError("Please run a Fit Analysis on the current job description first!");
        return;
    }

    try {
        const tenantId = state.tenantId || 'default-tenant';
        
        // Fetch candidates list to populate CV Selection
        const result = await listCandidates(tenantId);
        const candidates = result.candidates || [];
        
        const cvSelect = document.getElementById('df-cv-select');
        cvSelect.innerHTML = `<option value="">-- Upload a new CV file --</option>`;
        
        candidates.forEach(cand => {
            const opt = document.createElement('option');
            opt.value = cand.candidate_id;
            opt.innerText = `${cand.name} (${cand.email || 'No email'})`;
            cvSelect.appendChild(opt);
        });

        // Prefill Motivation Letter textarea if AI generated draft exists
        const letterTextarea = document.getElementById('df-letter-text');
        if (state.motivationLetter && state.motivationLetter.content) {
            letterTextarea.value = state.motivationLetter.content;
        } else {
            letterTextarea.value = '';
        }

        // Reset inputs
        document.getElementById('df-cv-file').value = '';
        document.getElementById('df-letter-file').value = '';
        document.getElementById('df-special-files').value = '';
        document.getElementById('df-letter-ai').checked = true;
        document.getElementById('df-has-special').checked = false;

        // Reset visibility wrappers
        toggleCVDocSource('');
        toggleLetterDocSource('ai');
        toggleSpecialDocsSource(false);

        // Open Modal
        const modal = document.getElementById('decision-flow-modal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    } catch (err) {
        console.error("Failed to initialize decision flow:", err);
        showError("Failed to initialize Apply Decision Flow.");
    }
}

/**
 * Close Decision Flow modal
 */
export function closeDecisionFlowModal() {
    const modal = document.getElementById('decision-flow-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

/**
 * Toggle CV file upload view
 */
export function toggleCVDocSource(value) {
    const wrapper = document.getElementById('df-cv-upload-wrapper');
    if (value === "") {
        wrapper.classList.remove('hidden');
    } else {
        wrapper.classList.add('hidden');
    }
}

/**
 * Toggle Motivation Letter text/upload view
 */
export function toggleLetterDocSource(value) {
    const selfWrapper = document.getElementById('df-letter-self-wrapper');
    const aiStatus = document.getElementById('df-letter-ai-status');

    if (value === 'self') {
        selfWrapper.classList.remove('hidden');
        aiStatus.classList.add('hidden');
    } else {
        selfWrapper.classList.add('hidden');
        aiStatus.classList.remove('hidden');
    }
}

/**
 * Toggle Special Documents multiple upload view
 */
export function toggleSpecialDocsSource(checked) {
    const wrapper = document.getElementById('df-special-wrapper');
    if (checked) {
        wrapper.classList.remove('hidden');
    } else {
        wrapper.classList.add('hidden');
    }
}

/**
 * Single-purpose helper: Resolve CV Source Selection
 */
async function selectCVChoice(appId, tenantId) {
    const cvSelectValue = document.getElementById('df-cv-select').value;
    
    // Existing selected
    if (cvSelectValue !== "") {
        // Build candidate original file download path URL
        return `/api/cv/candidates/${cvSelectValue}/file`;
    }

    // New file uploaded
    const cvFileInput = document.getElementById('df-cv-file');
    if (cvFileInput.files && cvFileInput.files.length > 0) {
        const file = cvFileInput.files[0];
        const updatedApp = await uploadApplicationFile(appId, 'cv', file, tenantId);
        return updatedApp.cv_file;
    }

    // Fallback: use active cv data on Sandbox
    if (state.cvFile) {
        const updatedApp = await uploadApplicationFile(appId, 'cv', state.cvFile, tenantId);
        return updatedApp.cv_file;
    }

    return null;
}

/**
 * Single-purpose helper: Resolve Motivation Letter Source Selection
 */
async function selectLetterChoice(appId, tenantId) {
    const choiceRadio = document.querySelector('input[name="df-letter-choice"]:checked').value;

    // Use AI Generated cover letter
    if (choiceRadio === 'ai') {
        const letterText = state.motivationLetter?.content || document.getElementById('df-letter-text').value.trim();
        if (!letterText) {
            return null;
        }
        // Compile string to standard File object
        const blob = new Blob([letterText], { type: "text/plain" });
        const letterFile = new File([blob], `${_sanitize_filename(state.jobPosition?.company || "Company")}_AI_Letter.txt`, { type: "text/plain" });
        
        const updatedApp = await uploadApplicationFile(appId, 'cover_letter', letterFile, tenantId);
        return updatedApp.cover_letter_file;
    }

    // Use Self Written letter
    const selfFileInput = document.getElementById('df-letter-file');
    if (selfFileInput.files && selfFileInput.files.length > 0) {
        const file = selfFileInput.files[0];
        const updatedApp = await uploadApplicationFile(appId, 'cover_letter', file, tenantId);
        return updatedApp.cover_letter_file;
    }

    const selfText = document.getElementById('df-letter-text').value.trim();
    if (selfText) {
        const blob = new Blob([selfText], { type: "text/plain" });
        const letterFile = new File([blob], "Self_Written_Letter.txt", { type: "text/plain" });
        
        const updatedApp = await uploadApplicationFile(appId, 'cover_letter', letterFile, tenantId);
        return updatedApp.cover_letter_file;
    }

    return null;
}

/**
 * Single-purpose helper: Resolve Special Documents Selection
 */
async function selectSpecialDocsChoice(appId, tenantId) {
    const hasSpecial = document.getElementById('df-has-special').checked;
    if (!hasSpecial) {
        return null;
    }

    const specialFilesInput = document.getElementById('df-special-files');
    if (specialFilesInput.files && specialFilesInput.files.length > 0) {
        const updatedApp = await uploadSpecialDocuments(appId, specialFilesInput.files, tenantId);
        return updatedApp.special_documents;
    }

    return null;
}

/**
 * Core Step 2 function: Stage selections, save as "to_apply"
 */
export async function stageDecisionFlowApplication() {
    const tenantId = state.tenantId || 'default-tenant';
    
    // Gather Requisition details from Candidate Sandbox Job
    const company = state.jobPosition?.company || document.getElementById('req-company')?.value.trim() || "Target Company";
    const title = state.jobPosition?.job_title || document.getElementById('req-title')?.value.trim() || "Software Requisition";

    const payload = {
        company_name: company,
        source: "other",
        applied_date: new Date().toISOString().split('T')[0],
        status: "to_apply",
        jd_summary: title
    };

    try {
        // Step A: Create Application staging row in SQLite
        const app = await createApplication(payload, tenantId);
        const appId = app.application_id;

        // Step B: Resolve CV Selection (Single-purpose function call)
        const cvRef = await selectCVChoice(appId, tenantId);

        // Step C: Resolve Letter Selection (Single-purpose function call)
        const clRef = await selectLetterChoice(appId, tenantId);

        // Step D: Resolve Special Documents Selection (Single-purpose function call)
        const specialDocsRef = await selectSpecialDocsChoice(appId, tenantId);

        // Step E: Update with completed_at and reference pointers
        const finalPayload = {
            company_name: app.company_name,
            source: app.source,
            applied_date: app.applied_date,
            status: "to_apply",
            jd_summary: app.jd_summary,
            cv_file: cvRef,
            cover_letter_file: clRef,
            special_documents: specialDocsRef,
            document_prep_completed_at: new Date().toISOString()
        };

        await updateApplication(appId, finalPayload, tenantId);

        showNotification(`Application for ${company} staged and saved successfully under 'To Apply'!`);
        closeDecisionFlowModal();
        
        // Refresh tracker listings
        renderTracker();
    } catch (err) {
        console.error("Failed to stage application:", err);
        showError("Failed to complete Document Selection Staging.");
    }
}

/**
 * Step 3: Flipped status to Applied and recorded timestamps (Checkbox triggered)
 */
export async function markAsApplied(appId) {
    const app = state.applications.find(a => a.application_id === appId);
    if (!app) return;

    try {
        const tenantId = state.tenantId || 'default-tenant';
        
        // ONLY flip status and record timestamp. Must not re-open selection.
        const payload = {
            company_name: app.company_name,
            source: app.source,
            applied_date: new Date().toISOString().split('T')[0],
            status: "applied",
            jd_summary: app.jd_summary,
            recruiter_response: app.recruiter_response,
            cv_file: app.cv_file,
            cover_letter_file: app.cover_letter_file,
            special_documents: app.special_documents,
            document_prep_completed_at: app.document_prep_completed_at,
            applied_confirmed_at: new Date().toISOString()
        };

        await updateApplication(appId, payload, tenantId);
        showNotification(`Application for ${app.company_name} successfully marked as Applied!`);
        renderTracker();
    } catch (err) {
        console.error("Failed to mark application as applied:", err);
        showError("Failed to confirm Applied action.");
    }
}

/**
 * Helper to sanitize filename in javascript
 */
function _sanitize_filename(filename) {
    return filename
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^\w\s.-]/g, '_')
        .replace(/[\s_]+/g, '_')
        .replace(/_+$/, '');
}

import { state } from './state.js';
import { 
    createApplication, 
    getApplications, 
    updateApplication, 
    deleteApplication, 
    uploadApplicationFile,
    uploadSpecialDocuments,
    listCandidates,
    generateTempPDF,
    finalizeTempPDF
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
    window.generateDecisionFlowLetterPDF = generateDecisionFlowLetterPDF;
    window.submitDecisionFlowLetterFeedback = submitDecisionFlowLetterFeedback;
}

/**
 * Fetch and render all job applications in the pipeline
 */
export async function renderTracker() {
    try {
        const tenantId = state.tenantId || 'default-tenant';
        
        // Fetch applications from backend (API returns List[ApplicationResponse])
        const result = await getApplications({}, tenantId);
        state.applications = Array.isArray(result) ? result : (result.applications || []);
        
        // Empty columns
        const statuses = ['to_apply', 'applied', 'in_review', 'interview', 'offer', 'rejected', 'ghosted'];
        statuses.forEach(status => {
            const col = document.getElementById(`col-${status}`);
            if (col) col.innerHTML = '';
            
            const badge = document.getElementById(`count-${status}`);
            if (badge) badge.innerText = '0';
        });

        const statusCounts = {};
        statuses.forEach(s => statusCounts[s] = 0);

        // Sort and populate columns
        state.applications.forEach(app => {
            const status = app.status || 'to_apply';
            const col = document.getElementById(`col-${status}`);
            if (!col) return;

            statusCounts[status]++;

            const card = document.createElement('div');
            card.className = "bg-slate-900 border border-slate-800 rounded-xl p-3.5 flex flex-col gap-2.5 shadow hover:border-emerald-500/30 transition-all group relative";
            card.draggable = false; // Simple CSS-based list tracker (MVP rules)

            // Applied Date String
            const appliedStr = app.applied_date ? new Date(app.applied_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'No date';

            // Mark as Applied Checkbox
            let applyCheckboxHtml = '';
            if (status === 'to_apply') {
                applyCheckboxHtml = `
                    <label class="flex items-center gap-1.5 text-[10px] font-bold text-emerald-400 cursor-pointer bg-emerald-500/5 hover:bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/10 transition-colors shrink-0">
                        <input type="checkbox" onchange="markAsApplied(${app.application_id})" class="accent-emerald-500">
                        Mark Applied
                    </label>
                `;
            }

            card.innerHTML = `
                <div class="flex items-start justify-between gap-2 min-w-0">
                    <div class="min-w-0 flex-1">
                        <h4 class="font-bold text-xs text-slate-100 truncate">${app.company_name}</h4>
                        <p class="text-[10px] text-slate-400 font-medium truncate mt-0.5">${app.jd_summary || 'No description'}</p>
                    </div>
                    <div class="flex items-center gap-1">
                        <button onclick="editApplication(${app.application_id})" class="text-slate-500 hover:text-emerald-400 transition-colors p-1 text-[11px]" title="Edit Application">
                            <i class="fa-solid fa-pen-to-square"></i>
                        </button>
                        <button onclick="deleteApplicationCard(${app.application_id})" class="text-slate-500 hover:text-rose-400 transition-colors p-1 text-[11px]" title="Delete Application">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>

                <div class="flex items-center justify-between gap-2 text-[10px] font-mono text-slate-500 pt-1.5 border-t border-slate-850/50">
                    <div class="flex items-center gap-1.5 truncate">
                        <span class="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-850 text-slate-400 capitalize">${app.source || 'Other'}</span>
                        <span>${appliedStr}</span>
                    </div>
                    ${applyCheckboxHtml}
                </div>
            `;
            col.appendChild(card);
        });

        // Update counts
        statuses.forEach(status => {
            const badge = document.getElementById(`count-${status}`);
            if (badge) badge.innerText = statusCounts[status].toString();
        });

    } catch (err) {
        console.error("Failed to render tracker:", err);
        showError("Failed to render Job Tracker board.");
    }
}

/**
 * Filter applications
 */
export function applyTrackerFilters() {
    // Simulating frontend filtering or sorting of pre-fetched dataset
    renderTracker();
}

/**
 * Open Modal to Add Application manually
 */
export function openNewApplicationModal() {
    document.getElementById('app-modal-title').innerText = "Add Job Application";
    document.getElementById('form-app-id').value = '';
    document.getElementById('app-tracker-form').reset();
    
    // Set default date to today
    document.getElementById('form-applied-date').value = new Date().toISOString().split('T')[0];

    // Hide file labels
    document.getElementById('form-cv-file-label').innerText = 'None';
    document.getElementById('form-cl-file-label').innerText = 'None';
    
    // Hide file section for new applications (only upload once created)
    document.getElementById('file-upload-section').classList.add('hidden');

    const modal = document.getElementById('application-modal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

/**
 * Close Application Modal
 */
export function closeApplicationModal() {
    const modal = document.getElementById('application-modal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

/**
 * Save Application form submission (Manually)
 */
export async function saveApplication(e) {
    e.preventDefault();
    const tenantId = state.tenantId || 'default-tenant';

    const appId = document.getElementById('form-app-id').value;
    const company = document.getElementById('form-company').value.trim();
    const source = document.getElementById('form-source').value;
    const appliedDate = document.getElementById('form-applied-date').value;
    const status = document.getElementById('form-status').value;
    const jdSummary = document.getElementById('form-jd-summary').value.trim();
    const recruiterResponse = document.getElementById('form-response').value.trim();

    const payload = {
        company_name: company,
        source: source,
        applied_date: appliedDate,
        status: status,
        jd_summary: jdSummary,
        recruiter_response: recruiterResponse
    };

    try {
        if (appId) {
            // Update
            await updateApplication(appId, payload, tenantId);
            showNotification(`Application for ${company} updated successfully!`);
        } else {
            // Create
            await createApplication(payload, tenantId);
            showNotification(`Application for ${company} added successfully!`);
        }
        closeApplicationModal();
        renderTracker();
    } catch (err) {
        console.error(err);
        showError(`Save Failed: ${err.message}`);
    }
}

/**
 * Edit existing application (Load details to form)
 */
export async function editApplication(appId) {
    try {
        const tenantId = state.tenantId || 'default-tenant';
        const app = await getApplication(appId, tenantId);

        document.getElementById('app-modal-title').innerText = "Edit Job Application";
        document.getElementById('form-app-id').value = app.application_id;
        document.getElementById('form-company').value = app.company_name;
        document.getElementById('form-source').value = app.source || 'other';
        
        // Date parsing safety
        if (app.applied_date) {
            document.getElementById('form-applied-date').value = app.applied_date.split('T')[0];
        }

        document.getElementById('form-status').value = app.status || 'to_apply';
        document.getElementById('form-jd-summary').value = app.jd_summary || '';
        document.getElementById('form-response').value = app.recruiter_response || '';

        // Display current documents if attached
        document.getElementById('form-cv-file-label').innerText = app.cv_file ? app.cv_file.split('/').pop() : 'None';
        document.getElementById('form-cl-file-label').innerText = app.cover_letter_file ? app.cover_letter_file.split('/').pop() : 'None';

        // Show file section
        document.getElementById('file-upload-section').classList.remove('hidden');

        const modal = document.getElementById('application-modal');
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    } catch (err) {
        console.error(err);
        showError(`Load Failed: ${err.message}`);
    }
}

/**
 * Delete application
 */
export async function deleteApplicationCard(appId) {
    if (!confirm("Are you sure you want to permanently delete this application card from your dashboard?")) {
        return;
    }

    try {
        const tenantId = state.tenantId || 'default-tenant';
        await deleteApplication(appId, tenantId);
        showNotification("Application removed successfully.");
        renderTracker();
    } catch (err) {
        console.error(err);
        showError(`Delete Failed: ${err.message}`);
    }
}

/**
 * Handle CV Upload directly inside Edit Form
 */
export async function uploadCVFile() {
    const appId = document.getElementById('form-app-id').value;
    const tenantId = state.tenantId || 'default-tenant';
    const input = document.getElementById('form-cv-file');

    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    try {
        const result = await uploadApplicationFile(appId, 'cv', file, tenantId);
        document.getElementById('form-cv-file-label').innerText = result.cv_file.split('/').pop();
        showNotification("CV file uploaded and bound successfully!");
    } catch (err) {
        console.error(err);
        showError(`CV upload failed: ${err.message}`);
    }
}

/**
 * Handle Cover Letter Upload directly inside Edit Form
 */
export async function uploadCLFile() {
    const appId = document.getElementById('form-app-id').value;
    const tenantId = state.tenantId || 'default-tenant';
    const input = document.getElementById('form-cl-file');

    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];

    try {
        const result = await uploadApplicationFile(appId, 'cover_letter', file, tenantId);
        document.getElementById('form-cl-file-label').innerText = result.cover_letter_file.split('/').pop();
        showNotification("Cover letter file uploaded and bound successfully!");
    } catch (err) {
        console.error(err);
        showError(`Letter upload failed: ${err.message}`);
    }
}

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

        // Clean up temporary PDF drafting states (Strictly on-demand!)
        state.dfPdfId = null;
        state.dfPdfUrl = null;
        state.dfPdfContent = null;

        // Reset AI cover letter sandbox views to Initial Placeholder
        document.getElementById('df-ai-letter-placeholder').classList.remove('hidden');
        document.getElementById('df-ai-letter-active-container').classList.add('hidden');
        document.getElementById('df-ai-letter-text').value = '';
        document.getElementById('df-ai-letter-pdf-preview').src = '';
        document.getElementById('df-letter-feedback-input').value = '';
        document.getElementById('df-letter-revision-spinner').classList.add('hidden');

        // Prefill generic Motivation Letter text for 'self' option
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
 * Handle manual cover letter PDF generation in-place (Tapped by user, NOT automatic!)
 */
export async function generateDecisionFlowLetterPDF() {
    if (!state.cvData || !state.jobPosition) {
        showError("CV and Job Position must be analyzed first.");
        return;
    }

    const btnInitial = document.getElementById('df-btn-initial-draft');
    btnInitial.disabled = true;
    btnInitial.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> Generating PDF Draft...`;

    const tenantId = state.tenantId || 'default-tenant';
    const aiTextarea = document.getElementById('df-ai-letter-text');
    const iframePreview = document.getElementById('df-ai-letter-pdf-preview');

    try {
        const result = await generateTempPDF(
            state.cvData,
            state.jobPosition,
            state.companyType || 'corporation',
            'fr', // Default French standard typeset
            'professional',
            'txt',
            tenantId
        );

        // Cache staging information
        state.dfPdfId = result.pdf_id;
        state.dfPdfUrl = result.pdf_url;
        state.dfPdfContent = result.content;

        // Load preview and raw text editor
        aiTextarea.value = result.content;
        iframePreview.src = result.pdf_url;

        // Toggle views
        document.getElementById('df-ai-letter-placeholder').classList.add('hidden');
        document.getElementById('df-ai-letter-active-container').classList.remove('hidden');
        showNotification("AI Cover letter composed and typeset PDF compiled successfully!");
    } catch (err) {
        console.error("Manual PDF draft generation failed:", err);
        showError(`Staging Draft Failed: ${err.message}`);
    } finally {
        btnInitial.disabled = false;
        btnInitial.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Generate AI Draft (PDF)`;
    }
}

/**
 * Handle AI Motivation Letter refinement/revision feedback inside the decision flow modal
 */
export async function submitDecisionFlowLetterFeedback() {
    const feedbackInput = document.getElementById('df-letter-feedback-input');
    const feedbackText = feedbackInput.value.trim();
    if (!feedbackText) {
        showError("Please enter your revision feedback first!");
        return;
    }

    if (!state.cvData || !state.jobPosition) {
        showError("A CV and Job Position must be loaded first.");
        return;
    }

    const tenantId = state.tenantId || 'default-tenant';
    const aiTextarea = document.getElementById('df-ai-letter-text');
    const iframePreview = document.getElementById('df-ai-letter-pdf-preview');
    const revisionSpinner = document.getElementById('df-letter-revision-spinner');
    const revisionBtn = document.getElementById('df-btn-letter-revision');

    // Show loading spinner
    revisionSpinner.classList.remove('hidden');
    revisionBtn.disabled = true;
    aiTextarea.value = "AI Agent is compiling updated typeset PDF draft based on feedback...";

    try {
        const result = await generateTempPDF(
            state.cvData,
            state.jobPosition,
            state.companyType || 'corporation',
            'fr',
            'professional',
            'txt',
            tenantId,
            feedbackText
        );

        state.dfPdfId = result.pdf_id;
        state.dfPdfUrl = result.pdf_url;
        state.dfPdfContent = result.content;

        aiTextarea.value = result.content;
        iframePreview.src = result.pdf_url;
        feedbackInput.value = ''; // clear input on success
        showNotification("AI Agent has successfully revised and re-compiled your PDF cover letter!");
    } catch (err) {
        console.error("AI revision failed:", err);
        showError(`Revision failed: ${err.message}`);
        aiTextarea.value = state.dfPdfContent || "AI generation failed. Enter feedback to retry.";
    } finally {
        revisionSpinner.classList.add('hidden');
        revisionBtn.disabled = false;
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
    const aiWrapper = document.getElementById('df-letter-ai-wrapper');

    if (value === 'self') {
        selfWrapper.classList.remove('hidden');
        aiWrapper.classList.add('hidden');
    } else {
        selfWrapper.classList.add('hidden');
        aiWrapper.classList.remove('hidden');
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
        // Re-draft compiled PDF draft on-demand
        if (!state.dfPdfId) {
            showError("Please generate the AI cover letter PDF draft before submitting!");
            throw new Error("No PDF Draft generated.");
        }

        const aiTextarea = document.getElementById('df-ai-letter-text');
        const letterText = aiTextarea ? aiTextarea.value.trim() : (state.dfPdfContent || "");
        
        let activePdfId = state.dfPdfId;

        // If the user made manual inline modifications, compile an updated temporary PDF first
        if (letterText !== state.dfPdfContent) {
            showNotification("Saving and compiling manual inline edits...");
            const compiled = await generateTempPDF(
                state.cvData,
                state.jobPosition,
                state.companyType || 'corporation',
                'fr',
                'professional',
                'txt',
                tenantId,
                null // no prompt, compile verbatim
            );
            activePdfId = compiled.pdf_id;
        }

        // Finalize temporary PDF (moves PDF from /tmp to /db/motivation_letter permanently)
        const companyName = state.jobPosition?.company || "Company";
        const jobTitle = state.jobPosition?.job_title || "Job";
        
        const finalResult = await finalizeTempPDF(activePdfId, companyName, jobTitle, tenantId);
        
        // Return permanent path of the compiled cover letter PDF
        return finalResult.pdf_path;
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

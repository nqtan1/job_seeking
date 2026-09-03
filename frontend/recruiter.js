/**
 * RecruitAI Console Client - Recruiter Control Center Logic Module
 */
import { state } from './state.js';
import { rankCandidates } from './api.js';
import { showNotification, showError } from './utils.js';

export async function runBatchScreening() {
    if (state.recruiterCandidates.length === 0) {
        showError('Screening group pool is empty! Drag in some candidate files first.');
        return;
    }

    const title = document.getElementById('req-title').value.trim();
    const company = document.getElementById('req-company').value.trim();
    const rawReqs = document.getElementById('req-requirements').value.trim();

    if (!title || !company) {
        showError('Please configure requisition details (Title & Company).');
        return;
    }

    showRecruiterLoader(true);

    try {
        const requirementsArray = rawReqs.split('\n').map(r => r.trim()).filter(Boolean);
        if (requirementsArray.length === 0) {
            requirementsArray.push("Python experience", "API systems development");
        }

        const candidatesPayload = state.recruiterCandidates.map(cand => ({
            candidate_id: cand.candidate_id,
            personal_info: {
                name: cand.name,
                email: cand.email,
                phone: cand.phone
            },
            skills: cand.skills,
            experiences: [
                {
                    job_title: "Software Engineer",
                    company: "Previous Tech",
                    responsibilities: ["Built scalable backend services"]
                }
            ]
        }));

        const targetJobPayload = {
            job_title: title,
            company: company,
            requirements: requirementsArray
        };

        const result = await rankCandidates(candidatesPayload, targetJobPayload, state.tenantId);
        state.batchRankings = result.rankings || result;
        console.log("Batch rankings completed successfully:", state.batchRankings);

        renderRecruiterOutput(title, company);
        showNotification("Candidate Shortlist Ranking complete!");

    } catch (err) {
        console.error(err);
        showError(`Screening Engine Error: ${err.message}. Check your terminal logs or .env.`);
        showRecruiterLoader(false);
    }
}

export function renderRecruiterOutput(title, company) {
    showRecruiterLoader(false);
    document.getElementById('recruiter-placeholder').classList.add('hidden');
    document.getElementById('recruiter-output').classList.remove('hidden');

    document.getElementById('requisition-label').textContent = `${title} | ${company}`;

    const list = state.batchRankings;
    document.getElementById('shortlist-count-badge').textContent = `${list.length} Candidate(s) Ranked`;

    const tbody = document.getElementById('rankings-table-body');
    tbody.innerHTML = '';

    list.forEach((item, index) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-850 transition-colors';
        
        let badgeClass = 'bg-slate-900 border border-slate-800 text-slate-400';
        const recommendation = item.decision || item.recommendation || 'maybe';
        if (recommendation.toLowerCase().includes('go') && !recommendation.toLowerCase().includes('no')) {
            badgeClass = 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
        } else if (recommendation.toLowerCase().includes('reject') || recommendation.toLowerCase().includes('no')) {
            badgeClass = 'bg-rose-500/10 text-rose-400 border border-rose-500/20';
        } else {
            badgeClass = 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
        }

        tr.innerHTML = `
            <td class="py-3 px-4 font-mono font-bold text-center text-sm">${index + 1}</td>
            <td class="py-3 px-4">
                <div class="font-bold text-slate-100">${item.name}</div>
                <div class="text-[10px] text-slate-500 font-mono mt-0.5">ID: ${item.candidate_id}</div>
            </td>
            <td class="py-3 px-4 text-center font-mono font-bold text-emerald-400 text-sm">${item.score || item.fit_score || 75}%</td>
            <td class="py-3 px-4">
                <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${badgeClass}">${recommendation.toUpperCase()}</span>
                <p class="text-[10px] text-slate-400 mt-1 max-w-sm leading-relaxed">${item.reasoning || item.reason || 'Candidate has strong overlapping skills.'}</p>
            </td>
            <td class="py-3 px-4 text-center">
                <button class="py-1 px-2 border border-slate-700 bg-slate-800 hover:bg-slate-700 hover:text-slate-100 rounded text-[10px] font-semibold flex items-center justify-center gap-1 mx-auto transition-colors" onclick="viewCandidateOutreach('${item.candidate_id}')">
                    <i class="fa-solid fa-reply"></i>
                    Outreach
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    if (list.length > 0) {
        viewCandidateOutreach(list[0].candidate_id);
    }
}

export function viewCandidateOutreach(candidateId) {
    const list = state.batchRankings;
    const rankedCandidate = list.find(item => item.candidate_id === candidateId);
    if (!rankedCandidate) return;

    state.activeOutreachCandidate = rankedCandidate;
    
    const decision = rankedCandidate.decision || rankedCandidate.recommendation || 'maybe';
    const isGo = decision.toLowerCase().includes('go') && !decision.toLowerCase().includes('no');
    
    const badge = document.getElementById('email-mode-badge');
    const label = document.getElementById('outreach-recipient-label');
    const textarea = document.getElementById('outreach-text-output');

    label.textContent = `Email Draft for ${rankedCandidate.name}:`;

    if (isGo) {
        badge.textContent = 'Invitation to Interview';
        badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
        
        textarea.value = `Subject: Invitation to Interview: Senior Backend Engineer - RecruitAI Inc.

Dear ${rankedCandidate.name},

I hope this email finds you well. 

My name is Recruitment Team at RecruitAI Inc. We recently reviewed your profile and resume against our Senior Backend Engineer requisition. 

Our team was highly impressed by your expertise, particularly around:
- ${rankedCandidate.reasoning || "Your strong overlapping technical alignment."}

We would love to schedule a brief 30-minute introductory Google Meet to discuss the opportunity and share more about our engineering challenges. Please let me know your general availability for this week.

Sincerely,
Outreach Desk
RecruitAI Inc.`;
    } else {
        badge.textContent = 'Polite Rejection';
        badge.className = 'text-[10px] font-bold px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20';

        textarea.value = `Subject: Update on your application: Senior Backend Engineer - RecruitAI Inc.

Dear ${rankedCandidate.name},

Thank you very much for your interest in the Senior Backend Engineer role at RecruitAI Inc. and for taking the time to share your resume with us.

After careful evaluation against our immediate requirements, we have decided to proceed with other candidates whose profiles align more closely with our direct tech stacks. 

We will keep your structured profile on file in our talent pool for future opportunities that match your background. We wish you the absolute best in your job search.

Warm regards,
Recruiting Desk
RecruitAI Inc.`;
    }
}

export function copyOutreachEmail() {
    const textarea = document.getElementById('outreach-text-output');
    if (!textarea.value) return;

    navigator.clipboard.writeText(textarea.value);
    const btn = document.getElementById('btn-copy-outreach');
    btn.innerHTML = `<i class="fa-solid fa-check text-emerald-400"></i> Copied!`;
    setTimeout(() => {
        btn.innerHTML = `<i class="fa-regular fa-copy"></i> Copy Outreach`;
    }, 2000);
}

export function clearBulkGroup() {
    state.recruiterCandidates = [];
    renderBulkList();
}

export function renderBulkList() {
    const listContainer = document.getElementById('bulk-list');
    listContainer.innerHTML = '';

    if (state.recruiterCandidates.length === 0) {
        listContainer.innerHTML = `<p class="text-xs text-slate-500 italic text-center py-4">No candidates in screening pool.</p>`;
        return;
    }

    state.recruiterCandidates.forEach(cand => {
        const div = document.createElement('div');
        div.className = 'bg-slate-900 border border-slate-800 p-2.5 rounded flex items-center justify-between text-xs';
        div.innerHTML = `
            <div class="flex items-center gap-2 min-w-0">
                <i class="fa-solid fa-user-check text-emerald-400 shrink-0"></i>
                <span class="font-semibold text-slate-200 truncate">${cand.name}</span>
            </div>
            <span class="font-mono text-[10px] font-semibold text-emerald-300 bg-emerald-500/5 px-1.5 py-0.5 rounded border border-emerald-500/10">Loaded</span>
        `;
        listContainer.appendChild(div);
    });
}

export function showRecruiterLoader(show) {
    const placeholder = document.getElementById('recruiter-placeholder');
    const loader = document.getElementById('recruiter-loader');
    const output = document.getElementById('recruiter-output');

    if (show) {
        placeholder.classList.add('hidden');
        output.classList.add('hidden');
        loader.classList.remove('hidden');
    } else {
        loader.classList.add('hidden');
    }
}

/**
 * RecruitAI Console Client - Backend API Client Layer
 */

/**
 * Upload and extract a CV PDF/image/txt
 */
export async function extractCV(file, tenantId) {
    const cvFormData = new FormData();
    cvFormData.append('file', file);

    const response = await fetch('/api/cv/extract', {
        method: 'POST',
        body: cvFormData,
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`CV extraction failed: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Extract a Job Description from raw text or document file
 */
export async function extractJob(inputType, file, text, tenantId) {
    const jdFormData = new FormData();
    if (inputType === 'file') {
        jdFormData.append('file', file);
    } else {
        jdFormData.append('job_text', text);
    }

    const response = await fetch('/api/jobs/extract', {
        method: 'POST',
        body: jdFormData,
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Job extraction failed: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Execute Candidate Fit Analysis
 */
export async function analyzeFit(cvData, jobPosition, companyType, customContext, tenantId) {
    const fitPayload = {
        candidate_cv: cvData,
        job_information: jobPosition,
        company_type: companyType,
        custom_context: customContext || null
    };

    const response = await fetch('/api/fit/analyze', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId
        },
        body: JSON.stringify(fitPayload)
    });

    if (!response.ok) {
        throw new Error(`Fit analysis failed: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Generate Motivation Letter Draft
 */
export async function generateLetter(cvData, jobPosition, companyType, language, tone, format, tenantId) {
    const payload = {
        cv_info: cvData,
        job_info: jobPosition,
        job_type: companyType,
        language: language,
        tone: tone,
        return_format: format
    };

    const response = await fetch('/api/motivation-letter/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        throw new Error(`Letter generation failed: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Screen and rank a list of candidates against a target Job Requisition
 */
export async function rankCandidates(candidates, targetJob, tenantId) {
    const payload = {
        candidates: candidates,
        target_job: targetJob
    };

    const response = await fetch('/api/hr/rank', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        throw new Error(`Screening failed: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Get active job search providers
 */
export async function getProviders() {
    const response = await fetch('/api/jobs/providers');
    if (!response.ok) {
        throw new Error(`Failed to fetch providers: status ${response.status}`);
    }
    return await response.json();
}

/**
 * Search job listings across registered providers
 */
export async function searchJobs(provider, query, department, contractType, tenantId) {
    const payload = {
        provider: provider || "france_travail",
        query: query || null,
        department: department || null,
        contract_type: contractType || null,
        page: 1,
        limit: 25
    };

    const response = await fetch('/api/jobs/search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        throw new Error(`Job search failed: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Fetch detailed job posting information
 */
export async function getJobDetail(provider, jobId, tenantId) {
    const response = await fetch(`/api/jobs/search/${provider}/${jobId}`, {
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch job detail: status ${response.status}`);
    }

    return await response.json();
}

/**
 * List all extracted candidates from SQLite for tenant
 */
export async function listCandidates(tenantId) {
    const response = await fetch('/api/cv/candidates', {
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to list candidates: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Fetch the original uploaded candidate document as a raw Blob
 */
export async function getCandidateFile(candidateId, tenantId) {
    const response = await fetch(`/api/cv/candidates/${candidateId}/file`, {
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch original candidate file: status ${response.status}`);
    }

    return await response.blob();
}


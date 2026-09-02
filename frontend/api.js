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

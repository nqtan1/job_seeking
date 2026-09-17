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
export async function generateLetter(cvData, jobPosition, companyType, language, tone, format, tenantId, customContext) {
    const payload = {
        cv_info: cvData,
        job_info: jobPosition,
        job_type: companyType,
        language: language,
        tone: tone,
        return_format: format,
        custom_context: customContext || null
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

/**
 * Create a new job application
 */
export async function createApplication(applicationData, tenantId) {
    const response = await fetch('/api/applications', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId
        },
        body: JSON.stringify(applicationData)
    });

    if (!response.ok) {
        throw new Error(`Failed to create application: status ${response.status}`);
    }

    return await response.json();
}

/**
 * List job applications with optional status and source filters
 */
export async function getApplications(filters = {}, tenantId) {
    const params = new URLSearchParams();
    if (filters.status) params.append('status', filters.status);
    if (filters.source) params.append('source', filters.source);
    if (filters.sort_by_date) params.append('sort_by_date', filters.sort_by_date);

    const queryString = params.toString();
    const url = `/api/applications${queryString ? '?' + queryString : ''}`;

    const response = await fetch(url, {
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch applications: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Retrieve details for a specific application
 */
export async function getApplication(applicationId, tenantId) {
    const response = await fetch(`/api/applications/${applicationId}`, {
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch application details: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Update a job application
 */
export async function updateApplication(applicationId, applicationData, tenantId) {
    const response = await fetch(`/api/applications/${applicationId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': tenantId
        },
        body: JSON.stringify(applicationData)
    });

    if (!response.ok) {
        throw new Error(`Failed to update application: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Delete a job application
 */
export async function deleteApplication(applicationId, tenantId) {
    const response = await fetch(`/api/applications/${applicationId}`, {
        method: 'DELETE',
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to delete application: status ${response.status}`);
    }
}

/**
 * Upload a document (CV or cover letter) for a job application
 */
export async function uploadApplicationFile(applicationId, fileType, file, tenantId) {
    const formData = new FormData();
    formData.append('file_type', fileType);
    formData.append('file', file);

    const response = await fetch(`/api/applications/${applicationId}/upload`, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to upload application file: status ${response.status}`);
    }

    return await response.json();
}

/**
 * Upload multiple special documents (portfolio, certificates, etc.) for a job application
 */
export async function uploadSpecialDocuments(applicationId, files, tenantId) {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    const response = await fetch(`/api/applications/${applicationId}/upload-special`, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Tenant-ID': tenantId
        }
    });

    if (!response.ok) {
        throw new Error(`Failed to upload special documents: status ${response.status}`);
    }

    return await response.json();
}


/**
 * RecruitAI Console Client - Application State Store
 */
export const state = {
    tenantId: 'default-tenant',
    companyType: 'corporation',
    cvFile: null,
    cvData: null,
    cvFileName: '',
    candidateId: null,
    jobPosition: null,
    fitCheck: null,
    motivationLetter: null,
    interviewKit: null,
    activeKitTab: 'tech',
    
    // Job Description File State
    jdFile: null,
    jdFileName: '',
    jdInputType: 'text',
    
    // Recruiter Hub state
    recruiterCandidates: [
        {
            candidate_id: "c1",
            name: "Jane Doe",
            email: "jane.doe@example.com",
            phone: "+1-555-0100",
            skills: ["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "CI/CD"]
        },
        {
            candidate_id: "c2",
            name: "John Smith",
            email: "john.smith@example.com",
            phone: "+1-555-0199",
            skills: ["Java", "Spring Boot", "MySQL", "Kubernetes", "Angular"]
        }
    ],
    batchRankings: null,
    activeOutreachCandidate: null
};

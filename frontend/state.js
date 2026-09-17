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
    
    // DB Candidates list
    dbCandidates: [],
    selectedDbCandidateId: '',

    // Job Description File State
    jdFile: null,
    jdFileName: '',
    jdInputType: 'text', // 'text', 'file', or 'search'
    
    // Job Search Engine State
    searchProvider: 'france_travail',
    searchQuery: '',
    searchDept: '',
    searchContract: '',
    searchDomain: '',
    searchResults: [],
    selectedSearchJob: null,

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
    activeOutreachCandidate: null,

    // Job Tracker State
    applications: [],
    trackerFilters: {
        status: '',
        source: '',
        sort_by_date: 'desc'
    },
    selectedApplicationId: null
};

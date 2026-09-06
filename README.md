# 🚀 RecruitAI: The Intelligent, Multi-Tenant Recruitment Companion

Welcome to **RecruitAI**, your modern, AI-powered assistant designed to bridge the gap between talented candidates and busy recruiting teams. 

Whether you are a job seeker trying to optimize your resume and ace your next interview, or an HR representative trying to screen, rank, and communicate with a batch of applicants in seconds, RecruitAI brings high-fidelity, enterprise-grade intelligence straight to your browser—completely locally, securely, and privately.

---

## ✨ Why RecruitAI?

Most recruiting tools are either overly complex enterprise software or simple, single-feature utilities. RecruitAI is built to be **practical, beautiful, and complete**:
*   **For Candidates**: It's a full-stack career coach. It doesn't just score your resume; it tells you exactly what is missing, drafts your cover letters, and prepares a tailored mock interview guide.
*   **For Recruiters**: It's a high-speed command center. Create a job requisition, drag and drop multiple resumes together, rank them instantly, and generate personalized email drafts in seconds.
*   **Built for Real-World Privacy (Multi-Tenancy)**: Designed from day one to support multiple distinct client companies. Your candidate data, original files, and AI evaluations are kept strictly isolated and secure under your own workspace.

---

## 🎨 A Quick Visual Tour of Your Workspaces

RecruitAI features a sleek, dark-themed "Slate & Emerald" dashboard divided into two simple, highly intuitive hubs:

### 1. The Candidate Sandbox
A structured, top-to-bottom wizard that helps you refine your application:
*   **Independent Document Uploads**: Upload your CV on the Left, paste or drag in the Job Description on the Right.
*   **Real-Time Visual Previews**: Watch your PDF, TXT, or image files render dynamically in local viewports right beneath the upload cards—no more switching tabs!
*   **Dynamic Radial Score Ring**: An animated, color-shifting matching score ring (Emerald for Great, Amber for Decent, Rose for Needs Improvement).
*   **Gap & Strengths Analysis**: Bulleted breakdowns of your competitive strengths and critical gaps.
*   **Actionable Advice**: Deep, custom, and highly practical coaching tips on how to improve your CV to stand out.
*   **Personalized Cover Letters**: Draft highly tailored motivation letters matching your background to the role’s exact needs.
*   **AI-Powered Mock Interview Kits**: If you're a good fit, the AI automatically prepares 3-5 technical questions, behavioral queries, and a copy-pasteable simulation prompt to practice in any LLM!

### 2. The Recruiter Hub
A bulk screening command center for HR professionals:
*   **Configure Requisitions**: Set target positions, company details, and core qualifications line-by-line.
*   **Bulk Ingestion**: Drag and drop a whole batch of resumes together to populate your screening pool.
*   **The Shortlist Table**: Compare all applicants in a clean ranking grid sorted by fit score, featuring colorful verdict badges (GO, MAYBE, NO_GO) and explicit recruiter reasoning.
*   **Automated outreach**: Click any candidate to auto-generate a customized, personalized email template—whether inviting them to an interview or sending an empathetic, brand-aligned rejection.

---

## ⚡ 2-Minute Quickstart

Getting RecruitAI up and running on your local machine is extremely easy and requires exactly zero complex setups.

### 1. Initialize the Environment
We use **`uv`**, an extremely fast Python tool, to handle packages. Open your terminal in the `backend/` directory and run:
```bash
cd backend
uv sync
```
*This will automatically configure a clean local environment and install all packages in under 1 second!*

### 2. Add Your Keys
Copy the environment template and add your Gemini API key or Google Cloud Project ID:
```bash
cp .env.example .env
```
*(Open `.env` in any text editor and fill in your details).*

### 3. Launch the Server!
Start the backend server:
```bash
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Now, simply open your browser and navigate to **`http://127.0.0.1:8000`** to experience RecruitAI live!

---

## 🔒 Absolute Privacy & Local Playbooks
*   **Data Isolation**: All SQLite databases, processing logs, and temporary caches are located strictly locally.
*   **Untracked Guides**: All advanced documentation and agent playbooks (`docs/` and `GEMINI.md`) are automatically ignored in `.gitignore`, ensuring your private files remain strictly local and are never pushed to public GitHub repositories.

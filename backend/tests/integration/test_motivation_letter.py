from motivation_letter import MotivationLetterRequest, MotivationLetterAgent
from cv.schema import CVInformation, PersonalInfo, Experience, RawSkill
from jobs.schema import JobPosition


def create_mock_cv() -> CVInformation:
    """Create mock CV data for testing"""
    return CVInformation(
        personal_info=PersonalInfo(
            name="John Doe",
            email="john@example.com",
            phone="+33612345678"
        ),
        experiences=[
            Experience(
                job_title="Senior AI Engineer",
                company="Tech Corp",
                start_date="2022",
                end_date="Present",
                description="Built ML systems"
            )
        ],
        skills=[RawSkill(name="Python"), RawSkill(name="ML")]
    )


def create_mock_job() -> JobPosition:
    """Create mock job data for testing"""
    return JobPosition(
        job_title="AI Engineer",           
        company="Startup XYZ",
        location="Paris, France",          
        description="Looking for AI expert",
        contract_type="CDI"               
    )


def test_motivation_letter_generation():
    """Test motivation letter generation"""
    # Setup
    cv = create_mock_cv()
    job = create_mock_job()
    
    request = MotivationLetterRequest(
        cv_info=cv,
        job_info=job,
        job_type="startup",
        language="fr",
        tone="professional",
        return_format="txt"
    )
    
    # Execute
    agent = MotivationLetterAgent()
    letter = agent.generate_letter(request)
    
    # Verify
    assert letter.content is not None, "Letter content should not be empty"
    assert len(letter.content) > 0, "Letter content should have text"
    assert letter.metadata.job_type == "startup", "Job type should be startup"
    assert letter.metadata.language == "fr", "Language should be French"
    assert letter.metadata.format == "txt", "Format should be txt"
    
    # Display results
    print("\n" + "="*70)
    print("MOTIVATION LETTER")
    print("="*70)
    print(letter.content)
    print("\n" + "="*70)
    print("METADATA")
    print("="*70)
    print(f"Job Type: {letter.metadata.job_type}")
    print(f"Language: {letter.metadata.language}")
    print(f"Tone: {letter.metadata.tone}")
    print(f"Format: {letter.metadata.format}")
    print(f"Generated: {letter.metadata.generated_at}")


def test_motivation_letter_pdf_rendering(tmp_path):
    """Test that MotivationLetterService compiles and renders a PDF successfully"""
    from motivation_letter.service import MotivationLetterService
    from motivation_letter.schema import MotivationLetter, MotivationLetterMetadata
    from datetime import datetime

    # 1. Setup mock data
    cv = create_mock_cv()
    job = create_mock_job()
    request = MotivationLetterRequest(
        cv_info=cv,
        job_info=job,
        job_type="startup",
        language="fr",
        tone="professional",
        return_format="txt"
    )

    letter = MotivationLetter(
        content="Ceci est le corps de ma superbe lettre de motivation.",
        metadata=MotivationLetterMetadata(
            job_type="startup",
            language="fr",
            tone="professional",
            format="txt",
            generated_at=datetime.now(),
            system_prompt_used="test_prompt",
            llm_model="test_model"
        )
    )

    # 2. Instantiate service with temp directory db_base_dir
    service = MotivationLetterService()
    service.db_base_dir = tmp_path
    service.result_base_dir = tmp_path / "motivation_letter" / "generate"
    service.result_base_dir.mkdir(parents=True, exist_ok=True)

    # 3. Generate LaTeX content and verify
    latex_content = service.generate_letter_content(request, letter.content)
    assert "\\documentclass[11pt,francais]{lettre}" in latex_content
    assert "\\begin{letter}" in latex_content
    assert "Startup XYZ" in latex_content
    assert "John Doe" in latex_content

    # 4. Compile PDF and verify on disk
    result_folder = service._get_result_folder(job.company, job.job_title)
    pdf_path = service.render_letter_pdf(latex_content, result_folder, "motivation_letter")
    
    assert pdf_path is not None, "PDF compilation failed"
    assert pdf_path.exists(), "PDF should be saved on disk"
    assert pdf_path.stat().st_size > 0, "PDF should not be empty"
    print(f"Integration PDF test passed! PDF generated successfully at: {pdf_path}")



if __name__ == "__main__":
    test_motivation_letter_generation()
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


if __name__ == "__main__":
    test_motivation_letter_generation()
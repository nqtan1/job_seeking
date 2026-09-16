from typing import Optional, List
from datetime import datetime
from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage

from cv.schema import CVInformation
from jobs.schema import JobPosition, CandidateAnalysis
from motivation_letter.schema import (
    MotivationLetter,
    MotivationLetterRequest,
    MotivationLetterMetadata
)

from agents import BaseAgent, AgentConfig
from motivation_letter.prompt import get_system_prompt, CUSTOM_CONTEXT_INSTRUCTION

class MotivationLetterAgent(BaseAgent):
    """
    Agent for generating motivation letters
    """
    
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        logger_name: str = "motivation_letter.agent",
        log_file: str = "motivation_letter_api.log",
        log_level: str = "INFO"
        ): 
        super().__init__(
            config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level
            )
        self.logger.info("MotivationLetterAgent initialized")
        
    # HELPER functions 
    def _build_user_message(self, request: MotivationLetterRequest) -> str:
        """
        Build the user message with all context for LLM
        """
        self.logger.info(f"Building user message for job type: {request.job_type}")
        
        cv_json = request.cv_info.model_dump_json(indent = 2)
        job_json = request.job_info.model_dump_json(indent=2)
        
        message = f"""
Please generate a motivation with the following information:

CANDIDATE CV:
{cv_json}

TARGET JOB:
{job_json}
"""
        # Add analysis if available
        if request.candidate_analysis: 
            self.logger.info("Adding candidate analysis to user message")
            analysis_json = request.candidate_analysis.model_dump_json(indent=2)
            message += f"\n\nCANDIDATE-JOB ANALYSIS:\n{analysis_json}"

        # Add custom context if provided
        if request.custom_context:
            self.logger.info("Adding custom context to user message")
            message += f"\n\n{CUSTOM_CONTEXT_INSTRUCTION.format(custom_context=request.custom_context)}"
            
        self.logger.info(f"User message built successfully (length: {len(message)} chars)")
        return message

    def _convert_to_latex(self, content: str) -> str:
        """
        Convert plain text to LaTeX document
        """
        self.logger.info("Converting content to LaTeX format")
        
        latex_template = r"""
\documentclass[12pt]{letter}
\usepackage[utf-8]{inputenc}
\usepackage{geometry}
\geometry{margin=1in}

\begin{document}

%s

\end{document}
""" % content.replace("\n", "\n\n")
        
        self.logger.info("LaTeX conversion completed")
        return latex_template
    
    def _post_process(self, content: str, format: str) -> str:
        """
        Post-process letter content
        """
        self.logger.info(f"Post-processing letter content with format: {format}")
        
        if format == "latex": 
            return self._convert_to_latex(content)
        
        self.logger.info("No post-processing needed for txt format")
        return content
    
    def _get_startup_attitudes(self) -> List[str]:
        """Attitudes candidate should demonstrate for startup"""
        attitudes = [
            "Entrepreneurial Mindset: Ready to wear multiple hats",
            "Adaptability: Comfortable with fast-paced, changing environment",
            "Impact-Driven: Focused on tangible outcomes, not process",
            "Innovation: Willing to challenge status quo and experiment",
            "Collaboration: Values lean team dynamics over hierarchy"
        ]
        self.logger.info(f"Generated {len(attitudes)} startup attitudes")
        return attitudes

    def _get_phd_attitudes(self) -> List[str]:
        """Attitudes candidate should demonstrate for PhD/Research"""
        attitudes = [
            "Research Independence: Self-directed problem solving",
            "Critical Thinking: Questions assumptions, seeks rigor",
            "Continuous Learning: Pursues depth and mastery",
            "Academic Rigor: Values methodology and scientific integrity",
            "Curiosity-Driven: Motivated by understanding, not just application"
        ]
        self.logger.info(f"Generated {len(attitudes)} PhD attitudes")
        return attitudes

    def _get_corporation_attitudes(self) -> List[str]:
        """Attitudes candidate should demonstrate for corporation"""
        attitudes = [
            "Strategic Thinking: Long-term value creation focus",
            "Reliability: Consistent delivery and accountability",
            "Scalability Mindset: Building systems for growth",
            "Team Player: Values stability and collaborative structure",
            "Professional Standards: Respects compliance and governance"
        ]
        self.logger.info(f"Generated {len(attitudes)} corporation attitudes")
        return attitudes
        
    def _generate_suggestions(self, request: MotivationLetterRequest) -> Optional[List]:
        """
        Generate attitude recommendations based on job type
        """
        self.logger.info(f"Generating suggestions for job type: {request.job_type}")
        
        if request.job_type == "startup":
            return self._get_startup_attitudes()
        elif request.job_type == "phd":
            return self._get_phd_attitudes()
        elif request.job_type == "corporation":
            return self._get_corporation_attitudes()
        
        self.logger.warning(f"Unknown job type: {request.job_type}")
        return None

    
    # Core functions
    def generate_letter(self, request: MotivationLetterRequest) -> MotivationLetter:
        """
        Generate a motivation letter based on request
        
        Args: 
            request: MotivationLetterRequest with all parameters
            
        Returns: 
            MotivationLetter with content and metadata
        """
        self.logger.info(f"Starting letter generation - job_type: {request.job_type}, language: {request.language}")

        try:
            # Step 1: Build system prompt 
            self.logger.info("Building system prompt")
            system_prompt = get_system_prompt(
                job_type=request.job_type,
                tone=request.tone,
                language=request.language
            )
            
            # Step 2: Generate and inject attitudes
            self.logger.info("Injecting attitudes into system prompt")
            attitudes = self._generate_suggestions(request)

            attitudes_context = ""
            if attitudes:
                attitudes_list = "\n".join([f"- {attitude}" for attitude in attitudes])
                attitudes_context = f"""
CANDIDATE KEY ATTITUDES TO EMPHASIZE:
{attitudes_list}

Use these attitudes naturally in the letter to highlight candidate's mindset alignment with this {request.job_type} role.
"""
                system_prompt += "\n" + attitudes_context
                self.logger.info(f"Attitudes injected: {len(attitudes)} items")
            
            # Step 3: Build user message
            self.logger.info("Building user message")
            user_message = self._build_user_message(request=request)
            
            # Step 4: Call LLM
            self.logger.info(f"Calling LLM model: {self.config.model_name}")
            response = self.model.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            self.logger.info("LLM response received successfully")
            
            # Step 5: Post-process 
            self.logger.info("Post-processing response")
            letter_content = self._post_process(content=response.content, format=request.return_format)
            
            # Step 6: Create metadata
            self.logger.info("Creating metadata")
            metadata = MotivationLetterMetadata(
                generated_at=datetime.now(),
                job_type=request.job_type,
                language=request.language,
                tone=request.tone,
                format=request.return_format,
                system_prompt_used=request.job_type,
                llm_model=self.config.model_name
            )
            
            # Step 7: Return structured output
            self.logger.info(f"Letter generation completed successfully")
            return MotivationLetter(
                content=letter_content,
                metadata=metadata,
                suggestions=None
            )
            
        except Exception as e:
            self.logger.error(f"Error generating motivation letter: {str(e)}", exc_info=True)
            raise
from typing import Optional, List
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage

from agents import BaseAgent, AgentConfig
from motivation_letter.schema import (
    MotivationLetterRequest, 
    MotivationLetter, 
    MotivationLetterMetadata
)
from motivation_letter.prompt import get_system_prompt, CUSTOM_CONTEXT_INSTRUCTION

class MotivationLetterAgent(BaseAgent):
    """
    Agent responsible for generating customized motivation letters 
    using LLMs based on candidate CV and target Job description.
    """
    
    def __init__(
        self, 
        config: Optional[AgentConfig] = None,
        logger_name: str = "motivation_letter.agent",
        log_file: str = "motivation_letter_api.log",
        log_level: str = "INFO"
    ):
        super().__init__(
            config=config,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level
        )
        self.logger.debug("MotivationLetterAgent initialized")
        
    # HELPER functions 
    def _build_user_message(self, request: MotivationLetterRequest) -> str:
        """
        Build the user message with all context for LLM
        """
        self.logger.debug(
            "Building user message context", 
            extra={"job_type": request.job_type}
        )
        
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
            self.logger.debug("Adding candidate analysis to user message")
            analysis_json = request.candidate_analysis.model_dump_json(indent=2)
            message += f"\n\nCANDIDATE-JOB ANALYSIS:\n{analysis_json}"

        # Add custom context if provided
        if request.custom_context:
            self.logger.debug("Adding custom context to user message")
            message += f"\n\n{CUSTOM_CONTEXT_INSTRUCTION.format(custom_context=request.custom_context)}"
            
        self.logger.debug(
            "User message context built successfully", 
            extra={"message_length": len(message)}
        )
        return message

    def _convert_to_latex(self, content: str) -> str:
        """
        Convert plain text to LaTeX document
        """
        self.logger.debug("Converting content to LaTeX format")
        
        latex_template = r"""
\documentclass[12pt]{letter}
\usepackage[utf-8]{inputenc}
\usepackage{geometry}
\geometry{margin=1in}

\begin{document}

%s

\end{document}
""" % content.replace("\n", "\n\n")
        
        self.logger.debug("LaTeX conversion completed")
        return latex_template
    
    def _post_process(self, content: str, format: str) -> str:
        """
        Post-process letter content
        """
        self.logger.debug(
            "Post-processing letter content", 
            extra={"format": format}
        )
        
        if format == "latex": 
            return self._convert_to_latex(content)
        
        self.logger.debug("No post-processing needed for txt format")
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
        self.logger.debug(
            "Generated startup attitudes", 
            extra={"count": len(attitudes)}
        )
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
        self.logger.debug(
            "Generated PhD attitudes", 
            extra={"count": len(attitudes)}
        )
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
        self.logger.debug(
            "Generated corporation attitudes", 
            extra={"count": len(attitudes)}
        )
        return attitudes
        
    def _generate_suggestions(self, request: MotivationLetterRequest) -> Optional[List]:
        """
        Generate attitude recommendations based on job type
        """
        self.logger.debug(
            "Generating suggestions for job type", 
            extra={"job_type": request.job_type}
        )
        
        if request.job_type == "startup":
            return self._get_startup_attitudes()
        elif request.job_type == "phd":
            return self._get_phd_attitudes()
        elif request.job_type == "corporation":
            return self._get_corporation_attitudes()
        
        self.logger.warning(
            "Unknown job type specified in request", 
            extra={"job_type": request.job_type}
        )
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
        # Business Transaction Start - INFO
        self.logger.info(
            "Starting motivation letter generation", 
            extra={
                "job_type": request.job_type, 
                "language": request.language, 
                "tone": request.tone, 
                "format": request.return_format
            }
        )

        try:
            # Step 1: Build system prompt 
            self.logger.debug("Building system prompt")
            system_prompt = get_system_prompt(
                job_type=request.job_type,
                tone=request.tone,
                language=request.language
            )
            
            # Step 2: Generate and inject attitudes
            self.logger.debug("Injecting attitudes into system prompt")
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
                self.logger.debug(
                    "Attitudes context injected successfully", 
                    extra={"attitudes_count": len(attitudes)}
                )
            
            # Step 3: Build user message
            self.logger.debug("Building user message context")
            user_message = self._build_user_message(request=request)
            
            # Step 4: Call LLM
            # Network Boundary - INFO
            self.logger.info(
                "Calling LLM model for motivation letter generation", 
                extra={"model_name": self.config.model_name}
            )
            response = self.model.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            self.logger.debug("LLM response received successfully")
            
            # Step 5: Post-process 
            self.logger.debug("Post-processing LLM letter response")
            letter_content = self._post_process(content=response.content, format=request.return_format)
            
            # Step 6: Create metadata
            self.logger.debug("Creating letter metadata")
            metadata = MotivationLetterMetadata(
                generated_at=datetime.now(),
                job_type=request.job_type,
                language=request.language,
                tone=request.tone,
                format=request.return_format,
                system_prompt_used=request.job_type,
                llm_model=self.config.model_name
            )
            
            # Business Transaction Success - INFO
            self.logger.info(
                "Motivation letter generated successfully", 
                extra={"content_length": len(letter_content)}
            )
            return MotivationLetter(
                content=letter_content,
                metadata=metadata,
                suggestions=None
            )
            
        except Exception as e:
            # System Failure - ERROR
            self.logger.error(
                "Error generating motivation letter", 
                exc_info=True, 
                extra={"job_type": request.job_type, "language": request.language}
            )
            raise

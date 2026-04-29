from agents import BaseAgent, AgentConfig
from cv.schema import CVInformation

from typing import Optional, Union, Dict
from pathlib import Path

from pydantic import BaseModel

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from google import genai

class CVAnalysisAgent(BaseAgent):
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self.client = genai.Client(api_key=self.config.api_key)
        
    def extract_cv(
        self, 
        file_path: Union[str, Path], 
        message: str,
        output_schema: Optional[BaseModel] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Union[BaseMessage, Dict]:
        """
        Extract information from CV
        """
        if system_prompt is None:
            system_prompt = "You are a virtual assistant designed to extract information from CVs"
        
        model = self.model.with_structured_output(output_schema) if output_schema else self.model
        
        file = self.client.files.upload(file=file_path)
        
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = self.client.files.get(name=file.name)
            
        message_obj = HumanMessage(
            content=[
                {"type": "text", "text": message},
                {"type": "file", "file_id": file.uri, "mime_type": "application/pdf"},
            ]
        )
        
        response = model.invoke([
            SystemMessage(content=system_prompt),
            message_obj
        ])
        return response

    def analyze_cv(
        self,
        cv_information: CVInformation,
        output_schema: BaseModel, 
        message: str,
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """
        Analyze general about candidate information
        """
        if system_prompt is None:
            system_prompt = "You are a virtual assistant designed to analyze CV information"
        
        model = self.model.with_structured_output(output_schema)
        
        cv_json = cv_information.model_dump_json(indent=2)
        
        full_prompt = f"""
USER REQUEST: 
{message}

CV INFORMATION:
{cv_json}        
"""
        response = model.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=full_prompt)
        ])
        return response
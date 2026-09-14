from typing import Optional, Dict, Any, List, Union
import json
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_core.tools import tool

from agents import BaseAgent, AgentConfig
from jobs.search.providers.manager import JobProviderManager
from jobs.search.prompt import SYSTEM_PROMPT_JOB_SEARCH


class JobSearchAgent(BaseAgent):
    """
    AI Agent that can search jobs and fetch details automatically.
    By binding search and detail retrieval functions as tools, the LLM
    can parse the user's natural language intent, invoke the appropriate APIs,
    and respond with nicely formatted job listings or detailed info.
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        provider_manager: Optional[JobProviderManager] = None,
        logger_name: str = "jobs.search_agent",
        log_file: str = "jobs_api.log",
        log_level: str = "INFO",
    ):
        self.provider_manager = provider_manager or JobProviderManager()
        
        # Dynamically list registered providers to feed into the prompt
        providers_list = self.provider_manager.list_providers()
        formatted_prompt = SYSTEM_PROMPT_JOB_SEARCH.format(
            active_providers_str=", ".join([f"'{p}'" for p in providers_list])
        )

        super().__init__(
            config=config,
            system_prompt=formatted_prompt,
            logger_name=logger_name,
            log_file=log_file,
            log_level=log_level,
        )
        self.logger.info("JobSearchAgent initialized with JobProviderManager and bound tools.")

    def run_chat_loop(self, user_message: str, max_iterations: int = 5) -> str:
        """
        Runs a tool-calling chat execution loop.
        Accepts user input, lets the LLM decide which tools to call,
        executes them, feeds results back to the LLM, and returns the final answer.
        """
        self.logger.info(f"Starting search chat loop for message: {user_message[:60]}...")
        
        # 1. Define tools using standard Python callable functions
        @tool
        def search_jobs(
            query: Optional[str] = None,
            department: Optional[str] = None,
            contract_type: Optional[str] = None,
            provider: str = "france_travail",
            page: int = 1,
            limit: int = 10,
        ) -> str:
            """
            Search for live jobs across active providers (e.g. 'france_travail', 'linkedin', 'jobteaser').
            Use this when the user asks to find, search, or list jobs.
            
            Args:
                query: Keywords to search (e.g., "python", "devops", "marketing")
                department: French department code (e.g., "75" for Paris, "69" for Rhône).
                contract_type: Type of contract, e.g., "CDI", "CDD", "Stage", "Alternance", "Freelance".
                provider: The active job platform to query. Defaults to 'france_travail'.
                page: Page number (default: 1)
                limit: Max results to return (default: 10, max: 150)
            """
            self.logger.info(f"Agent tool 'search_jobs' invoked: query={query}, dept={department}, contract={contract_type}, provider={provider}")
            try:
                results = self.provider_manager.search_jobs(
                    provider_name=provider,
                    query=query,
                    department=department,
                    contract_type=contract_type,
                    page=page,
                    limit=limit,
                )
                return results.model_dump_json()
            except Exception as e:
                self.logger.error(f"Error in search_jobs tool execution: {str(e)}")
                return json.dumps({"error": str(e), "results": []})

        @tool
        def get_job_detail(job_id: str, provider: Optional[str] = None) -> str:
            """
            Retrieve full details, description, company details, contract details,
            and application details for a single job by its ID or complete URL.
            
            Args:
                job_id: The job identifier slug (e.g., "212MZBL") or full URL.
                provider: Optional provider name. If omitted, the system will auto-detect from the URL domain.
            """
            self.logger.info(f"Agent tool 'get_job_detail' invoked: job_id={job_id}, provider={provider}")
            
            # Smart auto-detection from pasted URL domains
            if not provider:
                url_str = job_id.lower()
                if "linkedin.com" in url_str:
                    provider = "linkedin"
                elif "jobteaser.com" in url_str:
                    provider = "jobteaser"
                elif "francetravail.fr" in url_str or "pole-emploi.fr" in url_str or "candidat.francetravail.fr" in url_str:
                    provider = "france_travail"
                else:
                    # Default fallback
                    provider = "france_travail"

            try:
                details = self.provider_manager.get_job_detail(
                    provider_name=provider,
                    job_id=job_id,
                )
                return json.dumps({
                    "id": details["standard_info"]["id"],
                    "title": details["standard_info"]["title"],
                    "company": details["standard_info"]["company"],
                    "location": details["standard_info"]["location"],
                    "contract_type": details["job_position_data"]["contract_type"],
                    "description": details["standard_info"]["description"],
                    "skills": details["standard_info"]["skills"],
                    "salary": details["standard_info"]["salary_label"],
                    "experience": details["standard_info"]["experience_label"],
                    "url": details["standard_info"]["url"],
                    "provider": provider,
                }, indent=2)
            except Exception as e:
                self.logger.error(f"Error in get_job_detail tool execution: {str(e)}")
                return json.dumps({"error": str(e)})

        # 2. Bind tools to the model
        tools_list = [search_jobs, get_job_detail]
        model_with_tools = self.model.bind_tools(tools_list)

        # 3. Build a clean thread of messages
        # Start with the system prompt and conversation history
        messages: List[BaseMessage] = []
        for msg in self.conversation_history:
            if isinstance(msg, SystemMessage):
                messages.append(msg)
            elif not isinstance(msg, SystemMessage):
                # Include existing human/ai/tool messages if we want multi-turn memory
                messages.append(msg)

        # If system message is not in conversation_history, find and add it
        if not any(isinstance(m, SystemMessage) for m in messages) and len(self.conversation_history) > 0:
            # Add base class system prompt
            messages.insert(0, self.conversation_history[0])

        # Append current user message
        user_msg_obj = HumanMessage(content=user_message)
        messages.append(user_msg_obj)
        self.conversation_history.append(user_msg_obj)

        # Map tool names to actual functions for execution
        tools_map = {
            "search_jobs": search_jobs,
            "get_job_detail": get_job_detail,
        }

        # 4. Run iteration loop
        for i in range(max_iterations):
            self.logger.info(f"Chat loop iteration {i+1}/{max_iterations}")
            
            # Invoke model with bound tools
            response = model_with_tools.invoke(messages)
            messages.append(response)
            self.conversation_history.append(response)

            # If there are tool calls, execute them
            if response.tool_calls:
                self.logger.info(f"Model generated {len(response.tool_calls)} tool calls.")
                
                for tool_call in response.tool_calls:
                    name = tool_call["name"]
                    args = tool_call["args"]
                    call_id = tool_call["id"]

                    self.logger.info(f"Executing tool '{name}' with args {args}")
                    
                    if name in tools_map:
                        tool_func = tools_map[name]
                        # Execute tool function synchronously
                        tool_result = tool_func.invoke(args)
                        
                        # Append tool message to context
                        tool_msg = ToolMessage(
                            content=str(tool_result),
                            tool_call_id=call_id,
                            name=name,
                        )
                        messages.append(tool_msg)
                        self.conversation_history.append(tool_msg)
                    else:
                        self.logger.error(f"Unknown tool name called: '{name}'")
                        error_msg = ToolMessage(
                            content=f"Error: Tool '{name}' is not supported.",
                            tool_call_id=call_id,
                            name=name,
                        )
                        messages.append(error_msg)
                        self.conversation_history.append(error_msg)
                
                # Continue loop to let model digest tool results
                continue
            else:
                # No more tool calls; we are done!
                self.logger.info("Model responded directly. Search chat loop finished.")
                break

        # Trim conversation history to prevent infinite growth
        self._truncate_history_smart()
        
        # Return the final message content
        return messages[-1].content

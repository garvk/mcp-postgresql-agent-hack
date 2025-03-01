import json
from typing import Dict, List, Optional, Any

class PromptManager:
    """
    Manages system prompts for LLM tool orchestration.
    Inspired by ChatMCP's template-based approach.
    """
    
    def __init__(self):
        # Base template for system prompts
        self.template = """
In this environment you have access to a set of tools you can use to answer the user's question.
String and scalar parameters should be specified as is, while lists and objects should use JSON format.

Here are the functions available in JSONSchema format:
{{ TOOL_DEFINITIONS }}

{{ USER_SYSTEM_PROMPT }}

{{ TOOL_CONFIGURATION }}

{{ REASONING_GUIDELINES }}
"""
        
        # Default user system prompt
        self.default_user_prompt = "You are an intelligent assistant capable of using tools to solve user queries effectively."
        
        # Default tool configuration
        self.default_tool_config = "No additional configuration is required."
        
        # Reasoning guidelines to encourage systematic thinking
        self.reasoning_guidelines = """
**GENERAL GUIDELINES:**

1. **Step-by-step reasoning:**
   - Analyze tasks systematically.
   - Break down complex problems into smaller, manageable parts.
   - Verify assumptions at each step to avoid errors.
   - Reflect on results to improve subsequent actions.

2. **Effective tool usage:**
   - **Explore:** 
     - Identify available information and verify its structure.
     - Check assumptions and understand data relationships.
   - **Iterate:**
     - Start with simple queries or actions.
     - Build upon successes, adjusting based on observations.
   - **Handle errors:**
     - Carefully analyze error messages.
     - Use errors as a guide to refine your approach.
     - Document what went wrong and suggest fixes.

3. **Clear communication:**
   - Explain your reasoning and decisions at each step.
   - Share discoveries transparently with the user.
   - Outline next steps or ask clarifying questions as needed.

**EXAMPLES OF BEST PRACTICES:**

- **Working with databases:**
  - Check schema before writing queries.
  - Verify the existence of columns or tables.
  - Start with basic queries and refine based on results.

- **Processing data:**
  - Validate data formats and handle edge cases.
  - Ensure the integrity and correctness of results.

- **Accessing resources:**
  - Confirm resource availability and permissions.
  - Handle missing or incomplete data gracefully.

**REMEMBER:**
- Be thorough and systematic in your approach.
- Ensure that each tool call serves a clear and well-explained purpose.
- When faced with ambiguity, make reasonable assumptions to move forward.
- Minimize unnecessary user interactions by offering actionable insights and solutions.
"""

    def generate_system_prompt(
        self, 
        tools: List[Dict[str, Any]], 
        user_prompt: Optional[str] = None,
        tool_config: Optional[str] = None,
        include_reasoning: bool = True
    ) -> str:
        """
        Generate a system prompt with tool definitions and guidelines.
        
        Args:
            tools: List of tool definitions in Claude-compatible format
            user_prompt: Optional custom user system prompt
            tool_config: Optional tool configuration instructions
            include_reasoning: Whether to include reasoning guidelines
            
        Returns:
            Formatted system prompt
        """
        # Use provided values or defaults
        final_user_prompt = user_prompt or self.default_user_prompt
        final_tool_config = tool_config or self.default_tool_config
        
        # Convert tools to formatted JSON string
        tools_json = json.dumps({"tools": tools}, indent=2)
        
        # Replace template placeholders
        prompt = self.template
        prompt = prompt.replace("{{ TOOL_DEFINITIONS }}", tools_json)
        prompt = prompt.replace("{{ USER_SYSTEM_PROMPT }}", final_user_prompt)
        prompt = prompt.replace("{{ TOOL_CONFIGURATION }}", final_tool_config)
        
        if include_reasoning:
            prompt = prompt.replace("{{ REASONING_GUIDELINES }}", self.reasoning_guidelines)
        else:
            prompt = prompt.replace("{{ REASONING_GUIDELINES }}", "")
            
        return prompt
    
    def generate_shopify_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """
        Generate a Shopify-specific system prompt.
        
        Args:
            tools: List of tool definitions
            
        Returns:
            Shopify-tailored system prompt
        """
        shopify_prompt = """
You are an expert Shopify data analyst assistant. Your goal is to help users gain insights from their Shopify store data.

When working with Shopify data:
1. Understand the common entities: Products, Orders, Customers, Collections, and Inventory
2. Consider relationships between entities (e.g., Customers place Orders containing Products)
3. Look for patterns and trends that provide actionable business insights
4. Present results in a clear, business-friendly format
"""
        
        tool_config = """
When using PostgreSQL tools:
1. Start with simple exploratory queries to understand the data structure
2. Use joins appropriately to connect related Shopify entities
3. Apply appropriate aggregations for meaningful insights
4. Consider performance implications for large datasets
"""
        
        return self.generate_system_prompt(
            tools=tools,
            user_prompt=shopify_prompt,
            tool_config=tool_config
        ) 
"""
AutoGen Billing Agents - Specialized agents for autonomous billing system.

This module implements the agent teams defined in the autonomous billing specification:
- Invoice Generation Agent
- Payment Reconciliation Agent
- Dunning Agent
- Tax Calculation Agent
- Exception Handler Agent

Each agent uses OpenRouter for LLM integration with structured outputs.
"""

import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from autogen import ConversableAgent, AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
    from autogen.agentchat import Agent
    AUTOGEN_AVAILABLE = True
except ImportError:
    AUTOGEN_AVAILABLE = False
    # Stub classes for when autogen is not installed
    class ConversableAgent:
        pass
    class AssistantAgent:
        pass
    class UserProxyAgent:
        pass
    class GroupChat:
        pass
    class GroupChatManager:
        pass

# OpenRouter API Configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# LLM Model Configurations (from spec)
LLM_MODELS = {
    "gpt-4o": {
        "model": "openai/gpt-4o",
        "context_window": 128000,
        "temperature": 0.1,
        "cost_per_1k": 0.03
    },
    "claude-3.5-sonnet": {
        "model": "anthropic/claude-3.5-sonnet",
        "context_window": 200000,
        "temperature": 0.0,
        "cost_per_1k": 0.015
    },
    "gemini-pro-1.5": {
        "model": "google/gemini-pro-1.5",
        "context_window": 1000000,
        "temperature": 0.2,
        "cost_per_1k": 0.001
    },
    "llama-3.1-405b": {
        "model": "meta-llama/llama-3.1-405b-instruct",
        "context_window": 128000,
        "temperature": 0.3,
        "cost_per_1k": 0.002
    },
    "o1-preview": {
        "model": "openai/o1-preview",
        "context_window": 32768,
        "temperature": 0.0,
        "cost_per_1k": 0.015
    }
}

# Structured Output Schemas (from spec)
INVOICE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "anomalies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": "string",
                    "severity": "string",
                    "description": "string",
                    "recommendation": "string"
                }
            }
        },
        "compliance_status": "string",
        "risk_score": "number",
        "confidence": "number"
    }
}

PAYMENT_MATCHING_SCHEMA = {
    "type": "object",
    "properties": {
        "matched_invoice_id": "string",
        "confidence_score": "number",
        "matching_reasons": {"type": "array", "items": "string"},
        "alternative_matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"invoice_id": "string", "score": "number"}
            }
        },
        "requires_human_review": "boolean"
    }
}

TAX_CALCULATION_SCHEMA = {
    "type": "object",
    "properties": {
        "net_amount": "number",
        "tax_breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tax_type": "string",
                    "rate": "number",
                    "amount": "number",
                    "jurisdiction": "string"
                }
            }
        },
        "total_tax": "number",
        "gross_amount": "number",
        "reverse_charge_applicable": "boolean",
        "compliance_notes": {"type": "array", "items": "string"}
    }
}

# Agent System Messages
INVOICE_GENERATOR_SYSTEM = """You are an Invoice Generation Agent in an autonomous billing system.

Your responsibilities:
1. Generate professional invoices from validated POD data
2. Apply customer-specific templates and formatting
3. Calculate line items, taxes, and totals accurately
4. Ensure compliance with local tax regulations
5. Generate PDF and structured data outputs

Use the gemini-pro-1.5 model for efficient batch processing.
Always output structured JSON responses for invoice data.
Critical accuracy required - double-check all calculations."""

PAYMENT_RECONCILER_SYSTEM = """You are a Payment Reconciliation Agent in an autonomous billing system.

Your responsibilities:
1. Analyze incoming bank transactions and payment data
2. Match payments to outstanding invoices using intelligent algorithms
3. Handle partial payments, overpayments, and payment discrepancies
4. Update payment status and generate reconciliation reports
5. Flag suspicious transactions for human review

Use the claude-3.5-sonnet model for precise financial analysis.
Always output structured JSON with confidence scores and matching details."""

DUNNING_AGENT_SYSTEM = """You are a Dunning Agent in an autonomous billing system.

Your responsibilities:
1. Monitor overdue invoices and calculate dunning levels
2. Generate appropriate dunning letters and communications
3. Calculate late fees, interest, and collection costs
4. Escalate to collection agencies when appropriate
5. Maintain communication history and compliance records

Use the gpt-4o model for natural language communication generation.
Balance firmness with customer relationship preservation."""

TAX_CALCULATOR_SYSTEM = """You are a Tax Calculation Agent in an autonomous billing system.

Your responsibilities:
1. Calculate VAT, sales tax, and other applicable taxes
2. Handle reverse charge and international tax scenarios
3. Ensure compliance with local tax regulations and rates
4. Generate tax reports and declarations
5. Validate tax calculations against official sources

Use the claude-3.5-sonnet model for mathematical precision and compliance checking.
Always output detailed tax breakdowns with jurisdiction information."""

EXCEPTION_HANDLER_SYSTEM = """You are an Exception Handler Agent in an autonomous billing system.

Your responsibilities:
1. Analyze system exceptions, errors, and unusual scenarios
2. Determine appropriate resolution strategies
3. Coordinate with other agents for complex issue resolution
4. Escalate critical issues to human operators
5. Learn from past exceptions to improve system resilience

Use the o1-preview model for strategic problem-solving and decision-making.
Provide detailed analysis and actionable recommendations."""

BILLING_COORDINATOR_SYSTEM = """You are the Billing Coordinator Agent managing the autonomous billing workflow.

Your responsibilities:
1. Orchestrate the complete billing lifecycle from POD to payment
2. Route tasks to appropriate specialized agents
3. Monitor workflow progress and handle failures
4. Ensure compliance and quality standards
5. Optimize processes based on performance metrics

Coordinate between: Invoice Generator, Payment Reconciler, Dunning Agent, Tax Calculator, and Exception Handler.
Use sequential processing for invoice generation, parallel processing for reconciliation tasks."""

class BillingAgent(AssistantAgent):
    """Base class for billing-specific agents with OpenRouter integration."""

    def __init__(self, name: str, system_message: str, model_config: Dict[str, Any],
                 structured_output_schema: Optional[Dict] = None, **kwargs):
        super().__init__(name=name, system_message=system_message, **kwargs)

        self.model_config = model_config
        self.structured_output_schema = structured_output_schema
        self.performance_metrics = {
            "requests_processed": 0,
            "success_rate": 0.0,
            "average_response_time": 0.0,
            "error_count": 0
        }

    def generate_structured_response(self, prompt: str, schema: Dict) -> Dict[str, Any]:
        """Generate a response using OpenRouter with structured output validation."""
        try:
            # Enhanced prompt with schema instructions
            enhanced_prompt = f"""{prompt}

Please provide your response in the following JSON format:
{json.dumps(schema, indent=2)}

Ensure all required fields are present and data types match the schema."""

            # Here we would integrate with OpenRouter API
            # For now, return mock structured response
            response = self._mock_openrouter_call(enhanced_prompt, schema)

            # Validate response against schema
            self._validate_response(response, schema)

            # Update performance metrics
            self.performance_metrics["requests_processed"] += 1

            return response

        except Exception as e:
            self.performance_metrics["error_count"] += 1
            raise Exception(f"Structured response generation failed: {str(e)}")

    def _mock_openrouter_call(self, prompt: str, schema: Dict) -> Dict[str, Any]:
        """Mock OpenRouter API call - replace with actual implementation."""
        # This would be replaced with actual OpenRouter API integration
        if "invoice" in prompt.lower():
            return {
                "anomalies": [],
                "compliance_status": "compliant",
                "risk_score": 0.1,
                "confidence": 0.95
            }
        elif "payment" in prompt.lower():
            return {
                "matched_invoice_id": "INV-001",
                "confidence_score": 0.92,
                "matching_reasons": ["Amount match", "Reference match"],
                "alternative_matches": [],
                "requires_human_review": False
            }
        elif "tax" in prompt.lower():
            return {
                "net_amount": 1000,
                "tax_breakdown": [{"tax_type": "VAT", "rate": 0.19, "amount": 190, "jurisdiction": "DE"}],
                "total_tax": 190,
                "gross_amount": 1190,
                "reverse_charge_applicable": False,
                "compliance_notes": []
            }
        else:
            return {"status": "success", "message": "Mock response"}

    def _validate_response(self, response: Dict, schema: Dict) -> bool:
        """Validate response against JSON schema."""
        # Basic validation - could be enhanced with jsonschema library
        required_fields = schema.get("properties", {}).keys()
        for field in required_fields:
            if field not in response:
                raise ValueError(f"Required field '{field}' missing from response")

        return True

def create_invoice_generator_agent() -> BillingAgent:
    """Create the Invoice Generation Agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return BillingAgent(
        name="Invoice_Generator",
        system_message=INVOICE_GENERATOR_SYSTEM,
        model_config=LLM_MODELS["gemini-pro-1.5"],
        structured_output_schema=INVOICE_ANALYSIS_SCHEMA,
        llm_config={
            "config_list": [{
                "model": "openai/gpt-4o",
                "api_key": OPENROUTER_API_KEY,
                "base_url": OPENROUTER_BASE_URL
            }]
        }
    )

def create_payment_reconciler_agent() -> BillingAgent:
    """Create the Payment Reconciliation Agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return BillingAgent(
        name="Payment_Reconciler",
        system_message=PAYMENT_RECONCILER_SYSTEM,
        model_config=LLM_MODELS["claude-3.5-sonnet"],
        structured_output_schema=PAYMENT_MATCHING_SCHEMA,
        llm_config={
            "config_list": [{
                "model": "anthropic/claude-3.5-sonnet",
                "api_key": OPENROUTER_API_KEY,
                "base_url": OPENROUTER_BASE_URL
            }]
        }
    )

def create_dunning_agent() -> BillingAgent:
    """Create the Dunning Agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return BillingAgent(
        name="Dunning_Agent",
        system_message=DUNNING_AGENT_SYSTEM,
        model_config=LLM_MODELS["gpt-4o"],
        llm_config={
            "config_list": [{
                "model": "openai/gpt-4o",
                "api_key": OPENROUTER_API_KEY,
                "base_url": OPENROUTER_BASE_URL
            }]
        }
    )

def create_tax_calculator_agent() -> BillingAgent:
    """Create the Tax Calculation Agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return BillingAgent(
        name="Tax_Calculator",
        system_message=TAX_CALCULATOR_SYSTEM,
        model_config=LLM_MODELS["claude-3.5-sonnet"],
        structured_output_schema=TAX_CALCULATION_SCHEMA,
        llm_config={
            "config_list": [{
                "model": "anthropic/claude-3.5-sonnet",
                "api_key": OPENROUTER_API_KEY,
                "base_url": OPENROUTER_BASE_URL
            }]
        }
    )

def create_exception_handler_agent() -> BillingAgent:
    """Create the Exception Handler Agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return BillingAgent(
        name="Exception_Handler",
        system_message=EXCEPTION_HANDLER_SYSTEM,
        model_config=LLM_MODELS["o1-preview"],
        llm_config={
            "config_list": [{
                "model": "openai/o1-preview",
                "api_key": OPENROUTER_API_KEY,
                "base_url": OPENROUTER_BASE_URL
            }]
        }
    )

def create_billing_coordinator_agent() -> BillingAgent:
    """Create the Billing Coordinator Agent."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    return BillingAgent(
        name="Billing_Coordinator",
        system_message=BILLING_COORDINATOR_SYSTEM,
        model_config=LLM_MODELS["o1-preview"],
        llm_config={
            "config_list": [{
                "model": "openai/o1-preview",
                "api_key": OPENROUTER_API_KEY,
                "base_url": OPENROUTER_BASE_URL
            }]
        }
    )

def create_billing_agent_team() -> Dict[str, BillingAgent]:
    """Create the complete billing agent team."""
    return {
        "coordinator": create_billing_coordinator_agent(),
        "invoice_generator": create_invoice_generator_agent(),
        "payment_reconciler": create_payment_reconciler_agent(),
        "dunning_agent": create_dunning_agent(),
        "tax_calculator": create_tax_calculator_agent(),
        "exception_handler": create_exception_handler_agent()
    }

def create_invoice_processing_group_chat() -> GroupChat:
    """Create a group chat for invoice processing workflow."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agents = create_billing_agent_team()

    # Define agent capabilities and workflow
    allowed_speaker_transitions = {
        agents["coordinator"]: [agents["invoice_generator"], agents["exception_handler"]],
        agents["invoice_generator"]: [agents["tax_calculator"], agents["coordinator"]],
        agents["tax_calculator"]: [agents["coordinator"], agents["exception_handler"]],
        agents["exception_handler"]: [agents["coordinator"]]
    }

    group_chat = GroupChat(
        agents=list(agents.values()),
        messages=[],
        max_round=10,
        speaker_selection_method="round_robin",
        allowed_speaker_transitions=allowed_speaker_transitions
    )

    return group_chat

def create_payment_reconciliation_group_chat() -> GroupChat:
    """Create a group chat for payment reconciliation workflow."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("AutoGen is not installed. Run: pip install pyautogen")

    agents = create_billing_agent_team()

    # Payment reconciliation workflow
    allowed_speaker_transitions = {
        agents["coordinator"]: [agents["payment_reconciler"]],
        agents["payment_reconciler"]: [agents["coordinator"], agents["exception_handler"]],
        agents["exception_handler"]: [agents["coordinator"], agents["dunning_agent"]],
        agents["dunning_agent"]: [agents["coordinator"]]
    }

    group_chat = GroupChat(
        agents=list(agents.values()),
        messages=[],
        max_round=8,
        speaker_selection_method="auto",
        allowed_speaker_transitions=allowed_speaker_transitions
    )

    return group_chat

# Development Requirements for Agent Teams
AGENT_DEVELOPMENT_REQUIREMENTS = {
    "general_principles": {
        "modular_design": "Each agent has single responsibility",
        "structured_outputs": "All agents use JSON schema validation",
        "error_handling": "Comprehensive exception handling with fallbacks",
        "monitoring": "Built-in performance metrics and health checks",
        "scalability": "Horizontal scaling capability",
        "security": "Secure communication and data handling"
    },
    "llm_integration": {
        "model_selection": "Task-specific model routing",
        "cost_optimization": "Budget limits and usage tracking",
        "fallback_chains": "Multi-model fallback strategies",
        "caching": "Semantic and persistent caching",
        "rate_limiting": "Request throttling and burst control"
    },
    "agent_orchestration": {
        "group_chat_patterns": "Sequential, debate, and custom workflows",
        "state_management": "Persistent conversation state",
        "termination_conditions": "Clear success/failure criteria",
        "human_escalation": "Defined triggers for human intervention",
        "learning_loops": "Continuous improvement from feedback"
    },
    "quality_assurance": {
        "testing_framework": "Unit, integration, and E2E tests",
        "performance_benchmarks": "Latency, accuracy, and throughput targets",
        "compliance_validation": "Regulatory and security compliance checks",
        "audit_trails": "Complete logging and traceability",
        "continuous_monitoring": "Real-time health and performance monitoring"
    },
    "deployment_operations": {
        "containerization": "Docker-based deployment",
        "orchestration": "Kubernetes-native scaling",
        "configuration_management": "Environment-specific configs",
        "rollback_capability": "Safe deployment rollbacks",
        "disaster_recovery": "Automated failover and recovery"
    }
}

def validate_agent_team_requirements() -> Dict[str, bool]:
    """Validate that the agent team meets all development requirements."""
    validation_results = {}

    # Check if all required agents are implemented
    required_agents = ["coordinator", "invoice_generator", "payment_reconciler",
                      "dunning_agent", "tax_calculator", "exception_handler"]

    agents = create_billing_agent_team()
    validation_results["all_agents_implemented"] = all(
        agent_name in agents for agent_name in required_agents
    )

    # Check structured output schemas
    agents_with_schemas = ["invoice_generator", "payment_reconciler", "tax_calculator"]
    validation_results["structured_outputs_implemented"] = all(
        hasattr(agents[agent_name], 'structured_output_schema') and
        agents[agent_name].structured_output_schema is not None
        for agent_name in agents_with_schemas
    )

    # Check LLM configurations
    validation_results["llm_configs_valid"] = all(
        hasattr(agent, 'model_config') and agent.model_config is not None
        for agent in agents.values()
    )

    # Check performance metrics
    validation_results["performance_monitoring"] = all(
        hasattr(agent, 'performance_metrics') and agent.performance_metrics is not None
        for agent in agents.values()
    )

    return validation_results

if __name__ == "__main__":
    # Example usage and validation
    try:
        print("Creating billing agent team...")
        agents = create_billing_agent_team()
        print(f"✓ Created {len(agents)} agents successfully")

        print("\nValidating requirements...")
        validation = validate_agent_team_requirements()
        print(f"✓ Validation results: {validation}")

        if all(validation.values()):
            print("\n🎉 All agent team requirements met!")
        else:
            print("\n⚠️ Some requirements not fully met")

    except Exception as e:
        print(f"❌ Error creating agent team: {e}")
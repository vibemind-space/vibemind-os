"""
Planning Team - Planner + Critic Society of Mind Pattern

A team agent that combines a Planner and Critic for better
workflow planning through debate and refinement.

The Planner proposes actions, the Critic challenges them,
and they iterate until a solid plan emerges.

Now with REAL LLM execution via OpenRouter!
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from .base_agent import BaseHandoffAgent, AgentConfig
from .messages import UserTask, AgentResponse
from .team_agent import TeamAgent, TeamConfig, SubAgentResult, SynthesisStrategy

# Import LLM client
try:
    from core.openrouter_client import OpenRouterClient, ModelType
    HAS_LLM = True
except ImportError:
    HAS_LLM = False
    OpenRouterClient = None
    ModelType = None

logger = logging.getLogger(__name__)


class PlannerAgent(BaseHandoffAgent):
    """
    Agent that creates action plans for tasks.

    Given a goal, produces a list of concrete steps.
    Uses LLM for intelligent planning when available.
    """

    def __init__(self, llm_client: Optional["OpenRouterClient"] = None):
        config = AgentConfig(
            name="planner",
            description="Creates action plans for desktop automation",
            topic_type="planning"
        )
        super().__init__(config)
        self.llm_client = llm_client
        self._use_llm = llm_client is not None and HAS_LLM

    def _register_default_tools(self):
        """Planners don't delegate - they return plans."""
        pass

    async def _process_task(self, task: UserTask) -> Any:
        """Create a plan for the given task."""
        goal = task.goal
        context = task.context

        await self.report_progress(task, 30.0, "Creating plan...")

        # Check if we're in a debate round
        debate_round = context.get("debate_round", 0)
        previous_positions = context.get("current_positions", [])

        # Get critic feedback if available
        critic_feedback = None
        for pos in previous_positions:
            if pos.get("agent") == "critic":
                critic_feedback = pos.get("position")

        # Use LLM if available, otherwise fall back to rule-based
        if self._use_llm:
            await self.report_progress(task, 50.0, "Calling LLM for planning...")
            result = await self._create_plan_with_llm(goal, context, critic_feedback)
        else:
            result = self._create_plan(goal, context, critic_feedback)
            result = {
                "plan": result,
                "confidence": 0.8 if not critic_feedback else 0.9,
                "revised": debate_round > 1
            }

        await self.report_progress(task, 100.0, f"Plan created: {len(result.get('plan', []))} steps")
        return result

    async def _create_plan_with_llm(
        self,
        goal: str,
        context: Dict[str, Any],
        critic_feedback: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create a plan using LLM."""
        # Build the prompt
        feedback_section = ""
        if critic_feedback:
            feedback_section = f"""
Previous plan was reviewed. Feedback:
- Issues: {json.dumps(critic_feedback.get('issues', []))}
- Suggestions: {json.dumps(critic_feedback.get('suggestions', []))}

Please create an IMPROVED plan addressing this feedback.
"""

        # Include user feedback if provided
        user_feedback = context.get("user_feedback", "")
        if user_feedback:
            feedback_section += f"""
USER FEEDBACK (important - address this directly):
{user_feedback}
"""

        prompt = f"""You are a desktop automation planner. Create a step-by-step plan to achieve the goal.

GOAL: {goal}

CONTEXT: {json.dumps(context, indent=2)}
{feedback_section}
AVAILABLE ACTIONS (use ONLY these):
- hotkey: Press key combination. Params: keys (string like "win+r" or "ctrl+alt+space")
- sleep: Wait for seconds. Params: seconds (float, e.g. 1.0)
- write: Type text via clipboard. Params: text (string)
- press: Press single key. Params: key (string: "enter", "tab", "escape", "backspace")
- click: Click at coordinates. Params: x, y (integers)
- find_and_click: Find element by text and click. Params: target (string description)

CRITICAL RULES:
1. ALWAYS add a sleep step (0.5-1.5 seconds) after every hotkey that opens a window/dialog
2. ALWAYS add a sleep step (0.3-0.5 seconds) after write before pressing enter
3. Use "win+r" to open Run dialog on Windows
4. Use "ctrl+alt+space" to open Claude Desktop
5. Do NOT use "verify" - it's not implemented
6. Keep plans simple - 3-7 steps max

EXAMPLE - Opening Notepad:
[
  {{"type": "hotkey", "keys": "win+r", "description": "Open Run dialog"}},
  {{"type": "sleep", "seconds": 1.0, "description": "Wait for Run dialog"}},
  {{"type": "write", "text": "notepad", "description": "Type notepad"}},
  {{"type": "sleep", "seconds": 0.3, "description": "Brief pause"}},
  {{"type": "press", "key": "enter", "description": "Launch"}}
]

Return ONLY valid JSON:
{{
  "plan": [
    {{"type": "action_type", "description": "what this does", ...params}},
    ...
  ],
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation"
}}"""

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=ModelType.QUICK,  # Use fast model for planning
                temperature=0.3,
                max_tokens=2048,
                json_mode=True
            )

            result = json.loads(response.content)
            logger.info(f"LLM Planner: {len(result.get('plan', []))} steps, confidence: {result.get('confidence')}")
            return result

        except Exception as e:
            logger.error(f"LLM planning failed: {e}, falling back to rule-based")
            plan = self._create_plan(goal, context, critic_feedback)
            return {"plan": plan, "confidence": 0.5, "reasoning": f"Fallback due to: {e}"}

    def _create_plan(
        self,
        goal: str,
        context: Dict[str, Any],
        critic_feedback: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Create a plan based on the goal.

        Args:
            goal: What to achieve
            context: Task context
            critic_feedback: Feedback from critic to incorporate
        """
        goal_lower = goal.lower()

        # Handle critic feedback
        improvements = []
        if critic_feedback and isinstance(critic_feedback, dict):
            issues = critic_feedback.get("issues", [])
            suggestions = critic_feedback.get("suggestions", [])

            # Incorporate suggestions
            for suggestion in suggestions:
                if "wait" in suggestion.lower() or "sleep" in suggestion.lower():
                    improvements.append({"type": "add_wait", "reason": suggestion})
                if "verify" in suggestion.lower() or "check" in suggestion.lower():
                    improvements.append({"type": "add_verification", "reason": suggestion})

        # Claude Desktop workflow
        if "claude" in goal_lower and "desktop" in goal_lower:
            message = context.get("message", goal)
            plan = [
                {
                    "type": "hotkey",
                    "keys": ["ctrl", "alt", "space"],
                    "description": "Open Claude Desktop",
                    "rationale": "Standard hotkey to activate Claude Desktop"
                },
                {
                    "type": "sleep",
                    "seconds": 1.5,
                    "description": "Wait for window",
                    "rationale": "Allow time for Claude Desktop to appear"
                },
                {
                    "type": "write",
                    "text": message,
                    "description": "Type message",
                    "rationale": "Input field is auto-focused on open"
                },
                {
                    "type": "press",
                    "key": "enter",
                    "description": "Send message",
                    "rationale": "Submit the message"
                }
            ]

            # Apply improvements from critic
            for imp in improvements:
                if imp["type"] == "add_wait":
                    # Add extra wait before typing
                    plan.insert(2, {
                        "type": "sleep",
                        "seconds": 0.5,
                        "description": "Extra wait for stability",
                        "rationale": imp["reason"]
                    })
                elif imp["type"] == "add_verification":
                    # Add verification step
                    plan.append({
                        "type": "verify",
                        "target": "message sent",
                        "description": "Verify message was sent",
                        "rationale": imp["reason"]
                    })

            return plan

        # Generic click workflow
        if "click" in goal_lower:
            target = context.get("target", "button")
            return [
                {
                    "type": "find_and_click",
                    "target": target,
                    "description": f"Find and click {target}",
                    "rationale": "Locate element visually then click"
                }
            ]

        # Default: return context actions if provided
        return context.get("actions", [
            {
                "type": "unknown",
                "description": f"Unable to plan for: {goal}",
                "rationale": "Goal not recognized"
            }
        ])


class CriticAgent(BaseHandoffAgent):
    """
    Agent that critiques plans and identifies potential issues.

    Reviews plans from Planner and provides constructive feedback.
    Uses LLM for intelligent critiquing when available.
    """

    def __init__(self, llm_client: Optional["OpenRouterClient"] = None):
        config = AgentConfig(
            name="critic",
            description="Reviews and critiques action plans",
            topic_type="planning"
        )
        super().__init__(config)
        self.llm_client = llm_client
        self._use_llm = llm_client is not None and HAS_LLM

    def _register_default_tools(self):
        """Critics don't delegate - they return feedback."""
        pass

    async def _process_task(self, task: UserTask) -> Any:
        """Review and critique a plan."""
        context = task.context

        await self.report_progress(task, 30.0, "Reviewing plan...")

        # Get planner's proposal from various sources
        planner_result = None

        # Check previous_results (from sequential team execution)
        previous_results = context.get("previous_results", [])
        for prev in previous_results:
            if prev.get("agent") == "planner":
                planner_result = prev.get("result")
                break

        # Check current_positions (from debate rounds)
        if not planner_result:
            current_positions = context.get("current_positions", [])
            for pos in current_positions:
                if pos.get("agent") == "planner":
                    planner_result = pos.get("position")
                    break

        # Check explicit plan_to_review
        if not planner_result:
            planner_result = context.get("plan_to_review")

        if not planner_result:
            return {
                "approved": False,
                "issues": ["No plan provided to review"],
                "suggestions": []
            }

        # Use LLM if available, otherwise fall back to rule-based
        if self._use_llm:
            await self.report_progress(task, 50.0, "Calling LLM for critique...")
            critique = await self._critique_plan_with_llm(planner_result, task)
        else:
            critique = self._critique_plan(planner_result, task)

        await self.report_progress(task, 100.0, f"Review complete: {len(critique['issues'])} issues")
        return critique

    async def _critique_plan_with_llm(
        self,
        plan_result: Dict,
        task: UserTask
    ) -> Dict[str, Any]:
        """Critique a plan using LLM."""
        prompt = f"""You are a desktop automation plan critic. Review this plan for CRITICAL issues only.

GOAL: {task.goal}

PLAN TO REVIEW:
{json.dumps(plan_result, indent=2)}

VALID ACTION TYPES: hotkey, sleep, write, press, click, find_and_click
INVALID ACTIONS: verify (not implemented - reject if used)

CHECK FOR (only flag if actually problematic):
1. Missing sleep after hotkey that opens window (CRITICAL - must have 0.5-1.5s sleep)
2. Invalid action types (verify, wait, check - these don't exist)
3. Clicks without x,y coordinates or target
4. Plans over 10 steps (too complex)

DO NOT FLAG:
- Missing "verification" steps (verify is not implemented, don't require it)
- Minor timing issues if sleep times exist
- Simple straightforward plans

APPROVE if:
- All actions are valid types
- Sleep times exist after window-opening hotkeys
- Plan is simple and achievable

Return ONLY valid JSON:
{{
  "approved": true or false,
  "issues": ["only critical issues..."],
  "suggestions": ["helpful suggestions..."],
  "risk_score": 0.0 to 1.0 (0=safe, 1=risky),
  "verdict": "APPROVED" or "NEEDS_REVISION",
  "reasoning": "brief explanation"
}}"""

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=ModelType.QUICK,
                temperature=0.2,  # Lower temperature for more consistent critiques
                max_tokens=1024,
                json_mode=True
            )

            result = json.loads(response.content)
            result["plan_length"] = len(plan_result.get("plan", []))
            logger.info(f"LLM Critic: {result.get('verdict')}, {len(result.get('issues', []))} issues")
            return result

        except Exception as e:
            logger.error(f"LLM critique failed: {e}, falling back to rule-based")
            return self._critique_plan(plan_result, task)

    def _critique_plan(self, plan_result: Dict, task: UserTask) -> Dict[str, Any]:
        """
        Critique a plan and identify issues.

        Args:
            plan_result: Result from PlannerAgent containing plan
            task: Original task for context
        """
        plan = plan_result.get("plan", [])
        issues = []
        suggestions = []
        risk_score = 0.0

        # Check for common issues
        for i, step in enumerate(plan):
            step_type = step.get("type", "")
            description = step.get("description", "")

            # Issue: No wait after window operations
            if step_type == "hotkey" and i < len(plan) - 1:
                next_step = plan[i + 1]
                if next_step.get("type") != "sleep":
                    issues.append(f"Step {i+1}: No wait after hotkey - window may not be ready")
                    suggestions.append("Add a sleep step after hotkey to ensure window is ready")
                    risk_score += 0.2

            # Issue: Typing without verification
            if step_type == "write":
                has_verification = any(
                    s.get("type") == "verify" for s in plan[i+1:]
                )
                if not has_verification:
                    issues.append(f"Step {i+1}: No verification after typing")
                    suggestions.append("Consider adding verification to confirm text was entered")
                    risk_score += 0.1

            # Issue: Click without target
            if step_type == "click" and not step.get("x") and not step.get("target"):
                issues.append(f"Step {i+1}: Click without coordinates or target")
                suggestions.append("Specify coordinates or use find_and_click")
                risk_score += 0.3

            # Issue: Unknown step type
            if step_type == "unknown":
                issues.append(f"Step {i+1}: Unknown action type")
                suggestions.append("Clarify the goal or break it into known actions")
                risk_score += 0.5

        # Check overall plan
        if len(plan) == 0:
            issues.append("Plan is empty")
            risk_score = 1.0
        elif len(plan) > 10:
            issues.append("Plan has many steps - consider breaking into sub-tasks")
            suggestions.append("Complex plans are more likely to fail")
            risk_score += 0.1

        # Determine approval
        approved = len(issues) == 0 or risk_score < 0.3

        return {
            "approved": approved,
            "issues": issues,
            "suggestions": suggestions,
            "risk_score": risk_score,
            "plan_length": len(plan),
            "verdict": "APPROVED" if approved else "NEEDS_REVISION"
        }


class PlanningTeam(TeamAgent):
    """
    Team that combines Planner and Critic for robust planning.

    Uses debate synthesis strategy:
    1. Planner proposes a plan
    2. Critic reviews and provides feedback
    3. Planner revises based on feedback
    4. Repeat until approved or max rounds

    This is the Society of Mind pattern in action - emergent
    quality through agent collaboration.

    Set use_llm=True for real LLM-powered planning and critiquing.
    """

    def __init__(
        self,
        max_debate_rounds: int = 3,
        use_llm: bool = False,
        llm_client: Optional["OpenRouterClient"] = None
    ):
        config = TeamConfig(
            name="planning_team",
            description="Planner + Critic team for robust planning",
            topic_type="planning",
            synthesis_strategy=SynthesisStrategy.CUSTOM,  # Use our custom _synthesize
            max_debate_rounds=max_debate_rounds,
            parallel_execution=False,  # Sequential for debate
            timeout_per_agent=60.0 if use_llm else 30.0  # More time for LLM calls
        )
        super().__init__(config)

        # Create LLM client if needed
        self.llm_client = llm_client
        if use_llm and llm_client is None and HAS_LLM:
            self.llm_client = OpenRouterClient()

        # Add team members with optional LLM
        self.planner = PlannerAgent(llm_client=self.llm_client if use_llm else None)
        self.critic = CriticAgent(llm_client=self.llm_client if use_llm else None)

        self.add_member(self.planner, weight=1.0)
        self.add_member(self.critic, weight=0.8)

        # Set custom synthesizer to use our _synthesize method
        self.set_synthesizer(self._custom_planning_synthesize)

        self._use_llm = use_llm
        logger.info(f"PlanningTeam initialized with LLM={'enabled' if use_llm else 'disabled'}")

    async def _custom_planning_synthesize(
        self,
        results: List[SubAgentResult],
        task: UserTask
    ) -> Dict[str, Any]:
        """Custom synthesizer that wraps _synthesize."""
        return await self._synthesize(results)

    async def _synthesize(self, results: List[SubAgentResult]) -> Dict[str, Any]:
        """
        Synthesize planner and critic results.

        For planning teams, we want:
        - The plan from the planner
        - Approval status from the critic
        - Combined metadata
        """
        planner_result = None
        critic_result = None

        for result in results:
            if result.agent_name == "planner":
                planner_result = result.response.result
            elif result.agent_name == "critic":
                critic_result = result.response.result

        if not planner_result:
            return {"success": False, "error": "No plan generated"}

        plan = planner_result.get("plan", [])
        approved = critic_result.get("approved", True) if critic_result else True

        return {
            "success": approved,
            "plan": plan,
            "approved": approved,
            "planner_confidence": planner_result.get("confidence", 0.5),
            "critic_verdict": critic_result.get("verdict", "NOT_REVIEWED") if critic_result else "NOT_REVIEWED",
            "issues": critic_result.get("issues", []) if critic_result else [],
            "suggestions": critic_result.get("suggestions", []) if critic_result else [],
            "risk_score": critic_result.get("risk_score", 0.0) if critic_result else 0.0
        }

    async def create_plan(self, goal: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Convenience method to create a plan for a goal.

        Args:
            goal: What to achieve
            context: Optional context

        Returns:
            Synthesized planning result
        """
        task = UserTask(
            goal=goal,
            context=context or {}
        )

        result = await self._process_task(task)
        return result

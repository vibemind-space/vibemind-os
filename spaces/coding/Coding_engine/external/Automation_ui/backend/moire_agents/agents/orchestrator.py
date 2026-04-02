"""
Orchestrator Agent - Hauptkoordinator des Agent-Teams

Verantwortlich für:
- Koordination zwischen allen spezialisierten Agents
- Integration mit Claude CLI für komplexe Aufgaben
- Task-Planung und Ausführungssteuerung
- Claude Skills Orchestrierung
"""

import asyncio
import subprocess
import json
import os
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
except ImportError:
    # autogen-agentchat v0.7+ uses a different API; stub for now
    AssistantAgent = UserProxyAgent = GroupChat = GroupChatManager = None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status eines Tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class Task:
    """Ein Task der ausgeführt werden soll."""
    id: str
    goal: str
    status: TaskStatus
    steps: List[Dict[str, Any]]
    current_step: int
    context: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None


class ClaudeCLIWrapper:
    """
    Wrapper für Claude CLI (anthropic/claude-cli).
    
    Ermöglicht:
    - Ausführung von Claude CLI Befehlen
    - Nutzung von Claude Skills
    - Streaming von Responses
    """
    
    def __init__(self, skills_dir: Optional[str] = None):
        self.skills_dir = skills_dir or self._find_skills_dir()
        self.claude_path = self._find_claude_cli()
        
        if not self.claude_path:
            logger.warning("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-cli")
    
    def _find_claude_cli(self) -> Optional[str]:
        """Findet den Claude CLI Pfad."""
        # Versuche verschiedene Pfade
        possible_paths = [
            "claude",  # Im PATH
            "claude.cmd",  # Windows in PATH
            str(Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"),  # Windows npm global
            str(Path.home() / "AppData" / "Roaming" / "npm" / "claude"),  # Windows npm (no ext)
            str(Path.home() / ".local" / "bin" / "claude"),  # Linux/Mac
            "/usr/local/bin/claude",  # Mac homebrew
            "npx claude",  # Via npx (fallback)
        ]

        for path in possible_paths:
            try:
                # Check if file exists first for absolute paths
                if os.path.isabs(path) and not os.path.exists(path):
                    continue

                result = subprocess.run(
                    [path, "--version"] if not path.startswith("npx") else path.split() + ["--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    shell=(os.name == 'nt')  # Use shell on Windows
                )
                if result.returncode == 0:
                    logger.info(f"Found Claude CLI at: {path}")
                    return path
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue

        return None
    
    def _find_skills_dir(self) -> str:
        """Findet das Skills-Verzeichnis."""
        # Suche in verschiedenen Orten
        possible_dirs = [
            Path.cwd() / ".claude" / "skills",
            Path.cwd().parent / ".claude" / "skills",
            Path.home() / ".claude" / "skills",
        ]
        
        for dir_path in possible_dirs:
            if dir_path.exists():
                return str(dir_path)
        
        # Default: Erstelle im aktuellen Projekt
        default_dir = Path.cwd().parent / ".claude" / "skills"
        default_dir.mkdir(parents=True, exist_ok=True)
        return str(default_dir)
    
    def is_available(self) -> bool:
        """Prüft ob Claudia CLI verfügbar ist."""
        return self.claude_path is not None
    
    async def run_command(
        self,
        prompt: str,
        skill: Optional[str] = None,
        context_file: Optional[str] = None,
        output_format: str = "text"
    ) -> Dict[str, Any]:
        """
        Führt einen Claude CLI Befehl aus.
        
        Args:
            prompt: Der Prompt/die Anweisung
            skill: Optionaler Skill-Name
            context_file: Optionale Kontext-Datei (JSON)
            output_format: Format der Ausgabe (text/json)
        
        Returns:
            Dict mit 'success', 'output', 'error'
        """
        if not self.is_available():
            return {
                'success': False,
                'output': None,
                'error': 'Claude CLI not available'
            }
        
        try:
            # Build command for Claude Code CLI
            cmd = self.claude_path.split() if "npx" in self.claude_path else [self.claude_path]

            # -p for non-interactive (print) mode - REQUIRED
            cmd.append("-p")

            # Output format
            if output_format == "json":
                cmd.extend(["--output-format", "json"])

            # System prompt with skill content if provided
            if skill:
                skill_path = Path(self.skills_dir) / f"{skill}.md"
                if skill_path.exists():
                    skill_content = skill_path.read_text(encoding='utf-8')
                    cmd.extend(["--system-prompt", skill_content])

            # Context file as append to system prompt
            if context_file and Path(context_file).exists():
                context_content = Path(context_file).read_text(encoding='utf-8')
                cmd.extend(["--append-system-prompt", f"Context: {context_content}"])

            # Prompt as positional argument (must be last)
            cmd.append(prompt)

            logger.info(f"Running Claude CLI: {cmd[0]} -p ...")

            # Execute - use shell on Windows for .cmd files
            if os.name == 'nt':
                # On Windows, join command and use shell
                import shlex
                cmd_str = ' '.join(f'"{c}"' if ' ' in c else c for c in cmd)
                process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

            # Add timeout to prevent hanging
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            except asyncio.TimeoutError:
                process.kill()
                return {
                    'success': False,
                    'output': None,
                    'error': 'Claude CLI timed out after 60 seconds'
                }

            if process.returncode == 0:
                output = stdout.decode('utf-8').strip()
                if output_format == "json":
                    try:
                        output = json.loads(output)
                    except json.JSONDecodeError:
                        pass
                
                return {
                    'success': True,
                    'output': output,
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'output': None,
                    'error': stderr.decode('utf-8').strip()
                }
        
        except Exception as e:
            logger.error(f"Claude CLI error: {e}")
            return {
                'success': False,
                'output': None,
                'error': str(e)
            }
    
    async def run_skill(
        self,
        skill_name: str,
        inputs: Dict[str, Any],
        ui_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Führt einen Claude Skill aus.
        
        Args:
            skill_name: Name des Skills (ohne .md)
            inputs: Input-Parameter für den Skill
            ui_context: Optionaler UI-Kontext von MoireTracker
        
        Returns:
            Skill-Ergebnis
        """
        # Erstelle temporäre Kontext-Datei
        context = {
            'skill_inputs': inputs,
            'ui_context': ui_context
        }
        
        context_file = Path(self.skills_dir).parent / "temp_context.json"
        with open(context_file, 'w') as f:
            json.dump(context, f, indent=2)
        
        # Baue Prompt
        prompt = f"Execute skill '{skill_name}' with the provided inputs and UI context."
        
        result = await self.run_command(
            prompt=prompt,
            skill=skill_name,
            context_file=str(context_file),
            output_format="json"
        )
        
        # Cleanup
        if context_file.exists():
            context_file.unlink()
        
        return result
    
    def list_skills(self) -> List[str]:
        """Listet verfügbare Skills auf."""
        skills = []
        skills_path = Path(self.skills_dir)
        
        if skills_path.exists():
            for skill_file in skills_path.glob("*.md"):
                skills.append(skill_file.stem)
        
        return skills


class OrchestratorAgent:
    """
    Orchestrator Agent - Koordiniert das gesamte Agent-Team.
    
    Aufgaben:
    - Task-Zerlegung und Planung
    - Delegation an spezialisierte Agents
    - Claude CLI/Skills Integration
    - Überwachung des Fortschritts
    """
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        skills_dir: Optional[str] = None
    ):
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        self.openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
        self.anthropic_api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')
        
        # Claude CLI Wrapper
        self.claude_cli = ClaudeCLIWrapper(skills_dir=skills_dir)
        
        # Active tasks
        self.tasks: Dict[str, Task] = {}
        self.task_counter = 0
        
        # Registered agents
        self.agents: Dict[str, Any] = {}
        
        # LLM Config für AutoGen - OpenRouter Support
        if self.openrouter_api_key:
            self.llm_config = {
                "model": "anthropic/claude-3.5-sonnet",  # OpenRouter Model
                "api_key": self.openrouter_api_key,
                "base_url": "https://openrouter.ai/api/v1",
                "temperature": 0.3
            }
            logger.info("Using OpenRouter API for LLM")
        elif self.openai_api_key:
            self.llm_config = {
                "model": "gpt-4o-mini",
                "api_key": self.openai_api_key,
                "temperature": 0.3
            }
            logger.info("Using OpenAI API for LLM")
        else:
            # Kein API Key - nutze nur Claude CLI
            self.llm_config = False
            logger.info("No OpenAI/OpenRouter API key - using Claude CLI only")
        
        # AutoGen Assistant für Orchestrierung (nur wenn LLM Config vorhanden)
        if self.llm_config:
            self.assistant = AssistantAgent(
                name="Orchestrator",
                system_message=self._get_system_message(),
                llm_config=self.llm_config
            )
        else:
            self.assistant = None
        
        # Event handlers
        self._on_task_started: List[Callable] = []
        self._on_task_completed: List[Callable] = []
        self._on_step_completed: List[Callable] = []
    
    def _get_system_message(self) -> str:
        """System-Message für den Orchestrator."""
        skills = self.claude_cli.list_skills()
        skills_list = ", ".join(skills) if skills else "keine"
        
        return """Du bist der Orchestrator eines Agent-Teams für Desktop-Automation.

Deine Aufgaben:
1. Analysiere Benutzeranfragen und zerlege sie in ausführbare Schritte
2. Delegiere Aufgaben an spezialisierte Agents:
   - DataAnalyst: Analysiert OCR-Daten und UI-Kontext
   - Monitor: Überwacht Screen-Änderungen
   - ClaudeSkills: Nutzt Claude CLI für App-Erstellung
   - Interaction: Führt Klicks und Eingaben aus

3. Nutze Claude Skills für komplexe Aufgaben
   Verfügbare Skills: {skills_list}

4. Überwache den Fortschritt und reagiere auf Fehler

Bei jeder Anfrage:
1. Verstehe das Ziel
2. Prüfe den aktuellen UI-Kontext
3. Erstelle einen Aktionsplan
4. Delegiere an passende Agents
5. Verifiziere das Ergebnis

Antworte strukturiert mit:
- ANALYSE: Was ist das Ziel?
- PLAN: Welche Schritte sind nötig?
- DELEGATION: Welcher Agent macht was?
- STATUS: Aktueller Fortschritt
"""
    
    def register_agent(self, name: str, agent: Any):
        """Registriert einen spezialisierten Agent."""
        self.agents[name] = agent
        logger.info(f"Registered agent: {name}")
    
    def on_task_started(self, handler: Callable):
        """Event-Handler für Task-Start."""
        self._on_task_started.append(handler)
    
    def on_task_completed(self, handler: Callable):
        """Event-Handler für Task-Abschluss."""
        self._on_task_completed.append(handler)
    
    def on_step_completed(self, handler: Callable):
        """Event-Handler für Schritt-Abschluss."""
        self._on_step_completed.append(handler)
    
    async def create_task(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Task:
        """
        Erstellt einen neuen Task.
        
        Args:
            goal: Beschreibung des Ziels
            context: Optionaler Kontext (z.B. UI-Context)
        
        Returns:
            Task-Objekt
        """
        self.task_counter += 1
        task_id = f"task_{self.task_counter}"
        
        task = Task(
            id=task_id,
            goal=goal,
            status=TaskStatus.PENDING,
            steps=[],
            current_step=0,
            context=context or {}
        )
        
        self.tasks[task_id] = task
        
        # Plane Schritte
        task.steps = await self._plan_steps(goal, context)
        
        logger.info(f"Created task {task_id}: {goal} ({len(task.steps)} steps)")
        
        return task
    
    async def _plan_steps(
        self,
        goal: str,
        context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Plant die Schritte für ein Ziel."""
        # Nutze Claude CLI wenn verfügbar
        if self.claude_cli.is_available():
            prompt = f"""Zerlege folgendes Ziel in ausführbare Schritte für Desktop-Automation:

Ziel: {goal}

Kontext: {json.dumps(context or {{}}, indent=2)}

Antworte als JSON-Array:
[
  {{"action": "find_element", "target": "...", "description": "..."}}",
  {{"action": "click", "target": "...", "description": "..."}}",
  ...
]

Verfügbare Aktionen: find_element, click, type, scroll, wait, verify, capture, run_skill
"""
            result = await self.claude_cli.run_command(
                prompt=prompt,
                output_format="json"
            )
            
            if result['success'] and isinstance(result['output'], list):
                return result['output']
        
        # Fallback: Einfache regelbasierte Planung
        return self._plan_steps_fallback(goal)
    
    def _plan_steps_fallback(self, goal: str) -> List[Dict[str, Any]]:
        """Fallback-Planung ohne LLM."""
        goal_lower = goal.lower()
        steps = []
        
        # Screenshot als erstes
        steps.append({
            "action": "capture",
            "description": "Aktuellen Bildschirm erfassen"
        })
        
        if "öffne" in goal_lower or "open" in goal_lower:
            steps.append({
                "action": "find_element",
                "target": goal.replace("öffne", "").replace("open", "").strip(),
                "description": "Element zum Öffnen finden"
            })
            steps.append({
                "action": "click",
                "description": "Auf gefundenes Element klicken"
            })
        
        elif "starte" in goal_lower or "start" in goal_lower or "launch" in goal_lower:
            # Extract app name from goal
            app_name = goal_lower
            for word in ["starte", "start", "launch", "die app", "das programm", "the app"]:
                app_name = app_name.replace(word, "")
            app_name = app_name.strip()
            
            # Wenn kein App-Name gefunden, versuche aus Original-Goal
            if not app_name:
                app_name = goal.replace("Starte", "").replace("starte", "").strip()
            
            steps.append({
                "action": "press_key",
                "key": "win",
                "description": "Windows-Taste drücken (Startmenü öffnen)"
            })
            steps.append({
                "action": "wait",
                "duration": 0.7,
                "description": "Warten bis Startmenü offen ist"
            })
            steps.append({
                "action": "type",
                "text": app_name,
                "description": f"App-Namen eingeben: {app_name}"
            })
            steps.append({
                "action": "wait",
                "duration": 0.5,
                "description": "Warten auf Suchergebnisse"
            })
            steps.append({
                "action": "press_key",
                "key": "enter",
                "description": "Enter drücken um App zu starten"
            })
        
        elif "klick" in goal_lower or "click" in goal_lower:
            steps.append({
                "action": "find_element",
                "target": goal.replace("klick", "").replace("click", "").strip(),
                "description": "Klick-Ziel finden"
            })
            steps.append({
                "action": "click",
                "description": "Klick ausführen"
            })
        
        elif "schreib" in goal_lower or "type" in goal_lower:
            steps.append({
                "action": "type",
                "text": goal.split(":")[-1].strip() if ":" in goal else "",
                "description": "Text eingeben"
            })
        
        elif "erstelle" in goal_lower or "create" in goal_lower:
            steps.append({
                "action": "run_skill",
                "skill": "create_react_app",
                "description": "App mit Claude Skill erstellen"
            })
        
        else:
            steps.append({
                "action": "verify",
                "description": "Zustand analysieren"
            })
        
        return steps
    
    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """
        Führt einen Task aus.
        
        Args:
            task_id: ID des Tasks
        
        Returns:
            Ergebnis der Ausführung
        """
        task = self.tasks.get(task_id)
        if not task:
            return {'success': False, 'error': f'Task {task_id} not found'}
        
        task.status = TaskStatus.IN_PROGRESS
        
        for handler in self._on_task_started:
            handler(task)
        
        try:
            while task.current_step < len(task.steps):
                step = task.steps[task.current_step]
                
                logger.info(f"Executing step {task.current_step + 1}/{len(task.steps)}: {step.get('description', step['action'])}")
                
                result = await self._execute_step(step, task.context)
                
                step['result'] = result
                
                for handler in self._on_step_completed:
                    handler(task, step, result)
                
                if not result.get('success', False):
                    task.status = TaskStatus.FAILED
                    task.error = result.get('error', 'Step failed')
                    return {'success': False, 'error': task.error, 'step': task.current_step}
                
                # Update context mit Step-Ergebnis
                task.context.update(result.get('data', {}))
                task.current_step += 1
            
            task.status = TaskStatus.COMPLETED
            task.result = task.context
            
            for handler in self._on_task_completed:
                handler(task)
            
            return {'success': True, 'result': task.result}
        
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(f"Task {task_id} failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _execute_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Führt einen einzelnen Schritt aus."""
        action = step.get('action')
        
        if action == 'capture':
            # Delegiere an Monitor Agent
            if 'monitor' in self.agents:
                return await self.agents['monitor'].capture()
            return {'success': True, 'data': {}}
        
        elif action == 'find_element':
            # Delegiere an DataAnalyst
            if 'data_analyst' in self.agents:
                return await self.agents['data_analyst'].find_element(
                    step.get('target'),
                    context.get('ui_context')
                )
            return {'success': False, 'error': 'DataAnalyst not available'}
        
        elif action == 'click':
            # Delegiere an Interaction Agent
            if 'interaction' in self.agents:
                target = context.get('found_element') or step.get('target')
                return await self.agents['interaction'].click(target)
            return {'success': False, 'error': 'Interaction agent not available'}
        
        elif action == 'press_key':
            # Drücke eine Taste
            if 'interaction' in self.agents:
                return await self.agents['interaction'].press_key(step.get('key', ''))
            return {'success': False, 'error': 'Interaction agent not available'}
        
        elif action == 'type':
            if 'interaction' in self.agents:
                return await self.agents['interaction'].type_text(step.get('text', ''))
            return {'success': False, 'error': 'Interaction agent not available'}
        
        elif action == 'scroll':
            if 'interaction' in self.agents:
                return await self.agents['interaction'].scroll(
                    step.get('direction', 'down'),
                    step.get('amount', 3)
                )
            return {'success': False, 'error': 'Interaction agent not available'}
        
        elif action == 'wait':
            await asyncio.sleep(step.get('duration', 1.0))
            return {'success': True, 'data': {}}
        
        elif action == 'verify':
            # Verifiziere aktuellen Zustand
            if 'data_analyst' in self.agents:
                return await self.agents['data_analyst'].verify_state(
                    step.get('condition'),
                    context.get('ui_context')
                )
            return {'success': True, 'data': {'verified': True}}
        
        elif action == 'run_skill':
            # Führe Claude Skill aus
            skill_name = step.get('skill')
            inputs = step.get('inputs', {})
            
            result = await self.claude_cli.run_skill(
                skill_name,
                inputs,
                context.get('ui_context')
            )
            
            return {
                'success': result['success'],
                'data': result.get('output', {}),
                'error': result.get('error')
            }
        
        else:
            logger.warning(f"Unknown action: {action}")
            return {'success': False, 'error': f'Unknown action: {action}'}
    
    async def handle_user_request(
        self,
        request: str,
        ui_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Verarbeitet eine Benutzeranfrage.
        
        Args:
            request: Die Anfrage des Benutzers
            ui_context: Aktueller UI-Kontext von MoireTracker
        
        Returns:
            Ergebnis der Verarbeitung
        """
        logger.info(f"Handling request: {request}")
        
        # Erstelle Task
        task = await self.create_task(
            goal=request,
            context={'ui_context': ui_context}
        )
        
        # Führe aus
        result = await self.execute_task(task.id)
        
        return {
            'task_id': task.id,
            'goal': task.goal,
            'steps_count': len(task.steps),
            'status': task.status.value,
            'result': result
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt Status des Orchestrators zurück."""
        return {
            'total_tasks': len(self.tasks),
            'pending': sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING),
            'in_progress': sum(1 for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS),
            'completed': sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED),
            'failed': sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED),
            'registered_agents': list(self.agents.keys()),
            'available_skills': self.claude_cli.list_skills(),
            'claude_cli_available': self.claude_cli.is_available()
        }


# Singleton
_orchestrator_instance: Optional[OrchestratorAgent] = None


def get_orchestrator(
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None
) -> OrchestratorAgent:
    """Gibt Singleton-Instanz des Orchestrators zurück."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = OrchestratorAgent(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key
        )
    return _orchestrator_instance
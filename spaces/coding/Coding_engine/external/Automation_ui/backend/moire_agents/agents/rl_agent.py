"""
Reinforcement Learning Agent für Desktop Automation

Nutzt Q-Learning um:
- Aus erfolgreichen/gescheiterten Tasks zu lernen
- Action-Auswahl basierend auf gelernten Q-Values
- Exploration vs. Exploitation Balance (ε-greedy)
- Human Feedback Integration

Integriert sich mit dem SocietyOfMindOrchestrator.
"""

import asyncio
import logging
import os
import sys
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.rl_memory import (
    RLMemory, Episode, Transition, QTableEntry, HumanFeedback,
    RewardSource, get_rl_memory, calculate_step_reward
)

logger = logging.getLogger(__name__)


@dataclass
class ActionSuggestion:
    """Eine vorgeschlagene Action basierend auf Q-Learning."""
    action_type: str
    action_params: Dict[str, Any]
    action_text: str
    q_value: float
    confidence: float
    is_exploration: bool
    source: str  # 'q_table', 'llm_plan', 'exploration'


class RLAgent:
    """
    Reinforcement Learning Agent für Desktop Automation.
    
    Features:
    - ε-greedy Action Selection
    - Q-Table Lookup für bekannte States
    - Fallback auf LLM-Planning für unbekannte States
    - Automatic Reward Calculation
    - Human Feedback Integration
    """
    
    def __init__(
        self,
        rl_memory: Optional[RLMemory] = None,
        exploration_rate: float = 0.2,
        min_q_confidence: float = 0.3
    ):
        self.rl_memory = rl_memory or get_rl_memory()
        self.exploration_rate = exploration_rate
        self.min_q_confidence = min_q_confidence
        self._current_episode: Optional[Episode] = None
        self._step_index = 0
        self._last_state: Optional[Dict[str, Any]] = None
        self._action_history: List[Dict[str, Any]] = []
    
    # ==================== Episode Lifecycle ====================
    
    def start_task(self, task_description: str, task_id: str = "") -> Episode:
        """Startet eine neue RL-Episode für einen Task."""
        self._current_episode = self.rl_memory.start_episode(task_description, task_id)
        self._step_index = 0
        self._last_state = None
        self._action_history = []
        
        logger.info(f"RL Episode {self._current_episode.id} gestartet: {task_description[:50]}")
        return self._current_episode
    
    def end_task(self, success: bool, final_state: Optional[Dict[str, Any]] = None) -> float:
        """Beendet die aktuelle Episode."""
        if not self._current_episode:
            logger.warning("No active episode to end")
            return 0.0
        
        total_reward = self.rl_memory.end_episode(
            self._current_episode.id,
            success,
            final_state
        )
        
        logger.info(f"RL Episode {self._current_episode.id} beendet: success={success}, reward={total_reward:.2f}")
        
        self._current_episode = None
        return total_reward
    
    @property
    def current_episode(self) -> Optional[Episode]:
        return self._current_episode
    
    # ==================== Action Selection ====================
    
    def suggest_action(
        self,
        state: Dict[str, Any],
        available_actions: List[Dict[str, Any]],
        goal: str
    ) -> Optional[ActionSuggestion]:
        """
        Schlägt eine Action basierend auf Q-Learning vor.
        
        Args:
            state: Aktueller Screen State
            available_actions: Liste verfügbarer Actions (aus LLM-Plan)
            goal: Das Ziel des Tasks
        
        Returns:
            ActionSuggestion oder None wenn keine Empfehlung möglich
        """
        state_hash = RLMemory.hash_state(state)
        
        # Check if we should explore
        if self.rl_memory.should_explore():
            logger.info("RL: Exploration mode - selecting random action")
            if available_actions:
                import random
                action = random.choice(available_actions)
                return ActionSuggestion(
                    action_type=action.get('type', 'unknown'),
                    action_params=action.get('params', {}),
                    action_text=action.get('text', ''),
                    q_value=0.0,
                    confidence=0.0,
                    is_exploration=True,
                    source='exploration'
                )
            return None
        
        # Check Q-Table for known state-action pairs
        q_entries = self.rl_memory.get_q_values(state_hash)
        
        if q_entries:
            # Find best matching action from Q-Table
            best_entry = q_entries[0]  # Already sorted by q_value DESC
            
            if best_entry.confidence >= self.min_q_confidence:
                logger.info(f"RL: Using Q-Table action: {best_entry.action_key} (Q={best_entry.q_value:.2f})")
                
                # Parse action from key
                action_type, action_detail = self._parse_action_key(best_entry.action_key)
                
                return ActionSuggestion(
                    action_type=action_type,
                    action_params=self._build_params(action_type, action_detail),
                    action_text=best_entry.action_description,
                    q_value=best_entry.q_value,
                    confidence=best_entry.confidence,
                    is_exploration=False,
                    source='q_table'
                )
        
        # No confident Q-value found, use LLM plan
        if available_actions:
            action = available_actions[0]
            logger.info(f"RL: No Q-Table entry, using LLM plan: {action.get('text', '')[:50]}")
            return ActionSuggestion(
                action_type=action.get('type', 'unknown'),
                action_params=action.get('params', {}),
                action_text=action.get('text', ''),
                q_value=0.0,
                confidence=0.0,
                is_exploration=False,
                source='llm_plan'
            )
        
        return None
    
    def _parse_action_key(self, action_key: str) -> Tuple[str, str]:
        """Parst einen Action Key in Type und Detail."""
        parts = action_key.split(':', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return action_key, ''
    
    def _build_params(self, action_type: str, detail: str) -> Dict[str, Any]:
        """Baut Action Params aus Typ und Detail."""
        if action_type == 'click':
            return {'target': detail}
        elif action_type == 'type':
            return {'text': detail}
        elif action_type == 'press':
            return {'key': detail}
        elif action_type == 'hotkey':
            return {'keys': detail.split('+')}
        return {'raw': detail}
    
    def get_action_ranking(
        self,
        state: Dict[str, Any],
        actions: List[Dict[str, Any]]
    ) -> List[ActionSuggestion]:
        """
        Gibt alle Actions mit ihren Q-Values sortiert zurück.
        """
        state_hash = RLMemory.hash_state(state)
        q_entries = self.rl_memory.get_q_values(state_hash)
        q_lookup = {e.action_key: e for e in q_entries}
        
        ranked = []
        for action in actions:
            action_key = RLMemory.action_key(
                action.get('type', 'unknown'),
                action.get('params', {})
            )
            
            q_entry = q_lookup.get(action_key)
            
            ranked.append(ActionSuggestion(
                action_type=action.get('type', 'unknown'),
                action_params=action.get('params', {}),
                action_text=action.get('text', ''),
                q_value=q_entry.q_value if q_entry else 0.0,
                confidence=q_entry.confidence if q_entry else 0.0,
                is_exploration=False,
                source='q_table' if q_entry else 'llm_plan'
            ))
        
        # Sort by Q-value descending
        ranked.sort(key=lambda x: x.q_value, reverse=True)
        return ranked
    
    # ==================== Reward Recording ====================
    
    def record_step(
        self,
        state: Dict[str, Any],
        action_type: str,
        action_params: Dict[str, Any],
        action_text: str,
        result: str,
        verification: Dict[str, Any],
        next_state: Optional[Dict[str, Any]] = None,
        is_terminal: bool = False
    ) -> float:
        """
        Zeichnet einen Step auf und berechnet den Reward.
        
        Returns:
            Der berechnete Reward
        """
        if not self._current_episode:
            logger.warning("No active episode, cannot record step")
            return 0.0
        
        # Calculate reward
        reward, source = calculate_step_reward(result, verification, action_text)
        
        # Record transition
        self.rl_memory.record_transition(
            episode_id=self._current_episode.id,
            step_index=self._step_index,
            state=state,
            action_type=action_type,
            action_params=action_params,
            action_text=action_text,
            reward=reward,
            next_state=next_state,
            is_terminal=is_terminal,
            reward_source=source
        )
        
        # Update tracking
        self._step_index += 1
        self._last_state = next_state or state
        self._action_history.append({
            'step': self._step_index,
            'action': action_text,
            'reward': reward,
            'success': 'error' not in result.lower()
        })
        
        logger.debug(f"RL Step {self._step_index}: {action_text[:30]} → reward={reward:.2f}")
        
        return reward
    
    def apply_human_feedback(
        self,
        transition_id: int,
        feedback_type: str,
        corrected_reward: Optional[float] = None,
        comment: str = ""
    ):
        """Wendet Human Feedback auf eine Transition an."""
        # Get transition to know original reward
        conn = self.rl_memory._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT reward FROM rl_transitions WHERE id = ?', (transition_id,))
        row = cursor.fetchone()
        original_reward = row['reward'] if row else 0.0
        
        self.rl_memory.record_feedback(
            feedback_type=feedback_type,
            original_reward=original_reward,
            corrected_reward=corrected_reward,
            comment=comment,
            transition_id=transition_id
        )
        
        logger.info(f"Applied human feedback to transition {transition_id}: {feedback_type}")
    
    # ==================== Stats & Learning ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Gibt RL-Statistiken zurück."""
        stats = self.rl_memory.get_stats()
        stats['current_episode'] = self._current_episode.id if self._current_episode else None
        stats['current_step'] = self._step_index
        stats['action_history_length'] = len(self._action_history)
        return stats
    
    def get_learning_curve(self, window: int = 10) -> List[Dict[str, Any]]:
        """Gibt die Learning Curve zurück."""
        return self.rl_memory.get_learning_curve(window)
    
    def get_recent_episodes(self, limit: int = 20) -> List[Episode]:
        """Gibt die letzten Episoden zurück."""
        return self.rl_memory.get_recent_episodes(limit)
    
    def get_pending_feedback_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Gibt Transitions zurück die Human Feedback benötigen."""
        transitions = self.rl_memory.get_pending_feedback_transitions(limit)
        return [
            {
                'id': t.id,
                'episode_id': t.episode_id,
                'step': t.step_index,
                'action_type': t.action_type,
                'action_text': t.action_text,
                'reward': t.reward,
                'reward_source': t.reward_source.value,
                'state_summary': t.state_summary,
                'next_state_summary': t.next_state_summary,
                'timestamp': t.timestamp
            }
            for t in transitions
        ]
    
    def get_q_table_sample(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Gibt einen Sample aus der Q-Table zurück."""
        conn = self.rl_memory._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM rl_qtable 
            ORDER BY visit_count DESC, q_value DESC 
            LIMIT ?
        ''', (limit,))
        
        entries = []
        for row in cursor.fetchall():
            entries.append({
                'id': row['id'],
                'state_hash': row['state_hash'],
                'state_description': row['state_description'][:50] if row['state_description'] else '',
                'action_key': row['action_key'],
                'action_description': row['action_description'][:50] if row['action_description'] else '',
                'q_value': round(row['q_value'], 3),
                'visit_count': row['visit_count'],
                'confidence': round(row['confidence'], 2)
            })
        
        return entries
    
    def set_exploration_rate(self, rate: float):
        """Setzt die Exploration Rate."""
        self.exploration_rate = max(0.0, min(1.0, rate))
        self.rl_memory.exploration_rate = self.exploration_rate
        logger.info(f"Set exploration rate to {self.exploration_rate}")
    
    def set_learning_rate(self, rate: float):
        """Setzt die Learning Rate."""
        self.rl_memory.learning_rate = max(0.0, min(1.0, rate))
        logger.info(f"Set learning rate to {self.rl_memory.learning_rate}")


# ==================== Integration mit SocietyOfMindOrchestrator ====================

class RLEnhancedOrchestrator:
    """
    Wrapper um SocietyOfMindOrchestrator der RL-Features hinzufügt.
    """
    
    def __init__(
        self,
        orchestrator: Any,  # SocietyOfMindOrchestrator
        rl_agent: Optional[RLAgent] = None
    ):
        self.orchestrator = orchestrator
        self.rl_agent = rl_agent or RLAgent()
        self._use_rl = True
    
    async def execute_task(self, goal: str, max_rounds: int = 20) -> Dict[str, Any]:
        """Führt einen Task mit RL-Tracking aus."""
        # Start RL Episode
        task_id = str(datetime.now().timestamp())
        if self._use_rl:
            episode = self.rl_agent.start_task(goal, task_id)
        
        try:
            # Execute via orchestrator
            result = await self.orchestrator.execute_task(goal, max_rounds)
            
            # End RL Episode
            if self._use_rl:
                final_state = self.orchestrator.tools.get_last_state()
                total_reward = self.rl_agent.end_task(
                    success=result.get('success', False),
                    final_state=final_state
                )
                result['rl_reward'] = total_reward
                result['rl_episode_id'] = episode.id
            
            return result
            
        except Exception as e:
            # End episode on error
            if self._use_rl:
                self.rl_agent.end_task(success=False)
            raise
    
    def get_rl_stats(self) -> Dict[str, Any]:
        """Gibt RL-Statistiken zurück."""
        return self.rl_agent.get_stats()
    
    def set_rl_enabled(self, enabled: bool):
        """Aktiviert/Deaktiviert RL-Tracking."""
        self._use_rl = enabled
        logger.info(f"RL tracking {'enabled' if enabled else 'disabled'}")


# Singleton Instance
_rl_agent_instance: Optional[RLAgent] = None


def get_rl_agent() -> RLAgent:
    """Gibt Singleton-Instanz des RL Agents zurück."""
    global _rl_agent_instance
    if _rl_agent_instance is None:
        _rl_agent_instance = RLAgent()
    return _rl_agent_instance


# ==================== Main ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test RLAgent
    agent = get_rl_agent()
    
    print("RL Agent initialized")
    print(f"Stats: {agent.get_stats()}")
    
    # Simulate episode
    episode = agent.start_task("Test task: Open Notepad")
    
    state1 = {'texts': [{'text': 'Desktop'}], 'boxes': [{'category': 'icon'}]}
    state2 = {'texts': [{'text': 'Notepad'}], 'boxes': [{'category': 'window'}]}
    
    reward = agent.record_step(
        state=state1,
        action_type='press',
        action_params={'key': 'win'},
        action_text='Press Win key',
        result='Pressed key: win',
        verification={'verified': True, 'confidence': 80},
        next_state=state2
    )
    print(f"Step reward: {reward}")
    
    agent.end_task(success=True, final_state=state2)
    
    print(f"\nFinal stats: {agent.get_stats()}")
    print(f"Learning curve: {agent.get_learning_curve()}")
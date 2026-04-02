"""
Skill Acquisition System (V2 PHASE 5: P5.64-66)

P5.64: SkillLibrary
  - Persistent collection of learned skills
  - Each skill: name, trigger, action_sequence, target_system, success_rate
  - Grows with experience. Stored as JSON in data/skills/

P5.65: SkillComposition
  - Combines atomic skills into composite skills
  - E.g., "test" + "commit" = "safe_commit"
  - Suggests compositions based on frequent sequences

P5.66: SkillRefinement
  - A/B testing of skill variants
  - Parameter tuning (timeouts, retry counts, order)
  - Deactivates weak skills (success_rate < 0.3 after 10 attempts)
"""

import time
import json
import os
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger('brain.skill_library')


class SkillStatus(Enum):
    ACTIVE = "active"
    LEARNING = "learning"      # Still gathering data
    DEPRECATED = "deprecated"  # Low success, kept for reference
    ARCHIVED = "archived"      # Not used for 30+ days


@dataclass
class Action:
    """A single action step within a skill."""
    system: str          # Target system (e.g., "shell", "coding_engine", "automation_ui")
    command: str         # Action command
    params: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: float = 30000.0
    retry_count: int = 0
    required: bool = True  # If True, failure stops the skill

    def to_dict(self) -> Dict:
        return {
            'system': self.system,
            'command': self.command,
            'params': self.params,
            'timeout_ms': self.timeout_ms,
            'retry_count': self.retry_count,
            'required': self.required,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'Action':
        return cls(
            system=d.get('system', ''),
            command=d.get('command', ''),
            params=d.get('params', {}),
            timeout_ms=d.get('timeout_ms', 30000.0),
            retry_count=d.get('retry_count', 0),
            required=d.get('required', True),
        )


@dataclass
class Skill:
    """A learned skill with trigger conditions and action sequence."""
    name: str
    trigger_condition: str         # E.g., "task_type == 'deployment'"
    action_sequence: List[Action]
    target_system: str             # Primary system
    domain: str = ""
    description: str = ""
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    confidence: float = 0.5
    total_attempts: int = 0
    total_successes: int = 0
    status: SkillStatus = SkillStatus.LEARNING
    created_at: float = 0.0
    last_used_at: float = 0.0
    parent_skills: List[str] = field(default_factory=list)  # For composed skills
    variant_of: str = ""           # For A/B variants
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def record_outcome(self, success: bool, duration_ms: float) -> None:
        """Record a skill execution outcome."""
        self.total_attempts += 1
        if success:
            self.total_successes += 1
        self.success_rate = self.total_successes / self.total_attempts
        # Exponential moving average for duration
        alpha = 0.3
        if self.avg_duration_ms == 0.0:
            self.avg_duration_ms = duration_ms
        else:
            self.avg_duration_ms = alpha * duration_ms + (1 - alpha) * self.avg_duration_ms
        # Update confidence based on number of attempts
        self.confidence = min(0.99, self.success_rate * (1 - 1 / (1 + self.total_attempts)))
        self.last_used_at = time.time()

        # Transition status
        if self.total_attempts >= 5 and self.status == SkillStatus.LEARNING:
            self.status = SkillStatus.ACTIVE
        if self.total_attempts >= 10 and self.success_rate < 0.3:
            self.status = SkillStatus.DEPRECATED

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'trigger_condition': self.trigger_condition,
            'action_sequence': [a.to_dict() for a in self.action_sequence],
            'target_system': self.target_system,
            'domain': self.domain,
            'description': self.description,
            'success_rate': round(self.success_rate, 3),
            'avg_duration_ms': round(self.avg_duration_ms, 1),
            'confidence': round(self.confidence, 3),
            'total_attempts': self.total_attempts,
            'total_successes': self.total_successes,
            'status': self.status.value,
            'created_at': self.created_at,
            'last_used_at': self.last_used_at,
            'parent_skills': self.parent_skills,
            'variant_of': self.variant_of,
            'tags': self.tags,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'Skill':
        return cls(
            name=d.get('name', ''),
            trigger_condition=d.get('trigger_condition', ''),
            action_sequence=[Action.from_dict(a) for a in d.get('action_sequence', [])],
            target_system=d.get('target_system', ''),
            domain=d.get('domain', ''),
            description=d.get('description', ''),
            success_rate=d.get('success_rate', 0.0),
            avg_duration_ms=d.get('avg_duration_ms', 0.0),
            confidence=d.get('confidence', 0.5),
            total_attempts=d.get('total_attempts', 0),
            total_successes=d.get('total_successes', 0),
            status=SkillStatus(d.get('status', 'learning')),
            created_at=d.get('created_at', 0.0),
            last_used_at=d.get('last_used_at', 0.0),
            parent_skills=d.get('parent_skills', []),
            variant_of=d.get('variant_of', ''),
            tags=d.get('tags', []),
        )


class SkillLibrary:
    """
    P5.64: Persistent collection of learned skills.

    Skills grow from experience, are stored persistently, and
    can be matched to new tasks based on trigger conditions.
    """

    def __init__(self, persist_dir: Optional[str] = None, max_skills: int = 500):
        self.persist_dir = persist_dir
        self.max_skills = max_skills
        self._skills: Dict[str, Skill] = {}  # name -> Skill
        self._domain_index: Dict[str, List[str]] = defaultdict(list)
        self._total_executions = 0

        if persist_dir:
            self._load_from_disk()

    def register_skill(self, skill: Skill) -> None:
        """Register a new skill in the library."""
        if len(self._skills) >= self.max_skills:
            self._evict_weakest()
        self._skills[skill.name] = skill
        self._domain_index[skill.domain].append(skill.name)

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def find_matching_skills(self, task_type: str = "", domain: str = "",
                              system: str = "", min_confidence: float = 0.3,
                              status_filter: Optional[SkillStatus] = SkillStatus.ACTIVE) -> List[Skill]:
        """Find skills that match the given criteria."""
        candidates = []
        for skill in self._skills.values():
            if status_filter and skill.status != status_filter:
                continue
            if skill.confidence < min_confidence:
                continue

            # Simple trigger matching
            match_score = 0.0
            if task_type and task_type in skill.trigger_condition:
                match_score += 1.0
            if domain and (domain == skill.domain or domain in skill.tags):
                match_score += 0.5
            if system and system == skill.target_system:
                match_score += 0.3

            if match_score > 0:
                candidates.append((skill, match_score))

        candidates.sort(key=lambda x: (x[1], x[0].confidence), reverse=True)
        return [s for s, _ in candidates]

    def record_execution(self, skill_name: str, success: bool, duration_ms: float) -> bool:
        """Record the outcome of a skill execution."""
        skill = self._skills.get(skill_name)
        if not skill:
            return False
        skill.record_outcome(success, duration_ms)
        self._total_executions += 1
        return True

    def get_skills_by_domain(self, domain: str) -> List[Skill]:
        """Get all skills for a domain."""
        names = self._domain_index.get(domain, [])
        return [self._skills[n] for n in names if n in self._skills]

    def get_all_active(self) -> List[Skill]:
        """Get all active skills."""
        return [s for s in self._skills.values() if s.status == SkillStatus.ACTIVE]

    def _evict_weakest(self) -> None:
        """Remove the lowest confidence deprecated/archived skill."""
        candidates = [(n, s) for n, s in self._skills.items()
                       if s.status in (SkillStatus.DEPRECATED, SkillStatus.ARCHIVED)]
        if not candidates:
            candidates = [(n, s) for n, s in self._skills.items()]
        if candidates:
            worst_name = min(candidates, key=lambda x: x[1].confidence)[0]
            del self._skills[worst_name]

    def _load_from_disk(self) -> None:
        if not self.persist_dir or not os.path.isdir(self.persist_dir):
            return
        for filename in os.listdir(self.persist_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.persist_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    skill = Skill.from_dict(data)
                    self._skills[skill.name] = skill
                    self._domain_index[skill.domain].append(skill.name)
                except Exception as e:
                    logger.warning(f"Failed to load skill {filename}: {e}")

    def save_to_disk(self) -> None:
        """Persist all skills to disk."""
        if not self.persist_dir:
            return
        os.makedirs(self.persist_dir, exist_ok=True)
        for name, skill in self._skills.items():
            safe_name = name.replace('/', '_').replace('\\', '_')
            filepath = os.path.join(self.persist_dir, f"{safe_name}.json")
            try:
                with open(filepath, 'w') as f:
                    json.dump(skill.to_dict(), f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save skill {name}: {e}")

    def get_state(self) -> Dict:
        by_status = defaultdict(int)
        for s in self._skills.values():
            by_status[s.status.value] += 1
        return {
            'total_skills': len(self._skills),
            'by_status': dict(by_status),
            'total_executions': self._total_executions,
            'domains': list(self._domain_index.keys()),
            'top_skills': [s.to_dict() for s in
                           sorted(self._skills.values(), key=lambda s: s.confidence, reverse=True)[:5]],
        }

    @classmethod
    def from_yaml(cls, cfg: Dict) -> 'SkillLibrary':
        section = cfg.get('skill_library', {})
        return cls(
            persist_dir=section.get('persist_dir', None),
            max_skills=section.get('max_skills', 500),
        )


# ─── P5.65: Skill Composition ──────────────────────────────────────────

class SkillComposition:
    """
    P5.65: Combines atomic skills into composite skills.

    Detects frequent sequences of skills and proposes compositions.
    E.g., "test" + "commit" = "safe_commit".
    """

    def __init__(self, min_co_occurrences: int = 3,
                 min_combined_success: float = 0.6):
        self.min_co_occurrences = min_co_occurrences
        self.min_combined_success = min_combined_success
        self._sequence_buffer: List[List[str]] = []  # Recent skill sequences
        self._max_sequences = 200
        self._compositions_proposed = 0

    def record_skill_sequence(self, skill_names: List[str]) -> None:
        """Record a sequence of skills executed together."""
        if len(skill_names) >= 2:
            self._sequence_buffer.append(skill_names)
            if len(self._sequence_buffer) > self._max_sequences:
                self._sequence_buffer.pop(0)

    def discover_compositions(self, library: SkillLibrary) -> List[Dict]:
        """
        Analyze sequences to find composition candidates.

        Returns list of {name, components, combined_success_rate} dicts.
        """
        # Count consecutive pairs
        pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        for seq in self._sequence_buffer:
            for i in range(len(seq) - 1):
                pair_counts[(seq[i], seq[i + 1])] += 1

        proposals = []
        for (skill_a, skill_b), count in pair_counts.items():
            if count < self.min_co_occurrences:
                continue
            a = library.get_skill(skill_a)
            b = library.get_skill(skill_b)
            if not a or not b:
                continue

            combined_success = min(a.success_rate, b.success_rate)
            if combined_success < self.min_combined_success:
                continue

            composed_name = f"{skill_a}+{skill_b}"
            # Check if composition already exists
            if library.get_skill(composed_name):
                continue

            proposals.append({
                'name': composed_name,
                'components': [skill_a, skill_b],
                'combined_success_rate': round(combined_success, 3),
                'co_occurrences': count,
                'combined_actions': [a.to_dict() for a in a.action_sequence] +
                                    [a.to_dict() for a in b.action_sequence],
            })
            self._compositions_proposed += 1

        proposals.sort(key=lambda p: p['combined_success_rate'], reverse=True)
        return proposals

    def create_composite_skill(self, name: str, components: List[Skill],
                                trigger: str = "", domain: str = "") -> Skill:
        """Create a composite skill from component skills."""
        all_actions = []
        for comp in components:
            all_actions.extend(comp.action_sequence)

        return Skill(
            name=name,
            trigger_condition=trigger or " AND ".join(c.trigger_condition for c in components),
            action_sequence=all_actions,
            target_system=components[0].target_system if components else "",
            domain=domain or components[0].domain if components else "",
            description=f"Composed from: {', '.join(c.name for c in components)}",
            parent_skills=[c.name for c in components],
            tags=['composed'],
        )

    def get_state(self) -> Dict:
        return {
            'sequence_buffer_size': len(self._sequence_buffer),
            'compositions_proposed': self._compositions_proposed,
        }


# ─── P5.66: Skill Refinement ───────────────────────────────────────────

@dataclass
class ABTest:
    """An A/B test between two skill variants."""
    original_name: str
    variant_name: str
    parameter_changes: Dict[str, Any]
    original_successes: int = 0
    original_attempts: int = 0
    variant_successes: int = 0
    variant_attempts: int = 0
    min_samples: int = 10
    created_at: float = 0.0
    resolved: bool = False
    winner: str = ""

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def record_outcome(self, is_variant: bool, success: bool) -> None:
        if is_variant:
            self.variant_attempts += 1
            if success:
                self.variant_successes += 1
        else:
            self.original_attempts += 1
            if success:
                self.original_successes += 1

    def is_conclusive(self) -> bool:
        return (self.original_attempts >= self.min_samples and
                self.variant_attempts >= self.min_samples)

    def get_winner(self) -> Optional[str]:
        if not self.is_conclusive():
            return None
        orig_rate = self.original_successes / max(self.original_attempts, 1)
        var_rate = self.variant_successes / max(self.variant_attempts, 1)
        # Require at least 5% improvement to declare variant winner
        if var_rate > orig_rate + 0.05:
            return self.variant_name
        else:
            return self.original_name

    def to_dict(self) -> Dict:
        orig_rate = self.original_successes / max(self.original_attempts, 1)
        var_rate = self.variant_successes / max(self.variant_attempts, 1)
        return {
            'original': self.original_name,
            'variant': self.variant_name,
            'parameter_changes': self.parameter_changes,
            'original_rate': round(orig_rate, 3),
            'variant_rate': round(var_rate, 3),
            'original_attempts': self.original_attempts,
            'variant_attempts': self.variant_attempts,
            'conclusive': self.is_conclusive(),
            'winner': self.winner or (self.get_winner() or ""),
        }


class SkillRefinement:
    """
    P5.66: Refines skills over time via A/B testing and parameter tuning.

    - A/B tests skill variants
    - Tunes parameters (timeouts, retry counts)
    - Deactivates weak skills (success_rate < 0.3 after 10 attempts)
    """

    def __init__(self, deactivation_threshold: float = 0.3,
                 deactivation_min_attempts: int = 10,
                 improvement_threshold: float = 0.05):
        self.deactivation_threshold = deactivation_threshold
        self.deactivation_min_attempts = deactivation_min_attempts
        self.improvement_threshold = improvement_threshold
        self._active_tests: List[ABTest] = []
        self._completed_tests: List[ABTest] = []
        self._max_active_tests = 5
        self._total_refinements = 0

    def check_for_deactivation(self, library: SkillLibrary) -> List[str]:
        """Check and deactivate weak skills. Returns deactivated skill names."""
        deactivated = []
        for skill in list(library._skills.values()):
            if (skill.total_attempts >= self.deactivation_min_attempts and
                    skill.success_rate < self.deactivation_threshold and
                    skill.status == SkillStatus.ACTIVE):
                skill.status = SkillStatus.DEPRECATED
                deactivated.append(skill.name)
                self._total_refinements += 1
        return deactivated

    def propose_variant(self, skill: Skill) -> Optional[Tuple[Skill, ABTest]]:
        """
        Propose a variant of a skill with tweaked parameters.

        Returns (variant_skill, ab_test) or None if not suitable.
        """
        if len(self._active_tests) >= self._max_active_tests:
            return None
        if skill.total_attempts < 5:
            return None

        # Determine what to tweak
        changes = {}
        new_actions = []

        for action in skill.action_sequence:
            new_action = Action(
                system=action.system,
                command=action.command,
                params=dict(action.params),
                timeout_ms=action.timeout_ms,
                retry_count=action.retry_count,
                required=action.required,
            )
            # If skill has moderate failure rate, try adding retries
            if skill.success_rate < 0.8 and action.retry_count == 0:
                new_action.retry_count = 1
                changes['retry_count'] = f"{action.command}: 0 -> 1"
            # If skill is slow, try reducing timeout
            elif skill.avg_duration_ms > 10000 and action.timeout_ms > 10000:
                new_action.timeout_ms = action.timeout_ms * 0.7
                changes['timeout_ms'] = f"{action.command}: {action.timeout_ms} -> {new_action.timeout_ms}"

            new_actions.append(new_action)

        if not changes:
            return None

        variant_name = f"{skill.name}_v{skill.total_attempts}"
        variant = Skill(
            name=variant_name,
            trigger_condition=skill.trigger_condition,
            action_sequence=new_actions,
            target_system=skill.target_system,
            domain=skill.domain,
            description=f"Variant of {skill.name}: {changes}",
            variant_of=skill.name,
            tags=['variant'] + skill.tags,
        )

        ab_test = ABTest(
            original_name=skill.name,
            variant_name=variant_name,
            parameter_changes=changes,
        )
        self._active_tests.append(ab_test)

        return (variant, ab_test)

    def record_test_outcome(self, skill_name: str, success: bool) -> None:
        """Record outcome for any active A/B test involving this skill."""
        for test in self._active_tests:
            if skill_name == test.variant_name:
                test.record_outcome(is_variant=True, success=success)
            elif skill_name == test.original_name:
                test.record_outcome(is_variant=False, success=success)

    def resolve_tests(self, library: SkillLibrary) -> List[Dict]:
        """Resolve any conclusive A/B tests. Returns resolved test results."""
        resolved = []
        still_active = []

        for test in self._active_tests:
            if test.is_conclusive():
                winner = test.get_winner()
                test.winner = winner or ""
                test.resolved = True
                self._completed_tests.append(test)
                self._total_refinements += 1
                resolved.append(test.to_dict())

                # If variant won, promote it
                if winner == test.variant_name:
                    variant = library.get_skill(test.variant_name)
                    original = library.get_skill(test.original_name)
                    if variant:
                        variant.status = SkillStatus.ACTIVE
                    if original:
                        original.status = SkillStatus.DEPRECATED
                else:
                    # Original won, deprecate variant
                    variant = library.get_skill(test.variant_name)
                    if variant:
                        variant.status = SkillStatus.DEPRECATED
            else:
                still_active.append(test)

        self._active_tests = still_active
        return resolved

    def archive_unused(self, library: SkillLibrary, max_idle_days: float = 30.0) -> List[str]:
        """Archive skills not used for max_idle_days."""
        cutoff = time.time() - (max_idle_days * 86400)
        archived = []
        for skill in list(library._skills.values()):
            if (skill.last_used_at > 0 and skill.last_used_at < cutoff and
                    skill.status == SkillStatus.ACTIVE):
                skill.status = SkillStatus.ARCHIVED
                archived.append(skill.name)
        return archived

    def get_state(self) -> Dict:
        return {
            'active_tests': len(self._active_tests),
            'completed_tests': len(self._completed_tests),
            'total_refinements': self._total_refinements,
            'active_test_details': [t.to_dict() for t in self._active_tests],
        }

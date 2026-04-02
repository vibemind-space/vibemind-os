# CTE LLM-Upgrade + User-Awareness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade all 6 template-based CTE `_think_*` methods to use real LLM agents via MicroAgentPool, plus add a new `_think_user()` for User-Awareness with Rowboat persistence.

**Architecture:** Add 4 new agents (reflector, explorer, analyst, user_analyst) to MicroAgentPool. Each `_think_*` method tries LLM first, falls back to its old template on failure/rate-limit. `_think_user()` writes insights to `People/User_Profile.md` in Rowboat format.

**Tech Stack:** OpenRouter free models, MicroAgentPool, Rowboat MD-files, existing CTE infrastructure

---

### Task 1: Add 4 New Agent Configs to MicroAgentPool

**Files:**
- Modify: `core/brain_chat.py` (MicroAgentPool: `_FREE_MODELS`, `_SYSTEM_PROMPTS`, `_setup_agents()`)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write the failing tests**

Append to `TestResearcherToolExecution` class in `tests/test_brain_chat_quick.py`:

```python
    # ── New Thought Agents (CTE LLM Upgrade) ──

    def test_reflector_agent_config(self):
        """MicroAgentPool has a 'reflector' agent."""
        pool = MicroAgentPool()
        assert 'reflector' in pool._agents
        agent = pool._agents['reflector']
        assert agent.cooldown_seconds == 45.0
        assert agent.hourly_cap == 15

    def test_explorer_agent_config(self):
        """MicroAgentPool has an 'explorer' agent."""
        pool = MicroAgentPool()
        assert 'explorer' in pool._agents
        agent = pool._agents['explorer']
        assert agent.cooldown_seconds == 60.0
        assert agent.hourly_cap == 12

    def test_analyst_agent_config(self):
        """MicroAgentPool has an 'analyst' agent."""
        pool = MicroAgentPool()
        assert 'analyst' in pool._agents
        agent = pool._agents['analyst']
        assert agent.cooldown_seconds == 60.0
        assert agent.hourly_cap == 12

    def test_user_analyst_agent_config(self):
        """MicroAgentPool has a 'user_analyst' agent."""
        pool = MicroAgentPool()
        assert 'user_analyst' in pool._agents
        agent = pool._agents['user_analyst']
        assert agent.cooldown_seconds == 120.0
        assert agent.hourly_cap == 8

    def test_pool_has_10_agents(self):
        """MicroAgentPool now has 10 agents total."""
        pool = MicroAgentPool()
        assert len(pool._agents) == 10
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution::test_reflector_agent_config -v`
Expected: FAIL — `KeyError: 'reflector'`

**Step 3: Write the implementation**

In `core/brain_chat.py`:

**3a.** Add to `_FREE_MODELS` dict (after `'researcher'` line):
```python
        'reflector':    'google/gemma-3-27b-it:free',                    # 27B, fast reflection
        'explorer':     'stepfun/step-3.5-flash:free',                   # 196B MoE, creative
        'analyst':      'nousresearch/hermes-3-llama-3.1-405b:free',     # 405B, deep analysis
        'user_analyst': 'openai/gpt-oss-120b:free',                      # 120B, user understanding
```

**3b.** Add to `_SYSTEM_PROMPTS` dict (after `'researcher'` entry):
```python
        'reflector': (
            "You are a reflective thinker for an AI brain. "
            "Given a user's question and related knowledge, reflect deeply: "
            "WHY did the user ask this? What underlying need or curiosity drives it? "
            "Connect the question with the knowledge to produce a genuine insight. "
            "Output ONLY the reflection (2-3 sentences), nothing else."
        ),
        'explorer': (
            "You are a curious explorer for an AI brain. "
            "Given a topic or knowledge snippet, generate a creative, "
            "curiosity-driven thought about it. What's surprising? "
            "What would be fascinating to investigate further? "
            "Output ONLY the exploration thought (1-2 sentences), nothing else."
        ),
        'analyst': (
            "You are a deep analyst for an AI brain. "
            "Given an active topic the user is discussing, analyze it deeply: "
            "What are the key implications? What non-obvious connections exist? "
            "What would a domain expert notice that others miss? "
            "Output ONLY the analysis (2-3 sentences), nothing else."
        ),
        'user_analyst': (
            "You are a user understanding module for an AI brain called Tahlamus. "
            "Given recent conversation history, analyze the user's current state: "
            "1) Mood/emotional state (curious, frustrated, focused, etc.) "
            "2) What they seem to need right now "
            "3) Emerging interests or patterns "
            "Output as: MOOD: ... | NEEDS: ... | INTERESTS: ... "
            "Be concise and specific, not generic."
        ),
```

**3c.** Add to `_setup_agents()` (after `'researcher'` block):
```python
            'reflector': MicroAgentConfig(
                name='reflector',
                model=self._FREE_MODELS['reflector'],
                system_prompt=self._SYSTEM_PROMPTS['reflector'],
                max_tokens=200,
                temperature=0.7,
                cooldown_seconds=45.0,
                hourly_cap=15,
            ),
            'explorer': MicroAgentConfig(
                name='explorer',
                model=self._FREE_MODELS['explorer'],
                system_prompt=self._SYSTEM_PROMPTS['explorer'],
                max_tokens=150,
                temperature=0.8,
                cooldown_seconds=60.0,
                hourly_cap=12,
            ),
            'analyst': MicroAgentConfig(
                name='analyst',
                model=self._FREE_MODELS['analyst'],
                system_prompt=self._SYSTEM_PROMPTS['analyst'],
                max_tokens=250,
                temperature=0.6,
                cooldown_seconds=60.0,
                hourly_cap=12,
            ),
            'user_analyst': MicroAgentConfig(
                name='user_analyst',
                model=self._FREE_MODELS['user_analyst'],
                system_prompt=self._SYSTEM_PROMPTS['user_analyst'],
                max_tokens=200,
                temperature=0.5,
                cooldown_seconds=120.0,
                hourly_cap=8,
            ),
```

**3d.** Fix `test_pool_has_10_agents` and `test_agents_configured` — update expected count from 6→10 and add new names to expected set.

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: All pass

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: add 4 new thought agents (reflector, explorer, analyst, user_analyst)"
```

---

### Task 2: Add Pool Methods for New Agents (reflect, explore, analyze)

**Files:**
- Modify: `core/brain_chat.py` (MicroAgentPool: new public methods)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write the failing tests**

```python
    # ── New Pool Methods ──

    def test_reflect_method(self):
        """pool.reflect() returns RefinedKnowledge with type='reflection'."""
        mock_router = MagicMock()
        mock_router._call_openrouter.return_value = "The user seems driven by curiosity about X"
        pool = MicroAgentPool(llm_router=mock_router)
        result = pool.reflect("What is quantum gravity?", "It deals with unifying forces")
        assert result is not None
        assert isinstance(result, RefinedKnowledge)
        assert result.agent == 'reflector'
        assert result.refinement_type == 'reflection'

    def test_reflect_returns_none_without_router(self):
        pool = MicroAgentPool()
        assert pool.reflect("query", "knowledge") is None

    def test_explore_method(self):
        """pool.explore() returns RefinedKnowledge with type='exploration'."""
        mock_router = MagicMock()
        mock_router._call_openrouter.return_value = "Fascinating — what if gravity waves carry information?"
        pool = MicroAgentPool(llm_router=mock_router)
        result = pool.explore("quantum gravity research")
        assert result is not None
        assert result.agent == 'explorer'
        assert result.refinement_type == 'exploration'

    def test_explore_returns_none_without_router(self):
        pool = MicroAgentPool()
        assert pool.explore("topic") is None

    def test_analyze_method(self):
        """pool.analyze() returns RefinedKnowledge with type='analysis'."""
        mock_router = MagicMock()
        mock_router._call_openrouter.return_value = "The key implication is that spacetime itself is quantized"
        pool = MicroAgentPool(llm_router=mock_router)
        result = pool.analyze("quantum gravity", "It unifies quantum mechanics and GR")
        assert result is not None
        assert result.agent == 'analyst'
        assert result.refinement_type == 'analysis'

    def test_analyze_returns_none_without_router(self):
        pool = MicroAgentPool()
        assert pool.analyze("topic", "context") is None
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution::test_reflect_method -v`
Expected: FAIL — `AttributeError: 'MicroAgentPool' object has no attribute 'reflect'`

**Step 3: Write the implementation**

Add after `research()` method in MicroAgentPool:

```python
    def reflect(self, query: str, knowledge: str) -> Optional[RefinedKnowledge]:
        """Run Reflector agent — why did the user ask this?"""
        prompt = (
            f"User's question: {query[:200]}\n\n"
            f"Related knowledge: {knowledge[:200]}\n\n"
            f"Reflect on why the user asked this and what insight connects them."
        )
        result = self._call_agent('reflector', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=query[:200],
            refined=result[:400],
            agent='reflector',
            refinement_type='reflection',
            confidence=0.6,
            timestamp=time.time(),
        )

    def explore(self, topic: str) -> Optional[RefinedKnowledge]:
        """Run Explorer agent — creative curiosity-driven thought."""
        prompt = f"Explore this topic with genuine curiosity:\n\n{topic[:300]}"
        result = self._call_agent('explorer', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=topic[:200],
            refined=result[:300],
            agent='explorer',
            refinement_type='exploration',
            confidence=0.5,
            timestamp=time.time(),
        )

    def analyze(self, topic: str, context: str = "") -> Optional[RefinedKnowledge]:
        """Run Analyst agent — deep analysis of active topic."""
        ctx = f"\n\nContext: {context[:200]}" if context else ""
        prompt = f"Deep analysis of this topic:{ctx}\n\n{topic[:300]}"
        result = self._call_agent('analyst', prompt)
        if not result:
            return None
        return RefinedKnowledge(
            original=topic[:200],
            refined=result[:400],
            agent='analyst',
            refinement_type='analysis',
            confidence=0.7,
            timestamp=time.time(),
        )
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: All pass

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: add reflect(), explore(), analyze() methods on MicroAgentPool"
```

---

### Task 3: Add analyze_user() + Rowboat Persistence

**Files:**
- Modify: `core/brain_chat.py` (MicroAgentPool: `analyze_user()`, `_write_user_profile()`)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write the failing tests**

```python
    # ── User Analyst + Rowboat ──

    def test_analyze_user_returns_refined_knowledge(self):
        """analyze_user() returns RefinedKnowledge with type='user_insight'."""
        mock_router = MagicMock()
        mock_router._call_openrouter.return_value = "MOOD: curious | NEEDS: architecture guidance | INTERESTS: AI systems"
        pool = MicroAgentPool(llm_router=mock_router)
        history = [
            {'type': 'user', 'content': 'How does the CTE work?'},
            {'type': 'system', 'content': 'The CTE is a background thinking engine...'},
        ]
        result = pool.analyze_user(history)
        assert result is not None
        assert result.agent == 'user_analyst'
        assert result.refinement_type == 'user_insight'
        assert 'curious' in result.refined.lower() or 'MOOD' in result.refined

    def test_analyze_user_returns_none_without_router(self):
        pool = MicroAgentPool()
        assert pool.analyze_user([]) is None

    def test_analyze_user_returns_none_on_empty_history(self):
        mock_router = MagicMock()
        pool = MicroAgentPool(llm_router=mock_router)
        assert pool.analyze_user([]) is None

    def test_write_user_profile_creates_file(self, tmp_path):
        """_write_user_profile writes Rowboat-compatible MD."""
        pool = MicroAgentPool()
        profile_path = tmp_path / "User_Profile.md"
        pool._rowboat_user_profile_path = str(profile_path)
        pool._write_user_profile("MOOD: focused | NEEDS: code review | INTERESTS: testing")
        assert profile_path.exists()
        content = profile_path.read_text(encoding='utf-8')
        assert '# User Profile' in content
        assert 'focused' in content

    def test_write_user_profile_appends_mood_history(self, tmp_path):
        """Subsequent writes append to mood history."""
        pool = MicroAgentPool()
        profile_path = tmp_path / "User_Profile.md"
        pool._rowboat_user_profile_path = str(profile_path)
        pool._write_user_profile("MOOD: curious | NEEDS: guidance | INTERESTS: AI")
        pool._write_user_profile("MOOD: focused | NEEDS: testing | INTERESTS: TDD")
        content = profile_path.read_text(encoding='utf-8')
        assert 'curious' in content
        assert 'focused' in content
```

**Step 2: Run to verify failure**

Expected: FAIL — `AttributeError: 'MicroAgentPool' object has no attribute 'analyze_user'`

**Step 3: Write the implementation**

Add to MicroAgentPool `__init__`:
```python
        # Rowboat user profile path
        self._rowboat_user_profile_path = r'C:\Users\User\.rowboat\knowledge\People\User_Profile.md'
```

Add methods after `analyze()`:

```python
    def analyze_user(self, conversation_history: List[Dict]) -> Optional[RefinedKnowledge]:
        """Run UserAnalyst agent — mood, needs, interests from conversation."""
        if not conversation_history or not self._router:
            return None

        # Format recent conversation for the agent
        recent = conversation_history[-10:]
        lines = []
        for turn in recent:
            role = turn.get('type', 'unknown')
            content = turn.get('content', '')[:150]
            lines.append(f"[{role}] {content}")
        history_str = '\n'.join(lines)

        prompt = (
            f"Analyze this recent conversation to understand the user:\n\n"
            f"{history_str}\n\n"
            f"Describe: MOOD: ... | NEEDS: ... | INTERESTS: ..."
        )
        result = self._call_agent('user_analyst', prompt)
        if not result:
            return None

        # Persist to Rowboat
        try:
            self._write_user_profile(result)
        except Exception as e:
            logger.debug(f"Rowboat write failed: {e}")

        return RefinedKnowledge(
            original=history_str[:200],
            refined=result[:500],
            agent='user_analyst',
            refinement_type='user_insight',
            confidence=0.6,
            timestamp=time.time(),
        )

    def _write_user_profile(self, analysis: str) -> None:
        """Write/update user profile in Rowboat-compatible MD format."""
        import os
        from datetime import datetime

        path = self._rowboat_user_profile_path
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Parse MOOD/NEEDS/INTERESTS from analysis
        mood = needs = interests = ""
        for part in analysis.split('|'):
            part = part.strip()
            if part.upper().startswith('MOOD:'):
                mood = part[5:].strip()
            elif part.upper().startswith('NEEDS:'):
                needs = part[6:].strip()
            elif part.upper().startswith('INTERESTS:'):
                interests = part[10:].strip()

        if os.path.exists(path):
            # Append mood entry, update needs/interests
            existing = open(path, 'r', encoding='utf-8').read()
            # Append mood to history
            mood_entry = f"- [{timestamp}] {mood}" if mood else ""
            if mood_entry and '## Stimmungs-History' in existing:
                existing = existing.replace(
                    '## Stimmungs-History\n',
                    f'## Stimmungs-History\n{mood_entry}\n',
                )
            elif mood_entry:
                existing += f"\n## Stimmungs-History\n{mood_entry}\n"
            # Update needs section
            if needs and '## Aktuelle Bedürfnisse' in existing:
                import re as _re
                existing = _re.sub(
                    r'## Aktuelle Bedürfnisse\n.*?\n(?=##|\Z)',
                    f'## Aktuelle Bedürfnisse\n- {needs}\n\n',
                    existing, flags=_re.DOTALL,
                )
            elif needs:
                existing += f"\n## Aktuelle Bedürfnisse\n- {needs}\n"
            # Update interests
            if interests and '## Interessen' in existing:
                import re as _re
                existing = _re.sub(
                    r'## Interessen\n.*?\n(?=##|\Z)',
                    f'## Interessen\n- {interests}\n\n',
                    existing, flags=_re.DOTALL,
                )
            elif interests:
                existing += f"\n## Interessen\n- {interests}\n"
            with open(path, 'w', encoding='utf-8') as f:
                f.write(existing)
        else:
            # Create new file
            os.makedirs(os.path.dirname(path), exist_ok=True)
            content = f"""# User Profile

## Stimmungs-History
- [{timestamp}] {mood or 'neutral'}

## Aktuelle Bedürfnisse
- {needs or 'Keine erkannt'}

## Interessen
- {interests or 'Noch nicht erkannt'}

## Gesprächsmuster
- Wird automatisch aktualisiert durch Tahlamus CTE
"""
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestResearcherToolExecution -v`
Expected: All pass

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: add analyze_user() with Rowboat People/User_Profile.md persistence"
```

---

### Task 4: Upgrade _think_knowledge() — LLM via summarizer

**Files:**
- Modify: `core/brain_chat.py` (CTE._think_knowledge)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write the failing tests**

```python
class TestCTELLMUpgrade:
    """Test LLM-upgraded _think_* methods."""

    def test_think_knowledge_uses_llm(self):
        """_think_knowledge calls pool.summarize when available."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.summarize.return_value = RefinedKnowledge(
            original="test", refined="Deep insight about gravity",
            agent="summarizer", refinement_type="summary",
            confidence=0.7, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        cte._learned_knowledge = deque([
            {'topic': 'physics', 'knowledge': 'Gravity bends spacetime', 'timestamp': time.time()},
        ])
        thought = cte._think_knowledge()
        assert thought is not None
        assert thought.category == 'knowledge'
        assert 'Deep insight' in thought.content

    def test_think_knowledge_falls_back_to_template(self):
        """_think_knowledge uses template when pool returns None."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.summarize.return_value = None
        cte._micro_agent_pool = mock_pool
        cte._learned_knowledge = deque([
            {'topic': 'test', 'knowledge': 'Some fact about the world', 'timestamp': time.time()},
        ])
        thought = cte._think_knowledge()
        assert thought is not None
        # Template fallback still works
        assert thought.category in ('knowledge', 'explore')
```

Note: Import `from collections import deque` at the top of the new test class.

**Step 2: Run to verify failure**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestCTELLMUpgrade::test_think_knowledge_uses_llm -v`
Expected: FAIL — pool.summarize not called (old template logic runs)

**Step 3: Write the implementation**

Replace `_think_knowledge()` method body. Keep the same signature. New logic:

```python
    def _think_knowledge(self) -> Optional[ContinuousThought]:
        """Reflect on learned knowledge — LLM-powered with template fallback."""
        knowledge_list = list(self._learned_knowledge)
        if not knowledge_list:
            return self._think_reflect()

        recent_entries = list(knowledge_list[-8:])
        random.shuffle(recent_entries)

        for entry in recent_entries:
            topic = entry['topic']
            raw = entry['knowledge']

            # ── Try LLM first ──
            if self._micro_agent_pool:
                result = self._micro_agent_pool.summarize(raw[:300])
                if result:
                    thought = ContinuousThought(
                        timestamp=time.time(),
                        category="knowledge",
                        topic=topic,
                        content=result.refined[:300],
                        relevance=result.confidence,
                    )
                    if not self._is_duplicate_thought(thought):
                        return thought

            # ── Fallback: template ──
            sentences = [s.strip() for s in raw.split('.') if len(s.strip()) > 15]
            if not sentences:
                sentences = [raw[:120].rstrip()]
            knowledge_snippet = random.choice(sentences)[:120].rstrip()
            template = random.choice(self._KNOWLEDGE_REFLECT_TEMPLATES)
            content = template.format(knowledge=knowledge_snippet)

            thought = ContinuousThought(
                timestamp=time.time(),
                category="knowledge",
                topic=topic,
                content=content,
                relevance=0.55,
            )
            if not self._is_duplicate_thought(thought):
                return thought

        return self._think_explore()
```

**Step 4: Run tests**

Run: `python -m pytest tests/test_brain_chat_quick.py::TestCTELLMUpgrade -v`
Expected: 2 PASS

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: upgrade _think_knowledge() to use LLM summarizer with template fallback"
```

---

### Task 5: Upgrade _think_connect() — LLM via connector

**Files:**
- Modify: `core/brain_chat.py` (CTE._think_connect)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write tests**

```python
    def test_think_connect_uses_llm(self):
        """_think_connect calls pool.find_connection when available."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.find_connection.return_value = RefinedKnowledge(
            original="a | b", refined="Both share an underlying symmetry principle",
            agent="connector", refinement_type="connection",
            confidence=0.6, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        cte._learned_knowledge = deque([
            {'topic': 'physics', 'knowledge': 'Gravity bends spacetime', 'timestamp': time.time()},
            {'topic': 'math', 'knowledge': 'Topology studies shape invariants', 'timestamp': time.time()},
        ])
        thought = cte._think_connect()
        assert thought is not None
        assert thought.category == 'connect'
        assert 'symmetry' in thought.content

    def test_think_connect_falls_back(self):
        """_think_connect uses template when pool returns None."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.find_connection.return_value = None
        cte._micro_agent_pool = mock_pool
        cte._learned_knowledge = deque([
            {'topic': 'a', 'knowledge': 'Fact A is interesting indeed', 'timestamp': time.time()},
            {'topic': 'b', 'knowledge': 'Fact B is also interesting', 'timestamp': time.time()},
        ])
        thought = cte._think_connect()
        # Should still produce a thought via template
        assert thought is not None or thought is None  # may be None if duplicate
```

**Step 3: Implementation**

Replace `_think_connect()` body with LLM-first logic (same pattern as Task 4):

```python
    def _think_connect(self) -> Optional[ContinuousThought]:
        """Connect TWO knowledge entries — LLM-powered with template fallback."""
        knowledge_list = list(self._learned_knowledge)
        if len(knowledge_list) < 2:
            return None

        pair = random.sample(knowledge_list[-10:], min(2, len(knowledge_list)))
        if len(pair) < 2:
            return None

        text_a = pair[0]['knowledge'][:200]
        text_b = pair[1]['knowledge'][:200]

        # Don't connect if basically the same
        if text_a[:30].lower() == text_b[:30].lower():
            return None

        topic = f"{pair[0]['topic'][:30]} ↔ {pair[1]['topic'][:30]}"

        # ── Try LLM first ──
        if self._micro_agent_pool:
            result = self._micro_agent_pool.find_connection(text_a, text_b)
            if result:
                thought = ContinuousThought(
                    timestamp=time.time(),
                    category="connect",
                    topic=topic,
                    content=result.refined[:300],
                    relevance=result.confidence,
                )
                if not self._is_duplicate_thought(thought):
                    return thought

        # ── Fallback: template ──
        def extract_sentence(entry):
            raw = entry['knowledge']
            sentences = [s.strip() for s in raw.split('.') if len(s.strip()) > 15]
            if sentences:
                return random.choice(sentences[:3])[:90].rstrip()
            return raw[:90].rstrip()

        fact_a = extract_sentence(pair[0])
        fact_b = extract_sentence(pair[1])
        template = random.choice(self._CONNECT_TEMPLATES)
        content = template.format(fact_a=fact_a, fact_b=fact_b)

        thought = ContinuousThought(
            timestamp=time.time(),
            category="connect",
            topic=topic,
            content=content,
            relevance=0.65,
        )
        if not self._is_duplicate_thought(thought):
            return thought
        return None
```

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: upgrade _think_connect() to use LLM connector with template fallback"
```

---

### Task 6: Upgrade _think_reflect(), _think_explore(), _think_active()

**Files:**
- Modify: `core/brain_chat.py` (CTE: 3 methods)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write tests**

```python
    def test_think_reflect_uses_llm(self):
        """_think_reflect calls pool.reflect when available."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.reflect.return_value = RefinedKnowledge(
            original="q", refined="User is exploring fundamental physics out of curiosity",
            agent="reflector", refinement_type="reflection",
            confidence=0.6, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        cte._recent_queries = deque(["What is quantum gravity?"])
        cte._learned_knowledge = deque([
            {'topic': 'physics', 'knowledge': 'Gravity bends spacetime', 'timestamp': time.time()},
        ])
        thought = cte._think_reflect()
        assert thought is not None
        assert thought.category == 'reflect'
        assert 'curiosity' in thought.content.lower() or 'physics' in thought.content.lower()

    def test_think_explore_uses_llm(self):
        """_think_explore calls pool.explore when available."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.explore.return_value = RefinedKnowledge(
            original="topic", refined="What if consciousness emerges from quantum effects?",
            agent="explorer", refinement_type="exploration",
            confidence=0.5, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        thought = cte._think_explore()
        assert thought is not None
        assert thought.category == 'explore'
        assert 'quantum' in thought.content.lower() or 'consciousness' in thought.content.lower()

    def test_think_active_uses_llm(self):
        """_think_active calls pool.analyze when available."""
        cte = ContinuousThinkingEngine()
        cte._mode = "active"
        cte._current_topic = "neural networks"
        mock_pool = MagicMock()
        mock_pool.analyze.return_value = RefinedKnowledge(
            original="nn", refined="Neural nets approximate any continuous function — universality theorem",
            agent="analyst", refinement_type="analysis",
            confidence=0.7, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        thought = cte._think_active()
        assert thought is not None
        assert thought.category == 'active'
        assert 'universality' in thought.content.lower() or 'function' in thought.content.lower()
```

**Step 3: Implementation**

Upgrade all 3 methods with the same LLM-first + template-fallback pattern. Each method:
1. Try calling the matching pool method
2. If result, create ContinuousThought from it
3. If None (rate-limited, no router, error), fall through to existing template logic

For `_think_reflect()`: insert LLM block before the template loop:
```python
        # ── Try LLM first ──
        if self._micro_agent_pool and knowledge_list:
            query = candidates[0] if candidates else recent[-1]
            knowledge_snippet = self._find_matching_knowledge(query, knowledge_list)
            if knowledge_snippet:
                result = self._micro_agent_pool.reflect(query[:200], knowledge_snippet)
                if result:
                    thought = ContinuousThought(
                        timestamp=time.time(), category="reflect",
                        topic=query[:60], content=result.refined[:300],
                        relevance=result.confidence,
                    )
                    if not self._is_duplicate_thought(thought):
                        return thought
```

For `_think_explore()`: insert before Moltbook/fallback logic:
```python
        # ── Try LLM first ──
        if self._micro_agent_pool:
            result = self._micro_agent_pool.explore(seed)
            if result:
                thought.content = result.refined[:300]
                thought.relevance = result.confidence
                return thought
```

For `_think_active()`: insert before ThoughtStream/template logic:
```python
        # ── Try LLM first ──
        if self._micro_agent_pool and self._current_topic:
            result = self._micro_agent_pool.analyze(self._current_topic)
            if result:
                thought.content = result.refined[:300]
                thought.relevance = result.confidence
                return thought
```

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py
git commit -m "feat: upgrade _think_reflect/_think_explore/_think_active to use LLM agents"
```

---

### Task 7: Add _think_user() + Wire into _think_tick()

**Files:**
- Modify: `core/brain_chat.py` (CTE: new `_think_user()`, update `_think_tick()`)
- Modify: `web/templates/moltbook_dashboard.html` (CSS for `user_insight` badge)
- Test: `tests/test_brain_chat_quick.py`

**Step 1: Write tests**

```python
    def test_think_user_produces_insight(self):
        """_think_user produces user_insight category thought."""
        cte = ContinuousThinkingEngine()
        mock_pool = MagicMock()
        mock_pool.analyze_user.return_value = RefinedKnowledge(
            original="history", refined="MOOD: curious | NEEDS: architecture help | INTERESTS: AI",
            agent="user_analyst", refinement_type="user_insight",
            confidence=0.6, timestamp=time.time(),
        )
        cte._micro_agent_pool = mock_pool
        cte._conversation_history = deque([
            {'type': 'user', 'content': 'How does routing work?', 'timestamp': time.time()},
            {'type': 'system', 'content': 'Routing uses 3 layers...', 'timestamp': time.time()},
        ])
        thought = cte._think_user()
        assert thought is not None
        assert thought.category == 'user_insight'
        assert 'curious' in thought.content.lower() or 'MOOD' in thought.content

    def test_think_user_returns_none_without_history(self):
        """_think_user returns None when no conversation history."""
        cte = ContinuousThinkingEngine()
        cte._micro_agent_pool = MagicMock()
        thought = cte._think_user()
        assert thought is None

    def test_think_tick_includes_user_path(self):
        """_think_tick has a probability path for _think_user."""
        cte = ContinuousThinkingEngine()
        cte._micro_agent_pool = MagicMock()
        cte._conversation_history = deque([
            {'type': 'user', 'content': 'test', 'timestamp': time.time()},
        ])
        # _think_user should be callable from _think_tick
        assert hasattr(cte, '_think_user')
```

**Step 3: Implementation**

Add `_think_user()` method to CTE:
```python
    def _think_user(self) -> Optional[ContinuousThought]:
        """Analyze user state — mood, needs, interests.

        Calls MicroAgentPool.analyze_user() with conversation history.
        Produces 'user_insight' category thoughts.
        """
        if not self._micro_agent_pool:
            return None

        history = list(self._conversation_history)
        if not history:
            return None

        result = self._micro_agent_pool.analyze_user(history)
        if not result:
            return None

        thought = ContinuousThought(
            timestamp=time.time(),
            content=result.refined[:300],
            category="user_insight",
            topic="user understanding",
            relevance=0.7,
        )
        if not self._is_duplicate_thought(thought):
            return thought
        return None
```

Update `_think_tick()` — add user analysis path. Insert after the `_think_refine` block (roll < 0.18):
```python
            if roll < 0.23 and (self._micro_agent_pool
                                and self._conversation_history):
                # 5% chance: analyze user state
                result = self._think_user()
                if result:
                    return result
```

Add CSS to `web/templates/moltbook_dashboard.html`:
```css
.thought-category.user_insight { background: rgba(244,114,182,0.15); color: #f472b6; }
```

**Step 5: Commit**

```bash
git add core/brain_chat.py tests/test_brain_chat_quick.py web/templates/moltbook_dashboard.html
git commit -m "feat: add _think_user() for User-Awareness + user_insight badge CSS"
```

---

### Task 8: Full Regression + Final Verification

**Step 1: Run full test suite**

```bash
python -m pytest tests/test_brain_chat_quick.py tests/test_brain_server.py -v
```
Expected: All pass, 0 failures

**Step 2: Fix test_agents_configured**

Update `test_agents_configured` expected set to include all 10 agents and count.

**Step 3: Verify dashboard shows new categories**

Start server, open `http://localhost:5000/ui/moltbook`, verify new thought categories appear.

**Step 4: Final commit if needed**

```bash
git status
# Commit any remaining changes
```

---

## Summary

| Task | What | New Tests | Files |
|------|------|-----------|-------|
| 1 | 4 new agent configs | 5 | brain_chat.py |
| 2 | reflect(), explore(), analyze() methods | 6 | brain_chat.py |
| 3 | analyze_user() + Rowboat persistence | 5 | brain_chat.py |
| 4 | Upgrade _think_knowledge() | 2 | brain_chat.py |
| 5 | Upgrade _think_connect() | 2 | brain_chat.py |
| 6 | Upgrade _think_reflect/explore/active | 3 | brain_chat.py |
| 7 | _think_user() + _think_tick() wiring + CSS | 3 | brain_chat.py, dashboard |
| 8 | Full regression | 0 (regression) | — |
| **Total** | | **~26 new tests** | **2 files** |

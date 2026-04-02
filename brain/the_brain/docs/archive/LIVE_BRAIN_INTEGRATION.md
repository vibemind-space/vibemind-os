# Live Brain Integration Guide

## Overview

The **Live Brain Monitor** provides real-time monitoring of agentic conversations with active intervention capabilities. The brain watches conversations as they happen and triggers interventions when failure patterns emerge, **before** the task completely fails.

## Quick Start

### 1. Initialize the System

```python
from core.meta_router import MetaRouter
from core.brain_monitor import BrainActivityMonitor
from core.strategy_library import StrategyLibrary
from core.live_brain_monitor import LiveBrainMonitor
from core.conversation_trace_encoder import load_session_logs

# Initialize components
meta_router = MetaRouter(enable_hippocampus=True, seed=42)
brain_monitor = BrainActivityMonitor(history_length=100)
strategy_lib = StrategyLibrary(max_strategies_per_type=20)

# Pre-train on existing session logs
log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
all_traces = load_session_logs(log_dir, limit=None)

for trace in all_traces:
    features = trace.get_features()
    if features['success']:
        strategy_lib.add_strategy(
            task_type=features['tool_type'],
            tool_sequence=features['tools_used'],
            duration=features['duration_seconds'],
            success=True
        )

# Initialize live monitor
live_monitor = LiveBrainMonitor(
    meta_router=meta_router,
    brain_monitor=brain_monitor,
    strategy_library=strategy_lib,
    error_threshold=5,           # Trigger at 5 errors
    repetition_threshold=3,      # Trigger at 3x same tool
    qa_reject_threshold=3,       # Trigger at 3 QA rejects
    check_interval=2             # Check every 2 tool calls
)
```

### 2. Monitor a Conversation

```python
# Start monitoring
conversation = live_monitor.start_conversation("Deploy application to production")

# Update as events occur
conversation.add_tool_call("docker_create")
conversation.add_agent("DockerOperator")
intervention = live_monitor.update(conversation)

# Check if intervention triggered
if intervention:
    print(f"INTERVENTION: {intervention['reason']}")
    print(f"Urgency: {intervention['urgency']}")
    if intervention['recommendation']:
        rec = intervention['recommendation']
        print(f"Recommended strategy: {rec['strategy']}")
        print(f"Success rate: {rec['success_rate']:.1%}")

# Add more events
conversation.add_error()
conversation.add_tool_call("docker_start")
intervention = live_monitor.update(conversation)

# End conversation
live_monitor.end_conversation(conversation, success=True, outcome="completed")
```

### 3. Integration with Existing Agent System

```python
class MyAgent:
    def __init__(self):
        # Initialize live brain monitor
        self.live_monitor = LiveBrainMonitor(...)
        self.current_conversation = None

    def execute_task(self, task_description):
        # Start monitoring
        self.current_conversation = self.live_monitor.start_conversation(task_description)

        try:
            # Your existing task execution logic
            for step in self.task_steps:
                # Execute step
                tool_name = step.execute()

                # Update brain
                self.current_conversation.add_tool_call(tool_name)
                intervention = self.live_monitor.update(self.current_conversation)

                # Handle intervention
                if intervention:
                    if intervention['urgency'] == 'critical':
                        # Terminate immediately
                        raise TaskTerminationException(intervention['reason'])
                    elif intervention['recommendation']:
                        # Try recommended strategy
                        self._try_alternative_strategy(intervention['recommendation'])

                # Track errors
                if step.failed:
                    self.current_conversation.add_error()

            # Success
            self.live_monitor.end_conversation(
                self.current_conversation,
                success=True,
                outcome="completed"
            )

        except Exception as e:
            # Failure
            self.live_monitor.end_conversation(
                self.current_conversation,
                success=False,
                outcome=str(e)
            )
```

## API Reference

### LiveBrainMonitor

#### Constructor Parameters

- **meta_router** (MetaRouter): Trained meta-router for prediction
- **brain_monitor** (BrainActivityMonitor): Brain activity monitor
- **strategy_library** (StrategyLibrary): Library of successful strategies
- **error_threshold** (int, default=5): Error count to trigger intervention
- **repetition_threshold** (int, default=3): Tool repetition to trigger
- **qa_reject_threshold** (int, default=3): QA reject count to trigger
- **clarification_threshold** (int, default=4): Clarification count to trigger
- **duration_multiplier** (float, default=2.0): Duration multiplier vs expected
- **check_interval** (int, default=3): Check every N tool calls

#### Methods

**start_conversation(task_description: str) -> LiveConversationState**
- Start monitoring a new conversation
- Returns conversation state object to update

**update(conversation: LiveConversationState) -> Optional[Dict]**
- Update brain with current state and check for interventions
- Returns intervention dict if triggered, None otherwise

**end_conversation(conversation, success: bool, outcome: str)**
- End monitoring and learn from conversation
- Adds successful strategies to library
- Updates meta-router with failure patterns

**get_statistics() -> Dict**
- Get monitoring statistics
- Returns conversations monitored, interventions triggered, etc.

**visualize_statistics() -> str**
- ASCII visualization of statistics

### LiveConversationState

#### Methods

**add_tool_call(tool_name: str)**
- Record a tool call
- Updates tool counts and detects repetition

**add_error()**
- Record an error

**add_clarification()**
- Record a user clarification request

**add_qa_reject()**
- Record a QA rejection

**add_agent(agent_name: str)**
- Record agent involvement

**add_context_switch()**
- Record a context switch

**get_duration() -> float**
- Get elapsed duration in seconds

**get_features() -> Dict**
- Get current features as dict (compatible with ConversationTrace)

### Intervention Dict Structure

```python
{
    'reason': str,              # Why intervention triggered
    'urgency': str,             # 'low', 'medium', 'high', 'critical'
    'message': str,             # Human-readable message
    'current_state': Dict,      # Current conversation features
    'recommendation': {         # Recommended strategy (if found)
        'strategy': List[str],           # Tool sequence
        'expected_duration': float,      # Expected time
        'success_rate': float,           # Success rate (0-1)
        'confidence': float              # Confidence score
    },
    'alternatives': List[Dict]  # Alternative strategies
}
```

## Intervention Triggers

The live brain monitor triggers interventions when:

1. **High Error Count** (urgency: high)
   - Error count >= error_threshold (default: 5)
   - Pattern: Task experiencing repeated failures

2. **Tool Repetition** (urgency: critical)
   - Same tool called >= repetition_threshold times (default: 3)
   - Pattern: Agent stuck in loop, repeatedly trying same approach

3. **QA Rejections** (urgency: high)
   - QA reject count >= qa_reject_threshold (default: 3)
   - Pattern: Output quality degrading

4. **User Confusion** (urgency: medium)
   - Clarification count >= clarification_threshold (default: 4)
   - Pattern: Task unclear or unresolvable

5. **Duration Exceeded** (urgency: medium)
   - Duration > expected_duration * duration_multiplier (default: 2.0x)
   - Pattern: Task taking much longer than expected

## Strategy Recommendation System

When intervention is triggered, the brain:

1. **Queries Strategy Library** for the task type
2. **Retrieves Top-K Strategies** (default: 3) ranked by quality score
3. **Computes Confidence** based on:
   - Success rate of strategy
   - Number of times used (usage_factor)
   - Recency (recency_factor)
4. **Provides Alternatives** for fallback options

### Quality Score Formula

```
quality_score = success_rate * 0.6 + usage_factor * 0.3 + recency_factor * 0.1

where:
  usage_factor = min(usage_count / 10.0, 1.0)
  recency_factor = exp(-recency_weight * last_used)
```

## Incremental Learning

After each conversation ends, the system:

1. **Adds Successful Strategies** to library
   - Stores tool sequence, duration, success rate
   - Updates existing strategies if already present

2. **Encodes Failures** in hippocampal memory
   - High-error traces encoded as episodic memories
   - Similar future situations retrieve past failures

3. **Updates Strategy Quality**
   - Adjusts success rates with exponential moving average
   - Increments usage counts
   - Updates recency timestamps

## Example Use Cases

### Use Case 1: GitHub API Task

```python
# Agent trying to access private repo
conversation = live_monitor.start_conversation("Clone private repository")

conversation.add_tool_call("github_get_repo")
conversation.add_error()  # 403 Forbidden

conversation.add_tool_call("github_list_notifications")
conversation.add_error()  # Still no access

# ... 3 more errors ...

conversation.add_error()  # Error count: 5
intervention = live_monitor.update(conversation)  # TRIGGERED!

# intervention['reason'] = "High error count (5)"
# intervention['urgency'] = "high"
# intervention['message'] = "Consider terminating - no proven strategies for github tasks"
```

### Use Case 2: Docker Deployment Loop

```python
conversation = live_monitor.start_conversation("Deploy container")

conversation.add_tool_call("docker_create")
conversation.add_tool_call("docker_start")
conversation.add_error()

conversation.add_tool_call("docker_logs")  # 1st
conversation.add_tool_call("docker_logs")  # 2nd
conversation.add_tool_call("docker_logs")  # 3rd - LOOP DETECTED!

intervention = live_monitor.update(conversation)  # TRIGGERED!

# intervention['reason'] = "Tool repetition detected (3x 'docker_logs')"
# intervention['urgency'] = "critical"
# intervention['recommendation'] = {
#     'strategy': ['docker_create', 'docker_start'],
#     'success_rate': 0.85,
#     'expected_duration': 108.0
# }
```

### Use Case 3: Quality Degradation

```python
conversation = live_monitor.start_conversation("Generate report")

conversation.add_tool_call("fetch_data")
conversation.add_tool_call("format_report")
conversation.add_qa_reject()  # QA: "Missing fields"

conversation.add_tool_call("fetch_data")
conversation.add_tool_call("format_report")
conversation.add_qa_reject()  # QA: "Still incomplete"

conversation.add_tool_call("format_report")
conversation.add_qa_reject()  # QA: "Format wrong"

intervention = live_monitor.update(conversation)  # TRIGGERED!

# intervention['reason'] = "QA rejected 3 times (quality degrading)"
# intervention['urgency'] = "high"
```

## Statistics and Monitoring

```python
# Get statistics
stats = live_monitor.get_statistics()
print(f"Conversations: {stats['conversations_monitored']}")
print(f"Interventions: {stats['interventions_triggered']}")
print(f"Failures Prevented: {stats['failures_prevented']}")

# Visualize
print(live_monitor.visualize_statistics())
```

Output:
```
================================================================================
LIVE BRAIN MONITOR STATISTICS
================================================================================

Conversations Monitored: 42
Interventions Triggered: 8
Failures Prevented: 5
Strategy Library Size: 23

RECENT INTERVENTIONS:
--------------------------------------------------------------------------------
1. Access private repository
   Reason: High error count (6)
   Urgency: high

2. Deploy container
   Reason: Tool repetition detected (3x 'docker_logs')
   Urgency: critical
...
================================================================================
```

## Advanced Configuration

### Custom Intervention Logic

```python
class CustomLiveBrainMonitor(LiveBrainMonitor):
    def _check_intervention_conditions(self, conversation):
        # Call parent logic
        intervention = super()._check_intervention_conditions(conversation)
        if intervention:
            return intervention

        # Add custom condition: High context switching
        if conversation.context_switches > 10:
            return self._generate_intervention(
                conversation,
                reason=f"Excessive context switching ({conversation.context_switches})",
                urgency="medium"
            )

        return None
```

### Custom Strategy Ranking

```python
class CustomStrategyLibrary(StrategyLibrary):
    def get_quality_score(self, recency_weight=0.1):
        # Custom weighting
        return self.success_rate * 0.5 + \
               self.usage_factor * 0.4 + \
               self.recency_factor * 0.1
```

## Integration with Production Systems

### 1. Logging Integration

```python
import logging

class LoggingLiveBrainMonitor(LiveBrainMonitor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger('brain_monitor')

    def update(self, conversation):
        intervention = super().update(conversation)

        if intervention:
            self.logger.warning(
                f"Intervention triggered: {intervention['reason']}",
                extra={'conversation_id': conversation.task}
            )

        return intervention
```

### 2. Metrics Export

```python
from prometheus_client import Counter, Gauge

interventions_total = Counter('brain_interventions_total', 'Total interventions')
failures_prevented = Counter('brain_failures_prevented', 'Failures prevented')
conversations_monitored = Gauge('brain_conversations_active', 'Active conversations')

class MetricsLiveBrainMonitor(LiveBrainMonitor):
    def update(self, conversation):
        intervention = super().update(conversation)

        if intervention:
            interventions_total.inc()

        return intervention

    def end_conversation(self, conversation, success, outcome):
        if success and self.intervention_count > 0:
            failures_prevented.inc()

        super().end_conversation(conversation, success, outcome)
        conversations_monitored.dec()
```

### 3. Alert System

```python
class AlertingLiveBrainMonitor(LiveBrainMonitor):
    def __init__(self, *args, alert_webhook=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.alert_webhook = alert_webhook

    def update(self, conversation):
        intervention = super().update(conversation)

        if intervention and intervention['urgency'] == 'critical':
            # Send alert
            self._send_alert(intervention)

        return intervention

    def _send_alert(self, intervention):
        if self.alert_webhook:
            import requests
            requests.post(self.alert_webhook, json={
                'text': f"CRITICAL: {intervention['reason']}",
                'urgency': intervention['urgency']
            })
```

## Performance Considerations

- **Check Interval**: Set `check_interval` appropriately
  - Lower values (1-2): More responsive, higher overhead
  - Higher values (5-10): Less overhead, delayed detection

- **Strategy Library Size**: Limit with `max_strategies_per_type`
  - Too many strategies: Slow retrieval
  - Too few: Limited recommendations

- **Memory Usage**: Hippocampal memories grow over time
  - Monitor `meta_router.thalamo_system.hippocampus.num_memories`
  - Consider periodic pruning of old memories

## Troubleshooting

### Interventions Not Triggering

**Check thresholds:**
```python
print(f"Error threshold: {live_monitor.error_threshold}")
print(f"Repetition threshold: {live_monitor.repetition_threshold}")
print(f"Check interval: {live_monitor.check_interval}")
```

**Verify updates:**
```python
# Make sure you're calling update()
intervention = live_monitor.update(conversation)
```

### No Recommendations Available

**Check strategy library:**
```python
print(f"Strategies: {strategy_lib.total_strategies}")
print(f"Task types: {list(strategy_lib.strategies.keys())}")
```

**Pre-train on more data:**
```python
# Load more session logs
all_traces = load_session_logs(log_dir, limit=None)  # Load ALL
```

### High False Positive Rate

**Adjust thresholds:**
```python
live_monitor = LiveBrainMonitor(
    ...,
    error_threshold=8,          # Raise from 5
    repetition_threshold=5,     # Raise from 3
    check_interval=5            # Check less frequently
)
```

## Next Steps

1. **Integrate with your agentic system** using the examples above
2. **Pre-train on your session logs** for domain-specific strategies
3. **Tune intervention thresholds** based on your task types
4. **Monitor statistics** to measure effectiveness
5. **Add custom intervention logic** for your specific use cases

## Files

- **Core**: `core/live_brain_monitor.py`
- **Demo**: `demos/live_brain_demo.py`
- **Dependencies**:
  - `core/meta_router.py`
  - `core/brain_monitor.py`
  - `core/strategy_library.py`
  - `core/conversation_trace_encoder.py`

# Temporal Memory (Phase 7)

## Overview

**Purpose**: Track and predict time-based patterns in task execution
**Inspired by**: Hippocampal time cells and temporal sequence learning
**Status**: ✅ ACTIVE

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│          TEMPORAL MEMORY SYSTEM                      │
│                                                      │
│  ┌────────────┐    ┌────────────┐    ┌───────────┐ │
│  │ Timestamp  │───▶│  Pattern   │───▶│ Temporal  │ │
│  │ Extraction │    │  Matching  │    │ Context   │ │
│  │            │    │            │    │           │ │
│  │ Hour, Day, │    │ Historical │    │ Predicted │ │
│  │  Week      │    │  Patterns  │    │  Timing   │ │
│  └────────────┘    └────────────┘    └───────────┘ │
│         │                 │                 │       │
│   Time Features     Pattern DB         Predictions  │
└──────────────────────────────────────────────────────┘
```

### Components

**1. Time Feature Extractor** (`core/temporal_memory.py:45-120`)
- Hour of day (0-23)
- Day of week (Monday-Sunday)
- Week of month (1-5)
- Season, business hours

**2. Pattern Database** (`core/temporal_memory.py:122-200`)
- Historical task timing patterns
- Peak hours for task types
- Temporal correlations

**3. Temporal Context Generator** (`core/temporal_memory.py:202-280`)
- Current time context
- Expected patterns
- Anomaly detection

---

## Input

### From HierarchicalPlanner
```python
{
    "timestamp": datetime,      # Current time
    "task_type": str,          # Task category
    "task_history": List[{     # Past tasks
        "timestamp": datetime,
        "task_type": str,
        "outcome": str
    }]
}
```

### Timestamp Example
```python
from datetime import datetime

timestamp = datetime.now()
# 2025-10-21 14:30:15 (Tuesday afternoon)
```

---

## Processing

### 1. Extract Time Features
```python
# Location: core/temporal_memory.py:45-120

def extract_time_features(timestamp):
    # Convert timestamp to temporal features
    hour = timestamp.hour                    # 0-23
    day_of_week = timestamp.weekday()        # 0=Monday, 6=Sunday
    week_of_month = (timestamp.day - 1) // 7 + 1  # 1-5

    # Time of day categorization
    if 6 <= hour < 12:
        time_of_day = 'morning'
    elif 12 <= hour < 18:
        time_of_day = 'afternoon'
    elif 18 <= hour < 22:
        time_of_day = 'evening'
    else:
        time_of_day = 'night'

    # Business hours
    is_business_hours = (9 <= hour < 17) and (day_of_week < 5)

    return {
        'hour': hour,
        'day_of_week': day_of_week,
        'day_name': ['monday', 'tuesday', 'wednesday', 'thursday',
                     'friday', 'saturday', 'sunday'][day_of_week],
        'week_of_month': week_of_month,
        'time_of_day': time_of_day,
        'is_business_hours': is_business_hours
    }
```

### 2. Match Temporal Patterns
```python
# Location: core/temporal_memory.py:122-200

def match_patterns(time_features, task_type):
    # Search pattern database for matches
    matching_patterns = []

    for pattern in self.pattern_db:
        # Check if pattern matches current time
        if pattern['task_type'] == task_type:
            # Time-of-day match
            if pattern['time_of_day'] == time_features['time_of_day']:
                confidence = 0.8
            # Day-of-week match
            elif pattern['day_of_week'] == time_features['day_of_week']:
                confidence = 0.6
            else:
                confidence = 0.3

            matching_patterns.append({
                'pattern': pattern['description'],
                'confidence': confidence,
                'frequency': pattern['count']
            })

    # Sort by confidence
    matching_patterns.sort(key=lambda p: p['confidence'], reverse=True)

    return matching_patterns[:5]  # Top 5
```

### 3. Generate Temporal Context
```python
# Location: core/temporal_memory.py:202-280

def generate_context(time_features, matching_patterns):
    # Build temporal context for prediction

    context = {
        'time_of_day': time_features['time_of_day'],
        'day_of_week': time_features['day_name'],
        'is_business_hours': time_features['is_business_hours'],
        'temporal_patterns': []
    }

    # Add matching patterns
    for pattern in matching_patterns:
        if pattern['confidence'] > 0.5:
            context['temporal_patterns'].append({
                'pattern': pattern['pattern'],
                'confidence': pattern['confidence']
            })

    # Anomaly detection
    current_hour = time_features['hour']
    if current_hour < 6 or current_hour >= 22:
        context['anomaly'] = 'unusual_hour'

    return context
```

### 4. Update Pattern Database
```python
# Location: core/temporal_memory.py:282-340

def update_patterns(timestamp, task_type, outcome):
    # Extract time features
    time_features = self.extract_time_features(timestamp)

    # Create pattern key
    pattern_key = f"{task_type}_{time_features['time_of_day']}_{time_features['day_of_week']}"

    # Update or create pattern
    if pattern_key in self.patterns:
        self.patterns[pattern_key]['count'] += 1
        if outcome == 'success':
            self.patterns[pattern_key]['successes'] += 1
    else:
        self.patterns[pattern_key] = {
            'task_type': task_type,
            'time_of_day': time_features['time_of_day'],
            'day_of_week': time_features['day_of_week'],
            'count': 1,
            'successes': 1 if outcome == 'success' else 0,
            'description': f"{task_type} tasks at {time_features['time_of_day']}"
        }
```

---

## Output

### API Response Format
```json
{
  "temporal_context": {
    "time_of_day": "afternoon",
    "day_of_week": "tuesday",
    "is_business_hours": true,
    "temporal_patterns": [
      {
        "pattern": "docker tasks spike at 9am on mondays",
        "confidence": 0.7
      },
      {
        "pattern": "debugging common in afternoons",
        "confidence": 0.6
      }
    ],
    "current_time": "2025-10-21T14:30:15",
    "anomaly": null
  }
}
```

---

## Data Flow

```
Input: Timestamp + Task History
         │
         ▼
┌─────────────────────┐
│ Extract Features    │
│ hour, day, week     │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Pattern Matching    │
│ Search pattern DB   │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│ Generate Context    │
│ Build temporal ctx  │
└─────────────────────┘
         │
         ▼
    Output: Temporal Context
```

---

## Example Usage

### In HierarchicalPlanner
```python
# Location: core/hierarchical_planner.py:522-545

# Generate temporal context
temporal_context = None
if self.enable_temporal_memory and self.temporal_memory:
    temporal_context = self.temporal_memory.generate_context(
        timestamp=datetime.now(),
        task_type=task_type
    )

    # Use temporal patterns for prediction
    if temporal_context.get('temporal_patterns'):
        # Adjust confidence based on patterns
        pattern_boost = sum(
            p['confidence'] for p in temporal_context['temporal_patterns']
        ) / len(temporal_context['temporal_patterns'])

        confidence *= (1.0 + pattern_boost * 0.2)
```

---

## Key Algorithms

### Time Feature Encoding
```
time_vector = [
    sin(2π·hour/24),      # Cyclic hour encoding
    cos(2π·hour/24),
    sin(2π·day/7),        # Cyclic day encoding
    cos(2π·day/7),
    one_hot(time_of_day)  # Categorical time
]
```

### Pattern Similarity
```
similarity = exp(-λ·|hour₁ - hour₂|) · δ(day₁, day₂)

where:
- λ: Time decay parameter (0.1)
- δ: Kronecker delta (1 if same day, 0.5 otherwise)
```

### Pattern Confidence
```
confidence = (successes / total) · log(1 + count)

where:
- successes/total: Success rate
- log(1 + count): Frequency bonus (more data = more confident)
```

---

## Performance

| Metric | Value |
|--------|-------|
| **Latency** | ~2ms |
| **Memory Usage** | ~500B |
| **Pattern DB Size** | ~100 patterns typical |

---

## Dependencies

- **datetime**: Timestamp manipulation
- **NumPy**: Vector operations

---

## Future Enhancements

1. **Long-Term Patterns**: Multi-week, seasonal trends
2. **Circadian Models**: Model user's daily rhythms
3. **Temporal Prediction**: Predict task duration
4. **Time Series Forecasting**: LSTM for temporal sequences
5. **Anomaly Detection**: Flag unusual timing patterns

---

## Related Files

- **Implementation**: `core/temporal_memory.py`
- **Integration**: `core/hierarchical_planner.py:522-545`
- **API**: `production/production_planner.py:411-428`
- **Tests**: `test_all_features_seeded.py`

# Tahlamus Production Deployment Guide

**Complete guide for deploying Tahlamus with learned routing matrix in production**

---

## 📦 What You Get

### Complete Production System:
1. **`ProductionPlanner`** - Main production class with matrix management
2. **REST API Server** - Flask-based HTTP API
3. **Client Library** - Python client for easy integration
4. **Continuous Learning** - Real-time matrix updates from feedback
5. **Matrix Versioning** - Save/load different matrix versions
6. **Monitoring** - Performance tracking and statistics

---

## 🚀 Quick Start

### 1. Train Routing Matrix

```bash
# Train matrix with improved method
python demos/train_routing_matrix_improved.py

# Or save from existing training
python production/save_trained_matrix.py
```

**Output**:
```
Saved trained matrix: production/trained_matrices/routing_matrix_v20250115_trained.npy
Matrix norm: 1.338
Accuracy: 75%
```

### 2. Start API Server

```bash
python production/api_server.py
```

**Output**:
```
======================================================================
TAHLAMUS PRODUCTION API SERVER
======================================================================

API Endpoints:
  POST   /predict        - Make a prediction
  POST   /feedback       - Submit feedback
  GET    /stats          - Get statistics
  GET    /matrices       - List matrix versions
  POST   /save_matrix    - Save current matrix
  POST   /load_matrix    - Load specific matrix
  GET    /health         - Health check

Server running on http://localhost:5001
======================================================================
```

### 3. Use in Your Application

```python
from production.example_client import TahlamusClient

# Initialize client
client = TahlamusClient("http://localhost:5001")

# Make prediction
result = client.predict("Deploy with Docker immediately")

print(f"Action: {result['prediction']['primary_action']}")
print(f"Confidence: {result['prediction']['confidence']:.1%}")

# Submit feedback after execution
client.submit_feedback(
    task="Deploy with Docker immediately",
    prediction=result,
    success=True,
    user_rating=0.9
)
```

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      YOUR APPLICATION                           │
│                                                                 │
│  ┌────────────────┐                                            │
│  │ User Request   │                                            │
│  │ "Deploy Docker"│                                            │
│  └────────┬───────┘                                            │
│           │                                                     │
│           v                                                     │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ TahlamusClient (Python)                                │    │
│  │ client.predict(task)                                   │    │
│  └────────────────────┬───────────────────────────────────┘    │
└─────────────────────│─────────────────────────────────────────┘
                      │ HTTP POST /predict
                      v
┌─────────────────────────────────────────────────────────────────┐
│              TAHLAMUS API SERVER (Flask)                        │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ ProductionPlanner                                      │    │
│  │                                                        │    │
│  │  ┌──────────────────────────────────────────────┐     │    │
│  │  │ Trained Routing Matrix (Loaded)              │     │    │
│  │  │ - Version: v20250115_trained                 │     │    │
│  │  │ - Accuracy: 75%                              │     │    │
│  │  │ - Confidence: 54%                            │     │    │
│  │  └──────────────────────────────────────────────┘     │    │
│  │                                                        │    │
│  │  ┌──────────────────────────────────────────────┐     │    │
│  │  │ Hierarchical Planner (3 Layers)              │     │    │
│  │  │ - Layer 1: TaskFeatureRouter                 │     │    │
│  │  │ - Layer 2: ConversationPathPlanner           │     │    │
│  │  │ - Layer 3: DecisionRouter                    │     │    │
│  │  └──────────────────────────────────────────────┘     │    │
│  │                                                        │    │
│  │  ┌──────────────────────────────────────────────┐     │    │
│  │  │ Continuous Learning Engine                   │     │    │
│  │  │ - Collects feedback                          │     │    │
│  │  │ - Updates matrix online (LR=0.005)           │     │    │
│  │  │ - Saves feedback batches                     │     │    │
│  │  └──────────────────────────────────────────────┘     │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                      │ JSON Response
                      v
┌─────────────────────────────────────────────────────────────────┐
│                      YOUR APPLICATION                           │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Prediction Result:                                     │    │
│  │ {                                                      │    │
│  │   "primary_action": "suggest",                         │    │
│  │   "primary_weight": 0.65,                              │    │
│  │   "confidence": 0.70,                                  │    │
│  │   "alternatives": [...]                                │    │
│  │ }                                                      │    │
│  └────────────────────────────────────────────────────────┘    │
│           │                                                     │
│           v                                                     │
│  ┌────────────────┐                                            │
│  │ Execute Action │                                            │
│  │ Monitor Result │                                            │
│  └────────┬───────┘                                            │
│           │                                                     │
│           v                                                     │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ Submit Feedback:                                       │    │
│  │ client.submit_feedback(success=True, rating=0.9)       │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📚 Detailed Usage

### ProductionPlanner Class

```python
from production.production_planner import ProductionPlanner

# Initialize
planner = ProductionPlanner(
    session_log_dir="path/to/sessions",
    matrix_dir="production/trained_matrices",
    feedback_dir="production/feedback",
    matrix_version="v20250115_trained",  # Specific version or None for latest
    enable_continuous_learning=True,
    learning_rate=0.005  # Conservative for production
)

# Make prediction
result = planner.predict("Deploy with Docker urgently")

# Access prediction details
primary_action = result['prediction']['primary_action']
confidence = result['prediction']['confidence']
reasoning = result['prediction']['primary_reasoning']

# Submit feedback after execution
planner.submit_feedback(
    task="Deploy with Docker urgently",
    prediction=result,
    actual_action="suggest",  # What was actually done
    success=True,            # Did it work?
    user_rating=0.85,        # User satisfaction (0-1)
    execution_time_ms=1500   # How long did it take?
)

# Save updated matrix periodically
planner.save_matrix(
    version_name="v_after_100_feedbacks",
    notes="Matrix after processing 100 user feedbacks"
)

# Get statistics
stats = planner.get_statistics()
print(f"Accuracy: {stats['recent_accuracy']:.1%}")
print(f"Confidence: {stats['recent_avg_confidence']:.3f}")
```

### REST API Endpoints

#### POST /predict
**Request**:
```json
{
    "task": "Deploy with Docker immediately"
}
```

**Response**:
```json
{
    "task": "Deploy with Docker immediately",
    "prediction": {
        "primary_action": "suggest",
        "primary_weight": 0.65,
        "primary_reasoning": "Proactive guidance based on tool_trace + threat",
        "alternatives": [
            {"action": "retry", "weight": 0.25},
            {"action": "wait", "weight": 0.08}
        ],
        "confidence": 0.70,
        "processing_mode": "urgent",
        "task_type": "docker",
        "complexity": 0.40,
        "urgency": 0.90
    },
    "brain_state": {
        "dominant_modalities": ["tool_trace", "error_signal", "threat"],
        "gates": [0.05, 0.05, ..., 0.30]
    },
    "reasoning_chain": [
        "L1: Task classified as 'docker' (complexity=0.40, urgency=0.90)",
        "L2: Predicted sequence: build_image -> test -> deploy",
        "L3: Primary intervention: suggest (weight=65%)",
        ...
    ]
}
```

#### POST /feedback
**Request**:
```json
{
    "task": "Deploy with Docker immediately",
    "prediction": {...},  // From /predict response
    "actual_action": "suggest",
    "success": true,
    "user_rating": 0.9,
    "execution_time_ms": 1500
}
```

**Response**:
```json
{
    "message": "Feedback received",
    "total_feedback": 42,
    "continuous_learning": true
}
```

#### GET /stats
**Response**:
```json
{
    "total_predictions": 150,
    "total_feedback": 142,
    "current_matrix_version": "v20250115_trained",
    "continuous_learning_enabled": true,
    "learning_rate": 0.005,
    "recent_accuracy": 0.85,
    "recent_avg_confidence": 0.54,
    "feedback_buffer_size": 3
}
```

#### GET /matrices
**Response**:
```json
{
    "matrices": [
        {
            "version": "v20250115_trained",
            "timestamp": "2025-01-15T12:00:00",
            "accuracy": 0.75,
            "num_predictions": 500,
            "avg_confidence": 0.54,
            "notes": "Trained with improved method"
        },
        {
            "version": "v20250110_baseline",
            "timestamp": "2025-01-10T09:00:00",
            "accuracy": 0.60,
            "num_predictions": 200,
            "avg_confidence": 0.42,
            "notes": "Baseline random matrix"
        }
    ]
}
```

---

## ⚙️ Configuration

### Environment Variables

```bash
# API Server
export TAHLAMUS_PORT=5001
export TAHLAMUS_HOST=0.0.0.0

# Paths
export TAHLAMUS_SESSION_DIR=/path/to/sessions
export TAHLAMUS_MATRIX_DIR=/path/to/matrices
export TAHLAMUS_FEEDBACK_DIR=/path/to/feedback

# Learning
export TAHLAMUS_LEARNING_RATE=0.005
export TAHLAMUS_ENABLE_LEARNING=true
```

### Matrix Versioning Strategy

```
production/trained_matrices/
├── routing_matrix_v20250115_trained.npy      # Initial trained matrix
├── routing_matrix_v20250115_trained.json     # Metadata
├── routing_matrix_v20250116_update1.npy      # After 100 feedbacks
├── routing_matrix_v20250116_update1.json
├── routing_matrix_v20250117_update2.npy      # After 500 feedbacks
└── routing_matrix_v20250117_update2.json
```

**Best Practices**:
1. Save matrix every 100 feedbacks
2. Keep last 10 versions
3. Tag stable versions (e.g., `v_stable_20250115`)
4. A/B test new versions before full rollout

---

## 📊 Monitoring & Metrics

### Key Metrics to Track

```python
stats = planner.get_statistics()

# 1. Accuracy (most important!)
accuracy = stats['recent_accuracy']
# Target: > 75%

# 2. Confidence
confidence = stats['recent_avg_confidence']
# Target: 0.40 - 0.60 (balanced)

# 3. Feedback rate
feedback_rate = stats['total_feedback'] / stats['total_predictions']
# Target: > 80% (most predictions get feedback)

# 4. Matrix stability
# Check if matrix is converging (not changing too much)
```

### Logging

```python
import logging

logging.basicConfig(level=logging.INFO)

# Logs will show:
# - Each prediction made
# - Feedback received
# - Matrix updates
# - Accuracy changes
```

### Performance Monitoring

```python
import time

start = time.time()
result = planner.predict(task)
latency_ms = (time.time() - start) * 1000

# Target latency: < 100ms for predict()
```

---

## 🔄 Continuous Learning Workflow

```
┌─────────────────────────────────────────────────┐
│ 1. User makes request                           │
│    "Deploy with Docker"                         │
└───────────────────┬─────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────┐
│ 2. System makes prediction                      │
│    primary_action: "suggest" (65%)              │
│    confidence: 70%                              │
└───────────────────┬─────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────┐
│ 3. Action executed                              │
│    Execute "suggest" intervention               │
│    Monitor outcome                              │
└───────────────────┬─────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────┐
│ 4. Feedback collected                           │
│    success: True                                │
│    user_rating: 0.9                             │
│    execution_time: 1500ms                       │
└───────────────────┬─────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────┐
│ 5. Matrix updated (if continuous learning ON)   │
│    Strengthen: brain_gates -> "suggest"         │
│    Learning rate: 0.005 (conservative)          │
└───────────────────┬─────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────┐
│ 6. Feedback saved to disk                       │
│    Every 10 feedbacks                           │
│    production/feedback/feedback_TIMESTAMP.json  │
└───────────────────┬─────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────┐
│ 7. Matrix saved periodically                    │
│    Every 100 predictions                        │
│    New version created                          │
└─────────────────────────────────────────────────┘
```

---

## 🧪 A/B Testing

### Setup Two Versions

```python
# Version A: Current production matrix
planner_a = ProductionPlanner(
    matrix_version="v20250115_stable",
    enable_continuous_learning=False  # Frozen
)

# Version B: New experimental matrix
planner_b = ProductionPlanner(
    matrix_version="v20250116_experimental",
    enable_continuous_learning=True  # Still learning
)

# Route 90% to A, 10% to B
import random

def get_prediction(task):
    if random.random() < 0.9:
        return planner_a.predict(task), "A"
    else:
        return planner_b.predict(task), "B"

# Track metrics per version
metrics_a = {'accuracy': [], 'confidence': []}
metrics_b = {'accuracy': [], 'confidence': []}

# After N predictions, compare
if metrics_b['accuracy'] > metrics_a['accuracy']:
    print("Version B is better! Promote to production.")
    # planner_b.save_matrix(version_name="v_new_stable")
```

---

## 🔐 Security Considerations

1. **API Authentication**: Add API keys/JWT tokens
2. **Rate Limiting**: Prevent abuse
3. **Input Validation**: Sanitize task descriptions
4. **Matrix Integrity**: Sign/hash matrix files
5. **Feedback Validation**: Verify feedback sources

---

## 📈 Performance Optimization

### 1. Matrix Caching
```python
# Cache frequently used matrices in memory
matrix_cache = {}

def load_matrix_cached(version):
    if version not in matrix_cache:
        matrix_cache[version] = np.load(f".../{version}.npy")
    return matrix_cache[version]
```

### 2. Batch Predictions
```python
# Process multiple predictions in parallel
from concurrent.futures import ThreadPoolExecutor

def predict_batch(tasks):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(planner.predict, tasks))
    return results
```

### 3. Async Feedback
```python
# Don't wait for feedback to be processed
from threading import Thread

def submit_feedback_async(task, prediction, **kwargs):
    Thread(target=lambda: planner.submit_feedback(
        task, prediction, **kwargs
    )).start()
```

---

## 🎯 Summary

**You now have a complete production system with**:

✅ **Trained Routing Matrix** (75% accuracy, 54% confidence)
✅ **REST API Server** (Flask, 7 endpoints)
✅ **Python Client Library** (Easy integration)
✅ **Continuous Learning** (Online updates from feedback)
✅ **Matrix Versioning** (Save/load/compare)
✅ **Monitoring** (Stats, logs, metrics)
✅ **A/B Testing** (Compare matrix versions)

**Ready for production deployment!** 🚀

---

## 📞 Next Steps

1. **Deploy API Server**: Run on production server with gunicorn/uwsgi
2. **Integrate Client**: Add to your application
3. **Collect Feedback**: Start gathering real user feedback
4. **Monitor Performance**: Track accuracy/confidence over time
5. **Iterate**: Retrain periodically with accumulated feedback

**Questions? Check the code examples in `production/` directory!**

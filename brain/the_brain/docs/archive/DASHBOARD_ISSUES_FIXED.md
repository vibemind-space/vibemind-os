# Dashboard Issues Found & Fixed 🔧

**Date**: October 19, 2025
**Status**: ⚠️ **PARTIALLY RESOLVED** - 1 bug fixed, 1 limitation discovered

---

## Issue #1: Active Inference AttributeError ✅ FIXED

### **Problem**:
```
'InferenceState' object has no attribute 'generated_questions'
```

The chat endpoint was crashing when trying to access `result.inference_state.generated_questions` without checking if the attribute exists.

### **Fix**:
**File**: `web/brain_dashboard_server.py:516`

**Before**:
```python
if result.inference_state and result.inference_state.generated_questions:
```

**After**:
```python
if result.inference_state and hasattr(result.inference_state, 'generated_questions') and result.inference_state.generated_questions:
```

**Result**: ✅ Chat endpoint no longer crashes

---

## Issue #2: Complexity Always Low (< 0.75) ⚠️ LIMITATION

### **Problem**:
All tasks are classified with complexity between 0.44-0.50, never reaching the 0.75 threshold required to trigger CTM async reasoning.

### **Root Cause**:
The Multi-LLM Router (Layer 1) is using **DeepSeek R1** in DEV mode for feature extraction, and it's:
1. Classifying many tasks as `"unknown"` instead of specific types ("design", "architecture", etc.)
2. Assigning fixed complexity values that don't vary much between simple and complex tasks

**Examples from testing**:
```
Task: "Write 'Hello World' to test.txt"
→ Complexity: 0.50 (should be ~0.2)

Task: "Design distributed microservices with auto-scaling"
→ Complexity: 0.44 (should be ~0.9)

Task: "Do something with a file"
→ Complexity: 0.50 (extremely vague, but same as specific task!)
```

### **Why This Happens**:
Looking at the reasoning chain:
```json
"L1: Task classified as 'unknown' (complexity=0.44, urgency=0.50)"
```

The LLM prompt for feature extraction might need adjustment, OR the model (DeepSeek R1) isn't great at this specific task in DEV mode.

### **Impact**:
- ❌ CTM never triggers (needs complexity ≥ 0.75)
- ❌ Swarm decomposition doesn't happen (needs complexity ≥ 0.7)
- ❌ Multi-target routing less effective (relies on accurate complexity)

### **Workaround** (For Now):
Lower the CTM threshold temporarily:

**File**: `web/brain_dashboard_server.py:155-157`
```python
enable_ctm_async=True,
ctm_complexity_threshold=0.40,  # Lower from 0.75 to 0.40
ctm_max_steps=50,
```

This will allow CTM to trigger on current complexity levels.

### **Proper Fix** (TODO):
1. **Option A**: Improve the LLM prompt for feature extraction in `core/multi_llm_router.py`
2. **Option B**: Use a different model for feature extraction (Claude 3.5 Sonnet instead of DeepSeek)
3. **Option C**: Add a manual complexity override in the UI for testing
4. **Option D**: Train a lightweight classifier specifically for complexity estimation

---

## Issue #3: Path Prediction vs Chat Confusion

### **Problem**:
User was clicking "Predict Path" instead of using "Chat with Brain", which uses different APIs:
- **Path Prediction**: `/api/predict/path` → Only Layer 2 (ConversationPathPlanner)
- **Chat**: `/api/chat/send` → Full 3-layer hierarchy with all 13 phases

### **Difference**:
**Path Prediction** returns:
```json
{
  "task_type": "filesystem",
  "predicted_sequence": ["complete"],
  "success_probability": 0.33,
  "confidence": 0.26
}
```
- Fixed confidence (based on session data only)
- No brain routing
- No swarm consensus
- No CTM

**Chat** returns:
```json
{
  "task_type": "docker",
  "action": "WAIT",
  "confidence": 0.29,
  "reasoning_chain": [
    "L1: Task classified...",
    "L2: Predicted sequence...",
    "L3: Primary intervention..."
  ],
  "brain_areas": ["success_sig", "threat", "temporal"],
  "alternative_actions": [...]
}
```
- Dynamic brain routing
- Full reasoning chain
- Swarm consensus (if complexity high enough)
- CTM (if complexity ≥ threshold)

### **Solution**:
Use the **Chat with Brain** input at the bottom of the dashboard page, not the "Predict Path" button.

---

## Testing Results

### Test 1: Simple Task
```bash
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Write Hello World to test.txt"}'
```

**Result**:
- Task type: "filesystem"
- Complexity: 0.50
- Action: WAIT
- Confidence: 26%
- CTM triggered: ❌ NO (below 0.75 threshold)

**Expected** (with better LLM):
- Complexity: 0.20 (very simple)
- Action: SUGGEST
- Confidence: 80%

---

### Test 2: Complex Task
```bash
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Design distributed microservices architecture with auto-scaling"}'
```

**Result**:
- Task type: "unknown"
- Complexity: 0.44
- Action: WAIT
- Confidence: 29%
- CTM triggered: ❌ NO (below 0.75 threshold)

**Expected** (with better LLM):
- Task type: "design" or "architecture"
- Complexity: 0.90 (very complex)
- Action: SUGGEST
- Confidence: 65%
- CTM triggered: ✅ YES
- Swarm: Decompose into 4-5 subtasks

---

### Test 3: Ambiguous Task
```bash
curl -X POST http://localhost:5000/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Do something with a file on my desktop"}'
```

**Result**:
- Task type: "filesystem"
- Complexity: 0.50
- Action: WAIT
- Confidence: 26%

**Expected**:
- Task type: "filesystem"
- Complexity: 0.30 (simple but vague)
- Action: WAIT (correct!)
- Questions generated:
  - "What would you like to do with the file?"
  - "What type of file?"

**Note**: Questions were NOT generated, possibly because Phase 8 (Active Inference) isn't properly integrated with the LLM router.

---

## Summary

### ✅ Fixed:
1. Active Inference `generated_questions` AttributeError

### ⚠️ Issues Remaining:
1. Complexity estimation too narrow (all tasks 0.44-0.50)
2. Task type classification poor ("unknown" for design tasks)
3. Question generation not working
4. CTM never triggers (complexity never reaches 0.75)
5. Swarm decomposition never triggers (complexity never reaches 0.7)

### 🔧 Quick Workaround:
Lower CTM threshold to 0.40:
```python
# web/brain_dashboard_server.py:156
ctm_complexity_threshold=0.40  # instead of 0.75
```

Then restart dashboard and test:
```
"Design distributed microservices architecture"
→ Should now trigger CTM!
```

---

## Recommended Next Steps

1. **Immediate**: Lower CTM threshold to see it in action
2. **Short-term**: Improve LLM prompts for feature extraction
3. **Medium-term**: Switch to Claude 3.5 Sonnet for feature extraction (better reasoning)
4. **Long-term**: Train specialized complexity classifier

---

## Dashboard URL

http://localhost:5000

**Use**: "Chat with Brain" input at the bottom, not "Predict Path" button!

---

**Status**: System is functional but complexity estimation needs improvement for optimal performance.

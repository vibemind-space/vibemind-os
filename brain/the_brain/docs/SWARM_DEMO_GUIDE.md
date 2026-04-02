# Swarm Visualization Demo Guide

## Overview

**File**: `web/swarm_visualization_demo.html`

Interactive step-by-step visualization showing how Tahlamus Brain and AutoGen Swarm work together.

## How to Run

### Option 1: Open Directly
```bash
# Windows
start web/swarm_visualization_demo.html

# Mac/Linux
open web/swarm_visualization_demo.html
```

### Option 2: Via Browser
1. Navigate to `C:\Users\User\Desktop\Tahlamus\web\`
2. Double-click `swarm_visualization_demo.html`

## What the Demo Shows

### 12-Step Workflow

**Task**: "Deploy Docker container with Redis and health monitoring"

#### Steps:

1. **User Input**
   - User submits task

2. **Memory Systems** (🧩)
   - Retrieves 2 past Redis deployments
   - Success rate: 100%

3. **Predictive Coding** (🔮)
   - Low novelty detected
   - Confidence: HIGH

4. **Attention Mechanisms** (👁️)
   - Focus: tool_trace modality

5. **Compositional Reasoning** (🧱)
   - Breaks into subtasks:
     - pull_redis_image
     - create_container
     - configure_health_check

6. **Brain Analysis Complete**
   - Task Type: docker
   - Confidence: 0.85
   - Routes to docker_execution_agent

7. **Coordinator Routes** (🎯)
   - Hands off to Docker Agent

8. **Docker Agent Executes** (🐳)
   - Uses brain recommendations:
     - Tool: docker-compose
     - Memory: 2GB limit
     - Follows 3-step breakdown

9. **Docker → Monitoring Handoff** (🔄)
   - Container created: redis_1
   - Hands to Monitoring Agent

10. **Monitoring Agent** (📊)
    - Sets up health checks (30s interval)
    - Status: HEALTHY

11. **Monitoring → Coordinator Handoff** (✅)
    - Returns to Coordinator

12. **Learning & Completion** (🎯)
    - Meta-Learning updates success rate
    - Routing matrix updated
    - Memory consolidated

## Features

### Brain Features Panel (Left)
Shows **13 cognitive features** activating in real-time:
- 🧩 Memory Systems
- 🔮 Predictive Coding
- 👁️ Attention Mechanisms
- 🎯 Meta-Learning
- ⚡ Neuromodulation
- ⏰ Temporal Memory
- ❓ Active Inference
- 🧱 Compositional Reasoning
- 🔧 Tool Creation
- 🌟 Consciousness Metrics
- ♾️ Infinite Chat
- 🔍 Semantic Coherence
- 🧠 CTM Async

### Conversation Flow Panel (Center)
Shows message stream:
- 🟣 **Purple**: User input
- 🟠 **Orange**: Brain analysis
- 🟢 **Green**: Agent actions
- 🔴 **Red**: Handoffs

### Swarm Agents Panel (Bottom)
Shows **15 specialized agents**:
- 🎯 Coordinator
- 🐳 Docker Agent
- 🗄️ Database Agent
- 🌐 API Agent
- 🐛 Debugging Agent
- 📊 Monitoring Agent
- 🚀 Deployment Agent
- ✅ Testing Agent
- ♻️ Refactoring Agent
- 📝 Documentation Agent
- 🔒 Security Agent
- ❓ Active Inference
- 🧠 CTM Reasoning
- 💾 Memory Agent
- ⚙️ General Execution

## Controls

- **▶ Start Demo**: Begin from step 1
- **◀ Previous**: Go back one step
- **Next ▶**: Advance one step
- **↻ Reset**: Clear and start over

## Visual Indicators

### Active Elements
- **Green glow**: Active brain features
- **Blue glow**: Active agents
- **Smooth animations**: Fade in/out transitions

### Message Types
- **Border color** indicates message type
- **Background tint** shows category
- **Timestamp** for each message

## What You'll See

### 1. Brain-Guided Routing
Watch how the brain analyzes the task using multiple cognitive features simultaneously, then suggests the best agent.

### 2. Agent Handoffs
See agents coordinate through handoffs:
```
Coordinator → Docker Agent → Monitoring Agent → Coordinator
```

### 3. Brain Integration
Observe agents using brain features:
- **Memory**: Past experiences
- **Compositional**: Task breakdown
- **Tool Creation**: Tool recommendations

### 4. Continuous Learning
Final step shows the brain learning from the successful execution.

## Key Insights

### Multi-Feature Activation
The brain uses **multiple features simultaneously**:
- Memory + Predictive Coding + Attention (Steps 2-4)
- Memory + Compositional + Tool (Step 8)
- Memory + Meta-Learning + Neuromodulation (Step 12)

### Intelligent Handoffs
Agents hand off based on **expertise**:
- Docker for container management
- Monitoring for health checks
- Coordinator for orchestration

### Feedback Loop
The system **learns from execution**:
- Success rates updated
- Routing matrix improved
- Memory consolidated

## Customization

### Add New Steps
Edit `demoSteps` array in the HTML:
```javascript
{
    description: "Your step description",
    message: {
        type: 'agent',  // 'user', 'brain', 'agent', 'handoff'
        sender: 'Agent Name',
        content: 'Message content'
    },
    brainActive: ['memory', 'attention'],  // Active brain features
    agentsActive: ['docker', 'monitoring']  // Active agents
}
```

### Change Colors
Edit CSS gradients:
```css
background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
```

### Add More Agents
Add to `agents` array:
```javascript
{ id: 'your_agent', name: 'Your Agent', icon: '🤖', status: 'Idle' }
```

## Use Cases

1. **Demo to stakeholders**: Show how the system works
2. **Training**: Teach team about brain-swarm architecture
3. **Debugging**: Visualize execution flow
4. **Documentation**: Explain complex workflows visually

## Next Steps

1. Open the demo in browser
2. Click "▶ Start Demo"
3. Step through to see brain + swarm coordination
4. Try "Reset" and "Previous" to explore

**The demo runs entirely in the browser - no server needed!** 🎉

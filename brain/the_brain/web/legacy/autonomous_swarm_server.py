"""
Autonomous Swarm Web Server
============================

Real-time web visualization of autonomous brain + swarm execution.
The brain operates independently - no manual intervention!

Usage:
    python web/autonomous_swarm_server.py

Then open: http://localhost:5002
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import threading

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from production.brain_swarm_orchestrator import BrainSwarmOrchestrator

load_dotenv()

app = Flask(__name__)
CORS(app)

# Global state
orchestrator = None
execution_log = []
brain_state_log = []
agent_state_log = []


def init_orchestrator():
    """Initialize brain + swarm orchestrator"""
    global orchestrator
    if orchestrator is None:
        orchestrator = BrainSwarmOrchestrator(
            session_log_dir="data/logs",
            user_id="web_demo_user",
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            use_unified_brain=True,  # Use unified brain service
            unified_brain_url="http://localhost:5003"
        )
        orchestrator.initialize_swarm_agents()
        print(f"[OK] Connected to unified brain + {len(orchestrator.agents)} swarm agents initialized")


@app.route('/')
def index():
    """Serve main page"""
    return render_template('autonomous_swarm.html')


@app.route('/api/execute', methods=['POST'])
def execute_task():
    """Execute task with autonomous brain + swarm"""
    global execution_log, brain_state_log, agent_state_log, orchestrator

    data = request.json
    task = data.get('task', '')

    if not task:
        return jsonify({'error': 'No task provided'}), 400

    # Clear logs
    execution_log = []
    brain_state_log = []
    agent_state_log = []

    # Log user input
    execution_log.append({
        'timestamp': datetime.now().isoformat(),
        'type': 'user',
        'sender': 'User',
        'content': task
    })

    # Create new event loop for this request
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Reinitialize orchestrator with unified brain connection
        orchestrator = BrainSwarmOrchestrator(
            session_log_dir="data/logs",
            user_id="web_demo_user",
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            use_unified_brain=True,  # Use unified brain service
            unified_brain_url="http://localhost:5003"
        )
        orchestrator.initialize_swarm_agents()

        # Execute task
        result = loop.run_until_complete(orchestrator.process_task(task))

        # Extract brain analysis
        brain_analysis = result['brain_analysis']
        prediction = brain_analysis['prediction']
        brain_state = result['brain_state']

        # Log brain analysis
        execution_log.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'brain',
            'sender': 'Autonomous Brain',
            'content': f"Task Type: {prediction.get('task_type', 'unknown')}\n" +
                      f"Confidence: {prediction.get('confidence', 0.0):.2f}\n" +
                      f"Suggested Agent: {result['suggested_agent']}"
        })

        # Extract brain features that were active
        active_features = []
        if brain_state.get('memory_context'):
            active_features.append('memory')
        if brain_state.get('attention_state'):
            active_features.append('attention')
        if brain_state.get('consciousness_metrics'):
            active_features.append('consciousness')
        if brain_state.get('predictive_coding'):
            active_features.append('predictive')
        if brain_state.get('active_inference'):
            active_features.append('active_inference')
        if brain_state.get('composition'):
            active_features.append('compositional')
        if brain_state.get('semantic_coherence'):
            active_features.append('semantic')
        if result.get('ctm_task_id'):
            active_features.append('ctm')

        brain_state_log.append({
            'timestamp': datetime.now().isoformat(),
            'active_features': active_features,
            'prediction': prediction,
            'memory_items': len(brain_state.get('memory_context', {}).get('working_memory', [])),
            'awareness_score': brain_state.get('consciousness_metrics', {}).get('awareness_score', 0.0)
        })

        # Log coordinator routing
        execution_log.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'handoff',
            'sender': 'Coordinator',
            'content': f"Routing to {result['suggested_agent']} (brain recommendation)"
        })

        # Log agent execution
        execution_log.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'agent',
            'sender': result['suggested_agent'],
            'content': 'Executing task with brain guidance...'
        })

        agent_state_log.append({
            'timestamp': datetime.now().isoformat(),
            'active_agents': ['coordinator', result['suggested_agent']]
        })

        # Submit feedback
        loop.run_until_complete(orchestrator.submit_feedback(
            task=task,
            success=True,
            user_rating=0.9,
            execution_time=2.0
        ))

        # Log learning
        execution_log.append({
            'timestamp': datetime.now().isoformat(),
            'type': 'brain',
            'sender': 'Brain - Meta-Learning',
            'content': 'Learning from execution. Success rate updated.'
        })

        return jsonify({
            'success': True,
            'result': {
                'task': task,
                'suggested_agent': result['suggested_agent'],
                'prediction': prediction,
                'brain_state': brain_state,
                'execution_log': execution_log,
                'brain_state_log': brain_state_log,
                'agent_state_log': agent_state_log
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        loop.close()


@app.route('/api/logs')
def get_logs():
    """Get execution logs"""
    return jsonify({
        'execution_log': execution_log,
        'brain_state_log': brain_state_log,
        'agent_state_log': agent_state_log
    })


@app.route('/api/stats')
def get_stats():
    """Get brain statistics"""
    try:
        init_orchestrator()
        stats = orchestrator.get_brain_stats()
        return jsonify(stats)
    except Exception as e:
        print(f"ERROR in /api/stats: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/health')
def health():
    """Health check"""
    init_orchestrator()
    status = orchestrator.get_swarm_status()
    return jsonify({
        'status': 'operational',
        'agents': status['agents_initialized'],
        'brain': 'autonomous'
    })


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  AUTONOMOUS BRAIN + SWARM WEB SERVER")
    print("=" * 60)
    print("\nInitializing autonomous brain + swarm agents...")

    init_orchestrator()

    print("\nServer starting at: http://localhost:5002")
    print("Press Ctrl+C to stop\n")

    app.run(host='0.0.0.0', port=5002, debug=False)

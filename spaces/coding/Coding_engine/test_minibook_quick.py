"""Quick integration test for Minibook + Ollama clients."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engine.minibook_client import MinibookClient
from src.engine.ollama_client import OllamaClient

# Test Minibook
c = MinibookClient()
print("minibook healthy:", c.is_healthy())

agent = c.register_agent("test-arch-001")
print("agent:", agent.name, agent.id, "key:", agent.api_key[:8] + "...")

proj = c.create_project(agent.api_key, "test-whatsapp", "A test project")
print("project:", proj.name, proj.id)

joined = c.join_project(agent.api_key, proj.id, role="architect")
print("joined:", joined)

post = c.create_post(agent.api_key, proj.id, "Design Architecture", "Create the folder structure", post_type="discussion", tags=["arch"])
print("post:", post.title, post.id)

comment = c.create_comment(agent.api_key, post.id, "Here is the architecture plan...")
print("comment:", comment.id)

# Test Ollama
o = OllamaClient()
print("ollama healthy:", o.is_healthy())
answer = o.ask("What is 2+2? Reply with just the number.")
print("ollama answer:", answer.strip())

print("\nALL TESTS PASSED")

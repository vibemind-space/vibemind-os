# OpenRouter Configuration for Swarm Integration

## Why OpenRouter?

The swarm integration now **supports both OpenAI and OpenRouter**, with **OpenRouter recommended** because:

✅ **Cheaper** - Claude 3.5 Sonnet via OpenRouter costs less than GPT-4o direct
✅ **More Models** - Access to 100+ models (GPT, Claude, Llama, Gemini, etc.)
✅ **Already Used** - Tahlamus brain already uses OpenRouter for LLM features
✅ **Unified API** - One key for all models

## Quick Setup (5 Minutes)

### Step 1: Get OpenRouter API Key

1. Go to: https://openrouter.ai/keys
2. Sign up/login
3. Create new API key
4. Copy key (starts with `sk-or-v1-...`)

### Step 2: Add to .env

Update your `.env` file:

```env
# Recommended: OpenRouter (for both brain and swarm)
OPENROUTER_API_KEY=sk-or-v1-...

# Optional: OpenAI (if you prefer OpenAI direct for swarm)
OPENAI_API_KEY=sk-...
```

### Step 3: Test

```bash
python production/swarm_brain_cli.py agent-health
```

You should see:
```
✓ Using OpenRouter (anthropic/claude-3.5-sonnet)
Initializing swarm agents...
✓ 15 agents initialized
```

## How It Works

### Priority Order

1. **If `OPENROUTER_API_KEY` exists**: Use OpenRouter (recommended)
   - Model: `anthropic/claude-3.5-sonnet`
   - Cost: $3/million tokens (input), $15/million tokens (output)
   - Quality: Excellent reasoning and coding

2. **If `OPENAI_API_KEY` exists**: Use OpenAI direct
   - Model: `gpt-4o`
   - Cost: $2.50/million tokens (input), $10/million tokens (output)
   - Quality: Excellent general-purpose

3. **If neither exists**: Error with helpful message

### What Uses OpenRouter

**Swarm Agents** (via OpenRouter):
- All 15 specialized agents (Coordinator, Docker, Database, etc.)
- Agent system messages and reasoning
- Handoff coordination

**Tahlamus Brain** (via OpenRouter):
- Multi-LLM Router (`core/multi_llm_router.py`)
- Feature extraction, task classification
- Reasoning chain generation
- All 13 cognitive features that use LLMs

## Configuration Options

### Option 1: OpenRouter Only (Recommended)

```env
# .env file
OPENROUTER_API_KEY=sk-or-v1-...
```

**Result:**
- Brain uses OpenRouter ✓
- Swarm uses OpenRouter ✓
- Cost: ~$3-15/million tokens
- Models: Claude 3.5 Sonnet

### Option 2: Both OpenRouter and OpenAI

```env
# .env file
OPENROUTER_API_KEY=sk-or-v1-...
OPENAI_API_KEY=sk-...
```

**Result:**
- Brain uses OpenRouter ✓
- Swarm uses OpenRouter ✓ (OpenRouter takes priority)
- OpenAI key available as fallback

### Option 3: OpenAI Only

```env
# .env file
OPENAI_API_KEY=sk-...
```

**Result:**
- Brain uses OpenRouter if key exists (check existing .env)
- Swarm uses OpenAI
- Cost: ~$2.50-10/million tokens
- Models: GPT-4o

## Model Selection

### Current Default (OpenRouter)

```python
# production/brain_swarm_orchestrator.py:170
model="anthropic/claude-3.5-sonnet"
```

**Why Claude 3.5 Sonnet?**
- Excellent reasoning and coding abilities
- Good at following complex instructions
- Handles multi-step agent coordination well
- Cost-effective ($3 input / $15 output per million tokens)

### Alternative Models (via OpenRouter)

You can change the model in `production/brain_swarm_orchestrator.py:170`:

```python
# Fast and cheap (good for development)
model="deepseek/deepseek-chat"  # $0.14/million tokens

# High-quality reasoning
model="anthropic/claude-3.5-sonnet"  # $3/million tokens (current)
model="openai/gpt-4o"  # $2.50/million tokens

# Maximum intelligence
model="anthropic/claude-opus-4"  # $15/million tokens (when available)
model="openai/gpt-4-turbo"  # $10/million tokens

# Specialized models
model="google/gemini-2.0-flash-exp"  # Fast, cheap, long context
model="meta-llama/llama-3.1-70b-instruct"  # Open-source, cheap
```

See all models: https://openrouter.ai/models

## Cost Comparison

### OpenRouter (Current Setup)

**Claude 3.5 Sonnet** via OpenRouter:
- Input: $3.00 per million tokens
- Output: $15.00 per million tokens
- Typical swarm task (10 agent messages, 5k tokens total): ~$0.075

### OpenAI Direct

**GPT-4o**:
- Input: $2.50 per million tokens
- Output: $10.00 per million tokens
- Typical swarm task: ~$0.05

### Budget Option (via OpenRouter)

**DeepSeek Chat**:
- Input: $0.14 per million tokens
- Output: $0.28 per million tokens
- Typical swarm task: ~$0.0014 (50x cheaper!)

## Environment Variables Reference

Your `.env` file should have:

```env
# ============================================
# RECOMMENDED: OpenRouter (unified access)
# ============================================
OPENROUTER_API_KEY=sk-or-v1-...

# ============================================
# OPTIONAL: Specific providers
# ============================================
OPENAI_API_KEY=sk-...         # OpenAI direct (fallback)
ANTHROPIC_API_KEY=sk-ant-...  # Anthropic direct (unused by swarm)

# ============================================
# OPTIONAL: Memory features
# ============================================
SUPERMEMORY_API_KEY=sk-...    # For Infinite Chat memory

# ============================================
# OPTIONAL: Development mode
# ============================================
DEV_MODE=true  # Use cheaper models for development
```

## Troubleshooting

### Error: "No API key found in .env file"

**Solution:**
Add either `OPENROUTER_API_KEY` or `OPENAI_API_KEY` to `.env`:
```env
OPENROUTER_API_KEY=sk-or-v1-...
```

### Error: "Rate limit exceeded"

**OpenRouter:**
- Default: 20 requests/minute (free tier)
- Solution: Add credits at https://openrouter.ai/credits

**OpenAI:**
- Default: Depends on usage tier
- Solution: Wait or upgrade tier

### Error: "Model not found"

**OpenRouter:**
- Check model exists: https://openrouter.ai/models
- Use correct format: `provider/model-name`
- Example: `anthropic/claude-3.5-sonnet` ✓
- Example: `claude-3.5-sonnet` ✗ (missing provider)

### Which API key is being used?

Run with verbose output:
```bash
python production/swarm_brain_cli.py agent-health
```

Look for:
```
✓ Using OpenRouter (anthropic/claude-3.5-sonnet)
```
or
```
✓ Using OpenAI (gpt-4o)
```

## Performance Tips

### 1. Use Cheaper Models for Development

Edit `production/brain_swarm_orchestrator.py:170`:
```python
# Development
model="deepseek/deepseek-chat"  # $0.14/million tokens

# Production
model="anthropic/claude-3.5-sonnet"  # $3/million tokens
```

### 2. Enable DEV_MODE

In `.env`:
```env
DEV_MODE=true
```

This makes the **brain** use cheaper models. Swarm model is configured separately.

### 3. Monitor Costs

Check OpenRouter dashboard: https://openrouter.ai/activity

### 4. Set Budget Limits

OpenRouter Settings → Credits → Set monthly limit

## Integration with Tahlamus Brain

Both brain and swarm can share the same OpenRouter key:

```
┌─────────────────────────────────────┐
│  OPENROUTER_API_KEY (shared)        │
└──────────┬──────────────┬───────────┘
           │              │
           ▼              ▼
    ┌───────────┐  ┌──────────────┐
    │  Brain    │  │  Swarm       │
    │  (13      │  │  (15         │
    │  features)│  │  agents)     │
    └───────────┘  └──────────────┘
         │                │
         └────────┬───────┘
                  ▼
        Unified cost tracking
        Single billing account
```

## Summary

✅ **Setup**: Add `OPENROUTER_API_KEY` to `.env`
✅ **Cost**: ~$0.075 per swarm task (Claude 3.5 Sonnet)
✅ **Models**: 100+ available via OpenRouter
✅ **Integration**: Works with existing Tahlamus brain
✅ **Fallback**: Can use `OPENAI_API_KEY` if preferred

**Get started:**
```bash
# 1. Get key
# Visit: https://openrouter.ai/keys

# 2. Add to .env
echo "OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY_HERE" >> .env

# 3. Test
python production/swarm_brain_cli.py agent-health
```

**You're ready!** The swarm will use OpenRouter automatically. 🚀

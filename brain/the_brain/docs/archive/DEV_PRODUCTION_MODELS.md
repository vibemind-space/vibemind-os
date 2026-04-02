# Dev Mode vs Production Mode

The Multi-LLM Router now supports two modes: **Dev Mode** (currently available models) and **Production Mode** (cutting-edge 2025 models when they become available).

## Mode Configuration

Set in `.env` file:
```bash
DEV_MODE=true   # Use currently available models (default)
DEV_MODE=false  # Use cutting-edge 2025 models
```

## Model Comparison

| Function | Dev Model (Available Now) | Production Model (Future) | Status |
|----------|---------------------------|---------------------------|--------|
| **Fast Reasoning** | DeepSeek R1<br>$0.14/M tokens | Grok Code Fast 1<br>$0.80/M tokens | ✅ Dev working |
| **Strategic Planning** | Claude 3.5 Sonnet<br>$3.00/M tokens | GPT-5 Pro<br>$15.00/M tokens | ✅ Dev working |
| **Context Tracking** | Claude 3.5 Sonnet<br>$3.00/M tokens | Claude Sonnet 4.5<br>$3.00/M tokens | ✅ Dev working |
| **Communication** | GPT-4o<br>$2.50/M tokens | GPT-5 Chat<br>$10.00/M tokens | ✅ Dev working |
| **Long-term Memory** | Gemini 2.0 Flash<br>$0.075/M tokens | Gemini 2.5 Flash<br>$0.10/M tokens | ✅ Dev working |

## Cost Comparison

### Dev Mode (Currently Available)
- **Fast Reasoning**: DeepSeek R1 - $0.14/M tokens (ultra-cheap!)
- **Planning**: Claude 3.5 Sonnet - $3.00/M tokens
- **Context**: Claude 3.5 Sonnet - $3.00/M tokens
- **Communication**: GPT-4o - $2.50/M tokens
- **Memory**: Gemini 2.0 Flash - $0.075/M tokens (cheapest!)

**Estimated cost per 1000 tasks**: ~$0.50 - $1.00

### Production Mode (Future, Cutting-edge)
- **Fast Reasoning**: Grok Code Fast 1 - $0.80/M tokens
- **Planning**: GPT-5 Pro - $15.00/M tokens (premium)
- **Context**: Claude Sonnet 4.5 - $3.00/M tokens
- **Communication**: GPT-5 Chat - $10.00/M tokens
- **Memory**: Gemini 2.5 Flash - $0.10/M tokens

**Estimated cost per 1000 tasks**: ~$2.50 - $5.00

## Feature Comparison

### Dev Mode Advantages
✅ **Available right now** - All models are accessible via OpenRouter today
✅ **Very cost-effective** - DeepSeek R1 is 6x cheaper than Grok
✅ **Proven reliable** - Claude 3.5 Sonnet and GPT-4o are battle-tested
✅ **Fast** - DeepSeek R1 is extremely fast for reasoning tasks
✅ **Large context** - Gemini 2.0 Flash handles 1M tokens

### Production Mode Advantages (When Available)
🔮 **Cutting-edge performance** - Latest 2025 models with best capabilities
🔮 **Specialized models** - Grok optimized for code, GPT-5 for planning
🔮 **Even larger context** - Gemini 2.5 Flash promises 2M tokens
🔮 **Best-in-class** - Each model is the absolute best for its function

## Model Details

### Dev Mode Models

#### 1. DeepSeek R1 (Fast Reasoning)
- **Provider**: DeepSeek
- **Model**: `deepseek/deepseek-r1`
- **Strengths**: Ultra-fast, very cheap, excellent code understanding
- **Context**: 32K tokens
- **Use for**: Feature extraction, decision making, fast inference, code understanding

#### 2. Claude 3.5 Sonnet (Planning & Context)
- **Provider**: Anthropic
- **Model**: `anthropic/claude-3.5-sonnet`
- **Strengths**: Best strategic planning, excellent context tracking
- **Context**: 200K tokens
- **Use for**: Path planning, strategy selection, complex understanding, short-term memory

#### 3. GPT-4o (Communication)
- **Provider**: OpenAI
- **Model**: `openai/gpt-4o`
- **Strengths**: Most natural language generation, great user interaction
- **Context**: 128K tokens
- **Use for**: Question generation, user interaction, natural language

#### 4. Gemini 2.0 Flash (Long-term Memory)
- **Provider**: Google
- **Model**: `google/gemini-2.0-flash-exp`
- **Strengths**: Massive 1M context, very fast, ultra-cheap
- **Context**: 1M tokens (!)
- **Use for**: Episodic memory, pattern discovery, memory search, huge context

### Production Mode Models (Future)

#### 1. Grok Code Fast 1 (Fast Reasoning)
- **Provider**: xAI
- **Model**: `xai/grok-code-fast-1`
- **Strengths**: Optimized for code reasoning, ultra-fast
- **Expected**: 2025 Q1
- **Use for**: Feature extraction, decision making, fast inference, code understanding

#### 2. GPT-5 Pro (Strategic Planning)
- **Provider**: OpenAI
- **Model**: `openai/gpt-5-pro`
- **Strengths**: Best strategic thinking, complex reasoning
- **Expected**: 2025
- **Use for**: Path planning, strategy selection, complex understanding

#### 3. Claude Sonnet 4.5 (Context Tracking)
- **Provider**: Anthropic
- **Model**: `anthropic/claude-sonnet-4.5`
- **Strengths**: Context master, best short-term memory
- **Expected**: 2025
- **Use for**: Short-term memory, context maintenance, working memory

#### 4. GPT-5 Chat (Communication)
- **Provider**: OpenAI
- **Model**: `openai/gpt-5-chat`
- **Strengths**: Most natural communication, conversational AI
- **Expected**: 2025
- **Use for**: Question generation, user interaction, natural language

#### 5. Gemini 2.5 Flash (Long-term Memory)
- **Provider**: Google
- **Model**: `google/gemini-2.5-flash`
- **Strengths**: Massive 2M context, pattern discovery across huge histories
- **Expected**: 2025
- **Use for**: Episodic memory, pattern discovery, memory search, huge context

## Switching Between Modes

### Switch to Dev Mode (Default)
```bash
# In .env file
DEV_MODE=true
```

```python
# In code
from load_env import get_openrouter_key
from core.multi_llm_router import MultiLLMRouter

router = MultiLLMRouter(
    openrouter_api_key=get_openrouter_key(),
    dev_mode=True
)
```

### Switch to Production Mode
```bash
# In .env file
DEV_MODE=false
```

```python
# In code
router = MultiLLMRouter(
    openrouter_api_key=get_openrouter_key(),
    dev_mode=False
)
```

## Testing

Test the current configuration:
```bash
python test_openrouter.py
```

You should see:
- `[DEV MODE] Using currently available models` if DEV_MODE=true
- `[PRODUCTION MODE] Using cutting-edge 2025 models` if DEV_MODE=false

## Recommendations

### For Development & Testing
**Use Dev Mode** ✅
- Much cheaper (~50% cost savings)
- Available immediately
- Proven reliability
- Fast performance

### For Production (Now)
**Use Dev Mode** ✅
- Production models not yet available on OpenRouter
- Dev models are production-ready quality
- Significant cost savings
- Proven track record

### For Production (Future, when available)
**Consider Production Mode** 🔮
- When Grok Code Fast 1, GPT-5, and Claude 4.5 become available
- If you need absolute best performance
- If cost is less of a concern
- For mission-critical applications requiring cutting-edge capabilities

## Current Status

**As of January 2025:**
- ✅ Dev Mode: **Fully operational** with DeepSeek R1, Claude 3.5, GPT-4o, Gemini 2.0
- ⏳ Production Mode: **Waiting for model availability** (Grok, GPT-5, Claude 4.5, Gemini 2.5)

**Recommendation**: Use Dev Mode for all current deployments. Switch to Production Mode when cutting-edge models become available and your use case justifies the higher cost.

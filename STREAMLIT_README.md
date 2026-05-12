# TradingAgents - Streamlit Dashboard

A multi-agent LLM trading framework with an intuitive Streamlit web interface.

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 2. Configuration

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```bash
# LLM Provider (choose one or more)
OPENAI_API_KEY=your_openai_key_here
GOOGLE_API_KEY=your_google_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
XAI_API_KEY=your_xai_key_here
DEEPSEEK_API_KEY=your_deepseek_key_here

# Data Provider (optional - yfinance works without API key)
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here
```

### 3. Run the Dashboard

```bash
streamlit run streamlit_app.py
```

The dashboard will open in your browser at `http://localhost:8501`

## 📊 Dashboard Features

### Three Main Views:

1. **🔍 Single Ticker Deep Dive**
   - Comprehensive analysis of a single stock
   - Real-time agent execution tracking
   - Full and Fast mode analysis options
   - Detailed reports from all agent teams

2. **📋 Multi-Ticker Watchlist**
   - Analyze multiple stocks simultaneously
   - Compare recommendations across tickers
   - Batch processing with progress tracking

3. **📜 History**
   - View past analysis results
   - Track decision accuracy over time
   - Export reports to markdown

## 🤖 Agent Teams

The framework uses specialized AI agents organized into teams:

### Analyst Team
- **Market Analyst**: Technical analysis and price patterns
- **News Analyst**: News sentiment and market events
- **Social Analyst**: Social media sentiment analysis
- **Fundamentals Analyst**: Financial statements and metrics

### Research Team
- **Bull Researcher**: Identifies positive investment signals
- **Bear Researcher**: Identifies risks and concerns
- **Research Manager**: Synthesizes research into investment plan

### Trading Team
- **Trader**: Formulates specific trading strategies

### Risk Management Team
- **Aggressive Analyst**: High-risk/high-reward perspective
- **Conservative Analyst**: Risk-averse perspective
- **Neutral Analyst**: Balanced risk assessment

### Portfolio Management
- **Portfolio Manager**: Final decision on trade execution

## ⚙️ Configuration Options

### LLM Providers

Supported providers:
- OpenAI (GPT-4, GPT-5.x)
- Google (Gemini 2.x, 3.x)
- Anthropic (Claude 4.x)
- xAI (Grok 4.x)
- DeepSeek
- Qwen (Alibaba DashScope)
- GLM (Zhipu)
- OpenRouter
- Ollama (local models)
- Azure OpenAI (enterprise)

### Analysis Modes

**Full Mode** (default):
- All agents run fresh analysis
- Complete fundamental and technical analysis
- Comprehensive research debate
- Best for: New analysis, major market events

**Fast Mode**:
- Reuses fundamentals from prior run
- Fresh market/news/social analysis
- Faster execution (30-50% time savings)
- Best for: Daily updates, quick checks

### Data Vendors

- **yfinance** (default, no API key needed)
- **Alpha Vantage** (requires API key)

## 📁 Project Structure

```
TradingAgents/
├── streamlit_app.py          # Main entry point
├── dashboard/                 # Streamlit UI
│   ├── app.py                # Main dashboard app
│   ├── runner.py             # Background analysis runner
│   ├── utils.py              # Helper utilities
│   └── views/                # Dashboard views
│       ├── single_ticker.py  # Single stock analysis
│       ├── watchlist.py      # Multi-ticker analysis
│       └── history.py        # Historical results
├── tradingagents/            # Core framework
│   ├── agents/               # Agent implementations
│   ├── dataflows/            # Data fetching & processing
│   ├── graph/                # LangGraph workflow
│   ├── llm_clients/          # LLM provider integrations
│   └── default_config.py     # Default configuration
├── tests/                    # Unit tests
├── .env                      # Your API keys (create from .env.example)
└── pyproject.toml           # Package configuration
```

## 🔧 Advanced Usage

### Custom Configuration

You can customize the analysis by modifying `tradingagents/default_config.py` or passing a custom config:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-5.4"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 3

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("AAPL", "2026-05-10")
```

### Checkpoint Resume

Enable checkpoint resume to recover from interruptions:

```python
config["checkpoint_enabled"] = True
```

### Memory & Learning

The framework maintains a decision log at `~/.tradingagents/memory/trading_memory.md` that tracks:
- Past decisions for each ticker
- Realized returns (raw and alpha vs SPY)
- Lessons learned across all analyses

This memory is automatically injected into future analyses to improve decision quality.

## 🧪 Testing

Run the test suite:

```bash
pytest tests/
```

Run specific test categories:

```bash
pytest tests/ -m unit          # Fast unit tests
pytest tests/ -m integration   # Integration tests
pytest tests/ -m smoke         # Quick sanity checks
```

## 📝 Output & Reports

Analysis results are saved to:
- `~/.tradingagents/logs/<TICKER>/<DATE>/` - Detailed logs
- `~/.tradingagents/memory/trading_memory.md` - Decision history

Each analysis generates:
- Complete markdown report
- Individual agent reports (by team)
- Structured JSON state
- Performance metrics

## ⚠️ Disclaimer

TradingAgents is designed for research and educational purposes. Trading performance may vary based on many factors including:
- LLM model selection and temperature
- Market conditions and data quality
- Analysis date and time period
- Non-deterministic AI behavior

**This framework is not intended as financial, investment, or trading advice.**

## 🤝 Contributing

Contributions are welcome! Please see the main [README.md](README.md) for contribution guidelines.

## 📄 License

See [LICENSE](LICENSE) file for details.

## 🔗 Links

- [GitHub Repository](https://github.com/TauricResearch/TradingAgents)
- [Research Paper](https://arxiv.org/abs/2412.20138)
- [Discord Community](https://discord.com/invite/hk9PGKShPK)
- [Tauric Research](https://tauric.ai/)

---

Built with ❤️ by [Tauric Research](https://github.com/TauricResearch)

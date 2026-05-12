# 🚀 TradingAgents - START HERE

Welcome to **TradingAgents v0.3.0** - Streamlit Edition!

This is a multi-agent LLM trading framework with a beautiful web interface.

---

## ⚡ Quick Start (3 Steps)

### 1. Run the Start Script
```bash
./start.sh
```

That's it! The script will:
- ✅ Create virtual environment (if needed)
- ✅ Install dependencies
- ✅ Check for API keys
- ✅ Launch the dashboard at http://localhost:8501

### 2. Add Your API Keys (First Time Only)

If you see an error about missing API keys:

```bash
# Edit the .env file
nano .env  # or use your favorite editor

# Add at least one API key:
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
```

Then run `./start.sh` again.

### 3. Use the Dashboard

1. **Enter a ticker** (e.g., `AAPL`, `NVDA`, `TSLA`)
2. **Select analysts** (Market, News, Social, Fundamentals)
3. **Click "Run Analysis"**
4. **Watch the agents work** in real-time
5. **View the final decision** (Buy/Sell/Hold)

---

## 📚 Documentation

- **`STREAMLIT_README.md`** - Complete guide (installation, features, configuration)
- **`IMPROVEMENTS.md`** - Recommended improvements and enhancements
- **`CLEANUP_SUMMARY.md`** - What changed in v0.3.0
- **`README.md`** - Original project documentation

---

## 🎯 Key Features

### 🤖 Multi-Agent System
- **Analyst Team**: Market, News, Social, Fundamentals
- **Research Team**: Bull/Bear debate + Research Manager
- **Trading Team**: Trader formulates strategy
- **Risk Team**: Aggressive/Conservative/Neutral analysis
- **Portfolio Manager**: Final decision

### ⚡ Fast Mode
- Reuses fundamentals from recent analysis
- 60% faster execution
- Lower LLM costs
- Perfect for daily updates

### 💾 Smart Caching
- Instant reload of past analyses
- No duplicate LLM calls
- Saves time and money

### 📊 Real-Time Progress
- Live agent status tracking
- Streaming reports
- Elapsed time display
- Error handling with retry

### 🎨 Beautiful UI
- Clean, modern interface
- Dark theme optimized
- Responsive design
- Intuitive navigation

---

## 🔧 Configuration

### LLM Providers (Choose One or More)

```bash
# OpenAI (GPT-4, GPT-5.x)
OPENAI_API_KEY=sk-...

# Google (Gemini 2.x, 3.x)
GOOGLE_API_KEY=AIza...

# Anthropic (Claude 4.x)
ANTHROPIC_API_KEY=sk-ant-...

# DeepSeek (Recommended for cost)
DEEPSEEK_API_KEY=sk-...

# xAI (Grok 4.x)
XAI_API_KEY=...

# Qwen (Alibaba)
DASHSCOPE_API_KEY=...

# GLM (Zhipu)
ZHIPU_API_KEY=...
```

### Data Provider (Optional)

```bash
# Alpha Vantage (optional - yfinance works without API key)
ALPHA_VANTAGE_API_KEY=...
```

---

## 📖 Usage Examples

### Example 1: Quick Analysis
```
1. Open dashboard: ./start.sh
2. Enter ticker: AAPL
3. Click "Run Analysis"
4. Wait ~2-3 minutes
5. View decision: Buy/Sell/Hold
```

### Example 2: Fast Mode (Daily Update)
```
1. Run full analysis on Monday
2. On Tuesday, enable "Fast Mode"
3. Analysis completes in ~1 minute
4. Fundamentals reused, market data fresh
```

### Example 3: Custom Configuration
```
1. Select specific analysts (e.g., only Market + News)
2. Adjust debate rounds (1-3)
3. Choose models (DeepSeek for cost, GPT-5 for quality)
4. Run analysis
```

### Example 4: Programmatic Use
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4"
config["quick_think_llm"] = "gpt-5.4-mini"

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("AAPL", "2026-05-10")
print(decision)
```

---

## 🎓 Learning Path

### Beginner
1. Read `STREAMLIT_README.md` (15 min)
2. Run your first analysis (5 min)
3. Explore the dashboard views (10 min)

### Intermediate
1. Try Fast Mode (5 min)
2. Compare different LLM providers (20 min)
3. Analyze multiple tickers (15 min)

### Advanced
1. Read `IMPROVEMENTS.md` for enhancement ideas
2. Customize agent configuration
3. Integrate with your trading system
4. Contribute improvements

---

## 🐛 Troubleshooting

### "No API keys found"
→ Edit `.env` and add at least one LLM provider API key

### "Ticker not found"
→ Use official ticker symbols (e.g., `AAPL` not `Apple`)
→ Non-US stocks need exchange suffix (e.g., `7203.T` for Toyota)

### "Analysis failed"
→ Check your API key is valid
→ Check your internet connection
→ Try a different LLM provider
→ Click "Retry" button

### "Slow performance"
→ Use Fast Mode for daily updates
→ Use DeepSeek models (faster + cheaper)
→ Reduce debate rounds to 1

### "Import errors"
→ Make sure you're in the virtual environment
→ Run `pip install -e .` again
→ Check Python version (3.10+ required)

---

## 💡 Tips & Tricks

### Cost Optimization
- Use **DeepSeek** models (10x cheaper than GPT-4)
- Enable **Fast Mode** for daily updates
- Reduce **debate rounds** to 1
- Select only needed analysts

### Speed Optimization
- Use **Fast Mode** (60% faster)
- Use **DeepSeek V4 Flash** for quick thinking
- Run during off-peak hours
- Cache results for instant reload

### Quality Optimization
- Use **GPT-5.4** or **Claude 4.6** for deep thinking
- Increase **debate rounds** to 3
- Select **all analysts** for comprehensive view
- Run **full mode** for major decisions

### Best Practices
- Run full analysis weekly
- Use Fast Mode for daily updates
- Compare multiple tickers before deciding
- Review agent reasoning, not just final decision
- Track performance over time

---

## 🤝 Contributing

We welcome contributions! See `IMPROVEMENTS.md` for ideas.

### Quick Contribution Guide
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests (if applicable)
5. Submit a pull request

### Areas for Contribution
- UI/UX improvements
- New agent types
- Performance optimizations
- Documentation
- Bug fixes

---

## 📞 Support & Community

- **GitHub**: [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- **Discord**: [Join Community](https://discord.com/invite/hk9PGKShPK)
- **Twitter**: [@TauricResearch](https://x.com/TauricResearch)
- **Paper**: [arXiv:2412.20138](https://arxiv.org/abs/2412.20138)

---

## ⚠️ Disclaimer

TradingAgents is for **research and educational purposes only**.

- Not financial advice
- Not investment advice
- Not trading advice
- Past performance ≠ future results
- AI can make mistakes
- Always do your own research
- Consult a financial advisor

---

## 📄 License

See [LICENSE](LICENSE) file for details.

---

## 🎉 What's New in v0.3.0

### ✅ Streamlit-Only Focus
- Removed CLI interface
- Simplified codebase (25+ files removed)
- Single entry point (`streamlit_app.py`)
- Quick start script (`start.sh`)

### ✅ Better Documentation
- `STREAMLIT_README.md` - Complete guide
- `IMPROVEMENTS.md` - Enhancement roadmap
- `CLEANUP_SUMMARY.md` - Migration guide
- `START_HERE.md` - This file!

### ✅ Improved Dependencies
- Removed CLI-only packages
- Added Streamlit optimizations
- Smaller installation footprint

### ✅ Enhanced User Experience
- Clearer project structure
- Easier to get started
- Better error messages
- Improved documentation

---

## 🚀 Next Steps

1. **Run your first analysis**: `./start.sh`
2. **Read the full guide**: `STREAMLIT_README.md`
3. **Explore improvements**: `IMPROVEMENTS.md`
4. **Join the community**: [Discord](https://discord.com/invite/hk9PGKShPK)

---

**Happy Trading! 📈**

Built with ❤️ by [Tauric Research](https://github.com/TauricResearch)

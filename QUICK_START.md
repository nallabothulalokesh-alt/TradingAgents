# TradingAgents Dashboard - Quick Start Guide

## 🚀 Getting Started

The dashboard is already running at: **http://localhost:8501**

---

## ✅ What's New (Just Implemented)

### 1. Fixed Critical Bug
- Dashboard no longer crashes with duplicate element ID errors
- Multiple analyses can run without issues

### 2. Warnings Now Visible
- When structured output fails, you'll see warnings in the dashboard
- Example: "⚠️ Research Manager: structured-output failed; retrying as free text"

### 3. Stale Fundamentals Alert
- Fast Mode now warns if earnings occurred between runs
- Example: "⚠️ Earnings released on 2026-05-08 — fundamentals may be outdated"

---

## 📊 How to Use

### Single Ticker Analysis

1. **Enter Ticker** (e.g., NVDA, AAPL, TSLA)
   - Use ticker symbols, not company names
   - Dashboard validates automatically

2. **Select Date**
   - Defaults to today
   - Can analyze historical dates

3. **Choose Analysts**
   - Market (price & technicals)
   - Social (sentiment)
   - News (recent events)
   - Fundamentals (financials)

4. **Pick Models**
   - Deep thinker: `deepseek-v4-pro` (recommended)
   - Quick thinker: `deepseek-v4-flash` (recommended)
   - ⚠️ Avoid: `deepseek-reasoner`, `o1`, `o1-mini`

5. **Click "Run Analysis"**
   - Watch agents work in real-time
   - See reports as they complete
   - Final decision appears at top

---

## ⚡ Fast Mode

**What it does**: Reuses fundamentals + research from a recent run (within 7 days)

**When to use**:
- Analyzing same ticker on consecutive days
- Fundamentals haven't changed
- Want faster, cheaper analysis

**Speed**: ~3-4 minutes (vs 6-8 minutes full mode)

**Warning**: Dashboard now alerts if earnings occurred between runs!

---

## 🎯 Model Selection Guide

### ✅ Recommended Models

| Model | Use Case | Speed | Cost |
|-------|----------|-------|------|
| `deepseek-v4-pro` | Deep thinking, complex analysis | Medium | Low |
| `deepseek-v4-flash` | Quick tasks, simple analysis | Fast | Very Low |
| `gpt-4o` | OpenAI flagship | Medium | High |
| `claude-3-5-sonnet` | Anthropic flagship | Medium | High |

### ❌ Incompatible Models

| Model | Issue | Alternative |
|-------|-------|-------------|
| `deepseek-reasoner` | No tool_choice support | `deepseek-v4-pro` |
| `o1` | No tool calling | `o1-pro` or `gpt-4o` |
| `o1-mini` | No tool calling | `o1-pro` or `gpt-4o` |

---

## 🔍 Understanding Results

### Rating Scale
- **Buy** 🟢 - Strong conviction, high upside
- **Overweight** 🟢 - Positive outlook, above market weight
- **Hold** 🟡 - Neutral, maintain position
- **Underweight** 🟠 - Cautious, below market weight
- **Sell** 🔴 - Negative outlook, exit position

### Report Sections

1. **Market Analysis** - Price action, technicals, momentum
2. **Social Sentiment** - Reddit, Twitter, news sentiment
3. **News Analysis** - Recent events, insider trades
4. **Fundamentals** - Financials, valuation, growth
5. **Research Decision** - Bull vs Bear debate synthesis
6. **Trader Plan** - Entry/exit strategy, risk management
7. **Final Decision** - Portfolio Manager's verdict

---

## 📁 Where Data is Stored

### Analysis Results
```
~/.tradingagents/logs/
├── NVDA/
│   └── TradingAgentsStrategy_logs/
│       ├── full_states_log_2026-05-10.json
│       └── full_states_log_2026-05-09.json
├── AAPL/
│   └── TradingAgentsStrategy_logs/
│       └── full_states_log_2026-05-10.json
```

### Memory Log
```
~/.tradingagents/memory/
└── trading_memory.md
```

Contains:
- Past decisions
- Actual returns (raw + alpha)
- Reflections on what worked/didn't work
- Learning from mistakes

---

## ⚙️ Configuration Tips

### Enable Memory Log Rotation

Prevent unbounded log growth:

```python
# In your config
"memory_log_max_entries": 100  # Keep last 100 resolved entries
```

### Adjust Debate Depth

Balance speed vs thoroughness:

```python
"max_debate_rounds": 1,         # Fast: 1, Balanced: 2, Deep: 3
"max_risk_discuss_rounds": 1,   # Fast: 1, Balanced: 2, Deep: 3
```

---

## 🐛 Troubleshooting

### "Ticker not found"
- Use ticker symbol (AAPL), not company name (Apple)
- Non-US stocks need exchange suffix (7203.T for Toyota)

### "Model incompatible" error
- Switch to `deepseek-v4-pro` or `deepseek-v4-flash`
- Avoid `deepseek-reasoner`, `o1`, `o1-mini`

### Structured output warnings
- Normal behavior - pipeline falls back to free-text
- Consider switching to a more compatible model
- Analysis continues without issues

### Analysis stuck "Running"
- Check terminal logs for errors
- Verify API keys are set correctly
- Try stopping and restarting dashboard

---

## 📈 Best Practices

### Daily Workflow

1. **Morning**: Run full analysis for watchlist tickers
2. **Afternoon**: Use Fast Mode to check for updates
3. **Evening**: Review memory log for learning

### Multi-Day Analysis

1. **Day 1**: Full analysis (all agents)
2. **Day 2**: Fast Mode (reuse fundamentals)
3. **Day 3**: Fast Mode (check for earnings warning)
4. **After Earnings**: Full analysis (fresh fundamentals)

### Model Selection

- **Deep thinker**: Use best model you can afford
- **Quick thinker**: Use fast, cheap model
- **Consistency**: Stick with same models for comparability

---

## 🎓 Understanding Warnings

### ⚠️ Structured Output Failed
**What it means**: Model couldn't return structured data  
**Impact**: Analysis uses free-text instead (slightly less formatted)  
**Action**: Consider switching to `deepseek-v4-pro`

### ⚠️ Earnings Released
**What it means**: Fundamentals from prior run are outdated  
**Impact**: Fast Mode may use stale data  
**Action**: Run full analysis to get fresh fundamentals

### ⚠️ No Prior Run Found
**What it means**: Fast Mode can't find recent analysis  
**Impact**: Will run full analysis instead  
**Action**: None needed (automatic fallback)

---

## 🔄 Viewing History

1. Click **"History"** tab
2. See all past analyses
3. Filter by:
   - Ticker
   - Date range
   - Rating
4. Click any row to view full report

---

## 💡 Pro Tips

1. **Cache is your friend**: If you've analyzed a ticker+date before, it loads instantly
2. **Fast Mode saves time**: Use for daily updates on same ticker
3. **Watch for earnings**: Dashboard warns when fundamentals may be stale
4. **Memory log learns**: System improves by reflecting on past decisions
5. **Warnings are helpful**: Pay attention to dashboard warnings

---

## 📞 Need Help?

### Check Logs
```bash
# Analysis logs
ls ~/.tradingagents/logs/

# Memory log
cat ~/.tradingagents/memory/trading_memory.md
```

### Restart Dashboard
```bash
# Stop current process
# Then restart:
python3 -m streamlit run dashboard/app.py
```

---

## 🎉 You're Ready!

The dashboard is production-ready with:
- ✅ Stable, no crashes
- ✅ Clear warnings
- ✅ Smart caching
- ✅ Fast Mode optimization
- ✅ Comprehensive validation

**Start analyzing**: http://localhost:8501

---

**Version**: 1.0 (Production Ready)  
**Last Updated**: May 10, 2026

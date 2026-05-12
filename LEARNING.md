# TradingAgents — Learning Notes

A plain-English explanation of how the analysis works, what timeframe it is built for, and how to extend it for intraday, swing, and long-term investing.

---

## 1. What the system actually does

TradingAgents runs a team of AI agents that each look at a different slice of information about a stock, debate the findings, and produce a final Buy / Overweight / Hold / Underweight / Sell decision.

Think of it like a small trading desk:

```
Market Analyst  ──┐
News Analyst    ──┤──► Bull vs Bear Debate ──► Research Manager ──► Trader ──► Risk Team ──► Portfolio Manager
Fundamentals    ──┤                                                                              │
Social Analyst  ──┘                                                                              ▼
                                                                                         Final Decision
```

Each agent has a specific job, specific data it looks at, and a specific output. None of them talk to the market in real time — they all work from data that has already been fetched and stored.

---

## 2. What each agent looks at

### Market Analyst
- **Data**: Daily OHLCV price data (Open, High, Low, Close, Volume)
- **Tools**: Up to 8 technical indicators chosen from: 50 SMA, 200 SMA, 10 EMA, MACD, MACD Signal, MACD Histogram, RSI, Bollinger Bands (upper/middle/lower), ATR, VWMA
- **Output**: A detailed report on price trends, momentum, support/resistance levels, and volatility
- **Timeframe implied**: Days to weeks — all these indicators are calculated on daily candles

### News Analyst
- **Data**: News articles from the past week (company-specific + global macro)
- **Tools**: `get_news(query, start_date, end_date)` and `get_global_news(date, lookback_days)`
- **Output**: A report on recent events, macro conditions, and their likely market impact
- **Timeframe implied**: 1 week lookback — short-term catalyst analysis

### Social Media / Sentiment Analyst
- **Data**: Social media posts, public sentiment, company-specific news from the past week
- **Tools**: `get_news` (same tool, different prompt focus — looks for sentiment and social chatter)
- **Output**: A report on what the public and market participants are saying about the company
- **Timeframe implied**: 1 week — short-term sentiment, not long-term conviction
- **Important limitation**: This agent uses the same news API as the News Analyst. There is no actual Twitter/Reddit/StockTwits integration. It infers sentiment from news headlines, not raw social data.

### Fundamentals Analyst
- **Data**: Balance sheet, income statement, cash flow statement, company profile
- **Tools**: `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`
- **Output**: A report on the company's financial health — revenue, profit margins, debt, cash position
- **Timeframe implied**: Quarterly/annual data — this is genuinely long-term data, but the prompt asks for "the past week" which means it fetches the most recent filings, not a multi-year trend analysis

### Bull Researcher
- **Input**: All four analyst reports above
- **Job**: Build the strongest possible case FOR buying the stock — growth potential, competitive advantages, positive indicators
- **Output**: A debate argument (not a final decision)

### Bear Researcher
- **Input**: All four analyst reports + Bull's argument
- **Job**: Build the strongest possible case AGAINST buying — risks, overvaluation, negative signals
- **Output**: A counter-argument

> The Bull and Bear go back and forth for however many rounds you set (default: 1 round each). More rounds = more thorough debate = slower and more expensive.

### Research Manager
- **Input**: The full Bull vs Bear debate history
- **Job**: Judge the debate and produce a structured investment plan
- **Output**: Recommendation (Buy/Overweight/Hold/Underweight/Sell) + Rationale + Strategic Actions

### Trader
- **Input**: Research Manager's investment plan
- **Job**: Translate the plan into a concrete transaction proposal
- **Output**: Action (Buy/Hold/Sell) + Reasoning + optional Entry Price + Stop Loss + Position Sizing

### Risk Management Team (3 analysts)
- **Aggressive Analyst**: Argues for taking the trade, maximising upside
- **Conservative Analyst**: Argues for caution, minimising downside
- **Neutral Analyst**: Balanced view, weighs both sides
- They debate for however many rounds you set (default: 1)

### Portfolio Manager
- **Input**: Risk debate + Research plan + Trader proposal + Memory of past decisions
- **Job**: Make the final call
- **Output**: Rating (5-tier) + Executive Summary + Investment Thesis + optional Price Target + Time Horizon

---

## 3. What timeframe is the analysis built for?

### Short answer: **Swing trading — roughly 1 day to 4 weeks**

Here is the honest breakdown:

| Timeframe | What traders need | What this system provides | Verdict |
|-----------|------------------|--------------------------|---------|
| **Intraday** (minutes to hours) | 1m/5m/15m candles, real-time news, Level 2 order book, VWAP, pre-market data | Daily candles, weekly news | ❌ Not supported |
| **Swing trading** (1 day to 4 weeks) | Daily candles, weekly news, short-term technicals, earnings calendar | Daily candles, 1-week news, RSI/MACD/Bollinger Bands | ✅ This is what it's built for |
| **Long-term investing** (3 months to 3+ years) | Multi-year financials, DCF valuation, sector comparison, dividend history, macro cycles | Most recent quarterly filings only, no multi-year trend | ⚠️ Partial — fundamentals are there but not analyzed with a long-term lens |

---

## 4. How to read the output for each timeframe

### If you are swing trading
The output is most directly useful to you. When the Portfolio Manager says "Buy" with a time horizon of "2-4 weeks", that means:
- The technicals (RSI, MACD, Bollinger Bands) show a favorable setup on the daily chart
- Recent news and sentiment are supportive
- The bull case outweighed the bear case in the debate
- The risk team approved the trade

**What to do with it**: Use the entry price and stop-loss from the Trader's output as your trade parameters. The stop-loss is your maximum loss per share if the trade goes wrong.

### If you are a long-term investor
The output gives you a useful starting point but is not a complete long-term thesis. The fundamentals report tells you about the company's current financial health. The rating tells you whether the near-term setup is favorable. But it does not tell you:
- Whether the stock is cheap or expensive relative to its 5-year history
- What the fair value is (no DCF calculation)
- Whether the dividend is sustainable
- How the company compares to its sector peers over multiple years

**What to do with it**: Use it as a screening tool. If the system says "Sell" or "Underweight", that's a signal to be cautious even for a long-term position. If it says "Buy", do your own deeper research before committing long-term capital.

### If you are an intraday trader
The current system cannot help you directly. The data is daily, not intraday. A "Buy" signal from this system means the daily chart looks good — it says nothing about whether to buy at 9:35am or 2:45pm today.

**What to do with it**: Use it as a directional bias. If the system says "Buy", you know the daily trend is in your favour, so you might prefer to take long setups intraday rather than short ones. But your actual entry and exit decisions need intraday data that this system does not currently provide.

---

## 5. The rating scale explained

The Portfolio Manager uses a 5-tier scale borrowed from institutional equity research:

| Rating | Meaning | What to do |
|--------|---------|------------|
| **Buy** | Strong conviction, enter or add to position | High confidence signal — the bull case was dominant |
| **Overweight** | Favorable outlook, gradually increase exposure | Positive but not as strong — consider a partial position |
| **Hold** | Maintain current position, no action needed | Mixed signals — if you own it, keep it; if you don't, wait |
| **Underweight** | Reduce exposure, take partial profits | More negative than positive — consider trimming |
| **Sell** | Exit position or avoid entry | Strong negative signal — the bear case was dominant |

**Important**: These ratings are for the near-term (days to weeks) based on the current week's data. A "Hold" today does not mean the stock is bad long-term — it just means the near-term setup is neutral.

---

## 6. What the memory system does

After each analysis, the system saves the decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, it:

1. Looks up what it recommended last time
2. Calculates the actual return since then (raw return and alpha vs SPY)
3. Generates a "reflection" — what worked, what didn't
4. Injects this context into the Portfolio Manager's prompt

This means the system learns from its own past decisions over time. If it recommended "Buy" on NVDA and the stock dropped 10%, the next analysis will factor in that lesson.

---

## 7. Fast Mode explained

When you enable Fast Mode in the dashboard:

- **Fundamentals Analyst** is skipped — its output is reused from a recent prior run (within 7 days by default)
- **Bull/Bear Researchers** are skipped — their debate is reused
- **Research Manager** is skipped — its investment plan is reused
- **Market Analyst, News Analyst, Social Analyst** run fresh — because price and news change daily
- **Trader, Risk Team, Portfolio Manager** run fresh — because they need to react to today's market

**Why this makes sense**: Company fundamentals (balance sheet, income statement) only change quarterly. The bull/bear debate about a company's competitive position doesn't change week to week. What changes daily is price action and news. Fast Mode captures this — refresh what matters, reuse what doesn't.

**When to use Full Mode**: After earnings, major news events, or if more than a week has passed since the last run.

---

## 8. What the indicators mean (plain English)

| Indicator | What it measures | Signal |
|-----------|-----------------|--------|
| **50 SMA** | Average price over 50 days | Price above = uptrend; below = downtrend |
| **200 SMA** | Average price over 200 days | Long-term trend direction |
| **10 EMA** | Recent price momentum (last 10 days) | Fast-moving — shows short-term direction |
| **MACD** | Difference between 12 and 26 day EMAs | Positive = bullish momentum; negative = bearish |
| **RSI** | How overbought or oversold the stock is (0-100) | Above 70 = overbought (may fall); below 30 = oversold (may rise) |
| **Bollinger Bands** | Price range based on volatility | Price near upper band = stretched high; near lower band = stretched low |
| **ATR** | How much the price moves per day on average | High ATR = volatile stock; used to set stop-loss distances |
| **VWMA** | Moving average weighted by volume | Confirms trend — if price is above VWMA with high volume, trend is strong |

---

## 9. Limitations to be aware of

1. **No real-time data** — all data is end-of-day. The analysis reflects yesterday's close, not the current price.

2. **No intraday data** — cannot be used for day trading decisions directly.

3. **News is from yfinance** — not a professional news terminal. Some important news may be missed.

4. **Social sentiment is inferred** — there is no direct Twitter/Reddit integration. Sentiment is inferred from news headlines.

5. **LLM non-determinism** — running the same analysis twice may produce slightly different outputs because LLMs are probabilistic. The direction (Buy/Sell/Hold) is usually consistent but the exact wording and sometimes the rating can vary.

6. **Not financial advice** — this is a research tool. The agents can be wrong. Always apply your own judgment before making any trade.

7. **Fundamentals are quarterly** — the balance sheet and income statement only update 4 times a year. Between earnings, the fundamentals report will look the same.

8. **The debate is only as good as the data** — if yfinance returns incomplete or stale data for a ticker, the analysis quality drops. Non-US stocks and small caps are more prone to this.

---

## 10. How to extend for each timeframe (future improvements)

### For intraday trading
- Add a `get_intraday_data` tool that fetches 5-minute candles from yfinance (`interval="5m"`, `period="1d"`)
- Add intraday indicators: VWAP, 9 EMA, pre-market high/low
- Skip the Fundamentals Analyst entirely (irrelevant for intraday)
- Change the news lookback to same-day only
- Change the Portfolio Manager prompt to focus on entry/exit levels within the trading session

### For long-term investing
- Change the Fundamentals Analyst prompt to analyze 3-5 year revenue trends, P/E vs sector peers, debt trajectory, free cash flow yield
- Add a DCF (Discounted Cash Flow) tool that estimates fair value
- Add a sector comparison tool
- Change the news lookback to 1-3 months instead of 1 week
- Change the Portfolio Manager prompt to focus on 12-24 month thesis, not near-term catalysts

### The simplest implementation
Add a **Horizon** selector to the dashboard (Intraday / Swing / Long-Term). This single input would:
- Change the data window each analyst fetches
- Change the indicators the Market Analyst picks
- Change the framing in each agent's system prompt
- Change what the Portfolio Manager focuses on in its output

The infrastructure (LangGraph, agents, tools) is already there — it's mainly a prompt and data-window change.

---

## 11. Glossary

| Term | Meaning |
|------|---------|
| **Alpha** | Return above or below the market benchmark (SPY). Positive alpha = outperformed the market |
| **ATR** | Average True Range — a measure of daily price volatility |
| **Bollinger Bands** | Price envelope based on standard deviation — shows when a stock is stretched |
| **DCF** | Discounted Cash Flow — a method to estimate a stock's fair value based on future earnings |
| **EMA** | Exponential Moving Average — like SMA but gives more weight to recent prices |
| **MACD** | Moving Average Convergence Divergence — a momentum indicator |
| **RSI** | Relative Strength Index — measures overbought/oversold conditions (0-100 scale) |
| **SMA** | Simple Moving Average — average price over N days |
| **Stop-loss** | A price level at which you exit a trade to limit your loss |
| **VWAP** | Volume Weighted Average Price — the average price weighted by volume, used by intraday traders |
| **VWMA** | Volume Weighted Moving Average — like SMA but weighted by volume |

---

*Last updated: May 2026*
*Source: TradingAgents codebase analysis — agent prompts, schemas, and data tools*


---

## 12. How data actually flows — a complete technical breakdown

This section explains exactly where every piece of data comes from, how it is processed, and what the agents receive. This is the foundation for understanding how to improve the memory system.

---

### 12.1 The data routing layer

All data requests go through a single router in `tradingagents/dataflows/interface.py`. It works like a switchboard:

```
Agent calls get_stock_data()
        │
        ▼
interface.py → route_to_vendor("get_stock_data")
        │
        ├── config says "yfinance"  →  y_finance.get_YFin_data_online()
        └── config says "alpha_vantage"  →  alpha_vantage_stock.get_stock()
```

Every data function has two implementations — one for yfinance (free, no API key) and one for Alpha Vantage (paid, higher quality). You switch between them in the config. Right now everything defaults to yfinance.

There are 4 data categories, each with its own vendor setting:

| Category | Tools | Default vendor |
|----------|-------|---------------|
| `core_stock_apis` | `get_stock_data` | yfinance |
| `technical_indicators` | `get_indicators` | yfinance |
| `fundamental_data` | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | yfinance |
| `news_data` | `get_news`, `get_global_news`, `get_insider_transactions` | yfinance |

---

### 12.2 Price data — exactly what is fetched

**Function**: `get_YFin_data_online(symbol, start_date, end_date)`

**What it fetches**: `yf.Ticker(symbol).history(start=..., end=...)`

**What yfinance returns** (daily OHLCV):
```
Date, Open, High, Low, Close, Volume, Dividends, Stock Splits
```

**What the agent receives**: A CSV string like this:
```
Date,Open,High,Low,Close,Volume
2026-05-01,180.25,182.10,179.50,181.75,45230000
2026-05-02,181.75,183.00,180.00,182.50,38100000
...
```

**Important details**:
- Data is **end-of-day only** — no intraday prices
- Prices are **auto-adjusted** for splits and dividends
- The Market Analyst calls `get_stock_data` first to get this CSV, then calls `get_indicators` to calculate technical indicators on top of it

**Caching**: The system caches 5 years of OHLCV data per ticker in `~/.tradingagents/cache/<TICKER>-YFin-data-<start>-<end>.csv`. Once cached, it reads from disk instead of hitting yfinance again. This means if you run the same ticker twice, the second run is much faster.

**Look-ahead bias protection**: The code filters out any rows after `curr_date` so backtesting analyses never accidentally see future prices.

---

### 12.3 Technical indicators — how MACD, RSI etc. are calculated

**Function**: `get_stock_stats_indicators_window(symbol, indicator, curr_date, look_back_days)`

**What it does**:
1. Loads the cached OHLCV data (from step 12.2)
2. Passes it to the `stockstats` library
3. `stockstats` calculates the indicator mathematically from the OHLCV data
4. Returns a time series of daily values for the lookback period

**The `stockstats` library** is a Python wrapper around pandas that adds financial indicator calculations. It is entirely local — no API call, no internet needed. It computes everything from the raw price data.

**Exact formulas used**:

| Indicator | Formula | Lookback needed |
|-----------|---------|----------------|
| `close_50_sma` | Simple average of last 50 closing prices | 50 days |
| `close_200_sma` | Simple average of last 200 closing prices | 200 days |
| `close_10_ema` | Exponential weighted average, last 10 days | 10 days |
| `macd` | 12-day EMA minus 26-day EMA | 26 days |
| `macds` | 9-day EMA of the MACD line | 35 days |
| `macdh` | MACD minus MACD Signal | 35 days |
| `rsi` | 100 - (100 / (1 + avg_gain/avg_loss)) over 14 days | 14 days |
| `boll` | 20-day SMA (middle Bollinger Band) | 20 days |
| `boll_ub` | 20-day SMA + (2 × 20-day std dev) | 20 days |
| `boll_lb` | 20-day SMA - (2 × 20-day std dev) | 20 days |
| `atr` | Average of (High-Low, High-PrevClose, Low-PrevClose) over 14 days | 14 days |
| `vwma` | Sum(Close × Volume) / Sum(Volume) over 14 days | 14 days |
| `mfi` | Money Flow Index using price × volume over 14 days | 14 days |

**What the agent receives**: A text block like this:
```
## rsi values from 2026-04-24 to 2026-05-10:

2026-05-10: 62.4
2026-05-09: 58.1
2026-05-08: 55.7
...

RSI: Measures momentum to flag overbought/oversold conditions.
Usage: Apply 70/30 thresholds and watch for divergence to signal reversals.
```

**Key insight**: The Market Analyst picks up to 8 indicators from the list above. It chooses which ones to use based on the market context — it doesn't always use all of them. The LLM decides which combination is most relevant.

---

### 12.4 News data — exactly what is fetched and its limitations

**Function**: `get_news_yfinance(ticker, start_date, end_date)`

**What it fetches**: `yf.Ticker(ticker).get_news(count=20)`

**What yfinance returns**: Up to 20 news articles with:
- Title
- Summary (1-2 sentences)
- Publisher name
- URL link
- Publication date

**Critical limitation — this is NOT a real news feed**:
- yfinance scrapes Yahoo Finance's news section
- Yahoo Finance aggregates from a limited set of publishers (Reuters, AP, Motley Fool, Seeking Alpha, etc.)
- You get at most 20 articles, not a comprehensive feed
- The summary is just the article's meta description — not the full article text
- There is no sentiment score — the LLM infers sentiment from the title and summary text

**Global news function**: `get_global_news_yfinance(curr_date, look_back_days, limit)`

This searches yfinance for macro topics using 4 hardcoded queries:
1. "stock market economy"
2. "Federal Reserve interest rates"
3. "inflation economic outlook"
4. "global markets trading"

It deduplicates by title and returns up to 10 articles. This is a very thin macro news feed.

**What the agent receives**:
```
## NVDA News, from 2026-05-03 to 2026-05-10:

### NVIDIA Reports Record Revenue (source: Reuters)
NVIDIA Corporation reported record quarterly revenue of $26 billion...
Link: https://...

### AI Chip Demand Drives NVIDIA Stock Higher (source: Motley Fool)
...
```

---

### 12.5 Fundamentals data — what is fetched and how

**Function**: `get_fundamentals(ticker)` → `yf.Ticker(ticker).info`

**What yfinance returns**: A large dictionary of ~100 fields. The code extracts these specific ones:

| Field | What it means |
|-------|--------------|
| `longName` | Full company name |
| `sector` | e.g. "Technology" |
| `industry` | e.g. "Semiconductors" |
| `marketCap` | Total market value |
| `trailingPE` | Price / Earnings (last 12 months) |
| `forwardPE` | Price / Expected next year earnings |
| `pegRatio` | PE divided by growth rate |
| `priceToBook` | Price / Book value per share |
| `trailingEps` | Earnings per share (last 12 months) |
| `forwardEps` | Expected EPS next year |
| `dividendYield` | Annual dividend / Price |
| `beta` | Volatility vs market (1.0 = same as market) |
| `fiftyTwoWeekHigh` / `Low` | 52-week price range |
| `totalRevenue` | Annual revenue |
| `grossProfits` | Revenue minus cost of goods |
| `ebitda` | Earnings before interest, tax, depreciation |
| `netIncomeToCommon` | Net profit |
| `profitMargins` | Net income / Revenue |
| `operatingMargins` | Operating income / Revenue |
| `returnOnEquity` | Net income / Shareholders equity |
| `returnOnAssets` | Net income / Total assets |
| `debtToEquity` | Total debt / Shareholders equity |
| `currentRatio` | Current assets / Current liabilities |
| `bookValue` | Net assets per share |
| `freeCashflow` | Cash from operations minus capex |

**Balance sheet**: `yf.Ticker(ticker).quarterly_balance_sheet`
Returns a DataFrame with rows = line items (Total Assets, Total Liabilities, Cash, etc.) and columns = quarterly dates (last 4 quarters).

**Income statement**: `yf.Ticker(ticker).quarterly_income_stmt`
Returns Revenue, Gross Profit, Operating Income, Net Income for last 4 quarters.

**Cash flow**: `yf.Ticker(ticker).quarterly_cashflow`
Returns Operating Cash Flow, Investing Cash Flow, Financing Cash Flow, Free Cash Flow for last 4 quarters.

**Look-ahead bias protection**: The `filter_financials_by_date()` function removes any quarterly columns dated after `curr_date`. So if you're analyzing May 2026 but Q2 2026 earnings haven't been released yet, those columns are stripped out.

**What is missing from the fundamentals**:
- No 5-year revenue trend (only last 4 quarters)
- No DCF (discounted cash flow) valuation
- No peer comparison (no sector average PE, no competitor data)
- No analyst price targets (yfinance has this but it's not fetched)
- No earnings surprise history
- No institutional ownership data

---

### 12.6 The caching system — how data is stored

The system has a two-level cache:

**Level 1 — OHLCV price cache** (`~/.tradingagents/cache/`):
- File: `<TICKER>-YFin-data-<start>-<end>.csv`
- Contains: 5 years of daily OHLCV data
- Refreshed: Only when the file doesn't exist (no TTL — it's permanent until you delete it)
- Problem: If you run NVDA today and again in 3 months, it still uses the old cached file. New price data won't be fetched.

**Level 2 — Analysis results** (`~/.tradingagents/logs/`):
- File: `<TICKER>/TradingAgentsStrategy_logs/full_states_log_<DATE>.json`
- Contains: Complete agent state — all reports, debate history, final decision
- Used by: The dashboard cache check (if you run the same ticker+date twice, it loads from here instantly)

**Level 3 — Memory log** (`~/.tradingagents/memory/trading_memory.md`):
- Contains: Past decisions, realized returns, reflections
- Used by: Portfolio Manager on every run to inject past lessons

---

### 12.7 The memory system — current state and limitations

**What it stores** (in `trading_memory.md`):
```markdown
## NVDA | 2026-05-01 | Buy
**Decision**: Buy
**Reflection**: [generated after outcome is known]
**Raw Return**: +8.3%
**Alpha vs SPY**: +5.1%
**Status**: resolved
```

**How it works**:
1. After each analysis, the decision is saved as "pending" (no return yet)
2. On the next run for the same ticker, the system fetches the current price, calculates the return since the last decision, generates a reflection using the LLM, and marks it "resolved"
3. The Portfolio Manager receives the last few same-ticker decisions + cross-ticker lessons as context

**Current limitations of the memory system**:

1. **Only stores the final decision** — not the full reasoning chain. The Portfolio Manager sees "we said Buy on May 1 and it went up 8%" but not *why* we said Buy or which specific indicators drove it.

2. **No structured learning** — the reflection is free-text generated by the LLM. There's no structured extraction of "RSI was 65 and the stock went up" → "RSI above 60 is a positive signal for this ticker."

3. **No indicator memory** — the system doesn't remember what the RSI, MACD, or Bollinger Band values were when it made the decision. So it can't learn "when RSI was 72 we said Buy and it dropped — RSI above 70 is a sell signal for NVDA."

4. **No news memory** — the system doesn't remember what news was present when it made the decision. So it can't learn "earnings beats consistently lead to 5%+ moves for this ticker."

5. **No cross-ticker pattern memory** — the system doesn't learn "when semiconductor stocks are all showing RSI > 70, the sector tends to pull back."

6. **Memory is only injected into Portfolio Manager** — the Market Analyst, News Analyst, and Fundamentals Analyst don't see past decisions. They always start fresh.

7. **No time-decay** — a decision from 2 years ago is weighted the same as one from last week.

---

### 12.8 How to improve the data pipeline

#### News improvements (high impact)

**Problem**: yfinance gives you 20 article titles and summaries. That's thin.

**Option 1 — Add RSS feed scraping** (free):
```python
import feedparser

RSS_FEEDS = {
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "ft_markets": "https://www.ft.com/markets?format=rss",
    "wsj_markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "seeking_alpha": "https://seekingalpha.com/feed.xml",
}

def get_rss_news(ticker: str, lookback_days: int = 7) -> str:
    """Fetch and filter RSS news for a ticker."""
    articles = []
    for name, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if ticker.lower() in entry.title.lower() or ticker.lower() in entry.summary.lower():
                articles.append(entry)
    return format_articles(articles)
```

**Option 2 — Add NewsAPI** (free tier: 100 requests/day):
```python
import requests

def get_newsapi_articles(ticker: str, company_name: str, days: int = 7) -> str:
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": f"{ticker} OR {company_name}",
        "from": (date.today() - timedelta(days=days)).isoformat(),
        "sortBy": "relevancy",
        "apiKey": os.getenv("NEWSAPI_KEY"),
        "language": "en",
        "pageSize": 20,
    }
    response = requests.get(url, params=params)
    return format_newsapi_response(response.json())
```

**Option 3 — Add Reddit/StockTwits scraping** (for actual social sentiment):
```python
import praw  # Reddit API

def get_reddit_sentiment(ticker: str) -> str:
    """Get posts from r/stocks, r/investing, r/wallstreetbets mentioning the ticker."""
    reddit = praw.Reddit(client_id=..., client_secret=..., user_agent=...)
    subreddits = ["stocks", "investing", "SecurityAnalysis"]
    posts = []
    for sub in subreddits:
        for post in reddit.subreddit(sub).search(ticker, limit=10, time_filter="week"):
            posts.append({"title": post.title, "score": post.score, "comments": post.num_comments})
    return format_reddit_posts(posts)
```

#### Fundamentals improvements (medium impact)

**Problem**: Only last 4 quarters, no peer comparison, no DCF.

**Option 1 — Add multi-year trend**:
```python
# Change quarterly to annual for trend analysis
data = yf.Ticker(ticker).income_stmt  # 4 years of annual data
# Calculate YoY revenue growth, margin expansion/contraction
```

**Option 2 — Add analyst consensus**:
```python
info = yf.Ticker(ticker).info
analyst_target = info.get("targetMeanPrice")  # Average analyst price target
analyst_count  = info.get("numberOfAnalystOpinions")
recommendation = info.get("recommendationMean")  # 1=Strong Buy, 5=Strong Sell
```

**Option 3 — Add earnings calendar**:
```python
calendar = yf.Ticker(ticker).calendar
next_earnings = calendar.get("Earnings Date")  # When is the next earnings report?
```

#### Memory system improvements (high impact for long-term use)

**Problem**: Memory only stores final decisions, not the data that drove them.

**Proposed improvement — structured memory entries**:

Instead of just storing:
```
NVDA | 2026-05-01 | Buy | +8.3%
```

Store:
```json
{
  "ticker": "NVDA",
  "date": "2026-05-01",
  "decision": "Buy",
  "return": "+8.3%",
  "indicators_at_decision": {
    "rsi": 58.4,
    "macd": 2.1,
    "close_50_sma_distance": "+3.2%",
    "bollinger_position": "middle"
  },
  "news_sentiment": "positive",
  "earnings_proximity_days": 45,
  "market_regime": "uptrend",
  "outcome": "correct"
}
```

This structured data would let the Portfolio Manager learn:
- "When RSI was 55-65 and MACD was positive, our Buy calls were correct 73% of the time"
- "When earnings were within 14 days, our predictions were less reliable"
- "In downtrend market regimes, our Buy calls underperformed"

This is the most impactful improvement you could make to the system.

---

### 12.9 Data quality issues to be aware of

| Issue | Impact | Workaround |
|-------|--------|-----------|
| yfinance OHLCV cache never expires | Stale price data after weeks | Delete `~/.tradingagents/cache/` periodically |
| News is only 20 articles max | Thin news coverage | Add RSS or NewsAPI (see 12.8) |
| No full article text | LLM only sees headlines + 1-2 sentence summaries | Use web scraping to fetch full articles |
| Fundamentals only last 4 quarters | No long-term trend | Switch to annual data for trend analysis |
| Social sentiment is inferred from news | Not real social data | Add Reddit/StockTwits API |
| Non-US stocks have less yfinance coverage | Incomplete data for international tickers | Use Alpha Vantage for non-US stocks |
| yfinance rate limits | Occasional failures | The `yf_retry()` function handles this with exponential backoff |

---

*Section added: May 2026*

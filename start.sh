#!/bin/bash

# TradingAgents Streamlit Launcher
# Quick start script for the dashboard

echo "🚀 Starting TradingAgents Dashboard..."
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "⚠️  Virtual environment not found. Creating one..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source .venv/bin/activate

# Check if dependencies are installed
if ! python -c "import streamlit" 2>/dev/null; then
    echo "📥 Installing dependencies..."
    pip install -e .
    echo "✅ Dependencies installed"
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from example..."
    cp .env.example .env
    echo "✅ .env file created - please add your API keys!"
    echo ""
    echo "Edit .env and add your API keys, then run this script again."
    exit 1
fi

# Check if at least one API key is set
if ! grep -q "API_KEY=sk-" .env && ! grep -q "API_KEY=AIza" .env; then
    echo "⚠️  No API keys found in .env file"
    echo "Please add at least one LLM provider API key to .env"
    echo ""
    echo "Supported providers:"
    echo "  - OPENAI_API_KEY (OpenAI GPT models)"
    echo "  - GOOGLE_API_KEY (Google Gemini models)"
    echo "  - ANTHROPIC_API_KEY (Anthropic Claude models)"
    echo "  - DEEPSEEK_API_KEY (DeepSeek models)"
    echo ""
    exit 1
fi

echo ""
echo "✅ All checks passed!"
echo ""
echo "🌐 Opening dashboard at http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Launch Streamlit
streamlit run streamlit_app.py

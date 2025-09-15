#!/bin/bash

# Bank Nifty Strategy Runner Script

case "$1" in
    "run")
        echo "🚀 Running Bank Nifty Strategy..."
        python3 manage.py run_strategy
        ;;
    "profit")
        echo "💰 Running Strategy in Profit-Only Mode..."
        python3 manage.py run_strategy --profit-only
        ;;
    "watch")
        echo "👀 Running Strategy in Continuous Monitoring Mode..."
        python3 manage.py run_strategy --watch
        ;;
    "simulate")
        echo "🎮 Running Strategy in Simulation Mode..."
        python3 manage.py run_strategy --simulate
        ;;
    "force-simulate")
        echo "🔄 Force Running Strategy in Simulation Mode (WebSocket issues)..."
        python3 manage.py run_strategy --simulate
        ;;
    "test")
        echo "🔧 Testing Connection..."
        python3 manage.py test_connection
        ;;
    "setup")
        echo "⚙️ Setting up Strategy Configuration..."
        python3 manage.py setup_strategy
        ;;
    "status")
        echo "📊 Checking Strategy Status..."
        python3 strategy_status.py
        ;;
    "market")
        echo "🕐 Checking Market Hours..."
        python3 check_market_hours.py
        ;;
    "update")
        echo "📝 Updating Daily Parameters..."
        python3 update_daily_params.py
        ;;
    "params")
        echo "📋 Showing Current Parameters..."
        python3 update_daily_params.py --show
        ;;
    *)
        echo "🏦 Bank Nifty Strategy Runner"
        echo "================================"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  run      - Run live strategy (9:15 AM - 1:15 PM)"
        echo "  profit   - Run strategy in profit-only mode (high-probability trades)"
        echo "  watch    - Run strategy with continuous monitoring (wait for strong signals)"
        echo "  simulate - Run strategy in simulation mode"
        echo "  force-simulate - Force simulation mode (when WebSocket fails)"
        echo "  test     - Test connection and configuration"
        echo "  setup    - Setup strategy configuration"
        echo "  status   - Show current strategy status"
        echo "  market   - Check market hours"
        echo "  update   - Update daily parameters"
        echo "  params   - Show current parameters"
        echo ""
        echo "Examples:"
        echo "  $0 run      # Live trading"
        echo "  $0 profit   # Profit-only mode"
        echo "  $0 watch    # Continuous monitoring"
        echo "  $0 simulate # Test mode"
        echo "  $0 force-simulate # When WebSocket fails"
        echo "  $0 status   # Check status"
        ;;
esac 
#!/bin/bash

# Bank Nifty High Frequency Breakout Strategy Runner
# This script sets up and runs the strategy

echo "🚀 Bank Nifty High Frequency Breakout Strategy"
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Function to setup strategy
setup_strategy() {
    echo "📊 Setting up strategy configuration..."
    
    # Check if closing price is provided
    if [ -z "$1" ]; then
        echo "⚠️  No closing price provided. Will attempt to fetch automatically."
        python manage.py setup_strategy
    else
        echo "💰 Using provided closing price: ₹$1"
        python manage.py setup_strategy --closing-price $1
    fi
}

# Function to run strategy
run_strategy() {
    echo "🔄 Running strategy..."
    python manage.py run_strategy
}

# Function to test connection
test_connection() {
    echo "🔧 Testing Alice Blue connection..."
    if [ "$1" = "--skip-websocket" ]; then
        python manage.py test_connection --skip-websocket
    else
        python manage.py test_connection
    fi
}

# Function to test strategy logic
test_logic() {
    echo "🎯 Testing strategy logic..."
    python test_strategy_logic.py
}

# Function to update daily parameters
update_params() {
    echo "📅 Updating daily parameters..."
    python update_daily_params.py
}

# Function to show current parameters
show_params() {
    echo "📊 Showing current parameters..."
    python update_daily_params.py show
}

# Function to show help
show_help() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  setup [CLOSING_PRICE]  - Setup strategy with yesterday's closing price"
    echo "  run                    - Run the strategy (9:15-2:45 PM for testing)"
    echo "  test [--skip-websocket] - Test Alice Blue connection and WebSocket"
    echo "  logic                  - Test strategy logic (works anytime)"
    echo "  update                 - Update daily parameters interactively"
    echo "  params                 - Show current daily parameters"
    echo "  help                   - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 update              - Update daily parameters (interactive)"
    echo "  $0 params              - Show current parameters"
    echo "  $0 test                - Test connection (works anytime)"
    echo "  $0 test --skip-websocket - Test connection without WebSocket"
    echo "  $0 logic               - Test strategy logic without trading"
    echo "  $0 run                 - Run the strategy (market hours only)"
    echo ""
    echo "Note: Strategy runs between 9:15 AM and 2:45 PM (extended for testing)"
    echo "      Use 'update' command to set daily parameters"
    echo "      Use 'params' command to check current parameters"
}

# Main script logic
case "$1" in
    "setup")
        setup_strategy $2
        ;;
    "run")
        run_strategy
        ;;
    "test")
        test_connection $2
        ;;
    "logic")
        test_logic
        ;;
    "update")
        update_params
        ;;
    "params")
        show_params
        ;;
    "help"|"--help"|"-h"|"")
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac 
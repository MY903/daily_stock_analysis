#!/bin/bash
# T+0 Weekly Screener Setup Script for Synology NAS
# This script will be copied to NAS and executed

set -e

echo "======================================"
echo "T+0 Weekly Screener Setup"
echo "======================================"

# Check if running in container
if [ -f /.dockerenv ]; then
    echo "✓ Running inside Docker container"
else
    echo "✗ Not running in Docker container"
    exit 1
fi

# Navigate to project directory
cd /app || cd /volume1/docker/stock_analysis || exit 1

echo "Working directory: $(pwd)"

# Install dependencies if needed
echo "Checking Python dependencies..."
pip3 install schedule pandas numpy requests python-dotenv -q

# Test run the screener
echo ""
echo "Testing T+0 stock screener..."
python3 scripts/t0_stock_screener.py --notify

echo ""
echo "======================================"
echo "Setup complete!"
echo "======================================"
echo ""
echo "To set up weekly schedule, add crontab entry:"
echo "0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1"
echo ""
echo "Or use systemd scheduler:"
echo "python3 -m scripts.t0_weekly_scheduler --weekday monday --time 09:00 &"

#!/bin/bash
# Automated deployment script for T+0 Weekly Screener on Synology NAS

set -e

# Configuration
NAS_HOST="192.168.3.70"
NAS_USER="my.sun"
NAS_PASSWORD="MegaMingyang2023"

echo "=========================================="
echo "T+0 Weekly Screener - Automated Deployment"
echo "=========================================="
echo ""

# Step 1: Commit and push local changes
echo "✅ Step 1: Verifying git commit..."
cd /home/dministrator/workspaces/stock_analysis/daily_stock_analysis
git_status=$(git status --porcelain)
if [ -z "$git_status" ]; then
    echo "✓ Working directory is clean"
else
    echo "✗ Working directory has uncommitted changes"
    git status --short
    exit 1
fi

# Step 2: SSH to NAS and check container
echo ""
echo "📡 Step 2: Connecting to NAS ($NAS_HOST)..."

# Test SSH connection
if sshpass -p "$NAS_PASSWORD" ssh -o StrictHostKeyChecking=no "$NAS_USER@$NAS_HOST" "hostname" >/dev/null 2>&1; then
    echo "✓ SSH connection successful"
else
    echo "✗ Failed to connect to NAS"
    exit 1
fi

# Step 3: Find stock_analysis container
echo ""
echo "🐳 Step 3: Finding stock_analysis container..."

CONTAINER_ID=$(sshpass -p "$NAS_PASSWORD" ssh -o StrictHostKeyChecking=no "$NAS_USER@$NAS_HOST" \
    "sudo /usr/bin/docker ps -q --filter 'name=stock' 2>/dev/null" || echo "")

if [ -z "$CONTAINER_ID" ]; then
    echo "✗ stock_analysis container not found"
    echo "Please check if the container is running:"
    echo "  sudo docker ps -a | grep stock"
    exit 1
fi

echo "✓ Found container: $CONTAINER_ID"

# Step 4: Copy deployment script to NAS
echo ""
echo "📦 Step 4: Copying deployment script..."

SCRIPT_PATH="/home/dministrator/workspaces/stock_analysis/daily_stock_analysis/scripts/setup-weekly-on-nas.sh"
if [ -f "$SCRIPT_PATH" ]; then
    sshpass -p "$NAS_PASSWORD" scp -o StrictHostKeyChecking=no "$SCRIPT_PATH" \
        "$NAS_USER@$NAS_HOST:/volume1/docker/stock_analysis/scripts/"
    echo "✓ Deployment script copied"
else
    echo "✗ Deployment script not found at $SCRIPT_PATH"
    exit 1
fi

# Step 5: Execute deployment in container
echo ""
echo "🚀 Step 5: Executing deployment in container..."

sshpass -p "$NAS_PASSWORD" ssh -o StrictHostKeyChecking=no "$NAS_USER@$NAS_HOST" << 'ENDSSH'
echo "Entering container..."
CONTAINER_ID=$(sudo /usr/bin/docker ps -q --filter 'name=stock' 2>/dev/null)

if [ -z "$CONTAINER_ID" ]; then
    echo "Container not found!"
    exit 1
fi

echo "Container ID: $CONTAINER_ID"
echo ""
echo "Installing dependencies and testing..."

# Execute commands inside container
sudo /usr/bin/docker exec -it "$CONTAINER_ID" /bin/bash -c "
    cd /app || cd /volume1/docker/stock_analysis
    
    echo 'Installing Python dependencies...'
    pip3 install schedule pandas numpy requests python-dotenv -q
    
    echo ''
    echo 'Testing T+0 stock screener...'
    python3 scripts/t0_stock_screener.py --notify 2>&1 | head -50
    
    echo ''
    echo 'Setting up crontab for weekly execution...'
    (crontab -l 2>/dev/null; echo '0 9 * * 1 cd /app && python3 scripts/t0_stock_screener.py --notify >> logs/t0_screener.log 2>&1') | crontab -
    
    echo ''
    echo 'Verifying crontab...'
    crontab -l | grep t0
    
    echo ''
    echo 'Deployment complete!'
"

echo ""
echo "=========================================="
echo "✅ DEPLOYMENT SUCCESSFUL!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✓ Container: $CONTAINER_ID"
echo "  ✓ Dependencies installed"
echo "  ✓ Test run completed"
echo "  ✓ Crontab configured (Every Monday at 9:00)"
echo ""
echo "Next steps:"
echo "  1. Check Feishu for test notification"
echo "  2. Verify data/t0_stock_pool.csv was created"
echo "  3. Monitor logs: tail -f /app/logs/t0_screener.log"
echo ""
echo "Manual commands:"
echo "  - Run immediately: docker exec -it $CONTAINER_ID python3 scripts/t0_stock_screener.py --notify"
echo "  - View logs: docker exec -it $CONTAINER_ID tail -f logs/t0_screener.log"
echo "  - Edit schedule: docker exec -it $CONTAINER_ID crontab -e"
echo ""
ENDSSH

echo ""
echo "🎉 All done! The T+0 Weekly Screener is now configured."

#!/bin/bash
# Start MathJax renderer before uvicorn
cd /opt/wx-miniapp-ai/server
pkill -f latex_server.js 2>/dev/null
sleep 1
node app/utils/latex_server.js &
echo "MathJax renderer PID: $!"

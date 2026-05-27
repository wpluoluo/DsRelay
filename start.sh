#!/bin/sh
# Start Node.js sidecar proxy for opencode.ai routing
node /app/node_proxy.js &
NODE_PID=$!

# Start the main Python proxy
python /app/app.py

# If Python exits, stop Node.js
kill $NODE_PID 2>/dev/null

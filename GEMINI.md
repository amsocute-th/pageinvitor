# Agent Behavior Guidelines

- DO NOT stop, kill, or cancel any active background processes or servers (such as `web_server.py` running the dashboard) unless the user explicitly and clearly requests to do so in a message.
- Always ask the user for confirmation before proposing to terminate a running background task.

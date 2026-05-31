FROM dailyco/pipecat-base:latest

# The meeting brain (claude-agent-sdk) shells out to the Claude Code CLI, so the
# runtime needs Node + the CLI on PATH. Without it, wake-name MCP actions fail
# (the bot still listens/speaks; it just can't carry out tool requests).
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# bot.py imports the `app` package (config, meeting pipeline, services).
COPY ./app ./app
COPY ./bot.py bot.py

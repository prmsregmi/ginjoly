"""Meeting task agent.

Second application on ginjoly's shared voice infra. Joins a meeting through an
external Playwright bridge (mixed audio over a websocket), listens passively,
and only acts when addressed by a wake name — executing the request against
external MCP servers (Jira/Slack/Gmail) and speaking the result back.
"""

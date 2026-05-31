# Carleton — your meeting never forgets

You walk out of a two-hour call and can remember maybe the last three things said. The decisions, the tasks people casually agreed to, the one detail that was the whole point — gone. So you either spend 30 minutes rebuilding the meeting from memory, or you let it slip.

**Carleton sits in the call and does the remembering for you.** It listens the entire time, builds a live structured understanding of what's happening, and — the part that matters — **acts on it**: files the ticket, sends the email, drafts the doc. The moment someone asks, or in one batch at the end. Right there, in the meeting.

**Video demo (< 60s):** _TBA_

---

## How it works

Carleton joins your Google Meet as a guest (Playwright + Chrome), captures the mixed audio, and runs it through a Pipecat voice pipeline:

```
Meet audio → VAD → STT → WakeNameGate → TTS → back into the call
```

The design is deliberately **passive**. There is no conversational LLM in the pipeline, so Carleton never rambles, never interrupts, and costs almost nothing while it listens. It only speaks when addressed by name. Two things run off the voice path:

**1. Rolling extraction (background, every few minutes).** New transcript lines are folded into a structured working artifact:
- **context** — a tight running summary of what's been decided
- **open_tasks** — concrete, addressable asks ("create a ticket for the login bug")
- **preference_candidates** — durable team practices worth keeping across meetings

Because the brain reads `context + open_tasks + last N lines` instead of the full transcript, **cost scales with new speech per interval, not meeting length** — a two-hour call costs about the same per tick as a ten-minute one.

**2. The meeting brain (on demand).** When someone says *"Carleton, file that ticket"* or *"Carleton, email the deck to Sam,"* the `WakeNameGate` catches it and dispatches to a Claude Agent SDK agent wired to MCP tools — **Jira, Slack, Gmail, Linear, Google Drive** (plus servers you add at runtime from the dashboard). It executes immediately and confirms in one spoken sentence. At meeting end, **"run tasks"** executes everything Carleton noted that nobody verbally triggered, through the same tool interface.

Confirmed team preferences are written to long-term memory (Obsidian), so the next meeting starts already knowing how the team works.

**Production deployment.** The same pipeline is packaged for **Pipecat Cloud** (`bot.py` Daily-WebRTC entrypoint + Dockerfile + `pcc-deploy.toml`, cloud-built), where it runs as an auto-scaling agent — scale-to-zero when idle, an instance per session.

---

## Pipecat, Nemotron, and Cekura

### Pipecat
The entire voice path is Pipecat: Silero VAD, swappable STT/TTS, and the frame pipeline on `PipelineWorker`/`WorkerRunner`. The `WakeNameGate` is a custom `FrameProcessor` between STT and TTS that drops interim frames, suppresses self-echo (the bot re-hears its own TTS through the mixed Meet stream), and dispatches addressed requests **off** the voice path so the pipeline never blocks. Shipped to production on Pipecat Cloud via cloud build.

### Nemotron (open weights)
Carleton runs NVIDIA open models on the two jobs that happen constantly, where open-weights latency and cost win:
- **Rolling extraction (default):** `nvidia/nemotron-3-super` served over a vLLM OpenAI-compatible endpoint, called with a **forced JSON schema** and thinking disabled. It turns raw transcript lines into the `context / open_tasks / preference_candidates` artifact on every tick — fast, cheap, and structured. Anthropic is available as a drop-in fallback via one env var.
- **Speech-to-text:** **NVIDIA Parakeet** streaming ASR as a first-class STT provider (Deepgram and Gradium are the alternates), with VAD-driven turn finalization.

### Cekura
The hardest correctness problem for a passive, always-on meeting agent isn't answering well — it's **knowing when it's being addressed**. Acting on a mere mention of its name ("we should ask Carleton later") or on crosstalk is worse than missing a request. We treated this as a measurable property and built an evaluation suite around it.

We authored a **30-scenario test suite in Cekura**, run through Cekura's hosted **Pipecat (WebRTC) simulation** against the deployed agent. Each scenario pairs a distinct persona and speaking style with an intent and an expected outcome, spanning four dimensions:

1. **Addressed requests** — one per tool (Jira/Slack/Gmail/Linear/Drive), verifying the gate fires and the brain selects the correct tool.
2. **False-trigger traps** — the agent's name spoken *about* it, not *to* it; the bot must stay silent.
3. **Underspecified requests** — missing a required field; the bot must ask for exactly what it needs rather than guess.
4. **Impossible requests** — unsupported actions; the bot must decline plainly.

Cekura drives each persona conversation end-to-end and scores the transcripts, giving us per-dimension signal instead of anecdotes. The suite surfaced the expected failure mode — the agent occasionally reacting to its name mid-sentence — which we closed by hardening the `WakeNameGate`: leading-filler tolerance ("hey / ok so" before the name), strict first-meaningful-token addressing so mid-sentence mentions can't trigger, and self-echo suppression. On the re-run, the false-trigger class was eliminated while addressed-request and tool-selection coverage held. The result is a repeatable regression suite we can re-run on every change rather than a one-time check.

---

## What's new in the hackathon

Carleton was built during the hackathon:

- The passive meeting listener — Pipecat pipeline with no conversational LLM and the wake-word gate
- Rolling Nemotron extraction with snapshot-then-apply semantics so lines are never dropped mid-pass
- The meeting brain with MCP tool dispatch (Jira, Slack, Gmail, Linear, Google Drive, plus runtime-added servers)
- The end-of-meeting batch runner — the same executor the wake word uses
- Long-term Obsidian memory of team preferences across meetings
- The Carleton dashboard (Next.js + WebSocket: live transcript, tasks, and activity per meeting)
- The 30-scenario Cekura evaluation suite and the gate hardening it drove
- Pipecat Cloud deployment (Daily-WebRTC entrypoint, cloud build)

Built on top of Pipecat, Pipecat Cloud, the provider SDKs (NVIDIA, Deepgram, Cartesia, Anthropic), and the MCP servers.

---

## Feedback on the tools

**Pipecat** — the frame model is clean and genuinely composable. The one rough edge: there's no first-class way to run a side-effect off a frame. Both the wake-word dispatch and the rolling extractor need to fire async work without blocking the pipeline, and the only option is a raw `asyncio.create_task` that you must track and cancel yourself at teardown. We built that bookkeeping (cancel-on-End/Cancel, awaited cleanup), but a tracked `FrameProcessor.spawn_task()` that the framework cancels at cleanup would make this safe by default.

**Nemotron** — `nemotron-3-super` was a strong fit for high-frequency structured extraction: low latency with thinking off, and reliable schema-constrained JSON for short contexts, at a cost profile that makes a per-few-minutes loop practical. Parakeet streaming ASR integrated cleanly over websocket. Where it could improve: JSON adherence drifts on longer, messier inputs and benefits from strict schema re-prompting, and the streaming ASR's turn-finalization semantics took iteration to align with VAD stop events — clearer guidance there would shorten integration.

**Cekura** — the hosted Pipecat integration was the highlight: point it at a deployed agent (provider, API key, agent name) and it runs persona scenarios with zero glue, and auto-generating scenarios from an agent description is a fast on-ramp. Three things would make it stronger for agents like ours:
- **Multi-speaker simulation.** The simulation is single-caller / two-party, so it can't reproduce concurrent crosstalk — which is precisely the toughest false-trigger case for a meeting listener. N concurrent simulated speakers in one room would be high-value.
- **Consistent agent identifiers.** The `PipecatTracer` SDK takes an integer `agent_id` while the observe REST path uses a string identifier — easy to trip over.
- **Tracing for LLM-less pipelines.** The `PipecatTracer` assumes an in-pipeline `LLMContext` for transcript/tool-call capture. Pipelines that run the agent off-path (like ours) have no such context, so tool-call observability doesn't fit; documenting a supported pattern for this shape would help.

---

## Running it

```bash
# Backend bridge (FastAPI + Playwright + the voice pipeline):
cd connector/bridge
uv run --project ../../server --env-file ../../server/.env python main.py   # :8000

# Dashboard:
cd connector/web && npm run dev                                              # :3000

# Deploy the agent to Pipecat Cloud:
cd server
pc cloud auth login
pc cloud secrets set carleton-secrets --file .env.secrets
pc cloud deploy
```

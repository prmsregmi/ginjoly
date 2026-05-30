"use client";

import { useState, useEffect, useRef } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

type TranscriptLine =
  | { kind: "speech"; speaker: string; text: string }
  | { kind: "ai"; text: string }
  | { kind: "action"; label: string; detail: string };

type BotState = "idle" | "joining" | "waiting" | "live" | "error";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const AVATAR_COLORS: Record<string, string> = {
  Aria: "#f97316",
  Alex: "#7c3aed",
  Jordan: "#2563eb",
  Sam: "#059669",
};

function avatarColor(name: string) {
  return AVATAR_COLORS[name] ?? "#6b7280";
}

function fmt(s: number) {
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// ─── Small components ─────────────────────────────────────────────────────────

function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  return (
    <div
      style={{ width: size, height: size, background: avatarColor(name), flexShrink: 0 }}
      className="rounded-full flex items-center justify-center text-white font-semibold"
    >
      <span style={{ fontSize: size * 0.38 }}>{name[0].toUpperCase()}</span>
    </div>
  );
}

function StatusBadge({ state, status }: { state: BotState; status: string }) {
  const configs: Record<BotState, { color: string; pulse: boolean; label: string }> = {
    idle:    { color: "bg-gray-500",   pulse: false, label: "Idle" },
    joining: { color: "bg-yellow-500", pulse: true,  label: "Joining…" },
    waiting: { color: "bg-blue-500",   pulse: true,  label: "Waiting to be admitted" },
    live:    { color: "bg-green-500",  pulse: true,  label: "Live" },
    error:   { color: "bg-red-500",    pulse: false, label: "Error" },
  };
  const cfg = configs[state];
  return (
    <div className="flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${cfg.color} ${cfg.pulse ? "animate-pulse" : ""}`} />
      <span className="text-sm text-gray-300">{state === "live" ? cfg.label : status || cfg.label}</span>
    </div>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors group"
    >
      <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} className="group-hover:-translate-x-0.5 transition-transform">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
      </svg>
      Back
    </button>
  );
}

// ─── Landing ──────────────────────────────────────────────────────────────────

function LandingView({ onJoin }: { onJoin: (url: string) => void }) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleJoin = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("http://localhost:8000/api/join", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meeting_url: trimmed }),
      });
      if (!res.ok) throw new Error();
      onJoin(trimmed);
    } catch {
      setError("Backend unreachable — run: cd backend && python main.py");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#09090f] flex flex-col items-center justify-center px-4">
      {/* Logo */}
      <div className="mb-10 flex flex-col items-center gap-3">
        <div className="w-12 h-12 rounded-2xl bg-orange-500 flex items-center justify-center">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
            <path d="M12 2a3 3 0 0 1 3 3v4a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/>
            <path d="M19 10a7 7 0 0 1-14 0H3a9 9 0 0 0 8 8.94V21H8v2h8v-2h-3v-2.06A9 9 0 0 0 21 10h-2z"/>
          </svg>
        </div>
        <div className="text-center">
          <h1 className="text-2xl font-semibold text-white tracking-tight">Aria</h1>
          <p className="text-sm text-gray-500 mt-1">AI meeting assistant</p>
        </div>
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-[#111118] border border-white/[0.06] rounded-2xl p-6 shadow-xl">
        <p className="text-sm font-medium text-gray-300 mb-4">Send Aria to a Google Meet</p>

        <div className="space-y-3">
          <div className="relative">
            <input
              className="w-full bg-[#1a1a24] border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-white placeholder-gray-600 outline-none focus:border-orange-500/60 focus:ring-1 focus:ring-orange-500/20 transition-all"
              placeholder="https://meet.google.com/xxx-xxxx-xxx"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleJoin()}
              autoFocus
            />
          </div>

          <button
            onClick={handleJoin}
            disabled={loading || !url.trim()}
            className="w-full bg-orange-500 hover:bg-orange-400 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-xl py-3 transition-colors"
          >
            {loading ? "Starting bot…" : "Join meeting"}
          </button>

          {error && (
            <div className="flex items-start gap-2 bg-red-950/40 border border-red-900/40 rounded-xl px-3 py-2.5">
              <svg className="w-4 h-4 text-red-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              </svg>
              <p className="text-xs text-red-300">{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* Feature list */}
      <div className="mt-8 w-full max-w-md grid grid-cols-3 gap-3">
        {[
          { icon: "🎙️", label: "Listens to every speaker" },
          { icon: "🧠", label: "Understands context" },
          { icon: "⚡", label: "Creates tickets & more" },
        ].map((f) => (
          <div key={f.label} className="bg-[#111118] border border-white/[0.05] rounded-xl p-3 text-center">
            <div className="text-xl mb-1.5">{f.icon}</div>
            <div className="text-xs text-gray-500 leading-snug">{f.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Meeting room ─────────────────────────────────────────────────────────────

function MeetingView({ meetingUrl, onBack }: { meetingUrl: string; onBack: () => void }) {
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [botState, setBotState] = useState<BotState>("joining");
  const [status, setStatus] = useState("Starting bot…");
  const [statusHistory, setStatusHistory] = useState<string[]>(["Starting bot…"]);
  const [elapsed, setElapsed] = useState(0);
  const [activeTab, setActiveTab] = useState<"transcript" | "status" | "actions">("transcript");
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const shortUrl = meetingUrl.replace(/^https?:\/\/meet\.google\.com\//, "");

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws");
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);

      if (data.type === "status") {
        const msg: string = data.message;
        setStatus(msg);
        setStatusHistory((h) => [...h, msg]);

        const lower = msg.toLowerCase();
        if (lower.includes("starting") || lower.includes("navigating")) setBotState("joining");
        else if (lower.includes("waiting") || lower.includes("admitted")) setBotState("waiting");
        else if (lower.includes("audio capture active") || lower.includes("live")) setBotState("live");
        else if (lower.includes("error")) setBotState("error");
      }

      if (data.type === "transcript") {
        setLines((prev) => [...prev, { kind: "speech", speaker: `Speaker ${data.speaker ?? 0}`, text: data.text }]);
      }

      if (data.type === "assistant") {
        setLines((prev) => [...prev, { kind: "ai", text: data.text }]);
      }

      if (data.type === "action") {
        setLines((prev) => [...prev, { kind: "action", label: data.label, detail: data.detail }]);
      }
    };

    ws.onclose = () => {
      setBotState("error");
      setStatus("Connection lost");
    };

    return () => ws.close();
  }, []);

  useEffect(() => {
    if (botState !== "live") return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [botState]);

  useEffect(() => {
    if (activeTab === "transcript") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, activeTab]);

  const actions = lines.filter((l) => l.kind === "action") as Extract<TranscriptLine, { kind: "action" }>[];

  return (
    <div className="min-h-screen bg-[#09090f] flex flex-col">
      {/* Top bar */}
      <header className="border-b border-white/[0.06] bg-[#09090f] px-5 py-3.5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <BackButton onClick={onBack} />
          <div className="w-px h-4 bg-white/10" />
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-orange-500 flex items-center justify-center text-xs font-bold text-white">A</div>
            <div>
              <div className="text-sm font-medium text-white leading-none">Aria</div>
              <div className="text-xs text-gray-500 mt-0.5 font-mono">{shortUrl}</div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <StatusBadge state={botState} status={status} />
          {botState === "live" && (
            <div className="text-xs text-gray-500 font-mono tabular-nums">{fmt(elapsed)}</div>
          )}
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b border-white/[0.06] px-5 flex gap-0 shrink-0">
        {(["transcript", "status", "actions"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors capitalize ${
              activeTab === tab
                ? "border-orange-500 text-white"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab}
            {tab === "actions" && actions.length > 0 && (
              <span className="ml-1.5 bg-orange-500 text-white text-xs rounded-full px-1.5 py-0.5">
                {actions.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {/* Transcript tab */}
        {activeTab === "transcript" && (
          <div className="max-w-2xl mx-auto px-5 py-5 space-y-5">
            {lines.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3 text-center">
                <div className="w-10 h-10 rounded-full bg-orange-500/10 border border-orange-500/20 flex items-center justify-center">
                  <span className="w-2.5 h-2.5 rounded-full bg-orange-500 animate-pulse" />
                </div>
                <p className="text-sm text-gray-500">
                  {botState === "waiting" ? "Waiting to be admitted to the meeting…" : "Aria is listening…"}
                </p>
                <p className="text-xs text-gray-600">Transcript will appear here once audio is captured</p>
              </div>
            ) : (
              lines.map((line, i) => {
                if (line.kind === "speech") return (
                  <div key={i} className="flex gap-3 items-start">
                    <Avatar name={line.speaker} size={28} />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-gray-500 mb-1">{line.speaker}</div>
                      <p className="text-sm text-gray-200 leading-relaxed">{line.text}</p>
                    </div>
                  </div>
                );

                if (line.kind === "ai") return (
                  <div key={i} className="flex gap-3 items-start">
                    <Avatar name="Aria" size={28} />
                    <div className="flex-1 min-w-0 bg-orange-950/30 border border-orange-900/30 rounded-xl px-3.5 py-2.5">
                      <div className="text-xs text-orange-400 mb-1 font-medium">Aria</div>
                      <p className="text-sm text-orange-100/90 leading-relaxed">{line.text}</p>
                    </div>
                  </div>
                );

                if (line.kind === "action") return (
                  <div key={i} className="flex items-center gap-2.5 pl-10">
                    <div className="flex items-center gap-1.5">
                      <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="text-xs font-medium text-green-400">{line.label}</span>
                    </div>
                    <span className="text-xs text-gray-600">·</span>
                    <span className="text-xs text-gray-500">{line.detail}</span>
                  </div>
                );

                return null;
              })
            )}
            <div ref={bottomRef} />
          </div>
        )}

        {/* Status tab */}
        {activeTab === "status" && (
          <div className="max-w-2xl mx-auto px-5 py-5">
            <div className="bg-[#111118] border border-white/[0.06] rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/[0.06] flex items-center justify-between">
                <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">Bot activity log</span>
                <StatusBadge state={botState} status={status} />
              </div>
              <div className="divide-y divide-white/[0.04]">
                {statusHistory.length === 0 ? (
                  <p className="text-xs text-gray-600 px-4 py-4">No activity yet</p>
                ) : (
                  [...statusHistory].reverse().map((s, i) => (
                    <div key={i} className="flex items-start gap-3 px-4 py-3">
                      <div className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${i === 0 ? "bg-orange-500" : "bg-gray-700"}`} />
                      <p className="text-sm text-gray-300">{s}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Current state card */}
            <div className="mt-4 grid grid-cols-3 gap-3">
              {[
                { label: "Bot state", value: botState.charAt(0).toUpperCase() + botState.slice(1) },
                { label: "Duration", value: botState === "live" ? fmt(elapsed) : "—" },
                { label: "Transcript lines", value: lines.filter(l => l.kind === "speech").length.toString() },
              ].map((stat) => (
                <div key={stat.label} className="bg-[#111118] border border-white/[0.06] rounded-xl px-4 py-3">
                  <div className="text-xs text-gray-500 mb-1">{stat.label}</div>
                  <div className="text-lg font-semibold text-white">{stat.value}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions tab */}
        {activeTab === "actions" && (
          <div className="max-w-2xl mx-auto px-5 py-5">
            {actions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 gap-2 text-center">
                <div className="text-2xl">⚡</div>
                <p className="text-sm text-gray-500">No actions taken yet</p>
                <p className="text-xs text-gray-600">Ask Aria to create tickets, search docs, etc.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {actions.map((a, i) => (
                  <div key={i} className="bg-[#111118] border border-white/[0.06] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="w-6 h-6 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center shrink-0">
                      <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    <div>
                      <div className="text-sm font-medium text-white">{a.label}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{a.detail}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export default function Home() {
  const [meetingUrl, setMeetingUrl] = useState<string | null>(null);

  if (meetingUrl) {
    return <MeetingView meetingUrl={meetingUrl} onBack={() => setMeetingUrl(null)} />;
  }

  return <LandingView onJoin={setMeetingUrl} />;
}

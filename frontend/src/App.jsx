import { useState, useCallback, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import ChatPanel from "./components/ChatPanel/ChatPanel";
import DashboardPanel from "./components/DashboardPanel/DashboardPanel";
import "./styles.css";

const API_BASE = "/api/v1";

async function fetchSources() {
  const res = await fetch(`${API_BASE}/sources`);
  if (!res.ok) return [];
  return res.json();
}

async function callChat({ sourceId, question, userId = "demo-user", threadId }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_id: sourceId,
      question,
      user_id: userId,
      thread_id: threadId || undefined,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Draggable Divider ─────────────────────────────────────────────────────────
function useResizable(initialPx = 420, min = 280, max = 720) {
  const [width, setWidth] = useState(initialPx);
  const dragging = useRef(false);

  const onMouseDown = useCallback(() => {
    dragging.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  useEffect(() => {
    const onMove = (e) => {
      if (!dragging.current) return;
      const next = Math.min(max, Math.max(min, e.clientX));
      setWidth(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [min, max]);

  return [width, onMouseDown];
}

export { ReactMarkdown, fetchSources };
export default function App() {
  const [messages,   setMessages]   = useState(() => JSON.parse(localStorage.getItem('qm_msgs') || '[]'));
  const [dashSpec,   setDashSpec]   = useState(() => JSON.parse(localStorage.getItem('qm_dash') || 'null'));
  const [resultRows, setResultRows] = useState(() => JSON.parse(localStorage.getItem('qm_rows') || '[]'));
  const [loading,    setLoading]    = useState(false);
  const [threadId,   setThreadId]   = useState(() => localStorage.getItem('qm_thread') || null);
  const [sources,    setSources]    = useState([]);
  const [sourceId,   setSourceId]   = useState(() => localStorage.getItem('qm_source') || "");

  const [panelWidth, onDividerDown] = useResizable(420, 280, 760);

  // Sync state to localStorage
  useEffect(() => {
    localStorage.setItem('qm_msgs', JSON.stringify(messages));
    localStorage.setItem('qm_dash', JSON.stringify(dashSpec));
    localStorage.setItem('qm_rows', JSON.stringify(resultRows));
    if (threadId) localStorage.setItem('qm_thread', threadId);
    if (sourceId) localStorage.setItem('qm_source', sourceId);
  }, [messages, dashSpec, resultRows, threadId, sourceId]);

  const clearSession = () => {
    localStorage.clear();
    setMessages([]);
    setDashSpec(null);
    setResultRows([]);
    setThreadId(null);
  };

  // Load sources on mount
  useEffect(() => {
    fetchSources().then((list) => {
      setSources(list);
      if (list.length > 0 && !sourceId) setSourceId(list[0].id);
    });
  }, []);

  const handleAsk = useCallback(async ({ question }) => {
    if (!sourceId || !question) return;
    setLoading(true);
    setMessages((m) => [...m, { role: "user", text: question }]);
    try {
      const data = await callChat({ sourceId, question, threadId });
      if (data.thread_id) setThreadId(data.thread_id);
      if (data.dashboard_spec) setDashSpec(data.dashboard_spec);
      if (Array.isArray(data.results) && data.results.length) setResultRows(data.results);
      setMessages((m) => [
        ...m,
        {
          role:    "assistant",
          text:    data.summary || "Query complete.",
          sql:     data.sql || null,
          intent:  data.intent,
          reasoning: data.reasoning || [],
        },
      ]);
    } catch (err) {
      setMessages((m) => [...m, { role: "system", text: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }, [sourceId, threadId]);

  const selectedSource = sources.find((s) => s.id === sourceId);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="brand-dot" />
          QueryMind
        </div>
        <div className="topbar-status">
          <div className="status-dot" />
          {threadId ? (
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
              thread: {threadId.slice(0, 8)}…
            </span>
          ) : (
            <span>No active session</span>
          )}
          <button 
            onClick={clearSession}
            style={{ marginLeft: '12px', background: 'transparent', border: '1px solid #334155', color: '#94a3b8', borderRadius: '4px', cursor: 'pointer', fontSize: '11px', padding: '2px 8px' }}
          >
            Clear Session
          </button>
        </div>
      </header>

      <div className="split-layout" style={{ gridTemplateColumns: `${panelWidth}px 4px 1fr` }}>
        <ChatPanel
          messages={messages}
          loading={loading}
          onAsk={handleAsk}
          sources={sources}
          sourceId={sourceId}
          onSourceChange={setSourceId}
          selectedSource={selectedSource}
        />

        {/* Draggable divider */}
        <div className="resize-divider" onMouseDown={onDividerDown} />

        <DashboardPanel
          dashboardSpec={dashSpec}
          data={resultRows}
          loading={loading}
        />
      </div>
    </div>
  );
}

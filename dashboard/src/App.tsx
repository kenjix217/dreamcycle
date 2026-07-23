import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Clock,
  Database,
  Gauge,
  GitBranch,
  History,
  Loader2,
  Moon,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  ShieldAlert,
  Sparkles,
  Target,
  Trash2,
  X,
  XCircle,
  type LucideIcon,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  DreamCycleApi,
  DreamCycleApiError,
  type AdapterState,
  type CycleJob,
  type DashboardSettings,
  type HealthState,
  type MemoryItem,
  type RecallPayload,
  type RecordTurnPayload,
} from './api';

type ConnectionState = 'checking' | 'online' | 'offline';
type EventTone = 'neutral' | 'success' | 'warning' | 'danger';

interface EventEntry {
  id: string;
  title: string;
  detail: string;
  tone: EventTone;
  timestamp: number;
}

const STORAGE_KEY = 'dreamcycle.dashboard.settings.v1';
const DEFAULT_BASE_URL = import.meta.env.VITE_DREAMCYCLE_API_BASE || '/dreamcycle-api';
const PIPELINE_STEPS = [
  'Hermes conversation',
  'Turn stored',
  'Memory recalled',
  'Human reviewed',
  'Dataset forged',
  'LoRA evaluated',
  'Promoted or rolled back',
];

const DEFAULT_TURN: RecordTurnPayload = {
  user_content: '',
  assistant_content: '',
  source: 'dreamcycle-dashboard',
  conversation_id: '',
  trace_id: '',
  importance: 0.6,
  success: true,
  data_classification: 'public',
  metadata: {},
};

const DEFAULT_RECALL: RecallPayload = {
  query: '',
  limit: 6,
  role: null,
  source: null,
  successful_only: false,
  reviewed_only: false,
  minimum_importance: 0,
  classifications: [],
  metric: null,
};

export function App() {
  const [settings, setSettings] = useState<DashboardSettings>(() => loadSettings());
  const api = useMemo(() => new DreamCycleApi(settings), [settings]);
  const [health, setHealth] = useState<HealthState | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('checking');
  const [adapter, setAdapter] = useState<AdapterState | null>(null);
  const [job, setJob] = useState<CycleJob | null>(null);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [turn, setTurn] = useState<RecordTurnPayload>(DEFAULT_TURN);
  const [recall, setRecall] = useState<RecallPayload>(DEFAULT_RECALL);
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [notice, setNotice] = useState<{ tone: EventTone; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [confirmText, setConfirmText] = useState('');

  const pushEvent = useCallback((title: string, detail: string, tone: EventTone = 'neutral') => {
    setEvents((prev) =>
      [
        {
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          title,
          detail,
          tone,
          timestamp: Date.now(),
        },
        ...prev,
      ].slice(0, 24),
    );
  }, []);

  const showNotice = useCallback((tone: EventTone, text: string) => {
    setNotice({ tone, text });
    window.setTimeout(() => setNotice(null), 4600);
  }, []);

  const refresh = useCallback(async () => {
    setBusy('refresh');
    setConnection('checking');
    try {
      const nextHealth = await api.health();
      setHealth(nextHealth);
      setConnection('online');
      if (settings.apiKey.trim()) {
        const nextAdapter = await api.activeAdapter();
        setAdapter(nextAdapter);
      }
      pushEvent('Sidecar refresh', nextHealth.version || 'DreamCycle sidecar reachable', 'success');
    } catch (error) {
      setConnection('offline');
      showNotice('danger', messageFor(error));
      pushEvent('Sidecar unavailable', messageFor(error), 'danger');
    } finally {
      setBusy(null);
    }
  }, [api, pushEvent, settings.apiKey, showNotice]);

  useEffect(() => {
    persistSettings(settings);
  }, [settings]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.cycleStatus(job.id);
        setJob(next);
        if (next.status === 'completed' || next.status === 'failed') {
          pushEvent(
            `Cycle ${next.status}`,
            next.error || `Job ${next.id.slice(0, 12)} reached ${next.status}`,
            next.status === 'completed' ? 'success' : 'danger',
          );
          const nextAdapter = await api.activeAdapter().catch(() => null);
          if (nextAdapter) setAdapter(nextAdapter);
        }
      } catch (error) {
        pushEvent('Cycle poll failed', messageFor(error), 'warning');
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [api, job, pushEvent]);

  const handleSaveSettings = (event: FormEvent) => {
    event.preventDefault();
    persistSettings(settings);
    showNotice('success', 'Dashboard connection saved locally');
    void refresh();
  };

  const handleRecordTurn = async (event: FormEvent) => {
    event.preventDefault();
    setBusy('record');
    try {
      const recorded = await api.recordTurn(turn);
      setMemories((prev) => [recorded.assistant, recorded.user, ...prev].slice(0, 18));
      setTurn((prev) => ({ ...prev, user_content: '', assistant_content: '' }));
      pushEvent('Turn recorded', recorded.assistant.id, 'success');
      showNotice('success', 'Turn stored in DreamCycle memory');
    } catch (error) {
      showNotice('danger', messageFor(error));
      pushEvent('Record failed', messageFor(error), 'danger');
    } finally {
      setBusy(null);
    }
  };

  const handleRecall = async (event: FormEvent) => {
    event.preventDefault();
    setBusy('recall');
    try {
      const result = await api.recall(normalizeRecall(recall));
      setMemories(result.memories);
      pushEvent('Memory recalled', `${result.memories.length} scoped records returned`, 'success');
      showNotice('success', `${result.memories.length} memories recalled`);
    } catch (error) {
      showNotice('danger', messageFor(error));
      pushEvent('Recall failed', messageFor(error), 'danger');
    } finally {
      setBusy(null);
    }
  };

  const handleStartCycle = async () => {
    setBusy('cycle');
    try {
      const nextJob = await api.startCycle();
      setJob(nextJob);
      pushEvent('Cycle queued', nextJob.id, 'success');
      showNotice('success', 'Dream cycle queued');
    } catch (error) {
      showNotice('danger', messageFor(error));
      pushEvent('Cycle start failed', messageFor(error), 'danger');
    } finally {
      setBusy(null);
    }
  };

  const handleReview = async (memory: MemoryItem, approved: boolean) => {
    setBusy(memory.id);
    try {
      await api.review(memory.id, approved);
      setMemories((prev) =>
        prev.map((item) =>
          item.id === memory.id
            ? { ...item, reviewed: true, approved_for_training: approved }
            : item,
        ),
      );
      pushEvent(approved ? 'Memory approved' : 'Memory reviewed', memory.id, 'success');
    } catch (error) {
      showNotice('danger', messageFor(error));
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (memory: MemoryItem) => {
    setBusy(memory.id);
    try {
      await api.delete(memory.id);
      setMemories((prev) => prev.filter((item) => item.id !== memory.id));
      pushEvent('Memory deleted', memory.id, 'warning');
    } catch (error) {
      showNotice('danger', messageFor(error));
    } finally {
      setBusy(null);
    }
  };

  const handleRollback = async () => {
    if (confirmText !== 'ROLLBACK') {
      showNotice('warning', 'Type ROLLBACK before confirming adapter rollback');
      return;
    }
    setBusy('rollback');
    try {
      const result = await api.rollbackAdapter();
      setAdapter(result);
      setConfirmRollback(false);
      setConfirmText('');
      pushEvent('Adapter rollback', result.reason || result.active_path || 'rollback requested', 'warning');
      showNotice(result.accepted ? 'success' : 'warning', result.reason || 'Rollback returned no change');
    } catch (error) {
      showNotice('danger', messageFor(error));
      pushEvent('Rollback failed', messageFor(error), 'danger');
    } finally {
      setBusy(null);
    }
  };

  const approvedCount = memories.filter((item) => item.approved_for_training).length;
  const reviewedCount = memories.filter((item) => item.reviewed).length;
  const activeAdapterPath = adapter?.active_path || 'none';
  const cycleStatus = job?.status || 'idle';
  const phases = phaseRows(job);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Moon size={19} />
          </div>
          <div>
            <h1>DreamCycle Dashboard</h1>
            <p>Local memory, training, promotion, and rollback control</p>
          </div>
        </div>
        <div className="topbar-actions">
          <StatusPill state={connection} />
          <button className="btn btn-ghost" onClick={refresh} disabled={busy === 'refresh'}>
            {busy === 'refresh' ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            Refresh
          </button>
          <button className="btn btn-primary" onClick={handleStartCycle} disabled={busy === 'cycle'}>
            {busy === 'cycle' ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            Start Cycle
          </button>
        </div>
      </header>

      {notice && <div className={`notice notice-${notice.tone}`}>{notice.text}</div>}

      <section className="metrics-grid">
        <MetricCard
          icon={Activity}
          label="Sidecar"
          value={connection === 'online' ? 'Online' : connection === 'checking' ? 'Checking' : 'Offline'}
          unit={health?.version ? `version ${health.version}` : 'awaiting health'}
          tone={connection === 'online' ? 'success' : connection === 'offline' ? 'danger' : 'neutral'}
        />
        <MetricCard
          icon={GitBranch}
          label="Adapter"
          value={adapter?.available ? compactPath(activeAdapterPath) : 'Unavailable'}
          unit={adapter?.available ? 'active pointer' : 'adapter vault not configured'}
          tone={adapter?.active_path ? 'success' : 'warning'}
        />
        <MetricCard
          icon={Gauge}
          label="Cycle"
          value={cycleStatus}
          unit={job?.id ? `job ${job.id.slice(0, 12)}` : 'no active job'}
          tone={job?.status === 'failed' ? 'danger' : job?.status === 'completed' ? 'success' : 'neutral'}
        />
        <MetricCard
          icon={Database}
          label="Memory"
          value={`${memories.length}`}
          unit={`${reviewedCount} reviewed / ${approvedCount} approved`}
          tone={approvedCount > 0 ? 'success' : 'neutral'}
        />
      </section>

      <section className="workspace-grid">
        <aside className="side-rail">
          <Panel title="Connection" subtitle="Local sidecar target" icon={Network}>
            <form className="stack" onSubmit={handleSaveSettings}>
              <label className="field">
                <span>API base</span>
                <input
                  value={settings.baseUrl}
                  onChange={(event) => setSettings((prev) => ({ ...prev, baseUrl: event.target.value }))}
                  spellCheck={false}
                />
              </label>
              <label className="field">
                <span>API key</span>
                <input
                  type="password"
                  value={settings.apiKey}
                  onChange={(event) => setSettings((prev) => ({ ...prev, apiKey: event.target.value }))}
                  spellCheck={false}
                />
              </label>
              <button className="btn btn-solid" type="submit">
                <Save size={15} />
                Save
              </button>
            </form>
          </Panel>

          <Panel title="Adapter Vault" subtitle="Promotion pointer control" icon={ShieldAlert}>
            <div className="adapter-path" title={activeAdapterPath}>
              {activeAdapterPath}
            </div>
            <div className="button-row">
              <button className="btn btn-ghost" onClick={refresh}>
                <RefreshCw size={15} />
                Status
              </button>
              <button
                className="btn btn-danger"
                onClick={() => setConfirmRollback(true)}
                disabled={!adapter?.available}
              >
                <RotateCcw size={15} />
                Rollback
              </button>
            </div>
          </Panel>

          <Panel title="Cycle Rail" subtitle="Guarded improvement flow" icon={Sparkles}>
            <div className="pipeline">
              {PIPELINE_STEPS.map((step, index) => (
                <div key={step} className={index <= activeStepIndex(job) ? 'pipeline-step active' : 'pipeline-step'}>
                  <span>{index + 1}</span>
                  <p>{step}</p>
                </div>
              ))}
            </div>
          </Panel>
        </aside>

        <section className="main-column">
          <Panel title="Live Learning Graph" subtitle="Memory, review, and adapter signals" icon={BrainCircuit}>
            <MemoryGraph memories={memories} events={events} adapter={adapter} job={job} />
          </Panel>

          <div className="split-grid">
            <Panel title="Record Turn" subtitle="Write L2 episodic memory" icon={Database}>
              <form className="stack" onSubmit={handleRecordTurn}>
                <label className="field">
                  <span>User</span>
                  <textarea
                    value={turn.user_content}
                    onChange={(event) => setTurn((prev) => ({ ...prev, user_content: event.target.value }))}
                    rows={4}
                  />
                </label>
                <label className="field">
                  <span>Assistant</span>
                  <textarea
                    value={turn.assistant_content}
                    onChange={(event) =>
                      setTurn((prev) => ({ ...prev, assistant_content: event.target.value }))
                    }
                    rows={4}
                  />
                </label>
                <div className="form-grid">
                  <label className="field">
                    <span>Conversation</span>
                    <input
                      value={turn.conversation_id}
                      onChange={(event) =>
                        setTurn((prev) => ({ ...prev, conversation_id: event.target.value }))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Importance</span>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.05"
                      value={turn.importance}
                      onChange={(event) =>
                        setTurn((prev) => ({ ...prev, importance: Number(event.target.value) }))
                      }
                    />
                  </label>
                </div>
                <button className="btn btn-primary" type="submit" disabled={busy === 'record'}>
                  {busy === 'record' ? <Loader2 className="spin" size={15} /> : <Save size={15} />}
                  Record
                </button>
              </form>
            </Panel>

            <Panel title="Recall" subtitle="Search scoped L2 memory" icon={Search}>
              <form className="stack" onSubmit={handleRecall}>
                <label className="field">
                  <span>Query</span>
                  <textarea
                    value={recall.query}
                    onChange={(event) => setRecall((prev) => ({ ...prev, query: event.target.value }))}
                    rows={4}
                  />
                </label>
                <div className="form-grid">
                  <label className="field">
                    <span>Limit</span>
                    <input
                      type="number"
                      min="1"
                      max="50"
                      value={recall.limit}
                      onChange={(event) =>
                        setRecall((prev) => ({ ...prev, limit: Number(event.target.value) }))
                      }
                    />
                  </label>
                  <label className="field">
                    <span>Metric</span>
                    <select
                      value={recall.metric || ''}
                      onChange={(event) =>
                        setRecall((prev) => ({
                          ...prev,
                          metric: event.target.value ? (event.target.value as RecallPayload['metric']) : null,
                        }))
                      }
                    >
                      <option value="">default</option>
                      <option value="cosine">cosine</option>
                      <option value="l2">l2</option>
                      <option value="inner_product">inner product</option>
                    </select>
                  </label>
                </div>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={recall.reviewed_only}
                    onChange={(event) =>
                      setRecall((prev) => ({ ...prev, reviewed_only: event.target.checked }))
                    }
                  />
                  <span>Reviewed only</span>
                </label>
                <button className="btn btn-primary" type="submit" disabled={busy === 'recall'}>
                  {busy === 'recall' ? <Loader2 className="spin" size={15} /> : <Search size={15} />}
                  Recall
                </button>
              </form>
            </Panel>
          </div>

          <div className="split-grid reverse">
            <Panel title="Memory Review Queue" subtitle="Approve records for training" icon={CheckCircle2}>
              <MemoryList
                memories={memories}
                busy={busy}
                onApprove={(memory) => handleReview(memory, true)}
                onReject={(memory) => handleReview(memory, false)}
                onDelete={handleDelete}
              />
            </Panel>

            <Panel title="Cycle Monitor" subtitle="Queued, running, completed, failed" icon={History}>
              <CyclePanel job={job} phases={phases} events={events} />
            </Panel>
          </div>
        </section>
      </section>

      {confirmRollback && (
        <div className="modal-backdrop" role="presentation">
          <section className="rollback-modal" role="dialog" aria-modal="true" aria-labelledby="rollback-title">
            <div className="modal-header">
              <div>
                <h2 id="rollback-title">Confirm Adapter Rollback</h2>
                <p>Current adapter: {activeAdapterPath}</p>
              </div>
              <button className="icon-btn" onClick={() => setConfirmRollback(false)} aria-label="Close">
                <X size={16} />
              </button>
            </div>
            <label className="field">
              <span>Type ROLLBACK</span>
              <input
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                spellCheck={false}
                autoFocus
              />
            </label>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmRollback(false)}>
                Cancel
              </button>
              <button
                className="btn btn-danger"
                onClick={handleRollback}
                disabled={busy === 'rollback' || confirmText !== 'ROLLBACK'}
              >
                {busy === 'rollback' ? <Loader2 className="spin" size={15} /> : <RotateCcw size={15} />}
                Confirm Rollback
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function Panel({
  title,
  subtitle,
  icon: Icon,
  children,
}: {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  children: ReactNode;
}) {
  return (
    <section className="panel-gold card-shimmer">
      <div className="panel-heading">
        <div>
          <div className="panel-title">{title}</div>
          <div className="panel-sub">{subtitle}</div>
        </div>
        <div className="panel-icon">
          <Icon size={16} />
        </div>
      </div>
      {children}
    </section>
  );
}

function MetricCard({
  label,
  value,
  unit,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  icon: LucideIcon;
  tone: EventTone;
}) {
  return (
    <article className={`metric-gold metric-${tone}`}>
      <div className="metric-content">
        <div>
          <div className="m-label">{label}</div>
          <div className="m-value">{value}</div>
          <div className="m-unit">{unit}</div>
        </div>
        <div className="metric-icon">
          <Icon size={17} />
        </div>
      </div>
    </article>
  );
}

function StatusPill({ state }: { state: ConnectionState }) {
  const label = state === 'online' ? 'Sidecar Online' : state === 'checking' ? 'Checking' : 'Sidecar Offline';
  return (
    <span className={`status-pill status-${state}`}>
      <span />
      {label}
    </span>
  );
}

function MemoryGraph({
  memories,
  events,
  adapter,
  job,
}: {
  memories: MemoryItem[];
  events: EventEntry[];
  adapter: AdapterState | null;
  job: CycleJob | null;
}) {
  const nodes = graphNodes(memories, adapter, job);
  const activeEvents = events.slice(0, 5);
  return (
    <div className="graph-shell">
      <svg className="memory-graph" viewBox="0 0 980 360" role="img" aria-label="DreamCycle graph">
        <defs>
          <filter id="softGlow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {nodes.slice(1).map((node) => (
          <line key={`line-${node.id}`} x1="490" y1="180" x2={node.x} y2={node.y} className="graph-link" />
        ))}
        {nodes.map((node) => (
          <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
            <circle r={node.r} className={`graph-node ${node.tone}`} filter="url(#softGlow)" />
            <text y={node.r + 20} textAnchor="middle" className="graph-label">
              {node.label}
            </text>
          </g>
        ))}
      </svg>
      <div className="graph-side">
        <div className="graph-stat">
          <span>L2 Records</span>
          <strong>{memories.length}</strong>
        </div>
        <div className="graph-stat">
          <span>Reviewed</span>
          <strong>{memories.filter((item) => item.reviewed).length}</strong>
        </div>
        <div className="graph-stat">
          <span>Adapter</span>
          <strong>{adapter?.active_path ? 'active' : 'idle'}</strong>
        </div>
        <div className="mini-events">
          {activeEvents.length === 0 ? (
            <p>No local dashboard events yet</p>
          ) : (
            activeEvents.map((event) => (
              <div key={event.id} className={`mini-event event-${event.tone}`}>
                <span>{event.title}</span>
                <small>{formatTime(event.timestamp)}</small>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function MemoryList({
  memories,
  busy,
  onApprove,
  onReject,
  onDelete,
}: {
  memories: MemoryItem[];
  busy: string | null;
  onApprove: (memory: MemoryItem) => void;
  onReject: (memory: MemoryItem) => void;
  onDelete: (memory: MemoryItem) => void;
}) {
  if (memories.length === 0) {
    return <div className="empty-state">No recalled or recorded memories</div>;
  }
  return (
    <div className="memory-list">
      {memories.map((memory) => (
        <article key={memory.id} className="memory-row">
          <div className="memory-meta">
            <span>{memory.role}</span>
            <span>{memory.approved_for_training ? 'approved' : memory.reviewed ? 'reviewed' : 'pending'}</span>
            {typeof memory.similarity === 'number' && <span>{Math.round(memory.similarity * 100)}%</span>}
          </div>
          <p>{memory.content}</p>
          <div className="memory-actions">
            <button className="icon-btn" onClick={() => onApprove(memory)} disabled={busy === memory.id}>
              <CheckCircle2 size={15} />
            </button>
            <button className="icon-btn" onClick={() => onReject(memory)} disabled={busy === memory.id}>
              <XCircle size={15} />
            </button>
            <button className="icon-btn danger" onClick={() => onDelete(memory)} disabled={busy === memory.id}>
              <Trash2 size={15} />
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function CyclePanel({
  job,
  phases,
  events,
}: {
  job: CycleJob | null;
  phases: Array<{ name: string; status: string; detail: string }>;
  events: EventEntry[];
}) {
  return (
    <div className="cycle-panel">
      <div className="job-summary">
        <div>
          <span>Job</span>
          <strong>{job?.id ? job.id.slice(0, 18) : 'none'}</strong>
        </div>
        <div>
          <span>Status</span>
          <strong>{job?.status || 'idle'}</strong>
        </div>
        <div>
          <span>Updated</span>
          <strong>{job?.completed_at ? formatDate(job.completed_at) : job?.started_at ? formatDate(job.started_at) : '-'}</strong>
        </div>
      </div>

      <div className="phase-list">
        {phases.length === 0 ? (
          <div className="empty-state compact">No cycle phases reported</div>
        ) : (
          phases.map((phase) => (
            <div key={`${phase.name}-${phase.status}`} className="phase-row">
              <span className={phase.status === 'success' || phase.status === 'complete' ? 'dot ok' : 'dot'} />
              <div>
                <strong>{phase.name}</strong>
                <small>{phase.detail}</small>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="event-stream">
        {events.slice(0, 6).map((event) => (
          <div key={event.id} className={`event-row event-${event.tone}`}>
            <Clock size={13} />
            <div>
              <strong>{event.title}</strong>
              <small>{event.detail}</small>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function loadSettings(): DashboardSettings {
  if (typeof localStorage === 'undefined') {
    return { baseUrl: DEFAULT_BASE_URL, apiKey: '' };
  }
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') as Partial<DashboardSettings>;
    return {
      baseUrl: stored.baseUrl || DEFAULT_BASE_URL,
      apiKey: stored.apiKey || '',
    };
  } catch {
    return { baseUrl: DEFAULT_BASE_URL, apiKey: '' };
  }
}

function persistSettings(settings: DashboardSettings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

function normalizeRecall(value: RecallPayload): RecallPayload {
  return {
    ...value,
    source: value.source || null,
    role: value.role || null,
    query: value.query.trim(),
    classifications: value.classifications.filter(Boolean),
  };
}

function messageFor(error: unknown): string {
  if (error instanceof DreamCycleApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'DreamCycle request failed';
}

function compactPath(value: string): string {
  if (!value || value === 'none') return 'none';
  if (value.length <= 24) return value;
  const parts = value.split('/').filter(Boolean);
  return parts.length > 2 ? `.../${parts.slice(-2).join('/')}` : value.slice(0, 24);
}

function formatTime(value: number): string {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function activeStepIndex(job: CycleJob | null): number {
  if (!job) return 1;
  if (job.status === 'queued') return 4;
  if (job.status === 'running') return 5;
  if (job.status === 'completed') return 6;
  return 3;
}

function phaseRows(job: CycleJob | null): Array<{ name: string; status: string; detail: string }> {
  const phases = job?.report?.phases;
  if (!Array.isArray(phases)) return [];
  return phases
    .map((phase) => {
      if (!phase || typeof phase !== 'object') return null;
      const record = phase as Record<string, unknown>;
      return {
        name: String(record.name || 'phase'),
        status: String(record.status || 'unknown'),
        detail: String(record.reason || record.error || 'reported'),
      };
    })
    .filter((phase): phase is { name: string; status: string; detail: string } => phase !== null);
}

function graphNodes(memories: MemoryItem[], adapter: AdapterState | null, job: CycleJob | null) {
  const base = [
    { id: 'core', label: 'DreamCycle', x: 490, y: 180, r: 34, tone: 'core' },
    { id: 'l2', label: 'L2 Memory', x: 245, y: 105, r: 24, tone: memories.length ? 'success' : 'neutral' },
    {
      id: 'review',
      label: 'Review Gate',
      x: 300,
      y: 282,
      r: 23,
      tone: memories.some((item) => item.reviewed) ? 'success' : 'neutral',
    },
    {
      id: 'cycle',
      label: 'Cycle Job',
      x: 680,
      y: 95,
      r: 25,
      tone: job?.status === 'failed' ? 'danger' : job ? 'warning' : 'neutral',
    },
    {
      id: 'adapter',
      label: 'Adapter',
      x: 735,
      y: 274,
      r: 25,
      tone: adapter?.active_path ? 'success' : 'neutral',
    },
  ];
  return base;
}

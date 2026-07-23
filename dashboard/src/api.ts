export interface DashboardSettings {
  baseUrl: string;
  apiKey: string;
}

export interface HealthState {
  status?: string;
  version?: string;
  api?: string;
}

export interface AdapterState {
  available: boolean;
  active_path: string | null;
  accepted?: boolean | null;
  reason?: string | null;
  previous_path?: string | null;
}

export interface MemoryItem {
  id: string;
  namespace: string;
  user_id: string;
  content: string;
  role: string;
  source: string;
  conversation_id: string;
  trace_id: string;
  importance: number;
  success: boolean;
  reviewed: boolean;
  approved_for_training: boolean;
  data_classification: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  distance: number | null;
  similarity: number | null;
}

export interface KnowledgeItem {
  id: string;
  namespace: string;
  user_id: string;
  node_type: string;
  key: string;
  content: string;
  confidence: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  distance: number | null;
  similarity: number | null;
}

export interface KnowledgeStats {
  nodes: number;
  edges: number;
  provenance_links: number;
  node_types: Record<string, number>;
}

export interface KnowledgePromotePayload {
  memory_ids: string[];
  node_type: string;
  key: string;
  content: string;
  confidence: number;
  metadata: Record<string, unknown>;
}

export interface KnowledgeSearchPayload {
  query: string;
  limit: number;
  node_type?: string | null;
  metric?: 'cosine' | 'l2' | 'inner_product' | null;
}

export interface CycleJob {
  id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  report: Record<string, unknown> | null;
  error: string | null;
}

export interface RecordTurnPayload {
  user_content: string;
  assistant_content: string;
  source: string;
  conversation_id: string;
  trace_id: string;
  importance: number;
  success: boolean;
  data_classification: string;
  metadata: Record<string, unknown>;
}

export interface RecallPayload {
  query: string;
  limit: number;
  role?: string | null;
  source?: string | null;
  successful_only: boolean;
  reviewed_only: boolean;
  minimum_importance: number;
  classifications: string[];
  metric?: 'cosine' | 'l2' | 'inner_product' | null;
}

export class DreamCycleApiError extends Error {
  status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = 'DreamCycleApiError';
    this.status = status;
  }
}

export class DreamCycleApi {
  private settings: DashboardSettings;

  constructor(settings: DashboardSettings) {
    this.settings = settings;
  }

  health(): Promise<HealthState> {
    return this.request<HealthState>('GET', '/healthz', { auth: false });
  }

  activeAdapter(): Promise<AdapterState> {
    return this.request<AdapterState>('GET', '/v1/adapters/active');
  }

  rollbackAdapter(): Promise<AdapterState> {
    return this.request<AdapterState>('POST', '/v1/adapters/rollback');
  }

  startCycle(): Promise<CycleJob> {
    return this.request<CycleJob>('POST', '/v1/cycles');
  }

  cycleStatus(jobId: string): Promise<CycleJob> {
    return this.request<CycleJob>('GET', `/v1/cycles/${encodeURIComponent(jobId)}`);
  }

  recordTurn(payload: RecordTurnPayload): Promise<{ user: MemoryItem; assistant: MemoryItem }> {
    return this.request('POST', '/v1/memory/turns', { body: payload });
  }

  recall(payload: RecallPayload): Promise<{ memories: MemoryItem[] }> {
    return this.request('POST', '/v1/memory/search', { body: payload });
  }

  knowledgeStats(): Promise<KnowledgeStats> {
    return this.request('GET', '/v1/knowledge/stats');
  }

  promoteKnowledge(payload: KnowledgePromotePayload): Promise<KnowledgeItem> {
    return this.request('POST', '/v1/knowledge/promotions', { body: payload });
  }

  recallKnowledge(payload: KnowledgeSearchPayload): Promise<{ nodes: KnowledgeItem[] }> {
    return this.request('POST', '/v1/knowledge/search', { body: payload });
  }

  review(memoryId: string, approvedForTraining: boolean): Promise<{ success: boolean }> {
    return this.request('POST', `/v1/memory/${encodeURIComponent(memoryId)}/review`, {
      body: { approved_for_training: approvedForTraining },
    });
  }

  delete(memoryId: string): Promise<{ success: boolean }> {
    return this.request('DELETE', `/v1/memory/${encodeURIComponent(memoryId)}`);
  }

  private async request<T>(
    method: string,
    path: string,
    options: { body?: unknown; auth?: boolean } = {},
  ): Promise<T> {
    const headers: Record<string, string> = {};
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (options.auth !== false) {
      if (!this.settings.apiKey.trim()) {
        throw new DreamCycleApiError('DreamCycle API key is required');
      }
      headers.Authorization = `Bearer ${this.settings.apiKey}`;
    }
    const response = await fetch(`${trimTrailingSlash(this.settings.baseUrl)}${path}`, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    if (!response.ok) {
      const message = await errorMessage(response);
      throw new DreamCycleApiError(message, response.status);
    }
    return (await response.json()) as T;
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown; error?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (typeof body.error === 'string') return body.error;
  } catch {
    // Fall through to status text.
  }
  return `DreamCycle returned HTTP ${response.status}`;
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

import type { AgentArtsInvocationEnvelope } from './generated/contracts.ts';
import type {
  AgentArtsRuntimeTransport as AgentArtsTransportContract,
  RuntimeConfig,
} from './transport.ts';
import { validateRuntimeConfig } from './transport.ts';

const bridgeErrors = [
  'AGENTARTS_AUTH_ERROR',
  'AGENTARTS_RUNTIME_NOT_FOUND',
  'AGENTARTS_SERVER_ERROR',
  'AGENTARTS_HTTP_ERROR',
  'AGENTARTS_TIMEOUT',
  'AGENTARTS_NETWORK_ERROR',
  'INVALID_AGENTARTS_SESSION',
  'INVALID_RUNTIME_PAYLOAD',
];
export class AgentArtsTransportError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = 'AgentArtsTransportError';
  }
}

// Browser speaks only to its configured trusted bridge. Cloud URL/Authorization
// never enter this adapter. Session is correlation metadata, never business input.
export class AgentArtsRuntimeTransport implements AgentArtsTransportContract {
  readonly mode = 'AGENTARTS' as const;
  private readonly url: string;
  private readonly sessionId: string;
  private readonly fetcher: typeof fetch;
  constructor(
    config: Extract<RuntimeConfig, { mode: 'AGENTARTS' }>,
    private readonly onPresentation: (value: unknown) => void = () => {},
    options: { sessionId?: string; fetcher?: typeof fetch } = {},
  ) {
    validateRuntimeConfig(config);
    this.url = new URL(`/runtime/agentarts/${config.runtimeName}/invoke`, config.baseUrl).href;
    this.sessionId = options.sessionId ?? crypto.randomUUID();
    if (typeof this.sessionId !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(this.sessionId))
      throw new Error('INVALID_AGENTARTS_SESSION');
    this.fetcher = options.fetcher ?? globalThis.fetch;
  }
  async send(envelope: AgentArtsInvocationEnvelope, options?: { signal?: AbortSignal }) {
    const response = await this.fetcher.call(globalThis, this.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Copilot-Session-Id': this.sessionId,
      },
      body: JSON.stringify(envelope),
      signal: options?.signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    });
    let delivery: unknown;
    try {
      delivery = await response.json();
    } catch {
      delivery = null;
    }
    if (!response.ok) {
      const code =
        delivery && typeof delivery === 'object' && 'error' in delivery
          ? delivery.error
          : undefined;
      throw new AgentArtsTransportError(
        typeof code === 'string' && bridgeErrors.includes(code) ? code : 'AGENTARTS_BRIDGE_ERROR',
      );
    }
    if (
      !delivery ||
      typeof delivery !== 'object' ||
      Array.isArray(delivery) ||
      !Object.hasOwn(delivery, 'runtime') ||
      Object.keys(delivery).some((key) => !['runtime', 'presentation'].includes(key))
    ) {
      this.onPresentation(undefined);
      return { body: null };
    }
    const value = delivery as { runtime: unknown; presentation?: unknown };
    this.onPresentation(value.presentation);
    return {
      body: value.runtime,
      metadata: { httpStatus: response.status, sessionId: this.sessionId },
    };
  }
}

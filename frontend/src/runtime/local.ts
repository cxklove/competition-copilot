import type { AgentArtsInvocationEnvelope } from './generated/contracts.ts';
import type {
  LocalRuntimeTransport as LocalTransportContract,
  RuntimeConfig,
} from './transport.ts';
import { validateRuntimeConfig } from './transport.ts';

export const localInvocationPath = '/runtime/invoke';

// HTTP delivery only. P12/P14.1 validates the runtime portion; the presentation
// attachment remains unknown until P14.4 validates current request/ref binding.
export class LocalRuntimeTransport implements LocalTransportContract {
  readonly mode = 'LOCAL' as const;
  private readonly url: string;
  constructor(
    config: Extract<RuntimeConfig, { mode: 'LOCAL' }>,
    private readonly onPresentation: (value: unknown) => void = () => {},
    private readonly fetcher: typeof fetch = globalThis.fetch,
  ) {
    validateRuntimeConfig(config);
    this.url = new URL(localInvocationPath, config.baseUrl).href;
  }
  async send(envelope: AgentArtsInvocationEnvelope, options?: { signal?: AbortSignal }) {
    const response = await this.fetcher.call(globalThis, this.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(envelope),
      signal: options?.signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    });
    if (!response.ok) throw new Error('LOCAL_HTTP_FAILURE');
    let delivery: unknown;
    try {
      delivery = await response.json();
    } catch {
      delivery = null;
    }
    if (
      !delivery ||
      typeof delivery !== 'object' ||
      Array.isArray(delivery) ||
      !Object.hasOwn(delivery, 'runtime') ||
      Object.keys(delivery).some((key) => !['runtime', 'presentation'].includes(key))
    ) {
      this.onPresentation(undefined);
      return { body: null }; // Client classifies invalid delivery as CONTRACT_ERROR.
    }
    const value = delivery as { runtime: unknown; presentation?: unknown };
    this.onPresentation(value.presentation);
    return { body: value.runtime, metadata: { httpStatus: response.status } };
  }
}

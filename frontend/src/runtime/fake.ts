import type { AgentArtsInvocationEnvelope } from './generated/contracts.ts';
import type { RuntimeMode, RuntimeTransport, TransportMetadata } from './transport.ts';

type Step = { body: unknown; metadata?: TransportMetadata } | { error: Error };

export class FakeRuntimeTransport implements RuntimeTransport {
  readonly mode: RuntimeMode;
  readonly calls: AgentArtsInvocationEnvelope[] = [];
  private readonly steps: Step[];
  constructor(mode: RuntimeMode, steps: Step[]) {
    this.mode = mode;
    this.steps = steps.map((step) => ('error' in step ? step : structuredClone(step)));
  }
  async send(envelope: AgentArtsInvocationEnvelope, _options?: { signal?: AbortSignal }) {
    this.calls.push(structuredClone(envelope));
    const step = this.steps.shift();
    if (!step) throw new Error('FAKE_SCRIPT_EXHAUSTED');
    if ('error' in step) throw step.error;
    return structuredClone(step);
  }
}

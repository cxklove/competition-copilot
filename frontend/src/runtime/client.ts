import type {
  AgentArtsInvocationEnvelope,
  AgentRequest,
  AgentResponse,
  PublicRuntimeResult,
} from './generated/contracts.ts';
import type { RuntimeConfig, RuntimeTransport } from './transport.ts';
import { validateRuntimeConfig } from './transport.ts';
import { jsonCopy, responseOf, validateInput, validateOutput } from './validation.ts';

export type ClientErrorCode = 'TRANSPORT_ERROR' | 'CONTRACT_ERROR' | 'RUNTIME_ERROR' | 'ABORTED';
export class RuntimeClientError extends Error {
  readonly code: ClientErrorCode;
  readonly runtimeCode?: string;
  constructor(code: ClientErrorCode, runtimeCode?: string) {
    super(code);
    this.name = 'RuntimeClientError';
    this.code = code;
    this.runtimeCode = runtimeCode;
  }
}

export type ResumeEnvelope = Omit<AgentArtsInvocationEnvelope, 'request'> & {
  continuation_ref: string;
};

export class RuntimeInvocationClient {
  private readonly transport: RuntimeTransport;
  constructor(transport: RuntimeTransport, config: RuntimeConfig) {
    try {
      validateRuntimeConfig(config);
    } catch {
      throw new RuntimeClientError('CONTRACT_ERROR');
    }
    if (transport.mode !== config.mode) throw new RuntimeClientError('CONTRACT_ERROR');
    this.transport = transport;
  }

  async invoke(request: AgentRequest, options?: { signal?: AbortSignal }): Promise<AgentResponse> {
    return responseOf(await this.exchange({ request }, options));
  }

  async resume(
    envelope: ResumeEnvelope,
    options?: { signal?: AbortSignal },
  ): Promise<AgentResponse> {
    return responseOf(await this.exchange(envelope, options));
  }

  // Use exchange for the safe continuation_ref as well as the unchanged AgentResponse.
  // There is no stored last request/session/approval state and no automatic retry.
  async exchange(
    envelope: AgentArtsInvocationEnvelope,
    options?: { signal?: AbortSignal },
  ): Promise<PublicRuntimeResult> {
    let input: AgentArtsInvocationEnvelope;
    try {
      input = validateInput(jsonCopy(envelope));
    } catch {
      throw new RuntimeClientError('CONTRACT_ERROR');
    }
    const id =
      input.request?.request_id ??
      input.clarification?.source_request_id ??
      input.approval?.source_request_id ??
      input.message?.source_request_id;
    if (!id) throw new RuntimeClientError('CONTRACT_ERROR');
    if (options?.signal?.aborted) throw new RuntimeClientError('ABORTED');
    let body: unknown;
    try {
      const reply = await this.transport.send(input, options);
      body = reply.body; // Transport metadata is deliberately not business input/output.
    } catch {
      throw new RuntimeClientError(options?.signal?.aborted ? 'ABORTED' : 'TRANSPORT_ERROR');
    }
    if (options?.signal?.aborted) throw new RuntimeClientError('ABORTED');
    let result: PublicRuntimeResult;
    try {
      result = validateOutput(jsonCopy(body), id);
    } catch {
      throw new RuntimeClientError('CONTRACT_ERROR');
    }
    if (result.error) throw new RuntimeClientError('RUNTIME_ERROR', result.error.code);
    return result;
  }
}

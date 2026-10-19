import type { AgentArtsInvocationEnvelope } from './generated/contracts.ts';

export type RuntimeMode = 'LOCAL' | 'AGENTARTS';
export type RuntimeConfig =
  { mode: 'LOCAL'; baseUrl: string } | { mode: 'AGENTARTS'; baseUrl: string; runtimeName: string };

export type TransportMetadata = {
  correlationId?: string;
  sessionId?: string;
  httpStatus?: number;
  elapsedMs?: number;
};

export interface RuntimeTransport {
  readonly mode: RuntimeMode;
  send(
    envelope: AgentArtsInvocationEnvelope,
    options?: { signal?: AbortSignal },
  ): Promise<{ body: unknown; metadata?: TransportMetadata }>;
}

export interface LocalRuntimeTransport extends RuntimeTransport {
  readonly mode: 'LOCAL';
}
export interface AgentArtsRuntimeTransport extends RuntimeTransport {
  readonly mode: 'AGENTARTS';
}

export function validateRuntimeConfig(config: RuntimeConfig): void {
  if (!config || typeof config !== 'object' || Array.isArray(config))
    throw new Error('INVALID_PUBLIC_CONFIG');
  const keys = config.mode === 'LOCAL' ? ['mode', 'baseUrl'] : ['mode', 'baseUrl', 'runtimeName'];
  if (
    !['LOCAL', 'AGENTARTS'].includes(config.mode) ||
    typeof config.baseUrl !== 'string' ||
    config.baseUrl !== config.baseUrl.trim() ||
    Object.keys(config).some((key) => !keys.includes(key))
  )
    throw new Error('INVALID_PUBLIC_CONFIG');
  const url = new URL(config.baseUrl);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error('INVALID_PUBLIC_CONFIG');
  }
  if (
    config.mode === 'AGENTARTS' &&
    (typeof config.runtimeName !== 'string' ||
      !/^[a-z][a-z0-9-]{0,46}[a-z0-9]$/.test(config.runtimeName))
  ) {
    throw new Error('INVALID_PUBLIC_CONFIG');
  }
}

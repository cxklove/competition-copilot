import { createPresentedClient } from './results/ErrorPresentation.tsx';
import { AgentArtsRuntimeTransport } from './runtime/agentarts.ts';
import type { ArtifactReader } from './results/artifacts.ts';

export function createAgentArtsClient(baseUrl: string, runtimeName: string) {
  let attachment: unknown;
  const config = { mode: 'AGENTARTS', baseUrl, runtimeName } as const;
  const client = createPresentedClient(
    new AgentArtsRuntimeTransport(config, (value) => {
      attachment = value;
    }),
    config,
  );
  const readArtifacts: ArtifactReader = () => attachment;
  return { client, readArtifacts };
}

import { RuntimeInvocationClient } from './runtime/client.ts';
import { LocalRuntimeTransport } from './runtime/local.ts';
import type { ArtifactReader } from './results/artifacts.ts';

export function createLocalClient(baseUrl: string) {
  let attachment: unknown;
  const config = { mode: 'LOCAL', baseUrl } as const;
  const client = new RuntimeInvocationClient(
    new LocalRuntimeTransport(config, (value) => {
      attachment = value;
    }),
    config,
  );
  const readArtifacts: ArtifactReader = () => attachment;
  return { client, readArtifacts };
}

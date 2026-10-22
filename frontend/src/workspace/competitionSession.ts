import type { ArtifactReader, LinkedArtifact } from '../results/artifacts.ts';
import { validateArtifacts } from '../results/artifacts.ts';
import type { AgentContext, AgentResponse } from '../runtime/generated/contracts.ts';
import type { InvocationClient } from './useConversation.ts';

export type ReadRecord = {
  response: AgentResponse;
  context: AgentContext;
  artifacts: LinkedArtifact[];
};
const key = (response: AgentResponse) =>
  JSON.stringify([response.request_id, response.outcome, response.audit]);

// Cache validated hosting projections, not new facts or a business registry.
// A center read must not overwrite the attachment still displayed by Copilot.
export function competitionSession(
  client: InvocationClient,
  reader: ArtifactReader | undefined,
  received: (record: ReadRecord) => void,
) {
  const snapshots = new Map<string, unknown>();
  const contexts = new Map<string, AgentContext>();
  const wrapped: InvocationClient = {
    async exchange(envelope, options) {
      if (envelope.request)
        contexts.set(envelope.request.request_id, structuredClone(envelope.request.context ?? {}));
      const result = await client.exchange(envelope, options);
      if (result.response) {
        const response = result.response;
        const raw = reader?.(response);
        snapshots.set(key(response), raw === undefined ? undefined : structuredClone(raw));
        try {
          received({
            response: structuredClone(response),
            context: contexts.get(response.request_id) ?? {},
            artifacts: validateArtifacts(response, raw),
          });
        } catch {
          // Preserve invalid attachment for the existing fail-closed result UI.
        }
      }
      return result;
    },
    async invoke(request, options) {
      return (await this.exchange({ request }, options)).response!;
    },
  };
  return {
    client: wrapped,
    readArtifacts: (response: AgentResponse) => snapshots.get(key(response)),
  };
}

import { Ajv2020 } from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import schemas from './generated/contracts.json' with { type: 'json' };
import type {
  AgentArtsInvocationEnvelope,
  AgentResponse,
  ApprovalRequest,
  AuditReferences,
  PlanReference,
  PublicRuntimeResult,
} from './generated/contracts.ts';

const ajv = new Ajv2020({
  strict: true,
  allErrors: true,
  coerceTypes: false,
  useDefaults: false,
  removeAdditional: false,
});
addFormats(ajv);
const input = ajv.compile<AgentArtsInvocationEnvelope>(schemas.AgentArtsInvocationEnvelope);
const output = ajv.compile<PublicRuntimeResult>(schemas.PublicRuntimeResult);

function requireContract(condition: unknown): asserts condition {
  if (!condition) throw new Error('INVALID_RUNTIME_CONTRACT');
}

type Schema = {
  type?: string;
  $ref?: string;
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  items?: Schema;
};
type Rule = 'strip' | 'python-strip' | 'utc' | { items: Rule };

// Pydantic StringConstraints uses Unicode White_Space (not JS trim's BOM).
function strip(value: string): string {
  return value.replace(
    /^[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu,
    '',
  );
}

function applyRule(value: unknown, rule: Rule): unknown {
  if (value == null) return value;
  if (typeof rule === 'object') {
    requireContract(Array.isArray(value));
    return value.map((v) => applyRule(v, rule.items));
  }
  requireContract(typeof value === 'string');
  if (rule === 'strip' || rule === 'python-strip') {
    // Student public field validators call Python str.strip, unlike StableId.
    const canonical =
      rule === 'strip'
        ? strip(value)
        : value.replace(
            /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu,
            '',
          );
    requireContract(canonical.length > 0);
    return canonical;
  }
  // P12 AgentContract canonicalizes aware datetimes to UTC; keep microseconds.
  const fraction = value.match(/[Tt]\d{2}:\d{2}:\d{2}(?:\.(\d+))?/)?.[1] ?? '';
  const micros = fraction.slice(0, 6).padEnd(6, '0');
  return new Date(value).toISOString().slice(0, 19) + (Number(micros) ? `.${micros}` : '') + 'Z';
}

function compare(a: string, b: string): number {
  const left = Array.from(a, (v) => v.codePointAt(0)!);
  const right = Array.from(b, (v) => v.codePointAt(0)!);
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    if (left[i] !== right[i]) return left[i] - right[i];
  }
  return left.length - right.length;
}

function orderedUnique(values: unknown[]): unknown[] {
  requireContract(new Set(values).size === values.length);
  return values.sort((a, b) => compare(String(a), String(b)));
}

// Only public normalization/structural invariants; no capability or Domain decisions.
function canonicalize(
  raw: unknown,
  root: 'AgentArtsInvocationEnvelope' | 'PublicRuntimeResult',
): unknown {
  const document = schemas[root];
  const definitions = document.$defs as unknown as Record<string, Schema>;
  const rules = schemas.normalization as unknown as Record<string, Record<string, Rule>>;
  function visit(value: unknown, schema: Schema, model?: string): unknown {
    if (value == null) return value;
    if (schema.$ref) {
      const name = schema.$ref.split('/').at(-1)!;
      return visit(value, definitions[name], name);
    }
    if (schema.anyOf) {
      // Public unions are nullable, not competing business variants.
      return visit(
        value,
        schema.anyOf.find(
          (s) => '$ref' in s || 'properties' in s || !('type' in s && s.type === 'null'),
        )!,
      );
    }
    if (schema.items && Array.isArray(value)) return value.map((v) => visit(v, schema.items!));
    if (!schema.properties || typeof value !== 'object' || Array.isArray(value)) return value;
    const object = value as Record<string, unknown>;
    for (const [key, field] of Object.entries(schema.properties)) {
      if (!(key in object)) continue;
      object[key] = visit(object[key], field);
      const rule = model && rules[model]?.[key];
      if (rule) object[key] = applyRule(object[key], rule);
    }
    if (model === 'PlanReference' && object.milestone_ids)
      object.milestone_ids = orderedUnique(object.milestone_ids as unknown[]);
    if (model === 'ClarificationRequest' && object.fields)
      object.fields = orderedUnique(object.fields as unknown[]);
    if (model === 'StudentProfile' || model === 'StudentSkill') {
      const fields =
        model === 'StudentProfile' ? ['id', 'grade', 'school', 'major'] : ['skill_id', 'note'];
      for (const field of fields)
        if (object[field] != null) object[field] = applyRule(object[field], 'python-strip');
      if (model === 'StudentProfile') {
        for (const field of ['interests', 'goals'])
          if (object[field])
            object[field] = [
              ...new Set((object[field] as unknown[]).map((v) => applyRule(v, 'python-strip'))),
            ];
        const skills = (object.skills ?? []) as { skill_id: string }[];
        requireContract(new Set(skills.map((v) => v.skill_id)).size === skills.length);
      }
    }
    if (model === 'CapabilityInvocationRequest') {
      requireContract(object.intent !== 'UNKNOWN');
      requireContract((object.arguments_ref as { kind: string }).kind === 'CAPABILITY_ARGUMENTS');
      requireContract(object.capability !== 'revise_plan' || object.requires_approval === true);
    }
    if (model === 'AuditReferences') {
      for (const key of ['results', 'reasons']) {
        const refs = object[key] as
          | {
              kind?: string;
              ref_id?: string;
              result?: { kind: string; ref_id: string };
              reason_code?: string;
            }[]
          | undefined;
        const refKey = (r: NonNullable<typeof refs>[number]) =>
          [r.result?.kind ?? r.kind, r.result?.ref_id ?? r.ref_id, r.reason_code ?? ''].join(
            '\u0000',
          );
        refs?.sort((a, b) => compare(refKey(a), refKey(b)));
      }
    }
    if (model === 'ApprovalRequest')
      (object.instruction_refs as { ref_id: string }[])?.sort((a, b) =>
        compare(a.ref_id, b.ref_id),
      );
    if (model === 'AgentResponse')
      (object.plan_refs as PlanReference[])?.sort(
        (a, b) =>
          compare(a.plan_id, b.plan_id) ||
          a.version - b.version ||
          compare(a.content_digest, b.content_digest),
      );
    return object;
  }
  return visit(jsonCopy(raw), document, root);
}

export function jsonCopy<T>(value: T): T {
  // Reject non-JSON values instead of JSON.stringify silently dropping/coercing them.
  function visit(item: unknown): void {
    if (item === null || typeof item === 'string' || typeof item === 'boolean') return;
    if (typeof item === 'number') {
      requireContract(Number.isFinite(item));
      return;
    }
    requireContract(typeof item === 'object' && item !== null);
    requireContract(Array.isArray(item) || Object.getPrototypeOf(item) === Object.prototype);
    for (const value of Object.values(item)) visit(value);
  }
  visit(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

function planKey(plan: PlanReference): string {
  return JSON.stringify([plan.plan_id, plan.version, plan.content_digest]);
}

function auditValid(audit: AuditReferences | undefined): void {
  if (!audit) return;
  const refs = audit.results ?? [];
  const reasons = audit.reasons ?? [];
  const key = (r: { kind: string; ref_id: string }) => `${r.kind}\u0000${r.ref_id}`;
  requireContract(new Set(refs.map(key)).size === refs.length);
  requireContract(
    new Set(reasons.map((r) => `${key(r.result)}\u0000${r.reason_code}`)).size === reasons.length,
  );
  requireContract(reasons.every((r) => refs.some((ref) => key(ref) === key(r.result))));
}

function approvalValid(proposal: ApprovalRequest): void {
  requireContract(proposal.decision_ref.kind === 'REPLANNING_DECISION');
  requireContract(proposal.affected_scope_ref.kind === 'AFFECTED_SCOPE');
  requireContract(!proposal.resolution_ref || proposal.resolution_ref.kind === 'SCOPE_RESOLUTION');
  requireContract(proposal.proposed_input_ref.kind === 'REPLANNING_INPUT');
  requireContract(proposal.instruction_refs.every((r) => r.kind === 'REVISION_INSTRUCTION'));
  requireContract(
    new Set(proposal.instruction_refs.map((r) => r.ref_id)).size ===
      proposal.instruction_refs.length,
  );
  auditValid(proposal.audit);
  requireContract(
    (proposal.audit.reasons ?? []).some(
      (r) =>
        r.result.kind === proposal.decision_ref.kind &&
        r.result.ref_id === proposal.decision_ref.ref_id,
    ),
  );
  requireContract((proposal.audit.results ?? []).some((r) => r.kind === 'EVIDENCE'));
}

export function validateInput(raw: unknown): AgentArtsInvocationEnvelope {
  requireContract(input(raw));
  const value = canonicalize(raw, 'AgentArtsInvocationEnvelope') as AgentArtsInvocationEnvelope;
  requireContract(input(value));
  const replies = [value.clarification, value.approval, value.message].filter((v) => v != null);
  if (value.request) {
    requireContract(!value.continuation_ref && replies.length === 0);
    const c = value.request.context;
    if (c) {
      requireContract(!c.edition_id || c.competition_id);
      requireContract(!c.track_id || c.edition_id);
      requireContract(!c.profile_ref || c.profile_ref.kind === 'PROFILE');
      if (c.plan_ref) {
        const actual = {
          student_id: c.plan_ref.student_id,
          competition_id: c.plan_ref.target.competition_id,
          edition_id: c.plan_ref.target.edition_id,
          track_id: c.plan_ref.target.track_id,
        };
        for (const key of ['student_id', 'competition_id', 'edition_id', 'track_id'] as const) {
          requireContract(c[key] == null || c[key] === actual[key]);
        }
      }
    }
  } else requireContract(value.continuation_ref && replies.length === 1);
  if (value.clarification)
    requireContract(Object.values(value.clarification.values).some((v) => v != null));
  return value;
}

export function validateOutput(raw: unknown, requestId: string): PublicRuntimeResult {
  requireContract(output(raw));
  const value = canonicalize(raw, 'PublicRuntimeResult') as PublicRuntimeResult;
  requireContract(output(value));
  requireContract(Boolean(value.response) !== Boolean(value.error));
  const response = value.response;
  if (!response) {
    requireContract(!value.continuation_ref);
    return value;
  }
  requireContract(response.request_id === requestId);
  const needs = response.outcome === 'NEEDS_CLARIFICATION';
  const waits = response.outcome === 'WAITING_FOR_APPROVAL';
  const fails = response.outcome === 'FAILED';
  requireContract(
    ['NEEDS_CLARIFICATION', 'WAITING_FOR_APPROVAL', 'COMPLETED', 'FAILED'].includes(
      response.outcome,
    ),
  );
  requireContract(
    needs === Boolean(response.clarification) &&
      waits === Boolean(response.approval_request) &&
      fails === Boolean(response.error),
  );
  requireContract((needs || waits) === Boolean(value.continuation_ref));
  if (response.clarification) {
    requireContract(response.clarification.source_request_id === requestId);
    requireContract(
      new Set(response.clarification.fields).size === response.clarification.fields.length,
    );
  }
  if (response.approval_request) {
    requireContract(response.approval_request.source_request_id === requestId);
    approvalValid(response.approval_request);
  }
  auditValid(response.audit);
  const plans = response.plan_refs ?? [];
  requireContract(new Set(plans.map(planKey)).size === plans.length);
  return value;
}

export function responseOf(value: PublicRuntimeResult): AgentResponse {
  requireContract(value.response);
  return value.response;
}

import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import type {
  AgentArtsInvocationEnvelope,
  AgentResponse,
  PublicRuntimeResult,
} from '../src/runtime/generated/contracts.ts';
import {
  businessInvocations,
  responseSnapshotKey,
  runtimeTrace,
  waitForResponseByRequestId,
} from './runtimeTrace.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
Object.defineProperty(globalThis, 'window', { value: dom.window, configurable: true });
Object.defineProperty(globalThis, 'document', { value: dom.window.document, configurable: true });

function response(requestId: string): PublicRuntimeResult {
  return {
    response: {
      request_id: requestId,
      intent: 'GET_MY_COMPETITIONS',
      outcome: 'COMPLETED',
      message: 'Read',
      audit: { results: [], reasons: [] },
    },
    error: null,
  };
}
function request(
  requestId: string,
  intent: NonNullable<AgentArtsInvocationEnvelope['request']>['intent'],
): AgentArtsInvocationEnvelope {
  return {
    request: { request_id: requestId, intent, user_message: 'Explicit operation', context: {} },
  };
}

test('response identity survives inverted completion order', async () => {
  const a = response('a'),
    b = response('b');
  const source = {
    calls: [request('a', 'GET_MY_COMPETITIONS'), request('b', 'GET_MY_COMPETITION')],
    responses: [b, a],
  };
  assert.equal(await waitForResponseByRequestId(source, 'a'), a);
});

test('missing response reports expected and observed identities', async () => {
  const source = {
    calls: [request('expected', 'GET_MY_COMPETITIONS')],
    responses: [response('other')],
  };
  await assert.rejects(waitForResponseByRequestId(source, 'expected', 1), (error: Error) => {
    assert.match(error.message, /request_id=expected/);
    assert.match(error.message, /Observed requests/);
    assert.match(error.message, /Observed responses/);
    assert.match(error.message, /other/);
    return true;
  });
});

test('READ and mutations remain traced but cannot count as business invocations', () => {
  const source = {
    calls: [
      request('read', 'GET_MY_COMPETITIONS'),
      request('add', 'ADD_MY_COMPETITION'),
      request('state', 'UPDATE_MY_COMPETITION'),
      request('plan', 'BUILD_PLAN'),
    ],
    responses: [],
  };
  assert.deepEqual(
    runtimeTrace(source).map((r) => r.kind),
    ['READ', 'MUTATION', 'MUTATION', 'BUSINESS'],
  );
  assert.deepEqual(businessInvocations(source), ['BUILD_PLAN']);
  assert.throws(
    () => businessInvocations({ calls: [request('unknown', undefined)], responses: [] }),
    /Unclassified/,
  );
});

test('response snapshots include audit identity, not only the shared workflow request ID', () => {
  const before = response('workflow').response!;
  const after: AgentResponse = {
    ...before,
    audit: { results: [{ kind: 'TOOL_RESULT', ref_id: 'next' }], reasons: [] },
  };
  assert.notEqual(responseSnapshotKey(before), responseSnapshotKey(after));
});

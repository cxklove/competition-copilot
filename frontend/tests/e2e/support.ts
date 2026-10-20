// Test-only real HTTP composition and semantic comparison. No product routing/rules.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';
import { RuntimeInvocationClient } from '../../src/runtime/client.ts';
import { LocalRuntimeTransport } from '../../src/runtime/local.ts';
import { AgentArtsRuntimeTransport } from '../../src/runtime/agentarts.ts';
import type {
  AgentArtsInvocationEnvelope,
  PublicRuntimeResult,
} from '../../src/runtime/generated/contracts.ts';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
export const stamp = '2026-01-01T00:00:00Z';
export const modes = ['LOCAL', 'AGENTARTS'] as const;
export type Mode = (typeof modes)[number];
export type Delivery = { runtime: PublicRuntimeResult; presentation?: unknown };
export let urls: { local: string; bridge: string; gateway: string };
let backend: ReturnType<typeof spawn>;

export async function startHarness() {
  backend = spawn(
    path.join(root, 'backend/.venv/Scripts/python.exe'),
    ['backend/tests/agentarts_gateway_harness.py'],
    { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  urls = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => {
      backend.kill();
      reject(Error('E2E harness startup timeout'));
    }, 20000);
    backend.stdout!.on('data', (data) => {
      output += data;
      const match = output.match(/COMPAT_URLS=(\{[^\r\n]+\})/);
      if (match) {
        clearTimeout(timer);
        resolve(JSON.parse(match[1]));
      }
    });
    backend.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    backend.once('exit', (code) => {
      clearTimeout(timer);
      reject(Error(`E2E harness exited ${code}`));
    });
    backend.stderr!.on('data', (data) => {
      clearTimeout(timer);
      reject(Error(String(data)));
    });
  });
}
export async function stopHarness() {
  if (backend?.exitCode === null) {
    const ended = once(backend, 'exit');
    backend.kill();
    await ended;
  }
}
export async function resetScenario() {
  const response = await fetch(urls.gateway + '/__test__/reset', { method: 'POST', body: '{}' });
  assert.equal(response.status, 200);
}
export async function fault(mode: Mode, value: unknown) {
  const url = mode === 'LOCAL' ? urls.local : urls.gateway;
  const response = await fetch(url + '/__test__/control', {
    method: 'POST',
    body: JSON.stringify(value),
  });
  assert.equal(response.status, 200);
}
export function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

export function composition(
  mode: Mode,
  options: {
    baseUrl?: string;
    sessionId?: string;
    beforeDeliver?: (delivery: Delivery, signal?: AbortSignal | null) => Promise<void>;
  } = {},
) {
  let attachment: unknown;
  const calls: AgentArtsInvocationEnvelope[] = [];
  const deliveries: Delivery[] = [];
  const serverCounts: number[] = [];
  const fetcher: typeof fetch = async function (this: typeof globalThis, url, init) {
    assert.equal(this, globalThis);
    assert.equal(init?.credentials, 'omit');
    assert.ok(!new Headers(init?.headers).has('Authorization'));
    assert.ok(!String(url).includes('tools/call'));
    calls.push(JSON.parse(String(init?.body)));
    const response = await fetch(url, init);
    const delivery = (await response.clone().json()) as Delivery;
    deliveries.push(delivery);
    serverCounts.push(Number(response.headers.get('X-Local-Handler-Count')));
    await options.beforeDeliver?.(delivery, init?.signal);
    return response;
  };
  const baseUrl = options.baseUrl ?? (mode === 'LOCAL' ? urls.local : urls.bridge);
  const config =
    mode === 'LOCAL'
      ? ({ mode, baseUrl } as const)
      : ({ mode, baseUrl, runtimeName: 'competition-copilot' } as const);
  const receive = (value: unknown) => {
    attachment = value;
  };
  const transport =
    config.mode === 'LOCAL'
      ? new LocalRuntimeTransport(config, receive, fetcher)
      : new AgentArtsRuntimeTransport(config, receive, { fetcher, sessionId: options.sessionId });
  return {
    mode,
    client: new RuntimeInvocationClient(transport, config),
    readArtifacts: () => attachment,
    calls,
    deliveries,
    serverCounts,
  };
}
export type Composition = ReturnType<typeof composition>;

// Transport headers/session IDs/timing never enter this comparator. All public
// business IDs, complete response, artifacts and typed continuations DO enter it.
export function semanticTrace(value: Composition, container: HTMLElement) {
  return {
    payloads: structuredClone(value.calls),
    deliveries: structuredClone(value.deliveries),
    workflow: container.querySelector('.workflow-status')?.textContent,
    conversation: [...container.querySelectorAll('.message-list > li')].map((item) => ({
      requestId: item.getAttribute('data-request-id'),
      text: item.textContent,
    })),
    result: container.querySelector('.result-slot')?.textContent,
    hitl: container.querySelector('.hitl-panel')?.textContent,
    error: container.querySelector('[role="alert"]')?.textContent,
  };
}
export function assertParity(left: unknown, right: unknown) {
  assert.deepEqual(right, left);
}

// Existing React integration stack, not a mocked client. Layout requires the
// separate actual-browser smoke; jsdom is used only for semantic/UI assertions.
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' });
for (const key of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'Node',
  'Event',
  'MutationObserver',
] as const)
  Object.defineProperty(globalThis, key, {
    value: key === 'window' ? dom.window : dom.window[key],
    configurable: true,
  });
Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
  value: true,
  writable: true,
  configurable: true,
});

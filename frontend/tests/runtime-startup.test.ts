import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import { access, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { stopLocalRuntime, waitForLocalRuntime } from './runtimeStartup.ts';

async function withStartupProcess(
  script: string,
  check: (startup: Promise<string>, child: ChildProcess, directory: string) => Promise<void>,
  executable = process.execPath,
): Promise<void> {
  const directory = await mkdtemp(path.join(tmpdir(), 'competition-copilot-ci-startup-'));
  let child: ChildProcess | undefined;
  try {
    child = spawn(executable, ['-e', script], { cwd: directory, windowsHide: true });
    const startup = waitForLocalRuntime(child);
    await check(startup, child, directory);
  } finally {
    // 'close', unlike 'exit', also waits for stdout/stderr handles on Windows.
    if (child) await stopLocalRuntime(child);
    await rm(directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
  }
}

test('startup failure includes complete stdout, traceback and exit code', async () => {
  await withStartupProcess(
    `process.stdout.write('startup diagnostic\\n');
     process.stderr.write('Traceback (most recent call last):\\n');
     process.stderr.write('ValueError: Temporal raw digest mismatch\\n');
     process.exitCode = 1;`,
    async (startup) => {
      await assert.rejects(startup, (error: Error) => {
        assert.match(error.message, /exit code=1/);
        assert.match(error.message, /stdout:\nstartup diagnostic/);
        assert.match(error.message, /stderr:\nTraceback/);
        assert.match(error.message, /ValueError: Temporal raw digest mismatch\n$/);
        return true;
      });
    },
  );
});

test('startup success returns the announced dynamic port', async () => {
  await withStartupProcess(
    `process.stdout.write('LOCAL_RUNTIME_URL=http://127.0.0.1:54321\\n');`,
    async (startup) => {
      assert.equal(await startup, 'http://127.0.0.1:54321');
    },
  );
});

test('spawn failure includes the OS error and output sections', async () => {
  await withStartupProcess(
    '',
    async (startup) => {
      await assert.rejects(startup, (error: Error) => {
        assert.match(error.message, /Spawn error: .*ENOENT/);
        assert.match(error.message, /stdout:\n/);
        assert.match(error.message, /stderr:\n/);
        return true;
      });
    },
    'nonexistent-local-runtime-test-executable',
  );
});

test('assertion failure stops the running child before removing its OS temp directory', async () => {
  let directory: string | undefined;
  let child: ChildProcess | undefined;
  await assert.rejects(
    withStartupProcess(
      `process.stdout.write('LOCAL_RUNTIME_URL=http://127.0.0.1:54321\\n');
       setInterval(() => {}, 1000);`,
      async (startup, running, temporary) => {
        await startup;
        directory = temporary;
        child = running;
        assert.equal(path.dirname(temporary), tmpdir());
        assert.fail('controlled assertion failure');
      },
    ),
    /controlled assertion failure/,
  );
  assert.ok(child);
  assert.ok(directory);
  assert.ok(child.exitCode !== null || child.signalCode !== null);
  assert.equal(child.stdout?.closed, true);
  assert.equal(child.stderr?.closed, true);
  await assert.rejects(access(directory), { code: 'ENOENT' });
});

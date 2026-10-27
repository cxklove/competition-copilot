import type { ChildProcess } from 'node:child_process';

const closed = new WeakMap<ChildProcess, Promise<void>>();

function whenClosed(child: ChildProcess): Promise<void> {
  let completion = closed.get(child);
  if (!completion) {
    completion = new Promise((resolve) => child.once('close', () => resolve()));
    closed.set(child, completion);
  }
  return completion;
}

/** Stop a child registered by waitForLocalRuntime and await its drained pipes. */
export async function stopLocalRuntime(child: ChildProcess): Promise<void> {
  const completion = whenClosed(child);
  if (child.exitCode === null && child.signalCode === null) child.kill();
  await completion;
}

/** Wait for startup; report failures only after both output pipes have closed. */
export function waitForLocalRuntime(child: ChildProcess, timeoutMs = 20000): Promise<string> {
  // Register before startup can fail, so cleanup also works after 'close'.
  whenClosed(child);
  return new Promise((resolve, reject) => {
    let stdout = '';
    let stderr = '';
    let startupError: Error | undefined;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);
    child.stdout!.setEncoding('utf8');
    child.stderr!.setEncoding('utf8');
    child.stdout!.on('data', (chunk: string) => {
      stdout += chunk;
      const match = stdout.match(/LOCAL_RUNTIME_URL=(http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
    child.stderr!.on('data', (chunk: string) => {
      stderr += chunk;
    });
    child.once('error', (error) => {
      startupError = error;
    });
    // 'exit' can precede the final stderr data. 'close' guarantees drained pipes.
    child.once('close', (code, signal) => {
      clearTimeout(timer);
      const reason = timedOut ? 'startup timed out' : 'startup failed';
      reject(
        new Error(
          `Local Runtime ${reason}; exit code=${code}; signal=${signal}\n` +
            `${startupError ? `Spawn error: ${startupError.message}\n` : ''}` +
            `stdout:\n${stdout}\nstderr:\n${stderr}`,
        ),
      );
    });
  });
}

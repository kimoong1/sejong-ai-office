import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const sdkRoot = fileURLToPath(new URL('../', import.meta.url));
const fail = (code, message) => ({ ok: false, error: { code, message } });

/** Electron main / Node bridge. Python path is app configuration, never document input. */
export function parseFile(path, {
  python = 'python', timeoutMs = 20_000, maxOutputBytes = 24_000_000,
  limits = {}, signal,
} = {}) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isSafeInteger(maxOutputBytes) || maxOutputBytes <= 0) {
    throw new TypeError('Positive timeoutMs and maxOutputBytes required');
  }
  if (signal?.aborted) return Promise.resolve(fail('ABORTED', 'Parsing cancelled'));
  return new Promise((resolveResult) => {
    const child = spawn(python, ['-m', 'officeparse._worker'], {
      shell: false, windowsHide: true, cwd: sdkRoot,
      env: { ...process.env, PYTHONPATH: sdkRoot, PYTHONIOENCODING: 'utf-8' },
      stdio: ['pipe', 'pipe', 'ignore'],
    });
    let bytes = 0, settled = false;
    const chunks = [];
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      resolveResult(result);
    };
    const stop = (code, message) => { child.kill(); finish(fail(code, message)); };
    const abort = () => stop('ABORTED', 'Parsing cancelled');
    const timer = setTimeout(() => stop('TIMEOUT', 'Parser deadline exceeded'), timeoutMs);
    signal?.addEventListener('abort', abort, { once: true });
    // Covers an abort between the initial check and registering the listener.
    if (signal?.aborted) abort();
    child.on('error', () => finish(fail('WORKER_FAILED', 'Cannot start Python parser')));
    child.stdin.on('error', () => {});
    child.stdout.on('data', (chunk) => {
      if (settled) return;
      bytes += chunk.length;
      if (bytes > maxOutputBytes) return stop('RESOURCE_LIMIT', 'Worker output exceeds byte limit');
      chunks.push(chunk);
    });
    child.on('close', (code) => {
      if (settled) return;
      if (code !== 0) return finish(fail('WORKER_FAILED', 'Parser worker failed'));
      try { finish(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
      catch { finish(fail('WORKER_FAILED', 'Invalid worker result')); }
    });
    child.stdin.end(JSON.stringify({ path: resolve(path), limits }));
  });
}

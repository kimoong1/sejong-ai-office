import assert from 'node:assert/strict';
import { parseFile } from '../integrations/node.mjs';

const python = process.env.OFFICEPARSE_PYTHON || 'python';
const fixture = process.argv[2];
assert.ok(fixture, 'Pass a DOCX fixture path');
const good = await parseFile(fixture, { python });
assert.equal(good.ok, true, JSON.stringify(good));
assert.equal(good.document.format, 'docx');
assert.equal((await parseFile('missing.docx', { python })).error.code, 'IO_ERROR');
assert.equal((await parseFile(fixture, { python, timeoutMs: 1 })).error.code, 'TIMEOUT');
assert.equal((await parseFile(fixture, { python, maxOutputBytes: 10 })).error.code, 'RESOURCE_LIMIT');
const abort = new AbortController();
const pending = parseFile(fixture, { python, signal: abort.signal });
abort.abort();
assert.equal((await pending).error.code, 'ABORTED');
assert.equal((await parseFile(fixture, { python: 'officeparse-nonexistent-python' })).error.code, 'WORKER_FAILED');
console.log('Node bridge: 6 integration checks passed');

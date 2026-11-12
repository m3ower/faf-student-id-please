// Exercise generated scripts against isolated Postman variable stores. No HTTP calls.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const collection = JSON.parse(fs.readFileSync(path.join(root, 'postman/Student-ID-Please-Lab-1.postman_collection.json'), 'utf8'));
const local = new Map(), environment = new Map();
const stored = new Map(collection.variable.map(v => [v.key, v.value]));
const store = map => ({
  get: key => map.get(key), set: (key, value) => map.set(key, value),
  unset: key => map.delete(key), has: key => map.has(key),
});
let nextRequest;
const pm = {
  collectionVariables: store(stored), environment: store(environment), globals: store(new Map()),
  variables: {
    ...store(local),
    get: key => local.has(key) ? local.get(key) : environment.has(key) ? environment.get(key) : stored.get(key),
    replaceIn: text => text.replace(/\{\{([^{}]+)\}\}/g,
      (_, key) => key === '$guid' ? crypto.randomUUID() : String(pm.variables.get(key) ?? '')),
  },
  test: () => {}, // These checks exercise state transitions, not simulated HTTP assertions.
  response: {code: 202, json: () => ({state: 'PENDING'})},
  info: {requestName: 'DMs processed it (result)'},
  execution: {setNextRequest: name => {nextRequest = name;}},
};
function* walk(node) {
  yield node;
  for (const item of node.item || []) yield* walk(item);
}
function request(folder, name) {
  const service = collection.item.find(item => item.name === folder);
  return [...walk(service)].find(item => item.name === name);
}
function run(item, listen) {
  for (const event of item.event || []) {
    if (event.listen === listen) {
      vm.runInNewContext(event.script.exec.join('\n'), {pm, setTimeout: () => {}, atob});
    }
  }
}
let scripts = 0;
for (const file of fs.readdirSync(path.join(root, 'postman')).filter(f => f.endsWith('.postman_collection.json'))) {
  const document = JSON.parse(fs.readFileSync(path.join(root, 'postman', file), 'utf8'));
  for (const item of walk(document)) {
    for (const event of item.event || []) {
      const lines = event.script.exec || [];
      new vm.Script(Array.isArray(lines) ? lines.join('\n') : lines);
      scripts++;
    }
  }
}
const sessionId = crypto.randomUUID();
const business = {
  eventId: crypto.randomUUID(), type: 'ShiftStarted', producer: 'session-service', version: 1,
  occurredAt: new Date().toISOString(),
  payload: {sessionId, players: [crypto.randomUUID()], rulesetVersion: 1},
};
environment.set('discord_dms_sessionId', sessionId);
environment.set('discord_dms_shiftStartedEnvelope', JSON.stringify(business));
environment.set('moderation_sessionId', 'other-service-state');
const publication = request('discord-dms service', 'Session publishes ShiftStarted (event topic)');
run(publication, 'prerequest');
const envelope = JSON.parse(local.get('discord_dms_envelope'));
assert.deepEqual(envelope.payload, business); // Business JSON field names must remain unchanged.
assert.equal(envelope.topic, 'event.ShiftStarted.v1');
assert.equal(environment.get('moderation_sessionId'), 'other-service-state');
assert.equal(local.has('envelope'), false); // Computed and literal accessors must stay scoped.
run(publication, 'test');
assert.equal(local.get('discord_dms_resultId'), local.get('discord_dms_messageId'));
run(request('discord-dms service', 'DMs processed it (result)'), 'test');
assert.equal(local.get('discord_dms_polls'), 1);
assert.equal(nextRequest, pm.info.requestName);
stored.set('applicant_applicantConflictId', 'old fixture');
run(request('applicant service', 'Create disposable applicant'), 'prerequest');
assert.equal(stored.has('applicant_applicantConflictId'), false);
assert.match(stored.get('applicant_applicantStudentId'), /^postman-applicant-[0-9a-f-]{36}$/);
assert.equal(stored.has('applicantStudentId'), false);
assert.equal(local.has('sessionId'), false);
console.log(`PASS: ${scripts} scripts compile; shared variables, business payloads, environment overrides and bounded polling behave correctly`);

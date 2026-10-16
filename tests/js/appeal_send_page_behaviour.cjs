'use strict';
// Load the send page's real script (appeal.ts) over a fake copy of the page
// and report what the person would have in the letter boxes. One scenario
// per process.
//
//   node appeal_send_page_behaviour.cjs <compiled dir> <scenario>
//
// <compiled dir> holds tsc's commonjs output of appeal.ts and what it
// imports (static/js/ under it, the shared JSON at its root). The scenario's
// input is a JSON object on stdin: the draft as the browser read it out of
// the page, and what this browser's storage holds.
//
// Writes one JSON object to stdout; everything the page logs is swallowed.

const fs = require('fs');
const path = require('path');
const Module = require('module');
const {buildPage, install} = require(path.join(__dirname, 'fake_page.cjs'));

const [, , compiledDir, scenarioName] = process.argv;
if (!compiledDir || !scenarioName) {
  throw new Error('usage: appeal_send_page_behaviour.cjs <compiled dir> <scenario>');
}
const SCRIPTS = path.join(compiledDir, 'static', 'js');
const input = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');

// The ids are the real ones: test_the_send_page_keeps_your_letter.py checks
// them against the rendered appeal.html.
const MARKUP = `
<form id="share-form">
  <textarea id="scrubbed_appeal_text"></textarea>
</form>
<div id="pii-panel">
  <input id="pii_fname" />
  <input id="pii_lname" />
  <input id="pii_phone" />
  <input id="pii_email" />
  <input id="pii_street" />
  <input id="pii_city" />
  <input id="pii_state" />
  <input id="pii_zip" />
  <input id="pii_subscriber_id" />
  <input id="pii_group_id" />
</div>
<button id="descrub">Fill in your PII</button>
<form id="fax-form">
  <textarea id="id_completed_appeal_text"></textarea>
  <button id="fax_appeal">Fax My Appeal</button>
</form>
<button id="print_appeal">Print My Appeal</button>
`;

const page = buildPage(MARKUP);
install(page);
for (const level of ['debug', 'log', 'info', 'warn', 'error']) {
  console[level] = () => {};
}

// Every box starts empty, the way a browser hands it over.
for (const el of page.body.querySelectorAll('input').concat(page.body.querySelectorAll('textarea'))) {
  el.value = '';
}

// This browser's storage, from the scenario.
const stored = Object.assign({}, input.stored || {});
const localStorage = {
  getItem: (key) => (Object.prototype.hasOwnProperty.call(stored, key) ? stored[key] : null),
  setItem: (key, value) => {
    stored[key] = String(value);
  },
  removeItem: (key) => {
    delete stored[key];
  },
  key: (i) => Object.keys(stored)[i] || null,
  get length() {
    return Object.keys(stored).length;
  },
};
global.window.localStorage = localStorage;
global.localStorage = localStorage;

// Browser bundles the page imports but these scenarios never reach.
const load = Module._load;
Module._load = function (request, ...rest) {
  if (request === 'pdfjs-dist') return {GlobalWorkerOptions: {}};
  if (request === 'jspdf') return {jsPDF: function () {}};
  return load.call(this, request, ...rest);
};

const doc = page.document;
const draft = doc.getElementById('scrubbed_appeal_text');
const letter = doc.getElementById('id_completed_appeal_text');

function loadPage() {
  draft.value = input.draft || '';
  require(path.join(SCRIPTS, 'appeal.js'));
}

function report(extra) {
  process.stdout.write(
    JSON.stringify(
      Object.assign(
        {
          draft: draft.value,
          letter: letter.value,
          moved: page.movedThePerson,
        },
        extra || {},
      ),
    ),
  );
}

const scenarios = {
  // The page as it loads: the finished letter is built from the draft.
  load() {
    loadPage();
    report();
  },
  // The person types in the draft, and the finished letter follows.
  'type-in-draft'() {
    loadPage();
    draft.value = input.typed;
    draft.oninput({});
    report();
  },
};

const scenario = scenarios[scenarioName];
if (!scenario) throw new Error('unknown scenario ' + scenarioName);
Promise.resolve(scenario()).catch((error) => {
  process.stderr.write(String((error && error.stack) || error));
  process.exit(1);
});

'use strict';
const fs = require('node:fs');
const api = require('../browser/parser.js');
const template = fs.readFileSync(require('node:path').join(__dirname, '../agentshare/templates/review.html'), 'utf8');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = cases.map(test => {
  try {
    const bundle = api.buildBundle(new Uint8Array(Buffer.from(test.base64, 'base64')), test.format || 'auto', test.terms || []);
    return {bundle, ...(test.render ? {html:api.renderReview(bundle, template)} : {})};
  } catch (error) { return {error:error.message}; }
});
process.stdout.write(JSON.stringify(results));

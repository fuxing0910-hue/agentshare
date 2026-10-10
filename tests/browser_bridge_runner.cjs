'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const api = require('../browser/download_bridge.js');
const input = JSON.parse(fs.readFileSync(0,'utf8'));
const source = {}, token = 'a'.repeat(32);
const request = {type:'agentshare-download',token,content:'# Reviewed only\n',filename:'agentshare-selected.md',mime:'text/markdown;charset=utf-8',selected_count:1};
const event = {source,origin:'null',data:request};
assert.deepEqual(api.validateRequest(event,source,token),{content:request.content,filename:request.filename,mime:request.mime,selected_count:1});
for (const altered of [
  {...event,source:{}}, {...event,origin:'https://example.test'}, {...event,data:null}, {...event,data:[]},
  {...event,data:{...request,token:'b'.repeat(32)}}, {...event,data:{...request,type:'unrelated'}},
  {...event,data:{...request,filename:'../../private.txt'}}, {...event,data:{...request,mime:'text/javascript'}},
  {...event,data:{...request,content:undefined}}, {...event,data:{...request,content:''}},
  {...event,data:{...request,selected_count:0}}, {...event,data:{...request,selected_count:5001}},
  {...event,data:{...request,selected_count:1.5}}, {...event,data:{...request,extra:'PRIVATE_METADATA'}},
]) assert.equal(api.validateRequest(altered,source,token),null);
assert.equal(api.validateRequest(event,null,token),null);
assert.equal(api.validateRequest(event,source,null),null);
assert.equal(api.validateRequest({...event,data:{...request,filename:'agentshare-selected.html',mime:'text/html;charset=utf-8'}},source,token).filename,'agentshare-selected.html');
// The generated browser-specific override delegates content and fixed export
// properties; it never passes the candidate bundle or performs a child download.
const snippet = input.assets.template.split('// Sandbox downloads are delegated to the parent, without same-origin access.')[1].split('</script>')[0].replace('__AGENTSHARE_DOWNLOAD_TOKEN__',token);
let posted = null, target = null;
const status = {textContent:''};
const context = {download:null,selected:new Set(['e1']),window:{parent:{postMessage(value,origin){posted=value;target=origin;}}},document:{getElementById(id){assert.equal(id,'download-status');return status;}}};
vm.runInNewContext(snippet,context);
context.download(request.content,request.filename,request.mime);
assert.equal(target,'*');
assert.equal(api.validateRequest({source,origin:'null',data:posted},source,token).content,request.content);
assert.match(status.textContent,/Download requested/);
assert.doesNotMatch(status.textContent,/Downloaded/);
// Reconstruct solely immutable source assets. A live review DOM is deliberately
// absent from this API, so candidate contents, edits and private terms cannot
// leak into the saved offline tool.
assert.equal(api.portableTool(input.assets),input.standalone);
assert.ok(!api.portableTool(input.assets).includes('PRIVATE_ACTIVE_REVIEW_ONLY'));
assert.match(input.standalone,/id="save-tool"/);
assert.ok(!input.standalone.includes('outerHTML'));
process.stdout.write('Download bridge checks passed.\n');

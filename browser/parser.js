/* Local-only browser adapter. Keep fixture parity with agentshare/core.py. */
(function(root) {
  'use strict';
  const MAX_INPUT_BYTES = 20 * 1024 * 1024;
  const MAX_MESSAGE_CHARS = 100000;
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  // Python str.strip whitespace; unlike JS trim it does not remove a mid-file BOM.
  const trim = value => value.replace(/^[\t\n\v\f\r \x1c-\x1f\x85\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n\v\f\r \x1c-\x1f\x85\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu, '');
  class InputError extends Error { constructor(message) { super(message); this.name = 'AgentShareInputError'; } }
  const fail = message => { throw new InputError(message); };
  const names = new Map([
    ...['Bash','Read','Write','Edit','MultiEdit','Glob','Grep','Task','Agent','WebFetch','WebSearch','TodoWrite','Skill','AskUserQuestion','exec_command','shell','shell_command','apply_patch','write_stdin','update_plan','read_file','list_dir','find_file','grep_files'].map(name => [name,name]),
    ['functions.exec_command','exec_command'],['functions.apply_patch','apply_patch'],['functions.write_stdin','write_stdin']
  ]);
  const toolLabel = name => typeof name === 'string' ? (names.get(name) || 'Other tool') : 'Other tool';
  function messageEvent(kind, text, line) {
    let length = 0;
    for (const character of text) { if (++length > MAX_MESSAGE_CHARS) fail(`Line ${line}: message exceeds 100,000 characters.`); }
    if (!trim(text)) return null;
    if (/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/u.test(text)) fail(`Line ${line}: message contains an invalid Unicode surrogate.`);
    return {kind, label:kind === 'user' ? 'User message' : 'Assistant message', text, status:'info'};
  }
  function statusFor(payload) {
    if (payload.is_error === true) return 'error';
    if (payload.is_error === false) return 'success';
    if (['failed','error','failure'].includes(payload.status)) return 'error';
    if (['completed','success','succeeded'].includes(payload.status)) return 'success';
    return 'info';
  }
  function textBlocks(content, types) {
    if (typeof content === 'string') return content;
    return Array.isArray(content) ? content.filter(block => object(block) && types.includes(block.type) && typeof block.text === 'string').map(block => block.text).join('\n') : '';
  }
  function readRecords(bytes) {
    if (!(bytes instanceof Uint8Array)) fail('Input must be UTF-8 JSONL.');
    if (bytes.byteLength > MAX_INPUT_BYTES) fail('Input exceeds the 20 MiB file limit.');
    let text;
    try { text = new TextDecoder('utf-8', {fatal:true}).decode(bytes); }
    catch (_) { fail('Input must be UTF-8 JSONL.'); }
    const records = [];
    text.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/u).forEach((line, position) => {
      if (!trim(line)) return;
      let record;
      try { record = JSON.parse(line); }
      catch (_) { fail(`Line ${position + 1}: invalid JSON.`); }
      if (!object(record)) fail(`Line ${position + 1}: expected a JSON object.`);
      records.push([position + 1, record]);
    });
    if (!records.length) fail('Input contains no JSON records.');
    return records;
  }
  function detectFormat(records) {
    const kinds = new Set();
    records.forEach(([,record]) => {
      if (['response_item','event_msg','session_meta','turn_context'].includes(record.type)) kinds.add('codex');
      else if (['user','assistant'].includes(record.type) && object(record.message)) kinds.add('claude');
    });
    if (kinds.size > 1) fail('Mixed Claude and Codex records: select one transcript file.');
    if (!kinds.size) fail('No supported Claude or Codex records found. Choose a supported JSONL transcript.');
    return [...kinds][0];
  }
  function parseClaude(records) {
    const events = [], tools = new Map();
    let omitted = 0, unsupported = 0;
    for (const [line, record] of records) {
      const role = record.type, message = record.message;
      if (!['user','assistant'].includes(role) || !object(message)) { unsupported++; continue; }
      const content = message.content;
      let recognized = false;
      if (typeof content === 'string') {
        const event = messageEvent(role, content, line);
        if (event) { events.push(event); recognized = true; }
      } else if (Array.isArray(content)) {
        messageEvent(role, textBlocks(content, ['text']), line);
        for (const block of content) {
          if (!object(block)) continue;
          if (block.type === 'text' && typeof block.text === 'string') {
            const event = messageEvent(role, block.text, line);
            if (event) events.push(event);
            recognized = true;
          } else if (block.type === 'tool_use') {
            const label = toolLabel(block.name);
            if (typeof block.id === 'string') tools.set(block.id, label);
            events.push({kind:'tool',label,text:'Tool input omitted.',status:'info'});
            omitted++; recognized = true;
          } else if (block.type === 'tool_result') {
            const label = typeof block.tool_use_id === 'string' ? (tools.get(block.tool_use_id) || 'Other tool') : 'Other tool';
            events.push({kind:'tool',label,text:'Tool output omitted.',status:statusFor(block)});
            omitted++; recognized = true;
          }
        }
      }
      if (!recognized) unsupported++;
    }
    return [events, omitted, unsupported];
  }
  function codexMessage(payload, line) {
    if (payload.type !== 'message' || !['user','assistant'].includes(payload.role)) return null;
    return messageEvent(payload.role, textBlocks(payload.content, ['input_text','output_text']), line);
  }
  function parseCodex(records) {
    const events = [], tools = new Map(), canonical = new Map();
    let omitted = 0, unsupported = 0;
    const keyOf = event => JSON.stringify([event.kind, event.text]);
    for (const [line,record] of records) {
      if (record.type === 'response_item' && object(record.payload)) {
        const event = codexMessage(record.payload, line);
        if (event) { const key = keyOf(event); canonical.set(key, (canonical.get(key) || 0) + 1); }
      }
    }
    for (const [line,record] of records) {
      const payload = record.payload;
      if (!object(payload)) { unsupported++; continue; }
      if (record.type === 'response_item') {
        if (payload.type === 'message') {
          const event = codexMessage(payload, line);
          event ? events.push(event) : unsupported++;
        } else if (['function_call','custom_tool_call'].includes(payload.type)) {
          const label = toolLabel(payload.name);
          if (typeof payload.call_id === 'string') tools.set(payload.call_id, label);
          events.push({kind:'tool',label,text:'Tool input omitted.',status:statusFor(payload)}); omitted++;
        } else if (['function_call_output','custom_tool_call_output'].includes(payload.type)) {
          const label = typeof payload.call_id === 'string' ? (tools.get(payload.call_id) || 'Other tool') : 'Other tool';
          events.push({kind:'tool',label,text:'Tool output omitted.',status:statusFor(payload)}); omitted++;
        } else unsupported++;
      } else if (record.type === 'event_msg' && ['user_message','agent_message'].includes(payload.type)) {
        if (typeof payload.message !== 'string') { unsupported++; continue; }
        const event = messageEvent(payload.type === 'user_message' ? 'user' : 'assistant', payload.message, line);
        if (!event) { unsupported++; continue; }
        const key = keyOf(event), count = canonical.get(key) || 0;
        if (count) canonical.set(key, count - 1); else events.push(event);
      } else unsupported++;
    }
    return [events, omitted, unsupported];
  }
  function redactor(terms) {
    if (!Array.isArray(terms)) fail('Custom terms must be strings.');
    const normalized = new Set();
    for (let term of terms) {
      if (typeof term !== 'string') fail('Custom terms must be strings.');
      term = trim(term);
      if (!term) continue;
      if ([...term].length > 4096) fail('A custom term exceeds 4,096 characters.');
      normalized.add(term);
      if (normalized.size > 1000) fail('At most 1,000 custom terms are supported.');
    }
    const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const ordered = [...normalized].sort((a,b) => [...b].length - [...a].length || (a < b ? -1 : a > b ? 1 : 0));
    let custom = null;
    try { if (ordered.length) custom = new RegExp(ordered.map(escape).join('|'), 'gu'); }
    catch (_) { fail('Private terms exceed this browser engine\'s processing capacity. Use fewer terms or the Python CLI.'); }
    const patterns = [
      ['private_key', /-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/gu],
      ['assignment', /((?<![\p{L}\p{N}_])(?:[a-z0-9_-]*(?:api[_-]?key|access[_-]?token|secret|password|passwd|token)[a-z0-9_-]*|authorization)(?![\p{L}\p{N}_])["']?\s*[:=]\s*)("[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}\])]+)/giu],
      ['bearer', /(?<![\p{L}\p{N}_])Bearer[ \t]+[A-Za-z0-9._~+/=-]{4,}/giu],
      ['github_token', /(?<![\p{L}\p{N}_])(?:gh[pousr]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})(?![\p{L}\p{N}_])/gu],
      ['api_token', /(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}(?![A-Za-z0-9])/gu],
      ['aws_key', /(?<![\p{L}\p{N}_])(?:AKIA|ASIA)[A-Z0-9]{16}(?![\p{L}\p{N}_])/gu],
      ['email', /(?<![\p{L}\p{N}_])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\p{L}\p{N}_])/giu],
      ['home_path', /(?:(?<![\p{L}\p{N}_])[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]|(?<![\p{L}\p{N}_:])\/(?:home|Users)\/|(?<![\p{L}\p{N}_:])\/root(?:\/|(?=$|[\s"']))|(?<![\p{L}\p{N}_])~[\\/])[^\r\n"'<>|]*/giu],
    ];
    const counts = Object.create(null);
    function replacement(category, groups) {
      counts[category] = (counts[category] || 0) + 1;
      const marker = `[REDACTED:${category}]`;
      return category === 'assignment' ? groups[1] + marker : category === 'bearer' ? 'Bearer ' + marker : marker;
    }
    return {counts, redact(text) {
      for (const [category,pattern] of patterns) text = text.replace(pattern, (...groups) => replacement(category, groups));
      if (custom) text = text.replace(custom, (...groups) => replacement('custom', groups));
      return text;
    }};
  }
  const warnings = [
    'Automated redaction is incomplete. Review every selected event before sharing.',
    'Tool inputs and output bodies, source filenames, session IDs, and absolute timestamps are excluded.',
    'Only supported user/assistant text and tool summaries are retained. Reasoning, images, metadata, and other records are omitted.',
    'Tool outcomes use explicit status fields only; an omitted result body does not prove success or failure.',
    'Home-path redaction may omit the remainder of a line. Custom literal terms are case-sensitive.'
  ];
  function buildBundle(bytes, format='auto', terms=[]) {
    if (!['auto','claude','codex'].includes(format)) fail('Format must be auto, claude, or codex.');
    const records = readRecords(bytes), selected = format === 'auto' ? detectFormat(records) : format;
    const [raw,omitted,unsupported] = selected === 'claude' ? parseClaude(records) : parseCodex(records);
    if (!raw.length) fail(`No supported message or tool events for ${selected} format.`);
    const redaction = redactor(terms);
    const events = raw.map((event,index) => ({id:`e${index + 1}`,kind:event.kind,label:redaction.redact(event.label),text:redaction.redact(event.text),status:event.status,time:''}));
    const counts = Object.fromEntries(Object.entries(redaction.counts).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0));
    return {version:1,title:'AgentShare review',source_format:selected,events,stats:{events:events.length,omitted_tool_bodies:omitted,redactions:counts,unsupported_records:unsupported},warnings:[...warnings]};
  }
  function scriptJson(value) {
    return JSON.stringify(value).replace(/[&<>\u2028\u2029]/gu, character => ({'&':'\\u0026','<':'\\u003c','>':'\\u003e','\u2028':'\\u2028','\u2029':'\\u2029'}[character]));
  }
  function renderReview(bundle, template) {
    const marker = '__AGENTSHARE_BUNDLE_JSON__';
    if (template.split(marker).length !== 2) fail('Review template must contain exactly one data marker.');
    const text = value => typeof value === 'string' ? value : '';
    const count = value => Number.isSafeInteger(value) && value >= 0 ? value : 0;
    const events = [];
    (Array.isArray(bundle.events) ? bundle.events : []).forEach((event,index) => {
      if (!object(event)) return;
      const item = Object.fromEntries(['id','kind','label','text','status','time'].map(field => [field,text(event[field])]));
      item.id = `e${index + 1}`;
      if (!['user','assistant','tool'].includes(item.kind)) item.kind = 'tool';
      if (!['info','error','success'].includes(item.status)) item.status = 'info';
      events.push(item);
    });
    const stats = object(bundle.stats) ? bundle.stats : {};
    const redactions = object(stats.redactions) ? stats.redactions : {};
    const review = {version:1,title:'AgentShare review',source_format:text(bundle.source_format),events,
      stats:{events:events.length,omitted_tool_bodies:count(stats.omitted_tool_bodies),unsupported_records:count(stats.unsupported_records),redactions:Object.fromEntries(Object.entries(redactions).map(([key,value]) => [key,count(value)]))},
      warnings:(Array.isArray(bundle.warnings) ? bundle.warnings : []).filter(item => typeof item === 'string')};
    return template.replace(marker, () => scriptJson(review));
  }
  const api = Object.freeze({MAX_INPUT_BYTES,MAX_MESSAGE_CHARS,readRecords,buildBundle,renderReview,scriptJson});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AgentShareBrowser = api;
})(globalThis);

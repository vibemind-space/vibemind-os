(function(){
  'use strict';
  // Minimal viewer app – ES5 compatible
  var byId = function(id){ return document.getElementById(id); };
  var $stream = byId('streamlog');
  var $events = byId('eventlog');
  var $img = byId('browserimg');
  var $badge = byId('connstatus');
  var $meta = byId('sessionmeta');
  
  // Notify parent window once when first activity is detected (for auto-switching tabs)
  var _postedPlaywrightActivity = false;
  function _notifyParentActivity(){
    if (_postedPlaywrightActivity) return;
    try {
      if (window && window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'mcp_playwright_activity' }, '*');
        _postedPlaywrightActivity = true;
      }
    } catch(_e){}
  }

  function setBadge(state, text){
    if(!$badge) return;
    $badge.className = 'badge ' + (state==='ok'?'badge-ok':state==='err'?'badge-err':state==='warn'?'badge-warn':'badge-info');
    $badge.textContent = text || (state==='ok'?'Connected':'Connecting…');
  }
  function append(pre, text, cls){
    if(!pre) return;
    var span = document.createElement('span');
    if(cls) span.className = cls;
    try{
      if (text == null) { span.textContent = ''; }
      else if (typeof text === 'string') { span.textContent = text; }
      else if (typeof text === 'number' || typeof text === 'boolean') { span.textContent = String(text); }
      else if (typeof text === 'object') {
        // Prefer text/message/content fields
        if (text.text != null) { span.textContent = String(text.text); }
        else if (text.message != null) { span.textContent = String(text.message); }
        else if (text.content != null) {
          if (typeof text.content === 'string') { span.textContent = text.content; }
          else if (Array.isArray(text.content)) {
            try {
              span.textContent = text.content.map(function(c){
                if (typeof c === 'string') return c;
                if (c && typeof c.text === 'string') return c.text;
                return JSON.stringify(c);
              }).join(' ');
            } catch(_e) { span.textContent = JSON.stringify(text.content); }
          } else { span.textContent = JSON.stringify(text.content); }
        } else {
          // Compact key=value format for small objects; fallback to JSON
          try{
            var keys = Object.keys(text);
            if (keys.length && keys.length <= 4) {
              span.textContent = keys.map(function(k){
                var val = text[k];
                if (val && typeof val === 'object') return k + '=' + JSON.stringify(val);
                return k + '=' + String(val);
              }).join(' ');
            } else {
              span.textContent = JSON.stringify(text);
            }
          }catch(_e){ span.textContent = JSON.stringify(text); }
        }
      } else { span.textContent = String(text); }
    }catch(_e){ span.textContent = String(text||''); }
    pre.appendChild(span);
    pre.appendChild(document.createTextNode('\n'));
    pre.scrollTop = pre.scrollHeight;
  }
  function render(kind, payload){
    try{
      if(kind === 'chunk') return append($stream, payload, '');
      if(kind === 'status') return append($events, payload, 'ok');
      if(kind === 'error') return append($events, payload, 'err');
      // NEW: show generic server logs (clear comment for easy debug)
      if(kind === 'log') return append($events, payload, '');
      // NEW: show session lifecycle events
      if(kind && typeof kind === 'string' && (kind.indexOf('session') === 0 || kind.indexOf('session.') === 0)){
        var text = payload;
        try{
          if(payload && typeof payload === 'object'){
            text = 'Session: ' + String(payload.session_id||'') +
                   (payload.host!=null && payload.port!=null ? ' @ ' + String(payload.host)+ ':' + String(payload.port) : '') +
                   (payload.ui_url ? ' ' + String(payload.ui_url) : '');
          }
        }catch(_e){}
        return append($events, text, 'ok');
      }
      // Existing: tool activity
      if(kind === 'tool') { var r = append($events, payload, 'tool'); _notifyParentActivity(); return r; }
      // NEW: handle browser.* event kinds as browser activity
      if((kind === 'browser' || (typeof kind === 'string' && kind.indexOf('browser') === 0)) && payload){
        // Support data_uri, url, or raw base64 data
        if(payload.data_uri){ if($img) $img.src = payload.data_uri; }
        else if(payload.url){ if($img) $img.src = payload.url; }
        else if(payload.data){ if($img) $img.src = 'data:image/png;base64,' + String(payload.data); }
        if(payload.text) append($events, payload.text, 'tool');
        _notifyParentActivity();
        return;
      }
      if(kind === 'content') return append($stream, payload, '');
      if(kind === 'source') return append($events, 'Source: ' + payload, '');
      // Fallback: render unknown kinds in events for visibility
      return append($events, (kind?('['+kind+'] '):'') + (typeof payload==='string'?payload:JSON.stringify(payload||'')), '');
    }catch(_e){}
  }

  function coerceAndRender(item){
    try{
      var msg = item;
      if(typeof msg === 'string'){
        try { msg = JSON.parse(msg); } catch(_e) {}
      }
      if(!msg || typeof msg !== 'object') return;
      var kind = msg.kind || msg.type || '';
      // Prefer common fields: text -> payload -> value -> whole msg
      var payload = (msg.text != null)
        ? msg.text
        : (msg.payload != null)
          ? msg.payload
          : (msg.value != null)
            ? msg.value
            : msg;
      // Track sequence/id for polling
      try{
        if(typeof msg.seq === 'number'){ lastId = msg.seq; }
        else if(typeof msg.id === 'number'){ lastId = msg.id; }
        else if(typeof msg.since === 'number'){ lastId = msg.since; }
      }catch(_e){}
      render(kind, payload);
    }catch(_e){}
  }

  var useSSE = !!(window.EventSource);
  var lastId = 0;
  var _session = { id: null, name: null };

  function _parseSessionIdFromPath(){
    try{
      var p = String(window.location.pathname||'');
      // Expect /mcp/playwright/session/<id>/...
      var parts = p.split('/').filter(function(x){ return !!x; });
      var idx = -1;
      for(var i=0;i<parts.length;i++){
        if(parts[i] === 'session'){ idx = i; break; }
      }
      if(idx >= 0 && parts.length > idx+1){ return parts[idx+1]; }
      // Fallback: /mcp/playwright/<id>/...
      for(var j=0;j<parts.length;j++){
        if(parts[j] === 'playwright' && parts.length > j+1){ return parts[j+1]; }
      }
      return null;
    }catch(_e){ return null; }
  }

  function _setSessionMeta(){
    try{
      if(!$meta) return;
      var idTxt = _session.id ? String(_session.id) : '';
      var nameTxt = _session.name ? String(_session.name) : '';
      if(idTxt || nameTxt){
        var txt = '';
        if(idTxt) txt += 'id: ' + idTxt;
        if(nameTxt) txt += (txt? '  ' : '') + 'name: ' + nameTxt;
        $meta.textContent = txt;
        $meta.style.display = 'inline-block';
      } else {
        $meta.textContent = '';
        $meta.style.display = 'none';
      }
    }catch(_e){}
  }

  function _fetchSessionName(id, cb){
    try{
      var xhr = new XMLHttpRequest();
      xhr.open('GET', '/api/sessions', true);
      xhr.onreadystatechange = function(){
        if(xhr.readyState === 4){
          try{
            if(xhr.status === 200){
              var body = xhr.responseText || '{}';
              var data = {};
              try{ data = JSON.parse(body); }catch(_e){ data = {}; }
              var sessions = data.sessions || [];
              for(var i=0;i<sessions.length;i++){
                var s = sessions[i];
                if(s && s.session_id === id){
                  cb(null, s.name || null);
                  return;
                }
              }
              cb(null, null);
            } else {
              cb(new Error('status '+xhr.status));
            }
          }catch(err){ cb(err); }
        }
      };
      xhr.onerror = function(){ cb(new Error('network error')); };
      xhr.send();
    }catch(err){ cb(err); }
  }

  (function _initSession(){
    _session.id = _parseSessionIdFromPath();
    if(_session.id){
      _fetchSessionName(_session.id, function(_err, nm){
        if(nm) _session.name = nm;
        _setSessionMeta();
      });
    } else {
      _setSessionMeta();
    }
  })();
  function _resolveSessionPaths(){
    // Use paths relative to the current document to naturally scope to the session.
    // Works for both '/mcp/playwright/index.html' and '/mcp/playwright/session/<id>/index.html'.
    try {
      return { base: './', sse: './events', json: './events.json' };
    } catch(_e) {
      return { base: '/mcp/playwright/', sse: '/mcp/playwright/events', json: '/mcp/playwright/events.json' };
    }
  }

  function connectSSE(){
    try{
      // Prefer session-scoped SSE endpoint when embedded under /mcp/playwright/session/<id>/
      var paths = _resolveSessionPaths();
      var es = new EventSource(paths.sse);
      es.onopen = function(){ setBadge('ok', 'Connected (SSE)'); _setSessionMeta(); };
      es.onmessage = function(ev){
        try{
          var msg = JSON.parse(ev.data);
          coerceAndRender(msg);
        }catch(_e){ /* ignore parse error */ }
      };
      es.onerror = function(){
        try{ es.close(); }catch(_e){}
        setBadge('warn', 'SSE failed. Switching to poll…');
        connectPoll();
      };
    }catch(_e){ setBadge('err', 'SSE init failed'); connectPoll(); }
  }
  function connectPoll(){
    function loop(){
      var xhr = new XMLHttpRequest();
      // Use session-scoped Playwright JSON proxy
      var paths = _resolveSessionPaths();
      xhr.open('GET', paths.json + '?since=' + String(lastId), true);
      xhr.onreadystatechange = function(){
        if(xhr.readyState === 4){
          try{
            if(xhr.status === 200){
              var body = xhr.responseText || '';
              var data = {};
              try { data = JSON.parse(body); } catch(_e) { data = {}; }
              // Server returns object: { since, items }
              if(data && typeof data === 'object'){
                if(typeof data.since === 'number') lastId = data.since;
                var items = data.items || [];
                for(var i=0;i<items.length;i++){
                  coerceAndRender(items[i]);
                }
              }
              setTimeout(loop, 800);
            }else{
              setTimeout(loop, 1500);
            }
          }catch(_e){ setTimeout(loop, 1500); }
        }
      };
      xhr.onerror = function(){ setBadge('err', 'Poll error. Retrying…'); };
      xhr.send();
    }
    setBadge('ok', 'Connected (poll)');
    _setSessionMeta();
    loop();
  }

  if(useSSE) connectSSE(); else connectPoll();
})();
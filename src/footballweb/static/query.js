(function () {
  var resultEl = document.getElementById('result');
  var statusEl = document.getElementById('status');
  var csvBtn = document.getElementById('csv');
  var jsonBtn = document.getElementById('json');
  var select = document.getElementById('examples');
  var base = resultEl.dataset.resourceBase;
  var last = null;

  var editor = CodeMirror.fromTextArea(document.getElementById('q'), {
    mode: 'sparql', lineNumbers: true,
    extraKeys: { 'Ctrl-Enter': run, 'Cmd-Enter': run }
  });

  function setStatus(text) { statusEl.textContent = text; }

  function cell(value) {
    var td = document.createElement('td');
    if (value === null) return td;
    if (value.indexOf(base) === 0) {
      var a = document.createElement('a');
      a.href = '/page/' + value.slice(base.length);
      a.textContent = value;
      td.appendChild(a);
    } else if (/^https?:\/\//.test(value)) {
      var b = document.createElement('a');
      b.href = value; b.rel = 'noopener'; b.textContent = value;
      td.appendChild(b);
    } else {
      td.textContent = value;
    }
    return td;
  }

  function render(data) {
    resultEl.textContent = '';
    last = data;
    csvBtn.disabled = jsonBtn.disabled = data.form !== 'select';
    if (data.form === 'ask') {
      resultEl.textContent = data.boolean ? 'true' : 'false';
    } else if (data.form === 'graph') {
      var pre = document.createElement('pre');
      pre.textContent = data.turtle;
      resultEl.appendChild(pre);
      setStatus(data.truncated ? 'Turtle truncated to the first 1,000,000 characters' : '');
    } else {
      var table = document.createElement('table');
      var head = table.createTHead().insertRow();
      data.vars.forEach(function (v) { var th = document.createElement('th'); th.textContent = v; head.appendChild(th); });
      var body = table.createTBody();
      data.rows.forEach(function (row) {
        var tr = body.insertRow();
        data.vars.forEach(function (v) { tr.appendChild(cell(row[v])); });
      });
      resultEl.appendChild(table);
      setStatus(data.rows.length + ' rows' + (data.truncated ? ' (truncated to 1000)' : ''));
    }
  }

  var askInput = document.getElementById('ask');
  var answerEl = document.getElementById('answer');
  var generated = '';

  function askCell(c) {
    var td = document.createElement('td');
    if (c === null) return td;
    if (c.href) { var a = document.createElement('a'); a.href = c.href; a.textContent = c.text; td.appendChild(a); }
    else td.textContent = c.text;
    return td;
  }

  function showAnswer(data) {
    generated = data.sparql;
    answerEl.hidden = false;
    document.getElementById('meaning').textContent = data.interpretation;
    var notes = document.getElementById('notes');
    notes.textContent = '';
    data.notes.forEach(function (n) { var li = document.createElement('li'); li.textContent = n; notes.appendChild(li); });
    document.getElementById('generated').textContent = data.sparql;
    resultEl.textContent = '';
    var table = document.createElement('table');
    var head = table.createTHead().insertRow();
    data.vars.forEach(function (v) { var th = document.createElement('th'); th.textContent = v; head.appendChild(th); });
    var body = table.createTBody();
    data.rows.forEach(function (row) {
      var tr = body.insertRow();
      row.forEach(function (c) { tr.appendChild(askCell(c)); });
    });
    resultEl.appendChild(table);
    last = { form: 'select', vars: data.vars, rows: data.rows.map(function (row) {
      var o = {}; data.vars.forEach(function (v, i) { o[v] = row[i] ? row[i].text : null; }); return o; }) };
    csvBtn.disabled = jsonBtn.disabled = false;
    setStatus(data.rows.length ? data.rows.length + ' rows' : 'No rows. The data may not cover this question.');
  }

  function showMisunderstood(body) {
    answerEl.hidden = true;
    last = null; csvBtn.disabled = jsonBtn.disabled = true;
    resultEl.textContent = '';
    setStatus(body.error || 'Error');
    if (body.suggestions && body.suggestions.length) {
      var p = document.createElement('p');
      p.className = 'suggest';
      p.appendChild(document.createTextNode('Did you mean: '));
      body.suggestions.forEach(function (s) {
        var a = document.createElement('a'); a.href = '#'; a.textContent = s;
        a.addEventListener('click', function (e) { e.preventDefault(); askInput.value = s; ask(s); });
        p.appendChild(a);
      });
      resultEl.appendChild(p);
    }
  }

  function ask(q) {
    if (!q.trim()) return;
    setStatus('Thinking…');
    fetch('/api/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) { if (res.ok) showAnswer(res.body); else showMisunderstood(res.body); })
      .catch(function () { setStatus('Request failed'); });
  }

  document.getElementById('ask-form').addEventListener('submit', function (e) { e.preventDefault(); ask(askInput.value); });
  Array.prototype.forEach.call(document.querySelectorAll('a.try'), function (a) {
    a.addEventListener('click', function (e) { e.preventDefault(); askInput.value = a.textContent; ask(a.textContent); });
  });
  document.getElementById('open-editor').addEventListener('click', function () {
    editor.setValue(generated); select.value = ''; editor.focus();
    document.querySelector('.CodeMirror').scrollIntoView({ block: 'center' });
  });

  function run() {
    setStatus('Running…');
    fetch('/api/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: editor.getValue() })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { resultEl.textContent = ''; last = null; csvBtn.disabled = jsonBtn.disabled = true; setStatus(res.body.error || 'Error'); return; }
        setStatus('');
        render(res.body);
      })
      .catch(function () { setStatus('Request failed'); });
  }

  function download(name, type, text) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: type }));
    a.download = name; a.click(); URL.revokeObjectURL(a.href);
  }

  function csvQuote(v) { return v === null ? '' : '"' + v.replace(/"/g, '""') + '"'; }

  csvBtn.addEventListener('click', function () {
    if (!last || last.form !== 'select') return;
    var lines = [last.vars.join(',')];
    last.rows.forEach(function (row) { lines.push(last.vars.map(function (v) { return csvQuote(row[v]); }).join(',')); });
    download('results.csv', 'text/csv', lines.join('\n'));
  });
  jsonBtn.addEventListener('click', function () {
    if (last && last.form === 'select') download('results.json', 'application/json', JSON.stringify(last.rows, null, 2));
  });
  document.getElementById('run').addEventListener('click', run);
  document.getElementById('clear').addEventListener('click', function () {
    editor.setValue('');
    select.value = '';
    history.replaceState(null, '', location.pathname);
    resultEl.textContent = '';
    answerEl.hidden = true;
    last = null;
    csvBtn.disabled = jsonBtn.disabled = true;
    setStatus('');
    editor.focus();
  });

  fetch('/api/examples').then(function (r) { return r.json(); }).then(function (examples) {
    examples.forEach(function (ex) {
      var opt = document.createElement('option');
      opt.value = ex.id; opt.textContent = ex.name; select.appendChild(opt);
    });
    function choose(id) {
      var ex = examples.find(function (e) { return e.id === id; });
      if (ex) { editor.setValue(ex.query); select.value = id; run(); }
    }
    select.addEventListener('change', function () { history.replaceState(null, '', '#' + select.value); choose(select.value); });
    var asked = new URLSearchParams(location.search).get('ask');
    if (location.hash.length > 1) choose(location.hash.slice(1));
    else if (asked) { askInput.value = asked; ask(asked); }
    else askInput.focus();
  });
})();

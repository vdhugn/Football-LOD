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
    if (location.hash.length > 1) choose(location.hash.slice(1));
  });
})();

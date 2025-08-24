let patterns = [], selectedIdx = null, isNew = false;

// --- Toast Utility ---
function showToast(msg) {
    let t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = '';
    setTimeout(() => t.style.display = 'none', 1700);
}

// --- Load pattern list ---
// function loadPatterns(selectIdx = null) {
//     fetch('/patterns/list').then(res => res.json()).then(data => {
//         patterns = data.patterns;
//         let listDiv = document.getElementById('patternList');
//         listDiv.innerHTML = '';
//         patterns.forEach((p, idx) => {
//             let item = document.createElement('div');
//             item.className = 'pattern-list-item' + (idx === selectIdx ? ' selected' : '');
//             item.textContent = p.pattern_name;
//             item.onclick = () => selectPattern(idx);
//             listDiv.appendChild(item);
//         });
//         if (patterns.length && selectIdx !== null) selectPattern(selectIdx);
//     });
// }

// updated with pattern selection
function loadPatterns(selectIdx = null) {
    fetch('/patterns/list').then(res => res.json()).then(data => {
        patterns = data.patterns;
        let listDiv = document.getElementById('patternList');
        listDiv.innerHTML = '';
        patterns.forEach((p, idx) => {
            let item = document.createElement('div');
            item.className = 'pattern-list-item' + (idx === selectIdx ? ' selected' : '');
            item.textContent = p.pattern_name;
            item.onclick = () => selectPattern(idx);
            listDiv.appendChild(item);
        });
        if (patterns.length && selectIdx !== null && selectIdx >= 0) {
            selectPattern(selectIdx);
            setTimeout(() => {
                const item = document.querySelectorAll('.pattern-list-item')[selectIdx];
                if (item) item.scrollIntoView({ behavior: "smooth", block: "center" });
            }, 150);
        }
    });
}



// --- Select pattern for viewing/editing ---
function selectPattern(idx) {
    isNew = false;
    selectedIdx = idx;

    window.location.hash = encodeURIComponent(patterns[idx].pattern_name);  // ⬅️ This line updates the URL hash

    document.querySelectorAll('.pattern-list-item').forEach((i, j) => i.classList.toggle('selected', j === idx));


    // 🔹 Minimal toggle: hide others, show detail panel
    document.getElementById('welcomePanel').style.display = 'none';
    document.getElementById('newPatternPanel').style.display = 'none';
    const detail = document.getElementById('patternDetailPanel');
    detail.style.display = '';

    const p = patterns[idx];
    // 🔹 Minimal change: write into #patternDetailPanel (not #mainPanel)
    detail.innerHTML = `
        <div class="pattern-figure" id="patternFigure"><em>Loading...</em></div>
        <div class="field-label">Pattern Name:</div>
        <div style="margin-bottom:10px;font-size:1.09em;font-weight:bold;">${p.pattern_name}</div>
        <div class="field-label">Description:</div>
        <div class="pattern-desc"><textarea id="patternDescInput">${p.pattern_description || ''}</textarea></div>
        <div class="field-label">PNML File:</div>
        <input type="file" id="pnmlInput" accept=".pnml" style="margin-bottom:12px;">
        <div class="pattern-actions">
          <button onclick="savePattern()">Save</button>
          <button onclick="deletePattern()">Delete</button>
        </div>
    `;
  //   let p = patterns[idx];
  //   let panel = document.getElementById('mainPanel');
  //   panel.innerHTML = `
  //   <div class="pattern-figure" id="patternFigure"><em>Loading...</em></div>
  //   <div class="field-label">Pattern Name:</div>
  //   <div style="margin-bottom:10px;font-size:1.09em;font-weight:bold;">${p.pattern_name}</div>
  //   <div class="field-label">Description:</div>
  //   <div class="pattern-desc"><textarea id="patternDescInput">${p.pattern_description || ''}</textarea></div>
  //   <div class="field-label">PNML File:</div>
  //   <input type="file" id="pnmlInput" accept=".pnml" style="margin-bottom:12px;">
  //   <div class="pattern-actions">
  //     <button onclick="savePattern()">Save</button>
  //     <button onclick="deletePattern()">Delete</button>
  //   </div>
  // `;


    // Show SVG if exists
    fetch('/patterns/svg', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pattern_name: p.pattern_name})
    })
        .then(res => res.json())
        .then(data => {
            document.getElementById('patternFigure').innerHTML = data.svg || "<em>No PNML file uploaded.</em>";
        });
}

// --- Show panel for new pattern ---
function showNewPatternPanel() {
    isNew = true;
    selectedIdx = null;
    document.querySelectorAll('.pattern-list-item').forEach(i => i.classList.remove('selected'));
    document.getElementById('welcomePanel').style.display = 'none';
    document.getElementById('patternDetailPanel').style.display = 'none';
    document.getElementById('newPatternPanel').style.display = '';
    // Add listeners if needed:
    document.getElementById('saveNewBtn').onclick = savePattern;
    document.getElementById('cancelNewBtn').onclick = () => {
        document.getElementById('newPatternPanel').style.display = 'none';
        document.getElementById('welcomePanel').style.display = '';
    };

    document.getElementById('pnmlInput').addEventListener('change', function (e) {
        let file = e.target.files[0];
        if (!file) return;
        let fd = new FormData();
        fd.append('pnml', file);
        fetch('/patterns/preview_pnml', {method: 'POST', body: fd})
            .then(res => res.json())
            .then(data => {
                document.getElementById('newPatternFigure').innerHTML = data.svg || "<em>Failed to render PNML.</em>";
            });
    });

}


// --- Save or update pattern ---
function savePattern() {
    let name = isNew ? document.getElementById('patternNameInput').value.trim() : patterns[selectedIdx].pattern_name;
    let desc = document.getElementById('patternDescInput').value.trim();
    let pnmlFile = document.getElementById('pnmlInput').files[0];

    if (!name) return showToast("Pattern name required.");
    if (!desc) return showToast("Description required.");
    if (isNew && !pnmlFile) return showToast("Please upload a PNML file.");

    // Check for duplicate name on new
    if (isNew && patterns.some(p => p.pattern_name === name)) {
        return showToast("Pattern already exists.");
    }

    // Update CSV
    let updated = isNew ? [...patterns, {pattern_name: name, pattern_description: desc, has_pnml: !!pnmlFile}]
        : patterns.map((p, i) => i === selectedIdx ? {...p, pattern_description: desc} : p);
    fetch('/patterns/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({patterns: updated})
    })
        .then(() => {
            // Now upload PNML if present
            if (pnmlFile) {
                let fd = new FormData();
                fd.append('pattern_name', name);
                fd.append('pnml', pnmlFile);
                fetch('/patterns/upload_pnml', {method: "POST", body: fd}).then(() => {
                    showToast('Pattern saved.');
                    loadPatterns(updated.findIndex(p => p.pattern_name === name));
                });
            } else {
                showToast('Pattern saved.');
                loadPatterns(updated.findIndex(p => p.pattern_name === name));
            }
        });
}

// --- Delete pattern ---
function deletePattern() {
    if (!confirm("Delete this pattern? This cannot be undone.")) return;
    let name = isNew ? document.getElementById('patternNameInput').value.trim() : patterns[selectedIdx].pattern_name;
    let updated = patterns.filter(p => p.pattern_name !== name);
    fetch('/patterns/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({patterns: updated})
    }).then(() => {
        // Delete PNML too
        fetch('/patterns/delete_pnml', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pattern_name: name})
        }).then(() => {
            showToast('Pattern deleted.');
            loadPatterns();
            document.getElementById('mainPanel').innerHTML = '<div style="color:#777; text-align:center; margin-top: 100px;">Select a pattern or create a new one.</div>';
        });
    });
}

// commented
// document.addEventListener('DOMContentLoaded', () => {
//     loadPatterns();
// });

document.addEventListener('DOMContentLoaded', () => {
    fetch('/patterns/list')
        .then(res => res.json())
        .then(data => {
            patterns = data.patterns;
            const hash = decodeURIComponent(window.location.hash.slice(1));
            const targetIdx = hash ? patterns.findIndex(p => p.pattern_name === hash) : null;

            const listDiv = document.getElementById('patternList');
            listDiv.innerHTML = '';
            patterns.forEach((p, idx) => {
                let item = document.createElement('div');
                item.className = 'pattern-list-item' + (idx === targetIdx ? ' selected' : '');
                item.textContent = p.pattern_name;
                item.onclick = () => selectPattern(idx);
                listDiv.appendChild(item);
            });

            if (targetIdx !== null && targetIdx >= 0) {
                selectPattern(targetIdx);
                setTimeout(() => {
                    const item = document.querySelectorAll('.pattern-list-item')[targetIdx];
                    if (item) item.scrollIntoView({ behavior: "smooth", block: "center" });
                }, 150);
            }
        });
});


// --- Sidebar resizing logic ---
(function () {
  const sidebar = document.getElementById('sidebar');
  const resizer = document.getElementById('sidebar-resizer');
  if (!sidebar || !resizer) return;

  let isResizing = false, startX = 0, startWidth = 0;
  const MIN_W = 260, MAX_W = 600;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function onMove(e) {
    if (!isResizing) return;
    const delta = e.clientX - startX;
    sidebar.style.width = clamp(startWidth + delta, MIN_W, MAX_W) + 'px';
  }
  function stop() {
    if (!isResizing) return;
    isResizing = false;
    document.body.style.cursor = ''; document.body.style.userSelect = '';
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', stop);
  }
  resizer.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    isResizing = true;
    startX = e.clientX;
    startWidth = sidebar.getBoundingClientRect().width;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', stop);
  });
})();







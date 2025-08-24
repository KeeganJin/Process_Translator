// Utility: fix SVG width/height for responsive fit
function fixSvgSize(svgText) {
    if (!svgText) return svgText;
    svgText = svgText.replace(/width="[^"]+"/, 'width="100%"');
    svgText = svgText.replace(/height="[^"]+"/, 'height="100%"');
    return svgText;
}

let patternSVGs = [];

// --- File upload preview ---
document.getElementById('pnmlInput').addEventListener('change', (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    fetch('/preview', {
        method: 'POST',
        body: formData,
    })
        .then(res => res.json())
        .then(data => {
            let svg = data.petri_net_svg;
            if (svg) {
                svg = fixSvgSize(svg);
                document.getElementById('petri-net-canvas').innerHTML = svg;
            } else if (data.error) {
                document.getElementById('petri-net-canvas').innerHTML = `<em>Error: ${data.error}</em>`;
            } else {
                document.getElementById('petri-net-canvas').innerHTML = '<em>No preview available.</em>';
            }
            window.currentFileName = data.file_name;
            // Reset sidebars and LLM output
            document.getElementById('detectedPatterns').innerHTML = '';
            document.getElementById('patternDetails').innerHTML = '';
            document.getElementById('llmOutput').textContent = '';
            patternSVGs = [];
        })
        .catch(err => {
            console.error(err);
            document.getElementById('petri-net-canvas').innerHTML = `<em>Network error: ${err.message}</em>`;
        });
});

// --- Show pattern list and details in sidebar ---
function showDetectedPatterns(patterns) {
    const list = document.getElementById('detectedPatterns');
    list.innerHTML = '';
    if (!patterns.length) {
        list.innerHTML = '<em>No patterns detected.</em>';
        document.getElementById('patternDetails').innerHTML = '';
        return;
    }
    patterns.forEach((p, i) => {
        const btn = document.createElement('button');
        btn.textContent = p.pattern_name;
        btn.className = 'pattern-list-btn';
        btn.onclick = () => {
            document.getElementById('petri-net-canvas').innerHTML = fixSvgSize(p.svg);
            showPatternDetails(p);
            highlightActiveButton(i);
        };
        btn.style.borderLeft = `5px solid ${p.color || "#888"}`;
        list.appendChild(btn);
    });
    // Show first pattern as default
    showPatternDetails(patterns[0]);
    highlightActiveButton(0);
}

function showPatternDetails(pattern) {
    if (!pattern) {
        document.getElementById('patternDetails').innerHTML = '';
        return;
    }
    const mappingPretty = pattern.edge_mapping
  ? `<pre class="mapping-pretty">${JSON.stringify(pattern.edge_mapping, null, 2)}</pre>`
  : '<em>(none)</em>';



    const activities = (pattern.transitions || []).map(t => t.label || t.id).join(', ');
    let description = pattern.instantiated_description || pattern.description || '(none)';

    //use the activity from edge mapping to highlight
    if (pattern.edge_mapping) {
        Object.values(pattern.edge_mapping).forEach(label => {
            if (typeof label === 'string') {
                const safeLabel = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // Escape regex
                const regex = new RegExp(`\\b${safeLabel}\\b`, 'g');
                description = description.replace(regex, `<span class="highlight-activity">${label}</span>`);
            }
        });
    }


    document.getElementById('patternDetails').innerHTML =
        `
<div>
  <b>Pattern Name:</b>
  <span class="pattern-name-link" onclick="window.open('/patterns#' + encodeURIComponent('${pattern.pattern_name}'), '_blank')">
    ${pattern.pattern_name}
  </span>
</div>


<div><b>Retrieved Pattern Knowledge:</b> ${pattern.retrieved_knowledge} </div>
<div><b>Activity Label Mapping:</b> ${mappingPretty} </div>
<div><b>Instantiated Description:</b> ${pattern.instantiated_description || pattern.description || '(none)'}</div>
<div><b>Instantiated Description:</b> ${description}</div>
        
`;
}

function highlightActiveButton(activeIdx) {
    const list = document.getElementById('detectedPatterns');
    Array.from(list.children).forEach((btn, idx) => {
        btn.classList.toggle('active', idx === activeIdx);
    });
}

// --- Prompting (detect/LLM) logic ---
document.getElementById('startBtn').addEventListener('click', () => {
    const strategy = document.getElementById('strategy').value;

    const fileName = window.currentFileName;

    if (!fileName) {
        alert("Please upload a PNML file first.");
        return;
    }

    const formData = new FormData();
    formData.append('file_name', fileName);
    formData.append('strategy', strategy);


    // Optionally: show loading indicator
    document.getElementById('llmOutput').innerHTML = '<em>Loading...</em>';

    fetch('/translate', {
        method: 'POST',
        body: formData,
    })
        .then(res => res.json())
        .then(data => {
            // Always show plain SVG first
            let svg = data.petri_net_svg;
            document.getElementById('petri-net-canvas').innerHTML = fixSvgSize(svg) || '<em>No SVG output.</em>';
            window.currentFileName = data.file_name;

            // Show LLM output
            document.getElementById('llmOutput').innerHTML = marked.parse(data.llm_response || '');
            document.getElementById('llmPrompt').textContent = data.llm_prompt || '';
            // Show/hide sidebar patterns depending on strategy
            patternSVGs = data.detected_patterns || [];
            if (strategy === "pattern-augmented" && patternSVGs.length > 0) {
                document.querySelector('.sidebar').style.display = '';
                showDetectedPatterns(patternSVGs);
            } else {
                document.getElementById('detectedPatterns').innerHTML = '';
                document.getElementById('patternDetails').innerHTML = '';
            }
        })
        .catch(err => {
            console.error(err);
            document.getElementById('llmOutput').innerHTML = `<em>Network error: ${err.message}</em>`;
        });
});


// --- make the boarder draggable

// --- Sidebar resizing logic ---
(function () {
  const sidebar = document.getElementById('sidebar');
  const resizer = document.getElementById('sidebar-resizer');
  const root = document.querySelector('.flex-root');

  if (!sidebar || !resizer || !root) return;

  let isResizing = false;
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));

  function onMouseMove(e) {
    if (!isResizing) return;
    const rootRect = root.getBoundingClientRect();
    const newWidth = e.clientX - rootRect.left;  // width relative to flex container
    const minWidth = 260;                        // keep in sync with CSS
    const maxWidth = 600;
    sidebar.style.width = clamp(newWidth, minWidth, maxWidth) + 'px';
  }

  function stopResize() {
    if (!isResizing) return;
    isResizing = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', stopResize);
  }

  resizer.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    isResizing = true;
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', stopResize);
  });

  // Optional touch support
  resizer.addEventListener('touchstart', () => {
    isResizing = true;
    document.body.style.userSelect = 'none';
  }, { passive: true });

  window.addEventListener('touchmove', (e) => {
    if (!isResizing) return;
    const touch = e.touches[0];
    const rootRect = root.getBoundingClientRect();
    const newWidth = touch.clientX - rootRect.left;
    const minWidth = 260;
    const maxWidth = 600;
    sidebar.style.width = clamp(newWidth, minWidth, maxWidth) + 'px';
  }, { passive: true });

  window.addEventListener('touchend', stopResize);
})();


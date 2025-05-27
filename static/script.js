// --- SVG Size Fix Utility ---
function fixSvgSize(svgText) {
    if (!svgText) return svgText;
    svgText = svgText.replace(/width="[^"]+"/, 'width="100%"');
    svgText = svgText.replace(/height="[^"]+"/, 'height="100%"');
    return svgText;
}

// --- Pattern SVGs array, for swapping on click ---
let patternSVGs = [];

// --- Minimal upload button event (using delegated input) ---
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
        // Clear pattern and LLM info (on new file)
        document.getElementById('patternDetails').innerHTML = '';
        document.getElementById('llmOutput').textContent = '';
        patternSVGs = [];
    })
    .catch(err => {
        console.error(err);
        document.getElementById('petri-net-canvas').innerHTML = `<em>Network error: ${err.message}</em>`;
    });
});

// --- Pattern list rendering and SVG swapping ---
function showPatternList(patterns) {
    const list = document.getElementById('patternDetails');
    list.innerHTML = '';
    if (!patterns.length) {
        list.innerHTML = '<em>No patterns detected.</em>';
        return;
    }
    patterns.forEach((p, i) => {
        const btn = document.createElement('button');
        btn.textContent = p.pattern_name;
        btn.style.borderLeft = `5px solid ${p.color || "#888"}`;
        btn.style.background = '#f7f7fa';
        btn.style.margin = "0 0 10px 0";
        btn.style.display = "block";
        btn.style.width = "100%";
        btn.style.textAlign = "left";
        btn.style.padding = "8px";
        btn.style.border = "none";
        btn.style.borderRadius = "4px";
        btn.style.cursor = "pointer";
        btn.onmouseover = () => btn.style.background = '#e5e9ff';
        btn.onmouseout  = () => btn.style.background = '#f7f7fa';
        btn.onclick = () => {
            document.getElementById('petri-net-canvas').innerHTML = fixSvgSize(p.svg);
            highlightActiveButton(i);
            showPatternDescription(p);
        };
        list.appendChild(btn);
    });
    // Optionally, show description for the first pattern (default selection)
    if (patterns.length > 0) {
        highlightActiveButton(-1); // No initial selection; show only plain net
        showPatternDescription(null);
    }
}

function highlightActiveButton(activeIdx) {
    const list = document.getElementById('patternDetails');
    Array.from(list.children).forEach((btn, idx) => {
        btn.style.boxShadow = (idx === activeIdx) ? '0 0 0 2px #2e7df6' : 'none';
        btn.style.fontWeight = (idx === activeIdx) ? 'bold' : 'normal';
    });
}

function showPatternDescription(pattern) {
    document.getElementById('llmOutput').textContent = pattern ? (pattern.description || '') : '';
}

// --- Start/Detection button logic ---
document.getElementById('startBtn').addEventListener('click', () => {
    const strategy = document.getElementById('strategy').value;
    const userContext = document.getElementById('userContext').value;
    const fileName = window.currentFileName;

    if (!fileName) {
        alert("Please upload a PNML file first.");
        return;
    }

    const formData = new FormData();
    formData.append('file_name', fileName);
    formData.append('strategy', strategy);
    formData.append('user_input', userContext);

    fetch('/translate', {
        method: 'POST',
        body: formData,
    })
    .then(res => res.json())
    .then(data => {
        patternSVGs = data.detected_patterns || [];
        // Show default (plain) SVG at first
        let svg = data.petri_net_svg;
        document.getElementById('petri-net-canvas').innerHTML = fixSvgSize(svg) || '<em>No SVG output.</em>';
        showPatternList(patternSVGs);
        window.currentFileName = data.file_name;
        // Show default LLM response, unless a pattern is selected
        if (data.llm_response) {
            document.getElementById('llmOutput').textContent = data.llm_response || '';
        }
    })
    .catch(err => {
        console.error(err);
        document.getElementById('petri-net-canvas').innerHTML = `<em>Network error: ${err.message}</em>`;
    });
});

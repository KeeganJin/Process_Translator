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
        document.getElementById('patternList').innerHTML = '';
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
function showPatternList(patterns) {
    const list = document.getElementById('patternList');
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
    const activities = (pattern.transitions || []).map(t => t.label || t.id).join(', ');
    document.getElementById('patternDetails').innerHTML =
        `<div><b>Pattern Name:</b> ${pattern.pattern_name}</div>
     <div><b>Instantiated Description:</b> ${pattern.instantiated_description || pattern.description || '(none)'}</div>
         <div><b>Activities:</b> ${activities}</div>`;
}

function highlightActiveButton(activeIdx) {
    const list = document.getElementById('patternList');
    Array.from(list.children).forEach((btn, idx) => {
        btn.classList.toggle('active', idx === activeIdx);
    });
}

// --- Prompting (detect/LLM) logic ---
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
            showPatternList(patternSVGs);
        } else {
            document.getElementById('patternList').innerHTML = '';
            document.getElementById('patternDetails').innerHTML = '';
        }
    })
    .catch(err => {
        console.error(err);
        document.getElementById('llmOutput').innerHTML = `<em>Network error: ${err.message}</em>`;
    });
});

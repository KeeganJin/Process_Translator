// --- Petri net file upload and preview ---
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
            visualizeOriginalPetriNet(data);
            window.currentFileName = data.file_name;
            // Clear the detected net and pattern info until user starts detection
            document.getElementById('cy-detected').innerHTML = '';
            document.getElementById('patternDetails').innerHTML = '';
            document.getElementById('llmOutput').textContent = '';
        })
        .catch(err => {
            console.error(err);
            alert("Error loading Petri net:\n" + err.message);
        });
});

// --- Detection and prompting ---
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
            if (data.error) throw new Error(data.error);

            // Visualize detected net (side by side with original)
            visualizeDetectedPetriNet(data);

            // Pattern info panel
            const infoBox = document.getElementById("patternDetails");
            infoBox.innerHTML = '';
            (data.detected_patterns || []).forEach(p => {
                const div = document.createElement("div");
                div.style.borderLeft = `5px solid ${p.color}`;
                div.style.paddingLeft = "10px";
                div.style.marginBottom = "8px";
                const activityNames = p.transitions.map(t => t.label || "[silent]").join(", ");
                div.innerHTML = `
                    <strong>${p.pattern_name}</strong><br>
                    <small>${activityNames}</small><br>
                    ${p.description || ''}
                `;
                infoBox.appendChild(div);
            });

            // LLM output
            document.getElementById('llmOutput').textContent = data.llm_response || 'No response';
        })
        .catch(err => {
            console.error(err);
            alert("Error during detection or prompting.");
        });
});

// --- Visualization for original net (no patterns) ---
function visualizeOriginalPetriNet(data) {
    document.getElementById('cy-original').innerHTML = '';

    const elements = [];
    (data.places || []).forEach(place => {
        elements.push({
            data: {
                id: place.id,
                label: place.id,
                type: "place"
            }
        });
    });
    (data.transitions || []).forEach(trans => {
        elements.push({
            data: {
                id: trans.id,
                label: trans.label || "[\u03c4]",
                type: "transition"
            },
            classes: trans.label ? "" : "silent"
        });
    });
    (data.arcs || []).forEach(arc => {
        elements.push({
            data: {
                id: arc.source + '__' + arc.target,
                source: arc.source,
                target: arc.target
            }
        });
    });

    cytoscape({
        container: document.getElementById('cy-original'),
        elements: elements,
        style: getBaseStyles(),
layout:
    // getElkLayout(),
    {
  name: 'dagre',
  rankDir: 'LR',
  nodeSep: 70,
  edgeSep: 30,
  rankSep: 90
}


    });
}

// --- Visualization for detected patterns ---
function visualizeDetectedPetriNet(data) {
    console.log("Detected Net Data:", data);
    document.getElementById('cy-detected').innerHTML = '';

    data.elements.forEach(e => {
        if (Array.isArray(e.data.patterns)) {
            e.data.patterns = e.data.patterns.join(',');
        }
    });
    const patterns = data.detected_patterns || [];
    const patternColors = getPatternColors(patterns);

    const style = getBaseStyles();

    patterns.forEach(p => {
        style.push({
            selector: `node[patterns *= "${p.pattern_name}"]`,
            style: {
                'border-color': patternColors[p.pattern_name],
                'border-width': 6
            }
        });
        style.push({
            selector: `edge[patterns *= "${p.pattern_name}"]`,
            style: {
                'line-color': patternColors[p.pattern_name],
                'width': 4
            }
        });
    });

    cytoscape({
        container: document.getElementById('cy-detected'),
        elements: data.elements,
        style: style,
        layout: getElkLayout()
    });
}

// --- Shared Cytoscape Style ---
function getBaseStyles() {
    return [
        {
            selector: 'node[type="place"]',
            style: {
                'shape': 'ellipse',
                'width': 20,  // was 32
                'height': 20, // was 32
                'background-color': '#fff',
                'border-width': 1, // was 2
                'border-color': '#222',
                'label': 'data(label)'
            }
        },
        {
            selector: 'node[type="transition"]',
            style: {
                'shape': 'rectangle',
                'width': 14,  // was 24
                'height': 20, // was 36
                'background-color': '#ddd',
                'border-width': 1, // was 2
                'border-color': '#555',
                'label': 'data(label)'
            }
        },
        {
            selector: 'node.silent',
            style: {
                'shape': 'rectangle',
                'background-color': '#000',
                'width': 14, // was 24
                'height': 14, // was 24
                'label': '',
                'border-width': 1, // was 2
                'border-color': '#000'
            }
        },
        {
            selector: 'edge',
            style: {
                'width': 1, // was 2
                'line-color': '#888',
                'target-arrow-shape': 'triangle',
                'target-arrow-color': '#888',
                'curve-style': 'bezier',
                'arrow-scale': 1, // was 1.5
            }
        }
    ];
}

// --- Layout (ELK) ---
function getElkLayout() {
    return {
        name: 'elk',
        elk: {
            algorithm: 'layered',
            direction: 'RIGHT',
            'elk.spacing.nodeNode': 100,
            'elk.labelManagement': true,
            'elk.nodeLabels.placement': 'INSIDE V_CENTER H_CENTER',
            'elk.layered.spacing.nodeNodeBetweenLayers': 100,
            'elk.layered.spacing.edgeNodeBetweenLayers': 40,
            'elk.layered.spacing.edgeEdgeBetweenLayers': 40,
            'elk.layered.edgeRouting': 'ORTHOGONAL',
            'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF'
        }
    };
}

// --- Pattern color assignment ---
function getPatternColors(patterns) {
    const palette = [
        '#2a9d8f', '#e76f51', '#264653', '#f4a261', '#9d4edd',
        '#0077b6', '#b5179e', '#3a86ff', '#ffbe0b', '#ff006e'
    ];
    const names = patterns.map(p => p.pattern_name);
    const colorMap = {};
    names.forEach((name, idx) => {
        colorMap[name] = palette[idx % palette.length];
    });
    return colorMap;
}

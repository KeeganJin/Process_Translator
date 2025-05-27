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
            document.getElementById('patternDetails').innerHTML = '';
            document.getElementById('llmOutput').textContent = '';
        })
        .catch(err => {
            console.error(err);
            document.getElementById('petri-net-canvas').innerHTML = `<em>Network error: ${err.message}</em>`;
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
            // Update the SVG
            document.getElementById('petri-net-canvas').innerHTML = data.petri_net_svg || '<em>No SVG output.</em>';
            // Update pattern details
            const infoBox = document.getElementById("patternDetails");
            infoBox.innerHTML = '';
            (data.detected_patterns || []).forEach(p => {
                const div = document.createElement("div");
                div.style.borderLeft = `5px solid ${p.color || "#888"}`;
                div.style.paddingLeft = "10px";
                div.style.marginBottom = "8px";
                const activityNames = (p.transitions || []).map(t => t.label || "[silent]").join(", ");
                div.innerHTML = `<strong>${p.pattern_name}</strong><br><small>${activityNames}</small><br>${p.description || ''}`;
                infoBox.appendChild(div);
            });
            // Update LLM output
            document.getElementById('llmOutput').textContent = data.llm_response || 'No response';
        })
        .catch(err => {
            console.error(err);
            alert("Error during detection or prompting.");
        });
});

function fixSvgSize(svgText) {
    svgText = svgText.replace(/width="[^"]+"/, 'width="100%"');
    svgText = svgText.replace(/height="[^"]+"/, 'height="100%"');
    return svgText;
}

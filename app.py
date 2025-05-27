from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import os
import graphviz

from Utils.visual_backend import (
    get_petri_net_structure,
    extract_subnet_visual_elements,
    assign_colors_to_patterns,
    generate_petri_net_dot
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview():
    uploaded_file = request.files.get('file')
    if not uploaded_file:
        return jsonify({'error': 'No file uploaded'}), 400
    filename = secure_filename(uploaded_file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    uploaded_file.save(file_path)
    try:
        net_data = get_petri_net_structure(file_path)
        dot_str = generate_petri_net_dot(net_data, pattern_subnets=[])

        print("DOT STRING:\n", dot_str)


        graph = graphviz.Source(dot_str)
        svg_str = graph.pipe(format='svg').decode('utf-8')
        print("SVG STRING HEAD:\n", svg_str[:500])
        return jsonify({"petri_net_svg": svg_str, "file_name": filename})
    except Exception as e:
        print(f"PREVIEW ERROR: {e}")  # log to console
        return jsonify({'error': str(e)}), 500


@app.route('/translate', methods=['POST'])
def translate():
    filename = request.form.get('file_name')
    strategy = request.form.get('strategy')
    user_input = request.form.get('user_input')
    if not filename:
        return jsonify({'error': 'Missing file name'}), 400
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # === Hardcoded or Real Pattern Detection ===
    pattern_mapping = [
        {
            "pattern_name": "pattern_basic_xor_1",
            "edge_mapping": [
                {"a": "Back-order Part", "b": "Reserve Part"}
            ]
        },
        {
            "pattern_name": "pattern_PETRINET_1_1",
            "edge_mapping": [
                {"a": "Check Part Quality", "b": "Back-order Part", "c": "Reserve Part", "d": "Select Unchecked Part"}
            ]
        }
    ]
    pattern_subnets = extract_subnet_visual_elements(file_path, pattern_mapping)
    color_map = assign_colors_to_patterns([p["pattern_name"] for p in pattern_subnets])
    for pattern in pattern_subnets:
        pattern["color"] = color_map.get(pattern["pattern_name"], "#888")
    net_data = get_petri_net_structure(file_path)
    dot_str = generate_petri_net_dot(net_data, pattern_subnets)
    graph = graphviz.Source(dot_str)
    svg_str = graph.pipe(format='svg').decode('utf-8')
    prompt = f"This is a dummy LLM description for strategy: {strategy}"
    return jsonify({
        "petri_net_svg": svg_str,
        "detected_patterns": pattern_subnets,
        "llm_response": prompt,
        "file_name": filename,
        "strategy": strategy,
        "user_input": user_input
    })

if __name__ == '__main__':
    app.run()

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import os
import pm4py

from Utils.detector_v1 import PatternDetector
from Utils.prompting import PromptGenerator
from Utils.visual_backend import (petri_net_to_cytoscape_json, get_petri_net_structure,
                                  extract_subnet_visual_elements, assign_colors_to_patterns)
from Utils.visual_backend import generate_petri_net_dot  # Make sure the function is here!
import graphviz


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# # === Reusable Components ===
# pattern_detector = PatternDetector('./Dataset/patterns_eval/')
# prompt_generator = PromptGenerator(
#     './Dataset/pattern_dataset.csv',
#     './Dataset/petri_net_examples.csv'
# )

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
        return jsonify({**net_data, "file_name": filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/translate', methods=['POST'])
def translate():
    filename = request.form.get('file_name')
    # uploaded_file = request.files.get('file')
    strategy = request.form.get('strategy')
    user_input = request.form.get('user_input')

    if not filename:
        return jsonify({'error': 'Missing file name'}), 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # === Hardcoded Pattern Mapping ===
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

    # Optional: dummy prompt (since LLM isn't used yet)
    prompt = f"This is a dummy LLM description for strategy: {strategy}"

    # Extract subnet visuals using the fake mapping
    pattern_subnets = extract_subnet_visual_elements(file_path, pattern_mapping)
    print(pattern_subnets)
    # Assign colors to pattern names
    color_map = assign_colors_to_patterns([p["pattern_name"] for p in pattern_subnets])
    for pattern in pattern_subnets:
        pattern["color"] = color_map.get(pattern["pattern_name"], "#888")

    # Full net structure
    net_data = get_petri_net_structure(file_path)

    # Try cytoscape
    cy_data = petri_net_to_cytoscape_json(net_data, pattern_subnets)


    # -----------Let's try graphviz vis for our frontend-
    dot_str = generate_petri_net_dot(net_data, pattern_subnets)
    graph = graphviz.Source(dot_str)
    svg_bytes = graph.pipe(format='svg')
    svg_str = svg_bytes.decode('utf-8')



    # Return demo response
    return jsonify({
        **net_data,
        "elements": cy_data["elements"],
        "detected_patterns": pattern_subnets,
        "llm_response": prompt,
        "file_name": filename,
        "strategy": strategy,
        "user_input": user_input,
        "petri_net_svg": svg_str  # pls be working
    })


if __name__ == '__main__':
    app.run()

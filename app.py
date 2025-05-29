from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
import graphviz
from Utils.detector_v1 import PatternDetector
from Utils.prompting import PromptGenerator
from openai import OpenAI
import pandas as pd

from Utils.visual_backend import (
    get_petri_net_structure,
    extract_subnet_visual_elements,
    assign_colors_to_patterns,
    generate_petri_net_dot
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# initialize pattern detector
PATTERN_FOLDER = "database/patterns"
pattern_detector = PatternDetector(PATTERN_FOLDER)

# initialize prompt generator
PATTERNS_FILE_PATH = "database/pattern_dataset.csv"       # Update to your real path
EXAMPLE_FILE_PATH = "database/petri_net_examples.csv"     # Update to your real path

prompt_generator = PromptGenerator(PATTERNS_FILE_PATH, EXAMPLE_FILE_PATH)


# LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# client = OpenAI(api_key=LLM_API_KEY, base_url="https://api.deepseek.com")
client = OpenAI(api_key="sk-cd62a53898ed41fb85261f0de364457d", base_url="https://api.deepseek.com")

SYSTEM_INSTRUCTION = '''Please help me describe the Petri net process using clear, everyday language.
- Describe the steps in the flow of work, and if there are tasks that happen at the same time, clearly show that they occur together.
- If there are steps that happen exclusively, clearly show them. If there are loops, clearly show them.
- Show which steps happen simultaneously, exclusively, and which steps come one after another.
- Use words such as "then," "next," and "separately" to describe the flow.
- Use the exact activity names provided in the Petri net.
- Do not omit any activities.
- Silent transitions are used to facilitate the flow and form paths; also, show their effect in the description.
- Write the explanation for a non-technical audience.
- Do not generate extra information.

# Petri net specification:
Initial marking indicates the start of the process.
Final marking indicates the end of the process.'''

def call_llm(client, system_instruction, prompt):
    if not prompt or prompt.strip() == "":
        return ""
    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/preview', methods=['POST'])
def preview():
    print("PREVIEW ENDPOINT HIT!")
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

    task_description = user_input or "Please help me describe the Petri net."
    output_indic = ""
    pattern_svgs = []
    pattern_mapping = None  # default
    net_data = get_petri_net_structure(file_path)
    svg_str_plain = graphviz.Source(
        generate_petri_net_dot(net_data, pattern_subnets=[])
    ).pipe(format='svg').decode('utf-8')

    # Pattern-augmented strategy: run detection
    if strategy == "pattern-augmented":
        try:
            detect_result, pattern_mapping = pattern_detector.perform_detection(file_path)
            print("detect_result",detect_result)
        except Exception as e:
            return jsonify({'error': f'Pattern detection failed: {e}'}), 500

        if pattern_mapping:  # Patterns found
            pattern_subnets = extract_subnet_visual_elements(file_path, pattern_mapping)
            color_map = assign_colors_to_patterns([p["pattern_name"] for p in pattern_subnets])
            for pattern in pattern_subnets:
                pattern["color"] = color_map.get(pattern["pattern_name"], "#888")
            for pattern in pattern_subnets:
                dot_str = generate_petri_net_dot(net_data, [pattern])
                svg_str = graphviz.Source(dot_str).pipe(format='svg').decode('utf-8')
                pattern_svgs.append({
                    "pattern_name": pattern["pattern_name"],
                    "svg": svg_str,
                    "color": pattern["color"],
                    "description": pattern.get("description", ""),
                    "transitions": pattern.get("transitions", []),
                    # You can add more fields as needed
                })
        else:
            # No patterns found, pattern-augmented falls back to zero-shot
            pattern_mapping = None
            strategy = "zero_shot"  # Fallback strategy for prompt


    # --- Prompt Generation (always run exactly once, with correct mapping and strategy) ---
    try:
        print("here is pattern mapping",pattern_mapping)
        prompt = prompt_generator.create_prompt(
            file_path,
            strategy,
            pattern_mapping=pattern_mapping,
            n_shots=1,
            task_description=task_description,
            output_indic=output_indic
        )
    except Exception as e:
        prompt = f"Prompt generation failed: {e}"

    # --- LLM response ---
    try:
        llm_response = "fake LLM response"
        # llm_response = call_llm(client, SYSTEM_INSTRUCTION, prompt)
    except Exception as e:
        llm_response = f"LLM call failed: {e}"


    return jsonify({
        "petri_net_svg": svg_str_plain,
        "detected_patterns": pattern_svgs,  # empty unless pattern-augmented
        "llm_response": llm_response,
        "llm_prompt": prompt,
        "file_name": filename,
        "strategy": strategy,
        "user_input": user_input
    })

# @app.route('/translate', methods=['POST'])
# def translate():
#     filename = request.form.get('file_name')
#     strategy = request.form.get('strategy')
#     user_input = request.form.get('user_input')
#     if not filename:
#         return jsonify({'error': 'Missing file name'}), 400
#     file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#
#     task_description = user_input or "Please help me describe the Petri net."
#     output_indic = ""
#     pattern_svgs = []
#     pattern_mapping = None  # default
#
#
#     # ------------- Pattern Detection ---------------------
#     try:
#         detect_result, pattern_mapping = pattern_detector.perform_detection(file_path)
#     except Exception as e:
#         return jsonify({'error': f'Pattern detection failed: {e}'}), 500
#
#     if not detect_result or not pattern_mapping:
#         # No patterns detected: return plain SVG, empty pattern list
#         net_data = get_petri_net_structure(file_path)
#         dot_str = generate_petri_net_dot(net_data, pattern_subnets=[])
#         svg_str = graphviz.Source(dot_str).pipe(format='svg').decode('utf-8')
#         return jsonify({
#             "petri_net_svg": svg_str,
#             "detected_patterns": [],
#             "llm_response": "No patterns detected.",
#             "file_name": filename,
#             "strategy": strategy,
#             "user_input": user_input
#         })
#
#     pattern_subnets = extract_subnet_visual_elements(file_path, pattern_mapping)
#     color_map = assign_colors_to_patterns([p["pattern_name"] for p in pattern_subnets])
#     for pattern in pattern_subnets:
#         pattern["color"] = color_map.get(pattern["pattern_name"], "#888")
#
#     net_data = get_petri_net_structure(file_path)
#
#     # Generate SVGs for each pattern (highlight one at a time)
#     pattern_svgs = []
#     for pattern in pattern_subnets:
#         dot_str = generate_petri_net_dot(net_data, [pattern])  # Only highlight this pattern
#         graph = graphviz.Source(dot_str)
#         svg_str = graph.pipe(format='svg').decode('utf-8')
#         pattern_svgs.append({
#             "pattern_name": pattern["pattern_name"],
#             "svg": svg_str,
#             "color": pattern["color"],
#             "description": pattern.get("description", ""),
#         })
#
#     # Initial display: no highlight (just the net)
#     dot_str_plain = generate_petri_net_dot(net_data, pattern_subnets=[])
#     graph_plain = graphviz.Source(dot_str_plain)
#     svg_str_plain = graph_plain.pipe(format='svg').decode('utf-8')
#
# # ------------ Prompting ------------------
#     task_description = user_input or "Please help me describe the Petri net."
#     output_indic = ""
#
#     try:
#         prompt = prompt_generator.create_prompt(
#             file_path,
#             strategy,
#             pattern_mapping=pattern_mapping,
#             n_shots=1,
#             task_description=task_description,
#             output_indic=output_indic
#         )
#     except Exception as e:
#         prompt = f"Prompt generation failed: {e}"
#
#     # ---- LLM  prompt ---
#     try:
#         llm_response = call_llm(client, SYSTEM_INSTRUCTION, prompt)
#     except Exception as e:
#         llm_response = f"LLM call failed: {e}"
#
#     return jsonify({
#         "petri_net_svg": svg_str_plain,
#         "detected_patterns": pattern_svgs,
#         "llm_response": llm_response,  # <--- LLM's actual output!
#         "llm_prompt": prompt,  # <--- prompt for debugging/display
#         "file_name": filename,
#         "strategy": strategy,
#         "user_input": user_input
#     })
#




# --- Adjust these as needed
PATTERN_CSV = "database/pattern_dataset.csv"
PATTERN_PNML_DIR = "database/patterns"
@app.route("/patterns")
def patterns_page():
    return render_template("patterns.html")

@app.route("/patterns/list")
def patterns_list():
    df = pd.read_csv(PATTERN_CSV)
    patterns = []
    for _, row in df.iterrows():
        pattern_name = row["pattern_name"]
        pattern_desc = row["pattern_description"]
        pnml_path = os.path.join(PATTERN_PNML_DIR, f"{pattern_name}.pnml")
        patterns.append({
            "pattern_name": pattern_name,
            "pattern_description": pattern_desc,
            "has_pnml": os.path.exists(pnml_path)
        })
    return jsonify({"patterns": patterns})

@app.route("/patterns/svg", methods=["POST"])
def patterns_svg():
    data = request.get_json()
    pattern_name = data.get("pattern_name")
    pnml_path = os.path.join(PATTERN_PNML_DIR, f"{pattern_name}.pnml")
    if not os.path.exists(pnml_path):
        return jsonify({"svg": ""})
    # Reuse your Petri net -> SVG code

    net_data = get_petri_net_structure(pnml_path)
    dot_str = generate_petri_net_dot(net_data, pattern_subnets=[])
    svg_str = graphviz.Source(dot_str).pipe(format="svg").decode("utf-8")
    return jsonify({"svg": svg_str})

@app.route("/patterns/save", methods=["POST"])
def patterns_save():
    patterns = request.json.get("patterns", [])
    df = pd.DataFrame(patterns)
    df.to_csv(PATTERN_CSV, index=False)
    return jsonify({"status": "ok"})

@app.route("/patterns/upload_pnml", methods=["POST"])
def patterns_upload_pnml():
    pattern_name = request.form.get("pattern_name")
    file = request.files["pnml"]
    if not pattern_name or not file:
        return jsonify({"error": "Missing pattern name or file"}), 400
    fn = secure_filename(f"{pattern_name}.pnml")
    file.save(os.path.join(PATTERN_PNML_DIR, fn))
    return jsonify({"status": "ok"})

@app.route("/patterns/delete_pnml", methods=["POST"])
def patterns_delete_pnml():
    pattern_name = request.json.get("pattern_name")
    pnml_path = os.path.join(PATTERN_PNML_DIR, f"{pattern_name}.pnml")
    if os.path.exists(pnml_path):
        os.remove(pnml_path)
    return jsonify({"status": "ok"})

import tempfile

@app.route("/patterns/preview_pnml", methods=["POST"])
def patterns_preview_pnml():
    file = request.files.get("pnml")
    if not file:
        return jsonify({"svg": ""})
    tmp = tempfile.NamedTemporaryFile(suffix=".pnml", delete=False)
    tmp.close()  # Close the file so it can be written to by file.save()
    try:
        file.save(tmp.name)
        net_data = get_petri_net_structure(tmp.name)
        dot_str = generate_petri_net_dot(net_data, pattern_subnets=[])
        import graphviz
        svg_str = graphviz.Source(dot_str).pipe(format="svg").decode("utf-8")
        os.remove(tmp.name)
        return jsonify({"svg": svg_str})
    except Exception as e:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)
        return jsonify({"svg": f"<em style='color:red'>Preview error: {e}</em>"})


#
@app.route("/patterns/instantiated_description", methods=["POST"])
def pattern_instantiated_description():
    """
    Expects JSON: { "pattern_name": ..., "edge_mapping": [{"a": "A", "b": "B"}] }
    Returns: { "description": ... }
    """
    data = request.json
    pattern_name = data.get("pattern_name")
    edge_mapping = data.get("edge_mapping", [])
    # Defensive: wrap pattern_mapping in a list of dicts
    pattern_mapping = [{"pattern_name": pattern_name, "edge_mapping": [edge_mapping]}] if edge_mapping else [{"pattern_name": pattern_name, "edge_mapping": []}]
    desc_list = prompt_generator.generate_pattern_description_list(pattern_mapping)
    description = desc_list[0] if desc_list else ""
    return jsonify({"description": description})




if __name__ == '__main__':
    app.run(debug=True)

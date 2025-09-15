import pm4py
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
import graphviz
from Utils.detector_v1 import PatternDetector
from Utils.prompting import PromptGenerator
from openai import OpenAI
import pandas as pd
import re
import threading
import time
import uuid
import traceback, sys
from Utils.pattern_sustituted_feature import filter_patterns_by_overlap, collapse_patterns_to_indicator_transitions
import dotenv
from Utils.post_processing import find_subnet_based_on_activity_list_extend_silent_transition_v2


from Utils.visual_backend import (
    get_petri_net_structure,
    get_petri_net_structure_from_net,
    extract_subnet_visual_elements,
    assign_colors_to_patterns,
    generate_petri_net_dot
)
try:
    from dotenv import load_dotenv  # python-dotenv
except Exception:
    load_dotenv = None

app = Flask(__name__)

if os.environ.get("RENDER") is None and load_dotenv:
    # loads .env in project root if present
    load_dotenv()
    print("Loaded .env for local development", flush=True)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
print("DEEPSEEK_API_KEY present?", bool(os.environ.get("DEEPSEEK_API_KEY")), flush=True)

if not DEEPSEEK_API_KEY:
    # fail fast so you notice misconfiguration
    raise RuntimeError("DEEPSEEK_API_KEY not set. "
                       "Set it in Render (Environment tab) and/or your local .env")

# using a thread to get llm response in the backend
_JOBS = {}      # job_id -> {"status": "...", "result": {...}}
_JOBS_LOCK = threading.Lock()

def _new_job(payload=None):
    jid = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[jid] = {"status": "running", "result": None, "created_at": time.time(), "payload": payload or {}}
    return jid

def _set_job_done(jid, result):
    with _JOBS_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["status"] = "done"
            _JOBS[jid]["result"] = result

def _set_job_error(jid, message):
    with _JOBS_LOCK:
        if jid in _JOBS:
            _JOBS[jid]["status"] = "error"
            _JOBS[jid]["result"] = {"error": message}





app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# initialize pattern detector
PATTERN_FOLDER = "database/patterns"
pattern_detector = PatternDetector(PATTERN_FOLDER)

# initialize prompt generator
PATTERNS_FILE_PATH = "database/pattern_dataset.csv"
EXAMPLE_FILE_PATH = "database/petri_net_examples.csv"

prompt_generator = PromptGenerator(PATTERNS_FILE_PATH, EXAMPLE_FILE_PATH)


# LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# client = OpenAI(api_key=LLM_API_KEY, base_url="https://api.deepseek.com")



client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

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
            # model="deepseek-chat",

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

def call_llm_fast(client, system_instruction, prompt):
    '''use smllaer model to get a quick response for illustration'''
    if not prompt or prompt.strip() == "":
        return ""
    try:
        response = client.chat.completions.create(
            # model="deepseek-reasoner",
            model="deepseek-chat",

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

def _log(msg):
    print(msg, file=sys.stdout, flush=True)

def _run_llm_job(job_id, prompt, llm_model="R1"):
    try:
        # real call (uncomment when ready)
        # llm_response = call_llm(client, SYSTEM_INSTRUCTION, prompt)

        # placeholder so you can see polling work without LLM cost:
        # time.sleep(5); llm_response = "[demo] llm finished."
        _log(f"[JOB {job_id}] starting llm_model={llm_model!r}, prompt_len={len(prompt or '')}")

        llm_response = "The real LLM API is inactive to keep API safe."

        # if (llm_model or "").lower() in ("r1", "reasoner", "deepseek-reasoner"):
        #     llm_response = call_llm(client, SYSTEM_INSTRUCTION, prompt)
        # else:
        #     # treat anything else as "chat"
        #     llm_response = call_llm_fast(client, SYSTEM_INSTRUCTION, prompt)


        _set_job_done(job_id, {"llm_response": llm_response, "llm_prompt": prompt})
        _log(f"[JOB {job_id}] done (resp_len={len(llm_response or '')})")

    except Exception as e:
        _log(f"[JOB {job_id}] failed: {e}")
        traceback.print_exc()

        _set_job_error(job_id, f"LLM call failed: {e}")


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

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route('/translate', methods=['POST'])
def translate():
    filename = request.form.get('file_name')
    strategy = request.form.get('strategy')
    if not filename:
        return jsonify({'error': 'Missing file name'}), 400
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    task_description = "Please help me describe the Petri net."
    output_indic = ""
    pattern_svgs = []
    pattern_mapping = None  # default, if not found it remains None
    # net data: target petri net
    net_data = get_petri_net_structure(file_path)
    svg_str_plain = graphviz.Source(
        generate_petri_net_dot(net_data, pattern_subnets=[])
    ).pipe(format='svg').decode('utf-8')

    # Pattern-augmented strategy: run detection
    if strategy == "pattern-augmented":
        try:
            '''
            detect result and pattern_mapping result example
            detect_result [['pattern_basic_and_2', 'pattern_free_choice_petri_net_1']]
            pattern_mapping [{'pattern_name': 'pattern_basic_and_2', 'edge_mapping': [{'a': 'Manufacture product', 'b': 'Assemble accessories'}]}, {'pattern_name': 'pattern_free_choice_petri_net_1', 'edge_mapping': [{'f': 'Prepare shipment', 'e': 'Customer pickup', 'c': 'Manufacture product', 'd': 'Assemble accessories', 'a': 'Process standard order', 'b': 'Process customized order'}]}]
            '''
            detect_result, pattern_mapping = pattern_detector.perform_detection(file_path)
            print("detect_result", detect_result)
            print("pattern_mapping", pattern_mapping)
        except Exception as e:
            return jsonify({'error': f'Pattern detection failed: {e}'}), 500

        if pattern_mapping:  # Patterns found
            # find the subnet based on activity list in the pattern_mapping
            filtered_pattern_mapping, _ = filter_patterns_by_overlap(pattern_mapping)
            pattern_subnets = extract_subnet_visual_elements(file_path, filtered_pattern_mapping)

            # pattern_subnets = extract_subnet_visual_elements(file_path, pattern_mapping)
            color_map = assign_colors_to_patterns([p["pattern_name"] for p in pattern_subnets])


            # This part is commented and can be safely detected as I can put the edge mapping within the
            # patter_subnets, so each one item will have one edge mapping or activity mapping
            # mapping_dict = {
            #     m["pattern_name"]: m.get("edge_mapping", [{}])[0] if m.get("edge_mapping") else {}
            #     for m in pattern_mapping
            # }
            # print("pattern")
            # for pattern in pattern_subnets:
            #     pattern["color"] = color_map.get(pattern["pattern_name"], "#888")
            #     pattern["edge_mapping"] = mapping_dict.get(pattern["pattern_name"], {})

            for pattern in pattern_subnets:
                pattern["color"] = color_map.get(pattern["pattern_name"], "#888")

                dot_str = generate_petri_net_dot(net_data, [pattern])
                svg_str = graphviz.Source(dot_str).pipe(format='svg').decode('utf-8')
                # Generate instantiated description using attached mapping, activity mapping has the same content as
                # the edge mapping, but only as a mapping format
                pattern_mapping_for_desc = [{
                    "pattern_name": pattern["pattern_name"],
                    "edge_mapping": [pattern.get("activity_mapping", {})]
                }]


                # todo: retrieve pattern knowledge here
                # this part of description is depependent and only for visualization
                retrieved_knowledge = retrieve_pattern_knowledge_by_name(pattern["pattern_name"])
                descs = prompt_generator.generate_pattern_description_list(pattern_mapping_for_desc)
                # todo: remove the pattern name from the inst_desc
                inst_desc = descs[0] if descs else pattern.get("description", "")

                inst_desc = strip_leading_name_colon(inst_desc, pattern["pattern_name"])

                pattern_svgs.append({
                    # todo: put the retrieved pattern knowledge here
                    "pattern_name": pattern["pattern_name"],
                    "svg": svg_str,
                    "color": pattern["color"],
                    # This description is only Detected pattern '{pattern_name}' covering activities: {',
                    # '.join(activity_names)}
                    "retrieved_knowledge": retrieved_knowledge,
                    "description": pattern.get("description", ""),
                    "instantiated_description": inst_desc,
                    "transitions": pattern.get("transitions", []),
                    "edge_mapping": pattern.get("activity_mapping", {}),
                    # (other fields as needed)
                })

        else:
            # No patterns found, pattern-augmented falls back to zero-shot
            pattern_mapping = None
            strategy = "zero_shot"  # Fallback strategy for prompt


    # --- Prompt Generation (always run exactly once, with correct mapping and strategy) ---
    try:
        # here is the prompt (within the create_prompt method, it creates a pattern knowledge(description) list)
        print("here is pattern mapping",pattern_mapping)
        prompt = prompt_generator.create_prompt(
            file_path,
            strategy,
            pattern_mapping=filtered_pattern_mapping,
            n_shots=1,
            task_description=task_description,
            output_indic=output_indic
        )
    except Exception as e:
        prompt = f"Prompt generation failed: {e}"

    # --- LLM response --- WHY SO SLLLLLOOOOOWWW!!!!! MAN IAM FRUSTRATED
    try:
        llm_response = "LLM-generated Response"
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
    })

@app.route('/translate/start', methods=['POST'])
def translate_start():
    filename = request.form.get('file_name')
    strategy = request.form.get('strategy')

    llm_model = request.form.get('llm_model', 'R1')  # <--- NEW: default to R1

    if not filename:
        return jsonify({'error': 'Missing file name'}), 400
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    task_description = '''
    - Translate the given Petri net into a natural language description.
    - If the Petri net contains a pattern transition, e.g., pattern_1, treat it as an abstraction of a more complex behavior.
    - Use the provided context to expand each pattern transition into its full behavioral description.
    - Ensure the final natural language description faithfully captures both the basic Petri net structure and the 
    semantics of any pattern transitions.
    '''
    output_indic = ""
    pattern_svgs = []
    pattern_mapping = None

    # --- Always compute plain SVG of the full net (immediate)
    net_data = get_petri_net_structure(file_path)
    svg_str_plain = graphviz.Source(
        generate_petri_net_dot(net_data, pattern_subnets=[])
    ).pipe(format='svg').decode('utf-8')
    processed_svg_str = None

    # --- Pattern-augmented detection (still immediate, not background)
    if strategy == "pattern-augmented":
        try:
            detect_result, pattern_mapping = pattern_detector.perform_detection(file_path)
        except Exception as e:
            # We still return SVG + a job that will do the LLM; just no mapping
            pattern_mapping = None

        if pattern_mapping:
            filtered_pattern_mapping, _ = filter_patterns_by_overlap(pattern_mapping)
            pattern_subnets = extract_subnet_visual_elements(file_path, filtered_pattern_mapping)
            # pattern_subnets = extract_subnet_visual_elements(file_path, pattern_mapping)
            color_map = assign_colors_to_patterns([p["pattern_name"] for p in pattern_subnets])


            ori_net, ori_im, ori_fm = pm4py.read_pnml(file_path)
            # I forget what is the structure of saved_subnets
            processed_net, processed_im, processed_fm, replacements, saved_subnets = (
                collapse_patterns_to_indicator_transitions(
                ori_net, ori_im, ori_fm,
                filtered_pattern_mapping,
                find_subnet_fn=find_subnet_based_on_activity_list_extend_silent_transition_v2,
                indicator_key="pattern_indicator",
                in_place=True
            ))


            try:
                processed_net_data = get_petri_net_structure_from_net( processed_net, processed_im, processed_fm)
                processed_dot_str = generate_petri_net_dot(processed_net_data, pattern_subnets=[])
                processed_graph = graphviz.Source(processed_dot_str)
                processed_svg_str = processed_graph.pipe(format='svg').decode('utf-8')
            except Exception as e:
                print(f"PROCESSED ERROR: {e}")  # log to console
                processed_svg_str = None

            for pattern in pattern_subnets:
                pattern["color"] = color_map.get(pattern["pattern_name"], "#888")
                dot_str = generate_petri_net_dot(net_data, [pattern])
                svg_str = graphviz.Source(dot_str).pipe(format='svg').decode('utf-8')

                # make a small mapping wrapper for description generation
                mapping_for_desc = [{
                    "pattern_name": pattern["pattern_name"],
                    "edge_mapping": [pattern.get("activity_mapping", {})]
                }]

                retrieved_knowledge = retrieve_pattern_knowledge_by_name(pattern["pattern_name"])
                descs = prompt_generator.generate_pattern_description_list(mapping_for_desc)
                inst_desc = descs[0] if descs else pattern.get("description", "")
                inst_desc = strip_leading_name_colon(inst_desc, pattern["pattern_name"])

                pattern_svgs.append({
                    "pattern_name": pattern["pattern_name"],
                    "svg": svg_str,
                    "color": pattern["color"],
                    "retrieved_knowledge": retrieved_knowledge,
                    "description": pattern.get("description", ""),
                    "instantiated_description": inst_desc,
                    "transitions": pattern.get("transitions", []),
                    "edge_mapping": pattern.get("activity_mapping", {}),
                })
        else:
            pattern_mapping = None
            strategy = "zero-shot"

    # --- Build prompt (immediate)
    # use filtered_pattern_mapping
    try:
        prompt = prompt_generator.create_prompt(
            file_path,
            strategy,
            # pattern_mapping=pattern_mapping,
            pattern_mapping=filtered_pattern_mapping,

            n_shots=1,
            task_description=task_description,
            output_indic=output_indic,
            processed_net = processed_net,
            processed_im = processed_im,
            processed_fm = processed_fm,
            saved_subnets = saved_subnets
        )
    except Exception as e:
        prompt = f"Prompt generation failed: {e}"

    # --- Start background job for the SLOW LLM call
    job_id = _new_job({"file_name": filename, "llm_model": llm_model})
    t = threading.Thread(target=_run_llm_job, args=(job_id, prompt, llm_model), daemon=True)
    t.start()

    # Return immediately; llm_response is pending
    return jsonify({
        "job_id": job_id,
        "status": "running",
        "petri_net_svg": svg_str_plain,
        "petri_net_svg_processed": processed_svg_str,
        "detected_patterns": pattern_svgs,
        "llm_response": None,         # not ready yet
        "llm_prompt": prompt,         # show the prompt right away if you like
        "file_name": filename,
        "strategy": strategy,
    })

@app.route('/translate/status/<job_id>', methods=['GET'])
def translate_status(job_id):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        return jsonify({"job_id": job_id, "status": "not_found"}), 404

    if job["status"] == "done":
        return jsonify({
            "job_id": job_id,
            "status": "done",
            "llm_response": job["result"].get("llm_response"),
            "llm_prompt": job["result"].get("llm_prompt"),
        })
    elif job["status"] == "error":
        return jsonify({
            "job_id": job_id,
            "status": "error",
            "error": job["result"].get("error", "Unknown error")
        })
    else:
        return jsonify({"job_id": job_id, "status": "running"})


def retrieve_pattern_knowledge_by_name(pattern_name: str) -> str:
    """
    Return pattern_description from database/pattern_dataset.csv
    that matches the given pattern_name (case-insensitive), or '' if not found.
    CSV columns expected: has_pnml,pattern_description,pattern_name
    """
    try:
        df = pd.read_csv(PATTERN_CSV, dtype=str).fillna('')
        # normalize both sides for robust matching
        key = str(pattern_name).strip().casefold()
        mask = df['pattern_name'].astype(str).str.strip().str.casefold() == key
        if mask.any():
            return df.loc[mask, 'pattern_description'].iloc[0]
    except Exception as e:
        print(f"[WARN] get_pattern_knowledge_by_name failed: {e}")
    return 'retrieve fail'
def strip_leading_name_colon(text: str, pattern_name: str) -> str:
    """Remove a leading 'pattern_name:' (case-insensitive) from text."""
    if not isinstance(text, str) or not text:
        return text or ""
    rx = r'^\s*' + re.escape(str(pattern_name)) + r'\s*:\s*'
    return re.sub(rx, '', text, flags=re.IGNORECASE)

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

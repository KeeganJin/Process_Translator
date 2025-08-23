import pm4py
from Utils.post_processing import find_subnet_based_on_activity_list
import hashlib

def assign_colors_to_patterns(pattern_names):
    """
    Assigns a unique hex color string to each pattern name using hashing.
    Ensures consistent and visually distinct colors for each pattern.

    Returns:
        Dict: {pattern_name: color_hex}
    """
    def hash_to_color(name):
        hash_code = hashlib.md5(name.encode()).hexdigest()
        return f"#{hash_code[:6]}"  # Use first 6 hex digits as a color

    return {name: hash_to_color(name) for name in pattern_names}

def get_petri_net_structure(pnml_path):
    """
    Extracts places, transitions, arcs, and markings from a Petri net for visualization.
    Uses pm4py.read_pnml().
    """
    net, im, fm = pm4py.read_pnml(pnml_path)

    places = [{"id": p.name} for p in net.places]
    transitions = [{"id": t.name, "label": t.label} for t in net.transitions]
    arcs = [{"source": arc.source.name, "target": arc.target.name} for arc in net.arcs]
    initial_marking = [p.name for p in im if im[p] > 0]
    final_marking = [p.name for p in fm if fm[p] > 0]

    return {
        "places": places,
        "transitions": transitions,
        "arcs": arcs,
        "initial_marking": initial_marking,
        "final_marking": final_marking
    }



def extract_subnet_visual_elements(pnml_path, pattern_mapping):
    """
    For each detected pattern, extract the matched subnet's transitions (with labels),
    places, and arcs for frontend visualization.

    Returns a list of:
        {
            pattern_name: str,
            transitions: [{id: str, label: str}],
            places: [str],
            arcs: [(str, str)],
            description: str
        }
    """
    net, im, fm = pm4py.read_pnml(pnml_path)
    visual_subnets = []

    for entry in pattern_mapping:
        pattern_name = entry["pattern_name"]
        edge_mappings = entry["edge_mapping"]

        for mapping in edge_mappings:
            activity_names = list(mapping.values())
            # it remains the same with the pattern detector
            subnet = find_subnet_based_on_activity_list(net, activity_names)

            transitions = [{"id": t.name, "label": t.label} for t in subnet.transitions]
            places = [p.name for p in subnet.places]
            arcs = [(a.source.name, a.target.name) for a in subnet.arcs]

            visual_subnets.append({
                "pattern_name": pattern_name,
                "transitions": transitions,
                "places": places,
                "arcs": arcs,
                "description": f"Detected pattern '{pattern_name}' covering activities: {', '.join(activity_names)}"
            })

    return visual_subnets


def generate_petri_net_dot(net_data, pattern_subnets=None):
    """
    Minic layout of pm4py, not quite necessary, as the pattern
    Generates a Graphviz DOT string for a Petri net with optional pattern highlighting,
    and mimics PM4Py's left-to-right layout logic.
    """
    lines = []
    lines.append("digraph G {")
    lines.append("    rankdir=LR;")
    lines.append("    bgcolor=white;")
    lines.append("    compound=true;")
 # Or 'polyline' for less angular

    # Gather place roles
    arc_targets = {arc['target'] for arc in net_data['arcs']}
    arc_sources = {arc['source'] for arc in net_data['arcs']}
    all_places = {p['id'] for p in net_data['places']}

    initial_places = [p for p in net_data['places'] if p['id'] not in arc_targets]
    final_places = [p for p in net_data['places'] if p['id'] not in arc_sources]
    middle_places = [p for p in net_data['places']
                     if p['id'] in arc_targets and p['id'] in arc_sources]

    # Add places: initial → middle → final
    for place in initial_places + middle_places + final_places:
        pid = place['id']
        lines.append(f'    {pid} [label="{pid}", shape=circle];')

    # Add transitions (sorted for determinism)
    for trans in sorted(net_data['transitions'], key=lambda t: t['id']):
        tid = trans['id']
        label = trans.get('label', '')
        is_silent = (label is None) or (label.strip() == "") or (label.lower() in {"tau", "τ", "silent", "invisible"})
        if is_silent:
            lines.append(f'    {tid} [label="τ", shape=box, style=filled, fillcolor=black, fontcolor=white];')
        else:
            label = label.replace('"', '\\"') if label else tid
            lines.append(f'    {tid} [label="{label}", shape=box, style=filled, fillcolor=lightgrey];')

    # Rank enforcement for true left/right alignment
    if initial_places:
        lines.append(f'    {{rank=source; {"; ".join([p["id"] for p in initial_places])};}}')
    if final_places:
        lines.append(f'    {{rank=sink; {"; ".join([p["id"] for p in final_places])};}}')

    # Pattern highlighting (clusters), if any
    if pattern_subnets:
        for idx, pattern in enumerate(pattern_subnets):
            cluster_name = f"cluster_{idx}"
            color = pattern.get("color", "#deff2a")
            label = pattern.get("pattern_name", f"Pattern {idx+1}")
            dashed = 'dashed'
            node_ids = set(pattern.get('places', [])) | set(t['id'] for t in pattern.get('transitions', []))
            lines.append(f'    subgraph {cluster_name} {{')
            lines.append(f'        label="{label}";')
            lines.append(f'        style={dashed};')
            lines.append(f'        color="{color}";')
            for nid in node_ids:
                lines.append(f'        {nid};')
            lines.append('    }')

    # Add arcs, always sorted for consistent layout
    for arc in sorted(net_data['arcs'], key=lambda a: (a['source'], a['target'])):
        lines.append(f'    {arc["source"]} -> {arc["target"]};')

    lines.append("}")
    return "\n".join(lines)


# def generate_petri_net_dot(net_data, pattern_subnets):
#     """
#     Generates a Graphviz DOT string for the Petri net, highlighting each pattern subnet as a cluster.
#     :param net_data: dict with 'places', 'transitions', 'arcs', etc. (from get_petri_net_structure)
#     :param pattern_subnets: list of pattern subnets (from extract_subnet_visual_elements)
#     :return: DOT string
#     """
#     lines = []
#     lines.append('digraph PetriNet {')
#     lines.append('    rankdir=LR;')
#     lines.append('    bgcolor=white;')
#
#     # Define all places and transitions
#     for place in sorted(net_data['places'], key=lambda x: x['id']):
#         pid = place['id']
#         lines.append(f'    {pid} [label="{pid}", shape=circle];')
#
#     for trans in sorted(net_data['transitions'], key=lambda x: x['id']):
#         tid = trans['id']
#         label = trans.get('label', '')
#         is_silent = (label is None) or (label.strip() == "") or (label.lower() in {"tau", "τ", "silent", "invisible"})
#         if is_silent:
#             lines.append(f'    {tid} [label="τ", shape=box, style=filled, fillcolor=black, fontcolor=white];')
#         else:
#             label = label.replace('"', '\\"') if label else tid
#             # Default style; may be overridden by pattern cluster
#             lines.append(f'    {tid} [label="{label}", shape=box, style=filled, fillcolor=lightgrey];')
#
#     # >>>> ADD RANK ENFORCEMENT HERE <<<<
#     incoming = {arc['target'] for arc in net_data['arcs']}
#     outgoing = {arc['source'] for arc in net_data['arcs']}
#     all_places = {p['id'] for p in net_data['places']}
#
#     initial_places = sorted(list(all_places - incoming))
#     final_places = sorted(list(all_places - outgoing))
#
#     if initial_places:
#         lines.append(f'    {{rank=source; {"; ".join(initial_places)};}}')
#     if final_places:
#         lines.append(f'    {{rank=sink; {"; ".join(final_places)};}}')
#
#
#
#     # Define all arcs
#     for arc in sorted(net_data['arcs'], key=lambda x: (x['source'], x['target'])):
#         lines.append(f'    {arc["source"]} -> {arc["target"]};')
#
#     # Add clusters for each pattern
#     for idx, subnet in enumerate(pattern_subnets):
#         cluster_name = f'cluster_{idx}'
#         color = '#888'
#         if 'color' in subnet:
#             color = subnet['color']
#         label = subnet.get('pattern_name', f'Pattern {idx+1}')
#         lines.append(f'    subgraph {cluster_name} {{')
#         lines.append(f'        label = "{label}";')
#         lines.append(f'        style = dashed;')
#         lines.append(f'        color = "{color}";')
#         # Add all nodes in subnet to the cluster
#         for p in subnet['places']:
#             lines.append(f'        {p};')
#         for t in subnet['transitions']:
#             lines.append(f'        {t["id"]};')
#         lines.append('    }')
#
#     lines.append('}')
#     return '\n'.join(lines)

def petri_net_to_cytoscape_json(net_data, pattern_subnets):
    node_patterns = {}  # node_id -> set(pattern_name)
    edge_patterns = {}  # (source, target) -> set(pattern_name)

    for pattern in pattern_subnets:
        pname = pattern["pattern_name"]
        for t in pattern["transitions"]:
            node_patterns.setdefault(t["id"], set()).add(pname)
        for p in pattern["places"]:
            node_patterns.setdefault(p, set()).add(pname)
        for s, t in pattern["arcs"]:
            edge_patterns.setdefault((s, t), set()).add(pname)

    elements = []
    for place in net_data["places"]:
        node_id = place["id"]
        elements.append({
            "data": {
                "id": node_id,
                "label": node_id,
                "type": "place",
                "patterns": list(node_patterns.get(node_id, []))
            }
        })
    for trans in net_data["transitions"]:
        node_id = trans["id"]
        label = trans.get("label") or node_id
        elements.append({
            "data": {
                "id": node_id,
                "label": label,
                "type": "transition",
                "patterns": list(node_patterns.get(node_id, []))
            }
        })
    for arc in net_data["arcs"]:
        src, tgt = arc["source"], arc["target"]
        elements.append({
            "data": {
                "id": f"{src}__{tgt}",
                "source": src,
                "target": tgt,
                "patterns": list(edge_patterns.get((src, tgt), []))
            }
        })

    return {"elements": elements}

from collections import deque, defaultdict
import copy
from typing import List, Dict, Any, Tuple, Callable
from copy import deepcopy
from pathlib import Path
import pm4py
from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.petri_net.utils import petri_utils

from Utils.post_processing import find_subnet_based_on_activity_list_extend_silent_transition_v2

# Types for clarity
FindSubnetFn = Callable[[PetriNet, List[str]], PetriNet]
find_subnet_fn: FindSubnetFn = find_subnet_based_on_activity_list_extend_silent_transition_v2

def create_pattern_substituted_net(pnml_file, pattern_mapping):
    '''
    1. remove overlapping pattern. Done
    2. use transition name in such a format pattern_name_indicator_X
    3. find the subnet within the target petri net and replace it with a pattern indicator transition
    :return:
    return a pattern-substituted net
    '''

    pass

def filter_patterns_by_overlap(
    patterns: List[Dict[str, Any]],
    tie_break: str = "first",
    indicator_key: str = "pattern_indicator",
    annotate: str = "kept",     # "kept" or "all"
    in_place: bool = False      # if True, mutate `patterns`; else return copies
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filters overlapping patterns (share ≥1 mapped activity -> keep the one with most activities).
    Adds a new key `pattern_indicator` to patterns:
      "<pattern_name>_indicator_<n>" where n is that name's ordinal in the original list.

    Args
    ----
    patterns : list of dict (each has "pattern_name" and "edge_mapping")
    tie_break : {"first","last"}  # which index wins on equal activity counts
    indicator_key : str           # the key to add
    annotate : {"kept","all"}     # add indicator to kept only, or to all patterns
    in_place : bool               # mutate `patterns` or return deep copies

    Returns
    -------
    filtered_patterns : list[dict]  # kept patterns (same structure) with `pattern_indicator`
    explanations : list[dict]       # overlap resolution details
    """
    # Build activity sets
    norm = []
    for idx, p in enumerate(patterns):
        name = p.get("pattern_name", f"pattern_{idx}")
        acts = set()
        for m in p.get("edge_mapping", []):
            acts.update(m.values())
        norm.append({"index": idx, "pattern_name": name, "activities": acts, "size": len(acts)})

    n = len(norm)

    # Overlap graph
    adj = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if norm[i]["activities"] & norm[j]["activities"]:
                adj[i].append(j)
                adj[j].append(i)

    # Connected components (BFS)
    visited = [False] * n
    components = []
    for i in range(n):
        if not visited[i]:
            dq, comp = deque([i]), []
            visited[i] = True
            while dq:
                u = dq.popleft()
                comp.append(u)
                for v in adj[u]:
                    if not visited[v]:
                        visited[v] = True
                        dq.append(v)
            components.append(comp)

    # Pick survivor per component
    kept_indices = set()
    explanations = []
    for comp in components:
        if len(comp) == 1:
            kept_indices.add(comp[0])
            continue
        if tie_break == "last":
            best = max(comp, key=lambda k: (norm[k]["size"], norm[k]["index"]))
        else:  # "first"
            best = max(comp, key=lambda k: (norm[k]["size"], -norm[k]["index"]))
        kept_indices.add(best)
        losers = [k for k in comp if k != best]
        explanations.append({
            "component_indices": comp,
            "component_names": [norm[k]["pattern_name"] for k in comp],
            "kept_index": best,
            "kept_name": norm[best]["pattern_name"],
            "kept_size": norm[best]["size"],
            "removed_indices": losers,
            "removed_names": [norm[k]["pattern_name"] for k in losers],
        })

    kept_indices = sorted(kept_indices)

    # Build stable per-name ordinal indicators from ORIGINAL order
    name_counts = defaultdict(int)
    index_to_indicator = {}
    for idx, p in enumerate(patterns):
        name = p.get("pattern_name", f"pattern_{idx}")
        name_counts[name] += 1
        index_to_indicator[idx] = f"{name}_indicator_{name_counts[name]}"

    # Decide mutation vs copy
    base_seq = patterns if in_place else copy.deepcopy(patterns)

    # Annotate requested set
    if annotate == "all":
        for i, _ in enumerate(base_seq):
            base_seq[i][indicator_key] = index_to_indicator[i]
    else:  # "kept"
        for i in kept_indices:
            base_seq[i][indicator_key] = index_to_indicator[i]

    # Return only kept patterns
    filtered_patterns = [base_seq[i] for i in kept_indices]
    return filtered_patterns, explanations
def collapse_patterns_to_indicator_transitions(
    net: PetriNet,
    im: Marking,
    fm: Marking,
    filtered_pattern_mapping: List[Dict[str, Any]],
    find_subnet_fn: FindSubnetFn,
    indicator_key: str = "pattern_indicator",
    in_place: bool = True
) -> Tuple[PetriNet, Marking, Marking, List[Dict[str, Any]], Dict[str, PetriNet]]:
    if not in_place:
        from copy import deepcopy
        net, im, fm = deepcopy(net), deepcopy(im), deepcopy(fm)

    def activities_from_mapping(pat: Dict[str, Any]) -> List[str]:
        seen, out = set(), []
        for m in pat.get("edge_mapping", []):
            for a in m.values():
                if a not in seen:
                    seen.add(a); out.append(a)
        return out

    def idx_places(n: PetriNet):      return {p.name: p for p in n.places}
    def idx_transitions(n: PetriNet): return {t.name: t for t in n.transitions}

    def unique_t_name(n: PetriNet, base: str) -> str:
        names = {t.name for t in n.transitions}
        if base not in names: return base
        i = 2
        while f"{base}__{i}" in names: i += 1
        return f"{base}__{i}"

    def remove_nodes(n: PetriNet, places_to_remove, trans_to_remove):
        # remove arcs touching these nodes
        to_drop = [a for a in list(n.arcs)
                   if (a.source in places_to_remove) or (a.target in places_to_remove) or
                      (a.source in trans_to_remove)  or (a.target in trans_to_remove)]
        for a in to_drop:
            n.arcs.remove(a)
            # also unlink from node arc sets
            if a in a.source.out_arcs: a.source.out_arcs.remove(a)
            if a in a.target.in_arcs:  a.target.in_arcs.remove(a)
        for t in list(trans_to_remove):
            if t in n.transitions:
                n.transitions.remove(t)
        for p in list(places_to_remove):
            if p in n.places:
                n.places.remove(p)

    def boundary_places_in_original_net(orig: PetriNet, subnet: PetriNet):
        """Return (sources, sinks) as lists of Place objects from the ORIGINAL net.

        sources: places that feed transitions in the subnet but are not produced by transitions in the subnet
        sinks:   places that are produced by transitions in the subnet but do not feed transitions in the subnet
        """
        tnames = {t.name for t in subnet.transitions}
        pnames = {p.name for p in subnet.places}
        P = idx_places(orig)

        sources, sinks = [], []

        for pname in pnames:
            p = P.get(pname)
            if p is None:
                continue

            has_to_inside   = any(getattr(a.target, "name", None) in tnames for a in p.out_arcs)
            has_from_inside = any(getattr(a.source, "name", None) in tnames for a in p.in_arcs)

            if has_to_inside and not has_from_inside:
                sources.append(p)
            if has_from_inside and not has_to_inside:
                sinks.append(p)

        # Fallback: if extractor gave a proper WF-subnet with unique src/snk (no internal arcs),
        # detect them from the subnet itself.
        if (not sources or not sinks) and subnet is not None:
            src_candidates = [p for p in subnet.places if len(p.in_arcs) == 0]
            snk_candidates = [p for p in subnet.places if len(p.out_arcs) == 0]
            Pidx = idx_places(orig)
            if not sources and src_candidates:
                for sp in src_candidates:
                    if sp.name in Pidx:
                        sources.append(Pidx[sp.name])
            if not sinks and snk_candidates:
                for sp in snk_candidates:
                    if sp.name in Pidx:
                        sinks.append(Pidx[sp.name])

        return sources, sinks

    # --- PLAN (compute all data before mutating the net) ---
    plans, saved_subnets = [], {}
    for pat in filtered_pattern_mapping:
        indicator = pat[indicator_key]
        acts = activities_from_mapping(pat)
        subnet = find_subnet_fn(net, acts)
        src_places, snk_places = boundary_places_in_original_net(net, subnet)

        plans.append({
            "pattern_name": pat["pattern_name"],
            "indicator": indicator,
            "activities": acts,
            "src_names": [p.name for p in src_places],
            "snk_names": [p.name for p in snk_places],
            "subnet_place_names": {pl.name for pl in subnet.places},
            "subnet_trans_names": {tr.name for tr in subnet.transitions},
            "subnet": subnet
        })
        saved_subnets[indicator] = subnet

    # --- EXECUTE (collapse interiors, wire indicators) ---
    replacements = []
    for plan in plans:
        p_index = idx_places(net)
        t_index = idx_transitions(net)

        # Boundary sets (keep these places)
        keep_boundary = set(plan["src_names"]) | set(plan["snk_names"])

        # Remove all subnet places except boundary; remove all subnet transitions
        places_to_remove = [p_index[nm] for nm in plan["subnet_place_names"]
                            if nm in p_index and nm not in keep_boundary]
        trans_to_remove  = [t_index[nm] for nm in plan["subnet_trans_names"] if nm in t_index]
        removed_places = [pl.name for pl in places_to_remove]
        removed_trans  = [tr.name for tr in trans_to_remove]
        remove_nodes(net, places_to_remove, trans_to_remove)

        # Create indicator transition and connect to ALL boundary places
        # base = f"{plan['pattern_name']}__{plan['indicator']}__collapsed"
        # t_name = unique_t_name(net, base)
        # new_t = PetriNet.Transition(t_name, plan["indicator"])
        # net.transitions.add(new_t)

        base = plan["indicator"]  # e.g., "pattern_indicator_1" (or "<pattern>_indicator_1" with your current generator)
        t_name = unique_t_name(net, base)  # keep unique if a clash occurs
        new_t = PetriNet.Transition(t_name, base)  # label = same human-readable indicator
        net.transitions.add(new_t)

        # Use petri_utils to add arcs (keeps in_arcs/out_arcs consistent)
        for nm in plan["src_names"]:
            if nm in p_index:
                petri_utils.add_arc_from_to(p_index[nm], new_t, net)
        for nm in plan["snk_names"]:
            if nm in p_index:
                petri_utils.add_arc_from_to(new_t, p_index[nm], net)

        replacements.append({
            "pattern_name": plan["pattern_name"],
            "indicator": plan["indicator"],
            "activities": plan["activities"],
            "boundary_places": {"sources": plan["src_names"], "sinks": plan["snk_names"]},
            "added_transition": t_name,
            "removed_places": removed_places,
            "removed_transitions": removed_trans
        })

    return net, im, fm, replacements, saved_subnets

if __name__ == '__main__':
    pattern_mapping = [{'pattern_name': 'pattern_APN_1', 'edge_mapping': [{'e': 'Finalize payment',
                                                                           'c': 'Add Invoice to system',
                                                                           'd': 'Auto-deuction of payment',
                                                                           'b': 'Mail Invoice',
                                                                           'a': 'Generate Invocie'}]},
                       {'pattern_name': 'pattern_basic_and_2',
                        'edge_mapping': [{'a': 'Manufacture product', 'b': 'Assemble accessories'}]},
                       {'pattern_name': 'pattern_basic_xor_1',
                        'edge_mapping': [{'b': 'Prepare shipment', 'a': 'Customer pickup'}]},
                       {'pattern_name': 'pattern_basic_xor_1',
                        'edge_mapping': [{'b': 'Process customized order', 'a': 'Process standard order'}]},
                       {'pattern_name': 'pattern_free_choice_petri_net_1', 'edge_mapping': [
                           {'e': 'Prepare shipment', 'f': 'Customer pickup', 'c': 'Manufacture product',
                            'd': 'Assemble accessories', 'b': 'Process customized order',
                            'a': 'Process standard order'}]}]

    filtered_pattern_mapping, explanations = filter_patterns_by_overlap(pattern_mapping)
    print("pattern mapping", pattern_mapping)
    print("filtered pattern mapping", filtered_pattern_mapping)
    net, im, fm = pm4py.read_pnml(
        r"E:\Backup\Master_Program\Data_Science_Master_Program\2024SS\ProcessTranslator\uploads\ID_4_synthetic_petri_net_free_choice_and_apn.pnml"
    )
    net2, im2, fm2, replacements, saved_subnets = collapse_patterns_to_indicator_transitions(
        net, im, fm,
        filtered_pattern_mapping,
        find_subnet_fn=find_subnet_based_on_activity_list_extend_silent_transition_v2,
        indicator_key="pattern_indicator",
        in_place=True
    )
    pm4py.save_vis_petri_net(net2,im2,fm2,
                             r"E:\Backup\Master_Program\Data_Science_Master_Program\2024SS\ProcessTranslator\uploads"
                             r"\ID_4_processed.png"
)


import pm4py
from pm4py.objects.petri_net.obj import PetriNet
import itertools
import networkx as nx
from itertools import product
from pm4py import check_is_workflow_net

def verify_detected_pattern_in_petri_net(pnml_file, activity_list):
    '''
    check if the subnets extracted are WF-net

    :param pnml_file: pnml file address
    :param activity_list: List of activity names (transitions) to filter
    :return: is_wfnet -> Boolean

    Example use:
    activity_list = ['B', 'C','E']  # List of activities to filter by
    pnml_file = "./petri_net_dataset/target_DFA_concurrency_problem.pnml"
    verify_result = verify_detected_pattern_in_petri_net(pnml_file,activity_list)
    '''

    net, im, fm = pm4py.read_pnml(pnml_file)
    subnet = find_subnet_based_on_activity_list(net, activity_list)
    # pm4py.view_petri_net(subnet)

    is_wfnet = pm4py.check_is_workflow_net(subnet)
    return is_wfnet



def find_subnet_based_on_activity_list_solo(net, activity_list):
    """
    Find the subnet based on the activity name list. only return the net
    without im and fm. this version only find subnet and does not extend to find
    connected silent transitions.


    :param net: Petri net object from pm4py
    :param activity_list: List of activity names (transitions) to filter
    :return: Subnet Petri net
    """
    # Create a new empty Petri net for the subnet
    subnet = PetriNet("Subnet")

    # Mapping from old to new places and transitions
    place_mapping = {}
    transition_mapping = {}

    # Add transitions and their corresponding arcs to the subnet
    for transition in net.transitions:
        if transition.label in activity_list:
            # Add the transition to the subnet
            subnet_transition = PetriNet.Transition(transition.name, transition.label)
            subnet.transitions.add(subnet_transition)
            transition_mapping[transition] = subnet_transition

            # Add the input and output places for the transition
            for arc in transition.in_arcs:
                if arc.source not in place_mapping:
                    # Add the place to the subnet if not already added
                    subnet_place = PetriNet.Place(arc.source.name)
                    subnet.places.add(subnet_place)
                    place_mapping[arc.source] = subnet_place

                # Add the arc from the place to the transition in the subnet
                subnet_arc = PetriNet.Arc(place_mapping[arc.source], subnet_transition)
                subnet.arcs.add(subnet_arc)

            for arc in transition.out_arcs:
                if arc.target not in place_mapping:
                    # Add the place to the subnet if not already added
                    subnet_place = PetriNet.Place(arc.target.name)
                    subnet.places.add(subnet_place)
                    place_mapping[arc.target] = subnet_place

                # Add the arc from the transition to the place in the subnet
                subnet_arc = PetriNet.Arc(subnet_transition, place_mapping[arc.target])
                subnet.arcs.add(subnet_arc)

    return subnet

def find_subnet_based_on_activity_list_extend_silent_transition_deprecated(net, activity_list):
    """
    Find the subnet based on the activity name list.
    Recursively auto-extend the subnet to include silent transitions and their connected arcs/places
    until it finds a new transition with activty name.
    Compared with the deprecated one, it can extend based on silen transtion. use ProM specific.

    :param net: Petri net object from pm4py
    :param activity_list: List of activity names (transitions) to filter
    :return: Subnet Petri net
    """
    # Create a new empty Petri net for the subnet
    subnet = PetriNet("Subnet")

    # Mapping from old to new places and transitions
    place_mapping = {}
    transition_mapping = {}

    # Set to keep track of transitions in the subnet
    processed_transitions = set()

    # Add transitions and their corresponding arcs to the subnet
    def add_transition_to_subnet(transition):
        if transition in processed_transitions:
            return

        # Mark the transition as processed
        processed_transitions.add(transition)

        # Add the transition to the subnet
        subnet_transition = PetriNet.Transition(transition.name, transition.label)
        subnet.transitions.add(subnet_transition)
        transition_mapping[transition] = subnet_transition

        # Add the input and output places for the transition
        for arc in transition.in_arcs:
            if arc.source not in place_mapping:
                # Add the place to the subnet if not already added
                subnet_place = PetriNet.Place(arc.source.name)
                subnet.places.add(subnet_place)
                place_mapping[arc.source] = subnet_place

            # Add the arc from the place to the transition in the subnet
            subnet_arc = PetriNet.Arc(place_mapping[arc.source], subnet_transition)
            subnet.arcs.add(subnet_arc)

        for arc in transition.out_arcs:
            if arc.target not in place_mapping:
                # Add the place to the subnet if not already added
                subnet_place = PetriNet.Place(arc.target.name)
                subnet.places.add(subnet_place)
                place_mapping[arc.target] = subnet_place

            # Add the arc from the transition to the place in the subnet
            subnet_arc = PetriNet.Arc(subnet_transition, place_mapping[arc.target])
            subnet.arcs.add(subnet_arc)

    # Recursive function to extend the subnet
    def extend_subnet_with_silent_transitions():
        extended = False

        for transition in list(net.transitions):
            if transition in processed_transitions:
                continue

            # Check if the transition is silent and connected to the subnet
            if transition.label is None:
                for arc in transition.in_arcs:
                    if arc.source in place_mapping:
                        add_transition_to_subnet(transition)
                        extended = True
                        break
                for arc in transition.out_arcs:
                    if arc.target in place_mapping:
                        add_transition_to_subnet(transition)
                        extended = True
                        break

        return extended

    # Initialize the subnet with transitions from the activity list
    for transition in net.transitions:
        if transition.label in activity_list:
            add_transition_to_subnet(transition)

    # Recursively extend the subnet to include silent transitions
    while extend_subnet_with_silent_transitions():
        pass

    return subnet
def find_subnet_based_on_activity_list_extend_silent_transition(net, activity_list):
    """
    Find the subnet based on the activity name list. Auto-extend the subnet by adding silent transitions
    directly connected to places in the subnet, and return immediately if the subnet becomes a WF-net.


    :param net: Petri net object from pm4py
    :param activity_list: List of activity names (transitions) to filter
    :return: Subnet Petri net
    """
    from pm4py.objects.petri_net.utils import check_soundness

    # Create a new empty Petri net for the subnet
    subnet = PetriNet("Subnet")

    # Mapping from old to new places and transitions
    place_mapping = {}
    transition_mapping = {}

    def add_transition_and_places(transition):
        """Add a transition and its connected places/arcs to the subnet."""
        if transition not in transition_mapping:
            subnet_transition = PetriNet.Transition(transition.name, transition.label)
            subnet.transitions.add(subnet_transition)
            transition_mapping[transition] = subnet_transition

            # Add input places and arcs
            for arc in transition.in_arcs:
                if arc.source not in place_mapping:
                    subnet_place = PetriNet.Place(arc.source.name)
                    subnet.places.add(subnet_place)
                    place_mapping[arc.source] = subnet_place
                subnet_arc = PetriNet.Arc(place_mapping[arc.source], subnet_transition)
                subnet.arcs.add(subnet_arc)

            # Add output places and arcs
            for arc in transition.out_arcs:
                if arc.target not in place_mapping:
                    subnet_place = PetriNet.Place(arc.target.name)
                    subnet.places.add(subnet_place)
                    place_mapping[arc.target] = subnet_place
                subnet_arc = PetriNet.Arc(subnet_transition, place_mapping[arc.target])
                subnet.arcs.add(subnet_arc)

    # Step 1: Add initial transitions and places based on activity list
    for transition in net.transitions:
        if transition.label in activity_list:
            add_transition_and_places(transition)

    # Recursive extension process
    while True:
        silent_transitions_added = False
        silent_transitions_to_add = []

        # Find silent transitions directly connected to places in the current subnet
        for place in place_mapping.keys():
            for arc in list(place.in_arcs) + list(place.out_arcs):
                connected_transition = arc.source if arc.source != place else arc.target
                if isinstance(connected_transition, PetriNet.Transition) and connected_transition.label is None:
                    if connected_transition not in transition_mapping:
                        # Mark the silent transition for addition
                        silent_transitions_to_add.append(connected_transition)

        # Add all marked silent transitions and their connections
        for silent_transition in silent_transitions_to_add:
            add_transition_and_places(silent_transition)
            silent_transitions_added = True

        # Check if the current subnet is a WF-net after adding silent transitions
        if check_is_workflow_net(subnet):
            return subnet

        # Break if no new silent transitions were added
        if not silent_transitions_added:
            return subnet

    # Return the subnet (even if it is not a WF-net)
    return subnet


def find_subnet_based_on_activity_list_extend_silent_transition_v2(net, activity_list):
    """
    This is the version I implemented later to deal with the problem introduced by silent transitions in different
    directions.
    The logic is:
    \item If a silent transition is included by its downstream place, we recursively extend upstream places connected to the silent transition.
    \item If a silent transition is included by its upstream place, we recursively extend downstream places connected to the silent transition.
    \item If both upstream and downstream places meet, we recursively extend in both directions.
    However, it still has its limitation, if two places connect to a silent transition, when extending they both will be included,
    and it still can result in a Net that is not sound, so..
    I still use the v1 for implementation as there is no difference for current implementation,
    In fact, I think combined with silent transtion reduction rules will make it more effective!




    :param net: Petri net object from pm4py
    :param activity_list: List of activity names (transitions) to filter
    :return: Subnet Petri net
    """
    from pm4py.objects.petri_net.utils import check_soundness

    # Create a new empty Petri net for the subnet
    subnet = PetriNet("Subnet")

    # Mapping from old to new places and transitions
    place_mapping = {}
    transition_mapping = {}

    def add_transition_and_places(transition):
        """Well, I think directly add a transition and its connected places/arcs to the subnet."""
        if transition not in transition_mapping:
            subnet_transition = PetriNet.Transition(transition.name, transition.label)
            subnet.transitions.add(subnet_transition)
            transition_mapping[transition] = subnet_transition

            # Add input places and arcs
            for arc in transition.in_arcs:
                # note arc.source is a place object
                if arc.source not in place_mapping:
                    subnet_place = PetriNet.Place(arc.source.name)
                    subnet.places.add(subnet_place)
                    place_mapping[arc.source] = subnet_place
                subnet_arc = PetriNet.Arc(place_mapping[arc.source], subnet_transition)
                subnet.arcs.add(subnet_arc)

            # Add output places and arcs
            for arc in transition.out_arcs:
                if arc.target not in place_mapping:
                    subnet_place = PetriNet.Place(arc.target.name)
                    subnet.places.add(subnet_place)
                    place_mapping[arc.target] = subnet_place
                subnet_arc = PetriNet.Arc(subnet_transition, place_mapping[arc.target])
                subnet.arcs.add(subnet_arc)

    # Step 1: Add initial transitions and places based on activity list
    for transition in net.transitions:
        if transition.label in activity_list:
            add_transition_and_places(transition)

    # Recursive extension process
    while True:
        silent_transitions_added = False
        # Step 1: Find candidate silent transitions adjacent to subnet
        silent_transitions_to_consider = set()

        for place in place_mapping.keys():
            for arc in list(place.in_arcs) + list(place.out_arcs):
                connected_transition = arc.source if arc.source != place else arc.target
                if isinstance(connected_transition, PetriNet.Transition) and connected_transition.label is None:
                    if connected_transition not in transition_mapping:
                        silent_transitions_to_consider.add(connected_transition)

        # Step 2: Decide how to extend each silent transition
        for silent_transition in silent_transitions_to_consider:
            input_places_in_subnet = any(arc.source in place_mapping for arc in silent_transition.in_arcs)
            output_places_in_subnet = any(arc.target in place_mapping for arc in silent_transition.out_arcs)

            if not input_places_in_subnet and not output_places_in_subnet:
                continue

            # Add the silent transition itself
            subnet_transition = PetriNet.Transition(silent_transition.name, silent_transition.label)
            subnet.transitions.add(subnet_transition)
            transition_mapping[silent_transition] = subnet_transition
            silent_transitions_added = True

            if input_places_in_subnet and not output_places_in_subnet:
                # Subnet includes upstream places -> add downstream places
                for arc in silent_transition.out_arcs:
                    if arc.target not in place_mapping:
                        subnet_place = PetriNet.Place(arc.target.name)
                        subnet.places.add(subnet_place)
                        place_mapping[arc.target] = subnet_place
                    subnet.arcs.add(PetriNet.Arc(subnet_transition, place_mapping[arc.target]))
                for arc in silent_transition.in_arcs:
                    if arc.source in place_mapping:
                        subnet.arcs.add(PetriNet.Arc(place_mapping[arc.source], transition_mapping[silent_transition]))


            elif output_places_in_subnet and not input_places_in_subnet:
                # Subnet includes downstream places -> add upstream places
                for arc in silent_transition.in_arcs:
                    if arc.source not in place_mapping:
                        subnet_place = PetriNet.Place(arc.source.name)
                        subnet.places.add(subnet_place)
                        place_mapping[arc.source] = subnet_place
                    subnet.arcs.add(PetriNet.Arc(place_mapping[arc.source], subnet_transition))
                for arc in silent_transition.out_arcs:
                    if arc.target in place_mapping:
                        subnet.arcs.add(PetriNet.Arc(transition_mapping[silent_transition], place_mapping[arc.target]))

            else:
                # Both sides are in subnet -> add all places
                for arc in silent_transition.in_arcs:
                    if arc.source not in place_mapping:
                        subnet_place = PetriNet.Place(arc.source.name)
                        subnet.places.add(subnet_place)
                        place_mapping[arc.source] = subnet_place
                    subnet.arcs.add(PetriNet.Arc(place_mapping[arc.source], subnet_transition))
                for arc in silent_transition.out_arcs:
                    if arc.target not in place_mapping:
                        subnet_place = PetriNet.Place(arc.target.name)
                        subnet.places.add(subnet_place)
                        place_mapping[arc.target] = subnet_place
                    subnet.arcs.add(PetriNet.Arc(subnet_transition, place_mapping[arc.target]))

        # Check if the current subnet is a WF-net after adding silent transitions
        if check_is_workflow_net(subnet):
            return subnet

        # if silent_transitions_add is False, break if no new silent transitions were added
        if not silent_transitions_added:
            return subnet

    # Return the subnet (even if it is not a WF-net)
    return subnet


def find_subnet_based_on_activity_list(net, activity_list):

    subnet = find_subnet_based_on_activity_list_solo(net, activity_list)
    is_wfnet = pm4py.check_is_workflow_net(subnet)
    if is_wfnet:
        return subnet
    else:
        # v2 with directed silent extension
        subnet = find_subnet_based_on_activity_list_extend_silent_transition_v2(net, activity_list)
    return subnet


def find_possible_edge_mappings_between_nodes(target_graph, pattern_graph, origin_node_mapping):
    '''
    This func need work with find_valid_combinations
    Finds all possible mappings of edge labels between parallel edges in two multi-digraph

    Parameters:
    -----------
    target_graph : nx.MultiDiGraph
    pattern_graph : nx.MultiDiGraph

    origin_node_mapping : dict. isomorphism node mapping of target graph node: pattern graph node.

    Returns:
    --------
    edge_label_mappings : dict
    e.g. {(1, 2): [{'a': 'A'}], (2, 3): [{'b': 'B', 'c': 'C'}, {'b': 'C', 'c': 'B'}]}
        A dictionary where each key is a tuple `(u2, v2)`, representing an edge (or pair of nodes)
        in `pattern_graph`. The corresponding value is a list of possible mappings for the edge labels
        between pattern labels and target labels
    '''
    try:

        node_mapping = {value: key for key, value in origin_node_mapping.items()}
        # print(node_mapping)
        # Dictionary to store the possible mappings between edges for each node pair
        edge_label_mappings = {}

        # Iterate over each pair of nodes in G1 and G2
        for u2, v2 in pattern_graph.edges():
            if pattern_graph.has_edge(u2, v2):

                # Get all parallel edges (keyed by labels) between node u1 and v1 in G1
                edges_pattern_graph = list(pattern_graph.get_edge_data(u2, v2).items())
                # Find the corresponding node pair in G2 (since G1 and G2 are isomorphic, it is the same pair u1, v1)
                edges_target_graph = list(target_graph.get_edge_data(node_mapping[u2], node_mapping[v2]).items())
                if len(edges_pattern_graph) != len(edges_target_graph):
                    raise ValueError(f"Number of parallel edges between {u2}-{v2} in G1 and G2 do not match.")
                # Get the labels (keys) for the parallel edges in both graphs
                labels_pattern_graph = [item[1]['label'] for item in edges_pattern_graph]
                labels_target_graph = [item[1]['label'] for item in edges_target_graph]

                # Generate all possible mappings of edge labels from G1 to G2 between two nodes

                mapping_list = [list(zip(labels_pattern_graph, perm)) for perm in
                                itertools.permutations(labels_target_graph)]
                mapping_dict = [dict(sublist) for sublist in mapping_list]

                # Store the mappings for this node pair
                edge_label_mappings[(u2, v2)] = mapping_dict
    except Exception as e:
        raise RuntimeError(f"Error processing edge mappings for node pairs in graphs. Details: {str(e)}")from e
    # print(edge_label_mappings)
    return edge_label_mappings


def merge_dicts(dicts):
    """
    parameters:
    such is a example args({'a': 'A'}, {'b': 'B', 'c': 'C'}, {'b': 'D', 'c': 'C'})
    Merge a list of dictionaries only if there are no conflicting keys or values

    Return: dict. return merged dict if there is no conflict
    """
    merged = {}
    seen_values = set()

    for d in dicts:
        for key, value in d.items():
            if key in merged and merged[key] != value:
                return None  # Key conflict
            if value in seen_values and merged.get(key) != value:
                return None  # Value conflict
            merged[key] = value
            seen_values.add(value)
    # print(merged)
    return merged


def find_valid_combinations(edge_label_mappings):
    '''
    use with merge_dicts to remove conflicting mapping. it is used for each node mapping case.
    parameters:
        edge_label_mappings: extracted from find_possible_edge_mappings_between_nodes
    return: list
        if none, then for this node mapping, there is no valid mapping.
        @param edge_label_mappings:
        @return:
    E.g., {(1, 2): [{'a': 'A'}], (2, 3): [{'b': 'B', 'c': 'C'}, {'b': 'C', 'c': 'B'}],(3, 4): [{'b': 'D'}]}
    output: [] Because b is mapped to both B and D.

    '''
    # Get all combinations from product of dict values
    all_combinations = product(*edge_label_mappings.values())

    valid_combinations = []

    for combination in all_combinations:
        merged_dict = merge_dicts(combination)
        if merged_dict is not None:
            valid_combinations.append(merged_dict)
    return valid_combinations

def find_valid_edge_mapping_for_node_mapping(target_graph, pattern_graph, origin_node_mapping):
    '''
    this func is a wrap of the three func above.
    it is used to find edge mapping based on node mapping. for each node mapping it will be used.
    return:
        :param target_graph:
        :param pattern_graph:
        :param origin_node_mapping:
        :return: valid_combinations_list -> list
        e.g.,
        for a input: {(1, 2): [{'a': 'A'}], (2, 3): [{'b': 'B', 'c': 'C'}, {'b': 'C', 'c': 'B'}]}
        output: [{'a': 'A', 'b': 'C', 'c': 'D'}, {'a': 'A', 'b': 'D', 'c': 'C'}]
        list of dicts, each dict is a valid edge mapping
        if none, then no valid edge mapping
    '''
    edge_label_mappings = find_possible_edge_mappings_between_nodes(target_graph, pattern_graph, origin_node_mapping)
    valid_combinations_list = find_valid_combinations(edge_label_mappings)
    return valid_combinations_list


def filter_unique_dicts_v2(nested_list):
    """
    Filters a nested list of dictionaries to include only those with unique sets of values.

    Args:
        nested_list (list): A nested list containing lists of dictionaries.

    Returns:
        list: A nested list with only unique dictionaries based on their values.

    E.g.,
    input_list = [
    [{"b": "A", "a": "B"}],
    [{"b": "B", "a": "A"}],
    [{"b": "B", "a": "C"}],
    ]
    resut: [[{'b': 'A', 'a': 'B'}], [{'b': 'B', 'a': 'C'}]]
    """
    seen_sets = set()
    unique_nested_list = []

    for sublist in nested_list:
        unique_sublist = []
        for d in sublist:
            # Convert the dictionary's values into a frozenset for uniqueness comparison
            values_set = frozenset(d.values())
            if values_set not in seen_sets:
                seen_sets.add(values_set)
                unique_sublist.append(d)
        if unique_sublist:
            unique_nested_list.append(unique_sublist)

    return unique_nested_list

import pm4py
import networkx as nx
import matplotlib.pyplot as plt
from automata.fa.dfa import DFA
from automata.fa.nfa import NFA
from graphviz import Digraph
import xml.etree.ElementTree as ET
import networkx as nx
import matplotlib.pyplot as plt
import pm4py
from pm4py.objects.petri_net.obj import PetriNet
from Utils import post_processing
from collections import defaultdict


def generate_dfa_digraph_from_petri_net(petri_net_file_path):
    '''
    Flow:

    :param petri_net_file_path:
    :return: networkx.MultiDiGraph
    '''
    reach_graph = generate_reach_graph(petri_net_file_path)
    reach_digraph = convert_transition_system_to_digraph(reach_graph)
    nfa = convert_digraph_to_nfa(reach_digraph)
    dfa = nfa_to_dfa(nfa)
    # dfa.show_diagram()
    dfa_digraph = convert_dfa_to_digraph(dfa)

    return dfa_digraph


def generate_reach_graph(file_path):
    '''
    Create a reachability graph (transition system) for a petri net
    to view the reachability graph
    using pm4py.view_transition_system(reach_graph)
    :param file_path:
    :return:
    '''
    net, im, fm = pm4py.read_pnml(file_path)
    reach_graph = pm4py.convert_to_reachability_graph(net, im, fm)
    return reach_graph


def convert_transition_system_to_digraph(transition_system):
    '''
    to convert transition system object to a Digraph of networkx.

    This function create a multiDigraph which allows parallel loops for the original reachability graph.

    Parameters:

        :param transition_system: transition system is a class in pm4py.transition_system.TransitionSystem
        :return: nx.MultiDiGraph
    '''
    graph = nx.MultiDiGraph()  # Create a directed graph

    # Add states as nodes
    for state in transition_system.states:
        graph.add_node(state.name)

    # Add transitions as edges
    for transition in transition_system.transitions:
        graph.add_edge(transition.from_state.name, transition.to_state.name, label=transition.name)
        # print(transition.name)

    return graph


def convert_dfa_to_digraph(dfa):
    dfa_digraph = nx.MultiDiGraph()

    # Todo: add node type here. it can be use for isomorphism check

    # Add states as nodes
    for state in dfa.states:
        dfa_digraph.add_node(state)

    # Add transitions as edges with labels
    for start_state, transitions in dfa.transitions.items():
        for symbol, end_state in transitions.items():
            dfa_digraph.add_edge(start_state, end_state, label=symbol)

    # # Optional: Set initial state and final states as attributes
    # dfa_digraph.graph['initial_state'] = dfa.initial_state
    # dfa_digraph.graph['final_states'] = dfa.final_states
    return dfa_digraph


def convert_digraph_to_nfa(digraph):
    '''
    Purpose: convert a networkx Digrpah to a NFA object.

    the way of detection of silent transition can be changed from here.

    # Example usage:
    # Assume you have a reachability graph stored in a NetworkX DiGraph
    # Here, we will mock a simple graph as an example:

    # Create a mock reachability graph
    # G = nx.DiGraph()

    # # Add nodes (states)
    # G.add_nodes_from(["S0", "S1", "S2", "S3"])

    # # Add edges (transitions)
    # G.add_edge("S0", "S1", label="(t5, 'None')")  # Epsilon transition
    # G.add_edge("S1", "S2", label="(t6, 't6')")    # Normal transition
    # G.add_edge("S2", "S3", label="(t7, 't7')")    # Another normal transition
    # G.add_edge("S3", "S1", label="(t8, 'None')")  # Another epsilon transition
    G = reach_diGraph
    '''

    states = set(digraph.nodes())
    input_symbols = set()
    transitions = defaultdict(lambda: defaultdict(set))
    initial_state = None
    final_states = set()

    # in_degree is 0
    nodes_with_no_incoming = [node for node, in_degree in digraph.in_degree if in_degree == 0]
    initial_state = list(nodes_with_no_incoming)[0]

    for node in digraph.nodes:
        if digraph.out_degree(node) == 0:
            final_states.add(node)

    for u, v, data in digraph.edges(data=True):
        label = data.get('label', "")

        # label here is a string "(t1, 't1')", here using RE to get the contents
        string_representation = label
        tuple_content = string_representation.strip("()")
        tuple_elements = tuple(elem.strip().strip("'") for elem in tuple_content.split(","))
        label_tup = tuple_elements
        transition_name = label_tup[0]
        input_symbol = label_tup[1]

        # Handling epsilon transitions
        if input_symbol == 'None':
            input_symbol = ''
        else:
            input_symbols.add(input_symbol)

        transitions[u][input_symbol].add(v)

    # Create the NFA
    nfa = NFA(
        states=states,
        input_symbols=input_symbols,
        transitions=dict(transitions),
        initial_state=initial_state,
        final_states=final_states
    )

    return nfa


def nfa_to_dfa(nfa):
    dfa = DFA.from_nfa(nfa)
    return dfa


def dfa_minization(dfa):
    dfa_new = DFA.minify(dfa)
    return dfa_new


## isomorphism iwith edge one-to-one correspodence
def check_multidigraph_behavior(main_graph, pattern_graph):
    """
    Do the isomorphism check, there can be multiple isomorphism cases, so we use a list.

    :param main_graph: networkx.MultiDiGraph -> DFA of the petri net
    :param pattern_graph: networkx.DiGraph -> DFA of Pattern
    :return: True, edge_mappings_list_for_each_iso -> list of mapping(s) from pattern activity to
    target activity. E.g., [{'a': 'A', 'b': 'C', 'c': 'D'}, {'a': 'A', 'b': 'D', 'c': 'C'}]
    """
    # put the main_grpah as the first one, the resutl mapping is
    GM = nx.isomorphism.MultiDiGraphMatcher(main_graph, pattern_graph)
    if not GM.subgraph_is_isomorphic():
        print("not passing DFA subgraph is_isomorphic check!")
        return False, None

    # for iso_mapping in list(GM.subgraph_isomorphisms_iter()):
    isomorphism_list = list(GM.subgraph_isomorphisms_iter())
    print(isomorphism_list)
    print("lenth of isomorphism list", len(isomorphism_list))

    edge_mappings_list_for_each_iso = []
    for origin_node_mapping in isomorphism_list:
        print("node mapping: ",origin_node_mapping)
        # valid_combination list example[{'a': 'A', 'b': 'C', 'c': 'D'}, {'a': 'A', 'b': 'D', 'c': 'C'}] from key is pattern, value is target
        valid_combinations_list = post_processing.find_valid_edge_mapping_for_node_mapping(main_graph, pattern_graph,
                                                                                           origin_node_mapping)
        print("valid_combinations_list ",valid_combinations_list)
        # if two activities is changble with each other, then they two must be concurrent! so save one is enough
        # we only save the unique ones [{'a': 'A', 'b': 'C', 'c': 'D'}] is enough.
        #TODO: filter_unique_dicts here
        unique_combinations_list = filter_unique_dicts(valid_combinations_list)
        print("unique_combinations_list ",unique_combinations_list)
        edge_mappings_list_for_each_iso.append(unique_combinations_list)
        print("---------------------------------------------\n")

    #TODO: filter unique dict here
    print("edge_mappings_list_for_each_iso ",edge_mappings_list_for_each_iso)
    unique_edge_mappings_list_for_each_iso = post_processing.filter_unique_dicts_v2(edge_mappings_list_for_each_iso)
    print("unique_edge_mappings_list_for_each_iso: ",unique_edge_mappings_list_for_each_iso)
    return True, unique_edge_mappings_list_for_each_iso

def filter_unique_dicts(valid_combinations_list):
    """
    Filters a list of dictionaries to include only those with unique sets of values.

    Args:
        dict_list (list): A list of dictionaries.

    Returns:
        list: A list of dictionaries with unique sets of values.
    """
    seen_sets = set()
    unique_dicts = []

    for d in valid_combinations_list:
        # Convert the dictionary's values into a frozenset for uniqueness comparison
        values_set = frozenset(d.values())
        if values_set not in seen_sets:
            seen_sets.add(values_set)
            unique_dicts.append(d)

    return unique_dicts

def check_digraph_behavior(main_graph, subgraph):
    """
    Check if 'subgraph' is a subgraph of 'main_graph' and find the edge label mapping.
    VF2 algorithm cosider structural isomorphism, considers nodes and their connectiivity.
    Parameters:
    subgraph (nx.DiGraph): The smaller graph that may be a subgraph.
    main_graph (nx.DiGraph): The larger graph in which to check for subgraph.

    Returns:
    tuple: (bool, dict or None) - (Is subgraph, Edge label mapping)

    given reachability graph of two petri, check
    1. subgraph isomorphic
    2. edge mapping of two graphs consistency
    """
    # Check if subgraph is a subgraph of main_graph
    GM = nx.isomorphism.DiGraphMatcher(main_graph, subgraph)
    if not GM.subgraph_is_isomorphic():
        return False, None

    # Get the subgraph isomorphism mapping
    origin_node_mapping = GM.mapping

    # Invert the dictionary
    node_mapping = {value: key for key, value in origin_node_mapping.items()}
    print("the converted node mapping")
    # print(node_mapping)
    edge_mapping = {}

    for edge1 in subgraph.edges(data=True):
        # print(edge1)
        u1, v1, data1 = edge1
        label1 = data1.get('label', None)

        # print(u1)
        # print(v1)
        u2 = node_mapping[u1]
        v2 = node_mapping[v1]

        if (u2, v2) in main_graph.edges:
            edge2 = (u2, v2)
            print(f"edge in main graph {edge2}")
        else:
            return False, None

        # print(edge2)
        # print(main_graph.edges[edge2])
        label2 = main_graph.edges[edge2].get('label', None)

        if label1 in edge_mapping:
            if edge_mapping[label1] != label2:
                return False, None
        else:
            edge_mapping[label1] = label2

    return True, edge_mapping


def petri_net_isomorphism_check(pattern, full_net):
    # Convert the Petri nets to networkx DiGraphs
    pattern_graph = nx.DiGraph()
    full_net_graph = nx.DiGraph()

    # Add nodes and edges for the pattern
    for place in pattern['places']:
        pattern_graph.add_node(place, type='place')
    for transition in pattern['transitions']:
        pattern_graph.add_node(transition, type='transition')
    for arc in pattern['arcs']:
        pattern_graph.add_edge(arc[0], arc[1])

    # Add nodes and edges for the full Petri net
    for place in full_net['places']:
        full_net_graph.add_node(place, type='place')
    for transition in full_net['transitions']:
        full_net_graph.add_node(transition, type='transition')
    for arc in full_net['arcs']:
        full_net_graph.add_edge(arc[0], arc[1])

    # Define a node matcher to compare the 'type' attribute
    def node_match(n1, n2):
        return n1['type'] == n2['type']

    # Use the isomorphism function to find subgraph isomorphisms
    matcher = nx.algorithms.isomorphism.DiGraphMatcher(full_net_graph, pattern_graph, node_match=node_match)
    return matcher.subgraph_is_isomorphic()


def parse_pnml(pnml_file):
    '''
    if page is used to avoid the effect of final marking. final marking is also created in a place.
    '''
    tree = ET.parse(pnml_file)
    root = tree.getroot()
    page = root.find(".//page")

    namespace = {'pnml': 'http://www.pnml.org/version-2009/grammar/pnml'}

    places = {}
    transitions = {}
    arcs = []
    if page is not None:
        for place in page.findall('.//{*}place'):
            place_id = place.get('id')
            places[place_id] = {'type': 'place'}

        for transition in page.findall('.//{*}transition'):
            transition_id = transition.get('id')
            transitions[transition_id] = {'type': 'transition'}

        for arc in page.findall('.//{*}arc'):
            arc_id = arc.get('id')
            source = arc.get('source')
            target = arc.get('target')
            arcs.append((source, target))
    else:
        for place in root.findall('.//{*}place'):
            place_id = place.get('id')
            places[place_id] = {'type': 'place'}

        for transition in root.findall('.//{*}transition'):
            transition_id = transition.get('id')
            transitions[transition_id] = {'type': 'transition'}

        for arc in root.findall('.//{*}arc'):
            arc_id = arc.get('id')
            source = arc.get('source')
            target = arc.get('target')
            arcs.append((source, target))
    # considering namespace. but namespace could be applied.
    # for place in root.findall('.//pnml:place', namespace):
    #     place_id = place.get('id')
    #     places[place_id] = {'type': 'place'}
    #
    # for transition in root.findall('.//pnml:transition', namespace):
    #     transition_id = transition.get('id')
    #     transitions[transition_id] = {'type': 'transition'}
    #
    # for arc in root.findall('.//pnml:arc', namespace):
    #     source = arc.get('source')
    #     target = arc.get('target')
    #     arcs.append((source, target))

    return places, transitions, arcs


def convert_pnml_to_digraph(pnml_file):
    # it should work both on pnml file and pnml data.
    places, transitions, arcs = parse_pnml(pnml_file)
    graph = nx.DiGraph()

    for place_id in places:
        graph.add_node(place_id, type='place')
    for transition_id in transitions:
        graph.add_node(transition_id, type='transition')
    for arc in arcs:
        graph.add_edge(arc[0], arc[1])

    return graph


def node_match(n1, n2):
    return n1['type'] == n2['type']


def petri_net_graph_isomorphism_check(full_net_graph, pattern_graph):
    matcher = nx.algorithms.isomorphism.DiGraphMatcher(full_net_graph, pattern_graph,
                                                       node_match=node_match)
    return matcher.subgraph_is_isomorphic()

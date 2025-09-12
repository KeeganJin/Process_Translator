import os
import json

import networkx as nx
import pm4py
from Utils import petri_net_utils
import xml.etree.ElementTree as ET
from Utils.post_processing import verify_detected_pattern_in_petri_net
import Utils.post_processing as post_processing

class PetriNetPattern:
    '''
        init args: pattern_file_path
        load all pnml file as pattern, save important property
        pattern_name: str
        petri_net_params: net, im, fm
        petri_net_digraph: networkx.DiGraph
        reachability_digraph: networkx.MultiDiGraph
        DFA_digraph: networkx.MultiDigraph
    '''


    def __init__(self, pattern_file_path):
        # self.pattern_data = pattern_data
        #
        # self.places = pattern_data.get('places', [])
        # self.transitions = pattern_data.get('transitions', [])
        # self.arcs = pattern_data.get('arcs', [])
        # self.petri_net = None
        self.pattern_name = None
        self.petri_net_params = None
        self.petri_net_digraph = None
        self.reachability_digraph = None
        self.DFA_digraph = None

        self._get_pattern_name(pattern_file_path)
        self._generate_petri_net_params(pattern_file_path)
        self._generate_digraph(pattern_file_path)
        self._generate_reachability_digraph()
        self._generate_DFA_digraph(pattern_file_path)


    # def _parsing_pnml(self):
    #     self.pattern_data = None
    def _get_pattern_name(self, pattern_file_path):
        base_name = os.path.basename(pattern_file_path)
        file_name, file_extension = os.path.splitext(base_name)
        self.pattern_name = file_name


    def _generate_petri_net_params(self, pattern_file_path):
        self.petri_net_params = pm4py.read_pnml(pattern_file_path)


    def _generate_digraph(self, pattern_file_path):
        self.petri_net_digraph = petri_net_utils.convert_pnml_to_digraph(pattern_file_path)


    def _generate_reachability_digraph(self):
        if self.petri_net_params is None:
            print("petri net params can be found!")
        reachability_graph = pm4py.convert_to_reachability_graph(*self.petri_net_params)
        self.reachability_digraph = petri_net_utils.convert_transition_system_to_digraph(reachability_graph)


    def _generate_DFA_digraph(self, pattern_file_path):
        if self.reachability_digraph is None:
            raise ValueError("DiGraph has not been generated. Call _generate_reachability_digraph() first.")
        self.DFA_digraph = petri_net_utils.generate_dfa_digraph_from_petri_net(pattern_file_path)
        # nx.draw(self.DFA_digraph)


class PatternDetector:
    '''
    for all the detection, we only use the pattern names
    Limitations:
        for behavior detector,
        firstly, when there are two parallel edges, I am not sure if it will be mapped incorrectly.
        second, when the pattern is just a loop, this special case need to be considered.
    '''

    def __init__(self, patterns_folder):
        self.petrinet_patterns = self._load_patterns(patterns_folder)

    def _load_patterns(self, patterns_folder):
        '''
        load patterns from pnml file in the secified folder
        Return:
            list of PetriNetPattern Objects.
        '''

        patterns = []
        for filename in os.listdir(patterns_folder):
            if filename.endswith('.pnml'):
                pattern_filepath = os.path.join(patterns_folder, filename)
                patterns.append(PetriNetPattern(pattern_filepath))
        return patterns

        pass

    def perform_detection(self, petri_net_file_path):
        '''
        Detect which pattern from the pattern folder exist in the given petri net.

        :param petri_net_file_path: str
        :return: list
        '''

        detected_patterns = []
        # now we only utilize behavioral detector

        # # Rule-based detection (assuming this method is implemented)
        # rule_detector = self.RuleBasedDetector(petri_net_file_path)
        # rule_detector.perform_detection()
        # rule_based_results = rule_detector.summarize_constructs()
        # # print(rule_based_results)
        # # the rule based detector return a dict type
        # detected_patterns.extend(rule_based_results.items())
        #
        #
        # # Structure-based detection
        # structure_based_results = self.structure_based_detector(petri_net_file_path)
        #
        # detected_patterns.extend(structure_based_results)

        # Behavior-based detection
        # passed_edge_mapping: [[{'a': 'A', 'b': 'B', 'c': 'C'}]]
        behavior_based_results, petri_net_dfa_digraph, pattern_mapping = self.behavior_based_detector(
            petri_net_file_path)
        detected_patterns.append(behavior_based_results)

        # print(petri_net_dfa_digraph.edges(data=True))
        return detected_patterns, pattern_mapping

    def structure_based_detector(self, petri_net_file_path):
        """

        :param petri_net_file_path:
        :return:
        """
        detected_patterns = []
        pattern_mapping = []
        petri_net_digraph = petri_net_utils.convert_pnml_to_digraph(petri_net_file_path)
        for pattern in self.petrinet_patterns:
            print(f"structure_based_detector on pattern: {pattern.pattern_name}")
            pattern_digraph = pattern.petri_net_digraph
            detect_result = petri_net_utils.petri_net_graph_isomorphism_check(petri_net_digraph, pattern_digraph)
            if detect_result == True:
                detected_patterns.append(pattern.pattern_name)
                print(f"pattern: {pattern.pattern_name} - detected")
            else:
                print(f"pattern: {pattern.pattern_name} - not detected")
        return detected_patterns

    def behavior_based_detector(self, petri_net_filepath):
        '''
        perform behavior based detection (DFA graph), including three stages:
            preprocessing: generate_dfa_digraph_from_petri_net
            processing: petri_net_utils.check_multidigraph_behavior
            postprocessing: petri_net_utils.check_multidigraph_behavior, verify_detected_pattern_in_petri_net


        :param petri_net_filepath: str -> the target petri net
        :return: detected_patterns -> list[str], petri_net_dfa_digraph -> nx.MultiDiGraph
        '''
        detected_patterns = []
        pattern_mapping = []

        # preprocessing
        petri_net_dfa_digraph = petri_net_utils.generate_dfa_digraph_from_petri_net(petri_net_filepath)

        for pattern in self.petrinet_patterns:
            print(f"behavior_based_detector on pattern: {pattern.pattern_name}")
            pattern_DFA_digraph = pattern.DFA_digraph
            # in the DFA, activity is labelled on the edge
            # detect result is true, if there exist valid edge mapping from pattern to target
            detect_result, edge_mapping_list = petri_net_utils.check_multidigraph_behavior(petri_net_dfa_digraph,
                                                                                           pattern_DFA_digraph)
            # print("here is the edge mapping",edge_mapping_list)
            # here the edge_mapping can be a list. the edge here the is edge in DFA, which is activity in the
            # petri net. because of the concurrency, [[{'b': 'A', 'a': 'B'}], [{'b': 'B', 'a': 'A'}]], such situation can happen
            # in this case, we only randomly save one.
            print(f"edge_mapping_list: {edge_mapping_list}")

            #TODO: the edge_mapping_list is also need to be returned. For prompt generation.
            #TODO: [[{'b': 'A', 'a': 'B'}], [{'b': 'B', 'a': 'A'}]], for this case, we only need one. it is done within check multigraph

            if detect_result == True:

                # post-processing
                # each edge mapping corresponds to one ismorphism situation, and it can has more than
                # one mapping situation. e.g., [{'a': 'A', 'b': 'C', 'c': 'D'}, {'a': 'A', 'b': 'D', 'c': 'C'}]
                # above is an edge_mapping_candidate,
                for edge_mapping_candidates in edge_mapping_list:

                    # unique activity names in the target petri net.
                    unique_activity_list = list(set(value for d in edge_mapping_candidates for value in d.values()))
                    print("unique acitiviy name is the original petri net: ", unique_activity_list)

                    #TODO: we have unique activty list, check this and
                    subnet_is_WF_net = verify_detected_pattern_in_petri_net(petri_net_filepath, unique_activity_list)

                    # for the post-processing-> checking if subnet is WF-net, it is necessary for each node isomorphsim condistion,
                    # not necessary for each edge_mapping_candidate
                    if subnet_is_WF_net:
                        print("subnet is WF-net, and detected")
                        detected_patterns.append(pattern.pattern_name)
                        print(f"pattern: {pattern.pattern_name} - detected")
                        mapping_entry = {
                            'pattern_name': pattern.pattern_name,
                            'edge_mapping': edge_mapping_candidates
                        }
                        pattern_mapping.append(mapping_entry)
                    else:
                        print("subnet is not WF-net")
            else:
                print(f"pattern: {pattern.pattern_name} - not detected")
        print("pattern mapping: ", pattern_mapping)
        return detected_patterns, petri_net_dfa_digraph, pattern_mapping

    class RuleBasedDetector:
        '''
        This detector apply a logical condition to determine what constructs are included in it

        it detects three kinds of constructs:
            *

        '''

        def __init__(self, pnml_file):
            self.pnml_file = pnml_file
            self.tree = ET.parse(pnml_file)
            self.root = self.tree.getroot()
            self.ns = {'pnml': 'http://www.pnml.org/version-2009/grammar/pnml'}
            # dict
            self.places = {}
            self.transitions = {}

            # list of tuples
            self.arcs = []

            # detected constructs
            self.xor_split_constructs = []
            self.xor_join_constructs = []
            self.and_split_constructs = []
            self.and_join_constructs = []
            self.loop_constructs = []
            self.constructs_summary = {}

            self.graph = None

            self._parse_pnml()

        def perform_detection(self):
            self.detect_xor_constructs()
            self.detect_and_constructs()
            self.create_graph()
            self.detect_loops()

        def _parse_pnml(self):

            print("start parsing")
            '''to avoid the effect of final marking, find the page first'''

            page = self.root.find(".//page")
            # Find places, transitions, and arcs ignoring namespaces
            if page is not None:
                for place in page.findall('.//{*}place'):
                    place_id = place.get('id')
                    self.places[place_id] = place

                for transition in page.findall('.//{*}transition'):
                    transition_id = transition.get('id')
                    self.transitions[transition_id] = transition

                for arc in page.findall('.//{*}arc'):
                    source = arc.get('source')
                    target = arc.get('target')
                    self.arcs.append((source, target))
            else:
                for place in self.root.findall('.//{*}place'):
                    place_id = place.get('id')
                    self.places[place_id] = place

                for transition in self.root.findall('.//{*}transition'):
                    transition_id = transition.get('id')
                    self.transitions[transition_id] = transition

                for arc in self.root.findall('.//{*}arc'):
                    source = arc.get('source')
                    target = arc.get('target')
                    self.arcs.append((source, target))

        def detect_xor_constructs(self):
            print('detecting xor split and join constructs')
            for place_id, place_content in self.places.items():

                # the transition id
                incoming_transition = [arc[0] for arc in self.arcs if arc[1] == place_id]
                outgoing_transition = [arc[1] for arc in self.arcs if arc[0] == place_id]

                if len(incoming_transition) > 1:
                    # xor join
                    self.xor_join_constructs.append((place_id, incoming_transition))

                if len(outgoing_transition) > 1:
                    # xor split
                    self.xor_split_constructs.append((place_id, outgoing_transition))

            return self.xor_split_constructs, self.xor_join_constructs

        def detect_and_constructs(self):

            print('detecting and constructs')
            for transition_id, transition_content in self.transitions.items():
                incoming_place = [arc[0] for arc in self.arcs if arc[1] == transition_id]
                outgoing_place = [arc[1] for arc in self.arcs if arc[0] == transition_id]

                if len(outgoing_place) > 1:
                    # and join
                    self.and_join_constructs.append((transition_id, incoming_place))
                    # and split
                    self.and_split_constructs.append((transition_id, outgoing_place))

            return self.and_split_constructs, self.and_join_constructs

        def add_to_dict(dictionary, key, value):
            if key not in dictionary:
                dictionary[key] = []
            dictionary[key].append(value)

        # def summarize_constructs(self):
        #     if self.xor_split_constructs:
        #         print('xor split exist: ')
        #         self.constructs_summary['xor_split']=[]
        #         for place_id, target_transition_ids in self.xor_split_constructs:
        #             target_names = [extract_name(self.transitions[target_id]) for target_id in target_transition_ids]
        #             sum = f'''XOR split construct found at Place {self.places[place_id].get('id')} with outgoing arcs to: {target_names}'''
        #             self.constructs_summary['xor_split'].append(sum)
        #     return self.constructs_summary

        def summarize_constructs(self):
            """
            Summarizes all detected constructs and updates the constructs_summary dictionary.
            """
            if self.xor_split_constructs:
                self.constructs_summary['xor_split'] = [
                    f"XOR split at place {place_id} with outgoing to {target_ids}"
                    for place_id, target_ids in self.xor_split_constructs
                ]

            if self.xor_join_constructs:
                self.constructs_summary['xor_join'] = [
                    f"XOR join at place {place_id} with incoming from {source_ids}"
                    for place_id, source_ids in self.xor_join_constructs
                ]

            if self.and_split_constructs:
                self.constructs_summary['and_split'] = [
                    f"AND split at transition {transition_id} with outgoing to {target_ids}"
                    for transition_id, target_ids in self.and_split_constructs
                ]

            if self.and_join_constructs:
                self.constructs_summary['and_join'] = [
                    f"AND join at transition {transition_id} with incoming from {source_ids}"
                    for transition_id, source_ids in self.and_join_constructs
                ]

            if self.loop_constructs:
                self.constructs_summary['loops'] = [
                    f"Loop detected involving nodes: {cycle}"
                    for cycle in self.loop_constructs
                ]

            return self.constructs_summary

        def create_graph(self):
            self.graph = nx.DiGraph()
            self.graph.add_nodes_from(self.places.keys(), type='place')
            self.graph.add_nodes_from(self.transitions.keys(), type='transition')
            self.graph.add_edges_from(self.arcs)

        def detect_loops(self):
            if self.graph is None:
                raise ValueError("Graph not created. Call create_graph() first.")
            cycles = list(nx.simple_cycles(self.graph))
            self.loop_constructs.append(cycles)
            return cycles

        def visualize_petri_net(self):
            print("Visualizing")
            pn, im, fm = pm4py.read_pnml(self.pnml_file)
            pm4py.view_petri_net(pn, im, fm)

import pandas as pd
import pm4py


class PromptGenerator:
    def __init__(self, patterns_file, examples_file):
        """
        Initialize the PromptGenerator with file paths for patterns and examples.

        :param patterns_file: Path to the CSV file containing pattern descriptions.
        :param examples_file: Path to the CSV file containing examples.
        """
        self.patterns_file = patterns_file
        self.examples_file = examples_file

        # Load data into pandas DataFrames
        self.patterns_df = pd.read_csv(self.patterns_file)
        self.examples_df = pd.read_csv(self.examples_file)

    task_description = "translation"
    output_indic = "none"

    def generate_abstract_model_description(cls, process_model_path):
        net, im, fm = pm4py.read_pnml(process_model_path)
        model_abstraction = pm4py.llm.abstract_petri_net(net, im, fm)
        return model_abstraction

    def create_prompt(self, process_model_path,
                      strategy, pattern_mapping=None, n_shots=1,
                      task_description=task_description, output_indic=output_indic):
        """
        Create a prompt based on the specified strategy.

        :param pattern_name: Name of the pattern to use.
        :param strategy: The strategy for the prompt ('zero-shot', 'one-shot', 'few-shot', or 'customized_one').
        :param pattern_mapping: Mapping for the `customized_one` strategy (if applicable).
        :param n_shots: Number of examples to include for few-shot (default is 1).
        :return: A generated prompt string.
        """
        petrinet_abstraction = self.generate_abstract_model_description(process_model_path)

        if strategy == "zero-shot":
            # Zero-shot: Use the task description directly
            return (f"# Task: {task_description}\n"
                    f"# Input: {petrinet_abstraction}\n"
                    f"# Output:{output_indic}\n")

        elif strategy == "one-shot" or strategy == "few-shot":
            try:
                example = self.examples_df.sample(1).iloc[0]  # Randomly pick one example
                example_input = example['petri_net']
                example_output = example['description']
                return (
                    f"# Task: {task_description}\n\n"
                    f"# Example:\nInput: {example_input}\nOutput: {example_output}\n\n"
                    f"Now, respond to the following:\n"
                    f"# Input: {petrinet_abstraction}\n"
                    f"# Output: {output_indic}\n")
            except Exception as e:
                return f"Error reading examples: {e}"

        elif strategy == "pattern-augmented":

            '''
            pattern_mapping = 
            [{'pattern_name': 'example_pattern_1_with_and_split',  'edge_mapping': [{'b': 'B', 'a': 'A'}]},
             {'pattern_name': 'example_pattern_1_with_and_split','edge_mapping': [{'b': 'D', 'a': 'C'}]}]
            '''

            if not pattern_mapping:
                raise ValueError("Pattern mapping is required for pattern_augmented strategy.")

            context = ("The input petri net includes the following pattern sub-behaviors: ")
            pattern_description_list = self.generate_pattern_description_list(pattern_mapping)

            return (
                f"# Task: {task_description}\n"
                f"# Context:{context}"
                f"{pattern_description_list}\n"
                f"# Input: {petrinet_abstraction}\n"
                f"# Output: {output_indic}\n")

        else:
            raise ValueError(
                f"Invalid strategy '{strategy}'. Valid strategies are 'zero-shot', 'one-shot', 'few-shot', and 'customized_one'.")

    def generate_pattern_description_list(self, pattern_mapping):
        '''
            pattern_mapping =
            [{'pattern_name': 'example_pattern_1_with_and_split',  'edge_mapping': [{'b': 'B', 'a': 'A'}]},
             {'pattern_name': 'example_pattern_1_with_and_split','edge_mapping': [{'b': 'D', 'a': 'C'}]}]
        '''
        pattern_description_list = []
        for pattern in pattern_mapping:
            pattern_name = pattern['pattern_name']
            edge_mapping = pattern['edge_mapping']
            print("--------------------------\n")

            # description_mapping = {row['pattern_name']: row['description'] for row in table}
            description_mapping = self.patterns_df.set_index('pattern_name')['pattern_description'].to_dict()
            # Fetch the corresponding description
            description_template = description_mapping.get(pattern_name, "")
            if not description_template:
                description_template = "Description not found"
                continue
            print("description template: ", description_template)
            print("num of edge mapping set: ", len(edge_mapping))
            # Replace placeholders in the description with real activity names
            for mapping in edge_mapping:
                description = description_template
                for abstract_name, real_name in mapping.items():
                    placeholder = f"{{{abstract_name}}}"
                    description = description.replace(placeholder, real_name)

                description = pattern_name + ': ' + description
                pattern_description_list.append(description)
        return pattern_description_list

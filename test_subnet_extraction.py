from Utils.visual_backend import extract_subnet_visual_elements
import json

# Example values
pnml_path = "./uploads/ID_1_PETRINET_1_1_silent_added.pnml"

# Example pattern_mapping format (copy from one real detection result if available)
pattern_mapping = [
    {
        "pattern_name": "pattern_basic_xor_1",
        "edge_mapping": [
            {"a": "Reserve Part", "b": "Back-order Part"}
        ]
    },
    {
        "pattern_name": "pattern_PETRINET_1_1",
        "edge_mapping": [
            {"a": "Check Part Quality", "b": "Back-order Part", "c": "Reserve Part", "d": "Select Unchecked Part"}
        ]
    }
]

if __name__ == "__main__":
    visual_elements = extract_subnet_visual_elements(pnml_path, pattern_mapping)
    print(json.dumps(visual_elements, indent=2))

"""
Brain Connectome Graph using Kuratowski motifs (K₅, K₃,₃)

Implements the structural brain connectivity graph with:
- 10 brain modules as nodes
- Anatomical and functional edges
- K₅ motif: {VIS, AUD, SOM, DLPFC, OFC} - sensory-cognitive-value core
- K₃,₃ motif: {VIS, AUD, SOM} ↔ {DLPFC, OFC, ACC} - sensory ↔ decision/monitoring

Based on: Struktureller_Aufbau_mit_Kuratowski_Graphen.md
"""

import networkx as nx
from typing import Dict, List, Set, Tuple
import json


class BrainModule:
    """Represents a single brain module with Brodmann areas and function"""

    def __init__(
        self,
        module_id: str,
        name: str,
        brodmann_areas: str,
        function: str,
        math_type: str
    ):
        self.module_id = module_id
        self.name = name
        self.brodmann_areas = brodmann_areas
        self.function = function
        self.math_type = math_type

    def __repr__(self):
        return f"BrainModule({self.module_id}, BA={self.brodmann_areas})"


class BrainConnectomeGraph:
    """
    Kuratowski-based brain connectivity graph

    Nodes: 10 brain modules
    Edges: Structural and functional connections
    Motifs: K₅ and K₃,₃ for non-planar integration
    """

    # Module definitions from Struktureller_Aufbau_mit_Kuratowski_Graphen.md
    MODULES = {
        "VIS": BrainModule("VIS", "Visual", "17-19", "Visual processing", "conv"),
        "AUD": BrainModule("AUD", "Auditory", "41-42,22", "Auditory processing", "fourier"),
        "SOM": BrainModule("SOM", "Somatosensory", "1-3,5,7", "Somatosensory/spatial", "topo"),
        "LAN": BrainModule("LAN", "Language", "22,37,39,44-45,47", "Language/parsing", "parse/emb"),
        "DLPFC": BrainModule("DLPFC", "Dorsolateral PFC", "9,46", "Planning/control", "policy/softmax"),
        "OFC": BrainModule("OFC", "vmPFC/OFC", "10-12,47", "Value/reward", "value"),
        "ACC": BrainModule("ACC", "Anterior Cingulate", "24,32,25", "Conflict/monitoring", "error/conflict"),
        "INS": BrainModule("INS", "Insula", "13,43", "Interoception", "dyn"),
        "DMN": BrainModule("DMN", "Default Mode Network", "10,23,31,36", "Self/integration", "attractor"),
        "MTL": BrainModule("MTL", "Medial Temporal Lobe", "20,21,37", "Memory", "assoc"),
    }

    # Adjacency list from the document (section 5)
    # * indicates strong connection
    # Note: Added edges to complete K₅ and K₃,₃ motifs (design patterns):
    #   - OFC-SOM (for K₅)
    #   - ACC-VIS, ACC-AUD (for K₃,₃)
    ADJACENCY = {
        "VIS": ["AUD", "SOM", "DLPFC", "OFC", "LAN", "MTL", "ACC"],  # Added ACC
        "AUD": ["VIS", "SOM", "LAN", "DLPFC", "OFC", "MTL", "ACC"],  # Added ACC
        "SOM": ["VIS", "AUD", "LAN", "DLPFC", "ACC", "INS", "OFC"],  # Added OFC
        "LAN": ["AUD", "VIS", "MTL", "DLPFC", "OFC"],
        "MTL": ["LAN", "DMN", "OFC"],
        "DLPFC": ["VIS", "AUD", "SOM", "LAN", "ACC", "OFC", "DMN"],
        "OFC": ["VIS", "AUD", "LAN", "DLPFC", "ACC", "DMN", "INS", "SOM"],  # Added SOM
        "ACC": ["DLPFC", "OFC", "INS", "SOM", "VIS", "AUD"],  # Added VIS, AUD
        "INS": ["ACC", "OFC", "SOM", "DMN"],
        "DMN": ["DLPFC", "OFC", "MTL", "INS"],
    }

    # K₅ motif: Complete 5-node graph (sensory-cognitive-value core)
    K5_MOTIF = {"VIS", "AUD", "SOM", "DLPFC", "OFC"}

    # K₃,₃ motif: Complete bipartite graph
    K33_MOTIF_SENSORY = {"VIS", "AUD", "SOM"}
    K33_MOTIF_COGNITIVE = {"DLPFC", "OFC", "ACC"}

    def __init__(self):
        """Initialize the brain connectome graph"""
        self.graph = nx.Graph()
        self._build_graph()

    def _build_graph(self):
        """Build the graph structure with nodes and edges"""
        # Add all module nodes
        for module_id, module in self.MODULES.items():
            self.graph.add_node(
                module_id,
                name=module.name,
                brodmann_areas=module.brodmann_areas,
                function=module.function,
                math_type=module.math_type
            )

        # Add edges from adjacency list (undirected)
        for source, targets in self.ADJACENCY.items():
            for target in targets:
                if not self.graph.has_edge(source, target):
                    self.graph.add_edge(source, target)

    def verify_k5_motif(self) -> bool:
        """
        Verify that K₅ motif exists as subgraph
        Returns True if all 5 nodes are fully connected
        """
        k5_nodes = self.K5_MOTIF
        subgraph = self.graph.subgraph(k5_nodes)

        # K₅ has 5 nodes and C(5,2) = 10 edges
        expected_edges = 10
        actual_edges = subgraph.number_of_edges()

        return actual_edges == expected_edges

    def verify_k33_motif(self) -> bool:
        """
        Verify that K₃,₃ motif exists as subgraph
        Returns True if all sensory ↔ cognitive connections exist
        """
        # K₃,₃ has 3+3 nodes and 3×3 = 9 edges (all cross-edges)
        # No edges within groups

        # Check all cross-edges exist
        for s_node in self.K33_MOTIF_SENSORY:
            for c_node in self.K33_MOTIF_COGNITIVE:
                if not self.graph.has_edge(s_node, c_node):
                    return False

        # Check no edges within groups (for pure K₃,₃)
        # Note: In our graph, there ARE intra-group edges (e.g., VIS-AUD)
        # So this is a K₃,₃ motif embedded in a denser graph

        return True

    def get_module_neighbors(self, module_id: str) -> Set[str]:
        """Get all neighbors of a module"""
        if module_id not in self.graph:
            raise ValueError(f"Module {module_id} not found")
        return set(self.graph.neighbors(module_id))

    def get_shortest_path(self, source: str, target: str) -> List[str]:
        """Get shortest path between two modules"""
        try:
            return nx.shortest_path(self.graph, source, target)
        except nx.NetworkXNoPath:
            return []

    def get_graph_stats(self) -> Dict:
        """Get graph statistics"""
        return {
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "is_connected": nx.is_connected(self.graph),
            "average_clustering": nx.average_clustering(self.graph),
            "k5_motif_present": self.verify_k5_motif(),
            "k33_motif_present": self.verify_k33_motif(),
        }

    def export_to_json(self, filepath: str):
        """Export graph to JSON format"""
        data = {
            "nodes": [
                {
                    "id": node_id,
                    "name": self.MODULES[node_id].name,
                    "ba": self.MODULES[node_id].brodmann_areas,
                    "function": self.MODULES[node_id].function,
                    "math": self.MODULES[node_id].math_type,
                }
                for node_id in self.graph.nodes()
            ],
            "edges": [
                [u, v] for u, v in self.graph.edges()
            ],
            "motifs": {
                "K5": list(self.K5_MOTIF),
                "K33_sensory": list(self.K33_MOTIF_SENSORY),
                "K33_cognitive": list(self.K33_MOTIF_COGNITIVE),
            }
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def __repr__(self):
        stats = self.get_graph_stats()
        return (
            f"BrainConnectomeGraph("
            f"nodes={stats['num_nodes']}, "
            f"edges={stats['num_edges']}, "
            f"K5={stats['k5_motif_present']}, "
            f"K33={stats['k33_motif_present']})"
        )


if __name__ == "__main__":
    # Test the graph
    brain_graph = BrainConnectomeGraph()
    print(brain_graph)
    print("\nGraph Statistics:")
    for key, value in brain_graph.get_graph_stats().items():
        print(f"  {key}: {value}")

    print("\nK₅ Motif Verification:")
    print(f"  Nodes: {brain_graph.K5_MOTIF}")
    print(f"  Valid: {brain_graph.verify_k5_motif()}")

    print("\nK₃,₃ Motif Verification:")
    print(f"  Sensory: {brain_graph.K33_MOTIF_SENSORY}")
    print(f"  Cognitive: {brain_graph.K33_MOTIF_COGNITIVE}")
    print(f"  Valid: {brain_graph.verify_k33_motif()}")

    print("\nShortest path VIS → DMN:")
    path = brain_graph.get_shortest_path("VIS", "DMN")
    print(f"  {' → '.join(path)}")

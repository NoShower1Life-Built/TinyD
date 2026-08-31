from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

NODE_TYPES = frozenset({"tenant", "actor", "repository", "commit", "source_artifact", "build",
                        "container", "deployment", "workflow", "execution", "event", "input",
                        "output", "evidence", "policy", "attestation"})
RELATIONSHIPS = frozenset({"DERIVED_FROM", "BUILT_FROM", "DEPLOYED_AS", "AUTHORIZED_BY",
                           "EXECUTED_BY", "PRODUCED", "VERIFIED_BY", "ATTESTED_BY",
                           "BELONGS_TO", "SUPERSEDES"})


@dataclass(frozen=True)
class ProvenanceNode:
    node_id: str
    node_type: str
    digest: str | None = None


@dataclass(frozen=True)
class ProvenanceEdge:
    source_id: str
    relationship: str
    target_id: str


class CanonicalProvenanceGraph:
    def __init__(self) -> None:
        self.nodes: Dict[str, ProvenanceNode] = {}
        self.edges: List[ProvenanceEdge] = []

    def add_node(self, node: ProvenanceNode) -> None:
        if node.node_type not in NODE_TYPES:
            raise ValueError(f"unsupported node type: {node.node_type}")
        self.nodes[node.node_id] = node

    def add_edge(self, edge: ProvenanceEdge) -> None:
        if edge.relationship not in RELATIONSHIPS:
            raise ValueError(f"unsupported relationship: {edge.relationship}")
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise KeyError("provenance edge references unknown node")
        self.edges.append(edge)

    def resolve(self, subject_id: str) -> dict:
        if subject_id not in self.nodes:
            raise KeyError(subject_id)
        return {"subject": self.nodes[subject_id],
                "outgoing": tuple(e for e in self.edges if e.source_id == subject_id),
                "incoming": tuple(e for e in self.edges if e.target_id == subject_id)}

import base64, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.extend([str(ROOT / "packages/event-store/src"), str(ROOT / "packages/assurance/src")])
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from crypto import DigestArtifactAttestor, TrustKey, TrustRoot
from events import EventEnvelope
from ledger import InMemoryEvidenceLedger
from provenance import CanonicalProvenanceGraph, ProvenanceEdge, ProvenanceNode
from verification import DeterministicReplayVerifier, IndependentEvidenceVerifier

def make_event(event_id="e1", parent=None, idem=None, payload=None, policy_version="v1", policy_digest="p" * 64):
    return EventEnvelope(event_id=event_id,event_type="execution.completed",tenant_id="tenant-a",execution_id="exec-1",actor="system",capability="execute",operation="run",payload=payload or {"result":"ok"},parent_event_id=parent,idempotency_key=idem or event_id,policy_version=policy_version,policy_digest=policy_digest).with_integrity()

def test_event_integrity_and_secret_rejection():
    event=make_event(); assert event.verify_integrity()
    for key in ("token", "access_token", "client-secret", "Authorization", "private_key", "session_id"):
        with pytest.raises(ValueError, match="secret-bearing"):
            InMemoryEvidenceLedger().append(make_event(payload={key:"must-never-enter-evidence"}))

def test_ledger_is_idempotent_and_hash_chained():
    ledger=InMemoryEvidenceLedger(); event=make_event(idem="same")
    assert ledger.append(event)==ledger.append(event)
    with pytest.raises(ValueError, match="different event"): ledger.append(make_event(event_id="e2",idem="same",payload={"result":"different"}))
    assert ledger.verify_chain("tenant-a")

def test_independent_verification_and_replay():
    first=make_event("e1"); second=make_event("e2",parent="e1")
    assert IndependentEvidenceVerifier().verify(first).result=="VERIFIED"
    assert DeterministicReplayVerifier().replay("exec-1",[first,second]).result=="VERIFIED"
    assert DeterministicReplayVerifier().replay("exec-1",[make_event("e1",parent="wrong"),second]).result=="FAILED"

def test_provenance_is_canonical():
    graph=CanonicalProvenanceGraph(); graph.add_node(ProvenanceNode("build-1","build","a"*64)); graph.add_node(ProvenanceNode("artifact-1","source_artifact","b"*64)); graph.add_edge(ProvenanceEdge("artifact-1","BUILT_FROM","build-1")); assert graph.resolve("artifact-1")["outgoing"][0].relationship=="BUILT_FROM"

def test_real_ed25519_attestation_and_trust_root():
    private=Ed25519PrivateKey.generate(); public=private.public_key().public_bytes_raw(); root=TrustRoot((TrustKey("builder","v1","Ed25519",base64.b64encode(public).decode()),)); artifact="a"*64; attestation=DigestArtifactAttestor("builder","v1",private).attest(artifact); assert root.verify("builder","v1",f"tinyd-artifact-v1:{artifact}".encode(),attestation.signature_b64)

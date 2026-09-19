"""Provider-neutral contracts and deterministic runtime for SFC."""

from importlib.metadata import PackageNotFoundError, version as _installed_version

#: Read from package metadata so pyproject.toml is the only place a version is
#: written. Every surface that reports one - the CLI, the MCP server, an HTTP
#: response - reads this, so they cannot drift apart.
try:
    __version__ = _installed_version("systems-for-construction")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"

from .assurance import AssuranceError, MeasurementPolicy, evaluate_obligation, observe_measurement, validate_determination, validate_obligation
from .vocabulary import Term, Vocabulary, default_vocabulary
from .quantities import (
    Conversion,
    Dimension,
    IncompatibleDimensionError,
    MeasurementError,
    Quantity,
    UnknownUnitError,
    UnresolvedUnitError,
    resolve_unit,
)
from .authority import EvidenceAuthority, EvidenceAdmissionError
from .models import (
    CLOSING_STATUSES,
    Applicability,
    Counterexample,
    Determination,
    DeterminationReason,
    DeterminationStatus,
    EmptyPopulationPolicy,
    Evidence,
    Obligation,
    PopulationSpec,
    ProjectWorld,
    Requirement,
    Run,
    Unresolved,
    WorldElement,
)
from .proofs import Proof
from .conformance import ConformanceError, determination_violations, proof_violations, run_violations, validate_semantics
from .governance import Review, ReviewDecision, ValueRecord, current_review
from .ifc import load_ifc, parse_ifc_text
from .events import KNOWN_EVENT_TYPES, Event, EventLog, ReplayError, owns_event
from .control_plane import ControlPlane
from .agent_runtime import AgentRuntime, CandidateFinding, InvestigationResult, RegisteredTool, ToolObservation
from .providers import ProviderRequest, ProviderResponse, ToolCall
from .requirements import RequirementCompilationError, compile_requirement
from .investigation import InvestigationPublication, ReferenceInvestigationProvider, investigate_and_publish
from .gateway import IN_PROCESS, DataResidency, ExecutionScope, GatewayError, GatewayPolicy, GatewayRoute, ProviderGateway, ProviderRegistry, ProviderRouter, ReferenceEmbeddingProvider, ReferenceChatProvider, build_default_gateway
from .evidence_room import DocumentState, DocumentVersion, EvidenceEnvelope, EvidenceRoom, EvidenceState
from .readiness import ReadinessContribution, ReadinessReport, compute_readiness
from .reality import RealityComparison, RealityObservation, compare_position
from .activity import ActionTask, activity_feed, derive_tasks
from .work import WorkUnit, WorkUnitStatus, WORK_UNIT_TRANSITIONS

__all__ = [
    "__version__",
    "CLOSING_STATUSES",
    "Applicability",
    "Counterexample",
    "DeterminationReason",
    "DeterminationStatus",
    "EmptyPopulationPolicy",
    "PopulationSpec",
    "ControlPlane",
    "ReplayError",
    "Determination",
    "Evidence",
    "EvidenceAdmissionError",
    "EvidenceAuthority",
    "AssuranceError",
    "Term",
    "Vocabulary",
    "default_vocabulary",
    "validate_obligation",
    "Conversion",
    "Dimension",
    "IncompatibleDimensionError",
    "MeasurementError",
    "MeasurementPolicy",
    "Quantity",
    "UnknownUnitError",
    "UnresolvedUnitError",
    "observe_measurement",
    "resolve_unit",
    "AgentRuntime",
    "CandidateFinding",
    "Event",
    "EventLog",
    "KNOWN_EVENT_TYPES",
    "owns_event",
    "InvestigationResult",
    "Obligation",
    "ProjectWorld",
    "Proof",
    "ConformanceError",
    "determination_violations",
    "proof_violations",
    "run_violations",
    "validate_semantics",
    "Review",
    "ReviewDecision",
    "Requirement",
    "Unresolved",
    "RegisteredTool",
    "Run",
    "ProviderRequest",
    "ProviderResponse",
    "ToolCall",
    "ToolObservation",
    "RequirementCompilationError",
    "compile_requirement",
    "InvestigationPublication",
    "ReferenceInvestigationProvider",
    "investigate_and_publish",
    "IN_PROCESS",
    "DataResidency",
    "ExecutionScope",
    "GatewayPolicy",
    "GatewayError",
    "GatewayRoute",
    "ProviderGateway",
    "ProviderRegistry",
    "ProviderRouter",
    "ReferenceEmbeddingProvider",
    "ReferenceChatProvider",
    "build_default_gateway",
    "DocumentState",
    "DocumentVersion",
    "EvidenceEnvelope",
    "EvidenceRoom",
    "EvidenceState",
    "ReadinessContribution",
    "ReadinessReport",
    "compute_readiness",
    "RealityComparison",
    "RealityObservation",
    "compare_position",
    "ActionTask",
    "activity_feed",
    "derive_tasks",
    "WorkUnit",
    "WorkUnitStatus",
    "WORK_UNIT_TRANSITIONS",
    "ValueRecord",
    "WorldElement",
    "current_review",
    "load_ifc",
    "parse_ifc_text",
    "validate_determination",
    "evaluate_obligation",
]

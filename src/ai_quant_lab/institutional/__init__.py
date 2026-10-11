"""Institutional research controls layered on the safe AI Quant Lab core."""

from ai_quant_lab.institutional.brain import HypothesisDraft, ResearchBrain
from ai_quant_lab.institutional.data_intelligence import (
    DataCapability,
    DataIntelligenceEngine,
    DatasetQualityReport,
)
from ai_quant_lab.institutional.evolution import evolve_parameters
from ai_quant_lab.institutional.program import (
    ContinuousResearchConfig,
    ContinuousResearchProgram,
)
from ai_quant_lab.institutional.regime_engine import (
    InstitutionalRegime,
    InstitutionalRegimeAssessment,
    InstitutionalRegimeEngine,
)
from ai_quant_lab.institutional.registry import (
    CampaignStatus,
    EvolutionProposalStatus,
    InstitutionalResearchStore,
    ResearchCampaignRecord,
    ResearchControl,
    ResearchStageName,
    ResearchStageStatus,
    StrategyEvolutionProposalRecord,
)
from ai_quant_lab.institutional.selection import (
    BanditArmState,
    BanditSelection,
    BanditUpdate,
    eligible_strategies,
    thompson_select,
)
from ai_quant_lab.institutional.risk_engine import (
    PortfolioRiskLimits,
    PortfolioRiskSnapshot,
    PositionDirection,
    PositionRiskInput,
    evaluate_portfolio_risk,
)
from ai_quant_lab.institutional.scoring import (
    AdvancedPerformanceMetrics,
    QuantScore,
    QuantScoreEvidence,
    bonferroni_adjusted_p_value,
    calculate_advanced_metrics,
    calculate_quant_score,
)

__all__ = [
    "AdvancedPerformanceMetrics",
    "CampaignStatus",
    "BanditUpdate",
    "BanditSelection",
    "BanditArmState",
    "ContinuousResearchConfig",
    "ContinuousResearchProgram",
    "DataCapability",
    "DataIntelligenceEngine",
    "DatasetQualityReport",
    "InstitutionalRegime",
    "HypothesisDraft",
    "EvolutionProposalStatus",
    "InstitutionalRegimeAssessment",
    "InstitutionalRegimeEngine",
    "InstitutionalResearchStore",
    "PortfolioRiskLimits",
    "PortfolioRiskSnapshot",
    "PositionDirection",
    "PositionRiskInput",
    "QuantScore",
    "QuantScoreEvidence",
    "ResearchCampaignRecord",
    "ResearchBrain",
    "ResearchControl",
    "ResearchStageName",
    "ResearchStageStatus",
    "bonferroni_adjusted_p_value",
    "StrategyEvolutionProposalRecord",
    "calculate_advanced_metrics",
    "calculate_quant_score",
    "evaluate_portfolio_risk",
    "thompson_select",
    "evolve_parameters",
    "eligible_strategies",
]

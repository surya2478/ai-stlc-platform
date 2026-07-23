import type { AIProcessingStage } from "@/types/ai-processing";

const stages = (...labels: string[]): AIProcessingStage[] => labels.map((label) => ({ label }));

export const AI_PROCESSING_STAGES = {
  requirementAnalysis: stages(
    "Reading requirement sources",
    "Resolving taxonomy and project context",
    "Detecting ambiguity, gaps and conflicts",
    "Identifying impacted journeys and applications",
    "Preparing grounded analysis",
    "Validating output structure",
  ),
  testPlanning: stages(
    "Reading approved requirements",
    "Resolving taxonomy and journey context",
    "Preparing structured test planning artifacts",
    "Checking coverage and traceability",
    "Validating generated output",
  ),
  testCaseGeneration: stages(
    "Reading approved requirements",
    "Resolving taxonomy and journey context",
    "Identifying positive, negative, boundary and recovery scenarios",
    "Generating structured test cases",
    "Checking coverage and traceability",
    "Preparing generated artifacts",
  ),
  automationClassification: stages(
    "Loading the effective classification policy",
    "Evaluating deterministic eligibility rules",
    "Resolving application and adapter capabilities",
    "Identifying required MCPs and validators",
    "Calculating automation value and complexity",
    "Preparing the recommendation for review",
  ),
  applicationDiscovery: stages(
    "Resolving application and environment context",
    "Running readiness checks",
    "Connecting to the selected adapter",
    "Inspecting screens, elements and accessibility structure",
    "Capturing network and external-system evidence",
    "Preparing discovery-session output",
  ),
  scriptGeneration: stages(
    "Loading approved test and automation context",
    "Resolving framework configuration",
    "Compiling actions and locators",
    "Generating assertions and evidence hooks",
    "Running static validation",
    "Preparing generated script files",
  ),
  failureDiagnosis: stages(
    "Collecting execution evidence",
    "Correlating UI, API, database and event outcomes",
    "Classifying the failure source",
    "Identifying likely root causes",
    "Preparing recommendations",
    "Validating diagnosis evidence",
  ),
  healingRecommendation: stages(
    "Reading the failure diagnosis",
    "Evaluating impacted scripts and reusable assets",
    "Preparing controlled changes",
    "Running impact analysis",
    "Validating rollback and review requirements",
    "Preparing the healing proposal",
  ),
  testData: stages(
    "Reading the requested data profile",
    "Applying privacy and environment constraints",
    "Generating structured test data",
    "Validating schema and record integrity",
    "Preparing the generated dataset",
  ),
  knowledge: stages(
    "Reading the current request context",
    "Retrieving relevant knowledge",
    "Grounding the response in available evidence",
    "Preparing the response",
  ),
  report: stages(
    "Collecting project quality evidence",
    "Analyzing coverage and execution outcomes",
    "Preparing quality recommendations",
    "Generating the report artifact",
    "Validating report structure",
  ),
} satisfies Record<string, AIProcessingStage[]>;

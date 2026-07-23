export type AIProcessingStatus =
  | "idle"
  | "queued"
  | "processing"
  | "waiting"
  | "success"
  | "error"
  | "timeout"
  | "blocked"
  | "cancelled";

export type AIProcessingStage = {
  label: string;
  backendStatuses?: string[];
};

export type AIProcessingContext = {
  isOpen: boolean;
  status: AIProcessingStatus;
  actionName: string;
  title: string;
  actionLabel?: string;
  module?: string;
  artifactType?: string;
  currentStage?: string;
  stages?: AIProcessingStage[];
  stageIndex?: number;
  startedAt?: string;
  elapsedTimeSeconds?: number;
  projectId?: number | string;
  requirementId?: number | string;
  testCaseId?: number | string;
  applicationId?: number | string;
  environmentId?: number | string;
  requestId?: string;
  jobId?: string;
  agentRunId?: string;
  correlationId?: string;
  successMessage?: string;
  errorMessage?: string;
  errorCategory?: string;
  blockerReason?: string;
  canRetry?: boolean;
  canCancel?: boolean;
};

export type AIActionMetadata = Partial<
  Pick<
    AIProcessingContext,
    | "status"
    | "currentStage"
    | "stageIndex"
    | "requestId"
    | "jobId"
    | "agentRunId"
    | "correlationId"
    | "successMessage"
    | "errorMessage"
    | "errorCategory"
    | "blockerReason"
  >
>;

export type RunAIActionOptions<T> = {
  actionName: string;
  title: string;
  actionLabel?: string;
  module?: string;
  artifactType?: string;
  stages?: AIProcessingStage[];
  initialStage?: string;
  projectId?: number | string;
  requirementId?: number | string;
  testCaseId?: number | string;
  applicationId?: number | string;
  environmentId?: number | string;
  successMessage?: string | ((result: T) => string);
  execute: () => Promise<T>;
  getResultMetadata?: (result: T) => AIActionMetadata;
  canRetry?: boolean;
  timeoutMs?: number;
};

export const INITIAL_AI_PROCESSING_CONTEXT: AIProcessingContext = {
  isOpen: false,
  status: "idle",
  actionName: "",
  title: "AI is Working",
  elapsedTimeSeconds: 0,
};

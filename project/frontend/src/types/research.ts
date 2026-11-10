/** Research workspace contracts for reads, reviewed drafts and bounded execution. */
export type ResearchStatus = 'pending' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled';
export type Facet = 'method' | 'dataset' | 'result' | 'limitation';
export interface ResearchSummary { id: string; status: ResearchStatus; revision: number; goal_preview?: string | null }
export interface ResearchList { items: ResearchSummary[]; total: number; limit: number; offset: number }
export interface ResearchStep {
  id: string; objective: string; tool_name: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  result: { elapsed_ms: number; error_type: string | null; error_code: string | null; warnings: string[] } | null;
}
export interface ResearchClaim {
  claim_id: string; document_id: string; facet: Facet; statement: string;
  citation: { chunk_id: string; char_start: number; char_end: number; quote: string };
}
export interface ResearchSource {
  claim_id: string; chunk_set_id: string; page_start: number | null; page_end: number | null;
  section_path: string[];
  source_locator: { source: { uri: string }; spans: { block_id: string; char_start: number; char_end: number; page_start: number | null; page_end: number | null }[] };
}
export interface ComparisonCell { facet: Facet; status: 'supported' | 'missing' | 'uncertain' | 'conflict'; statement: string | null; claim_ids: string[]; reasons: string[] }
export interface ResearchArtifact {
  artifact_id: string; corpus_id: string; completion_status?: 'partial' | 'ready_for_review';
  rows: { document_id: string; title: string; cells: ComparisonCell[] }[];
  citations: ResearchClaim[]; citation_sources?: ResearchSource[]; knowledge_gaps: string[];
}
export type ClaimReviewDecision = 'retain' | 'withdraw' | 'reset';
export interface ClaimReviewEvent {
  event_id: string; task_id: string; source_artifact_id: string; claim_id: string;
  actor_id: number; sequence: number; task_revision: number; previous_event_id: string | null;
  decision: ClaimReviewDecision; reason: string; reviewed_at: string;
}
export interface ClaimReviewItem {
  claim: ResearchClaim; source: ResearchSource;
  review_status: 'unreviewed' | 'retained' | 'withdrawn'; latest_event_id: string | null;
}
export interface ClaimReviewView {
  view_id: string; task_id: string; task_revision: number; source_artifact_id: string;
  items: ClaimReviewItem[]; events: ClaimReviewEvent[]; artifact: ResearchArtifact;
  annotation_status: 'owner_review_overlay'; quality_gate_passed: false; model_calls: 0; embedding_calls: 0;
}
export interface ResearchTask {
  id: string; goal: string; status: ResearchStatus; revision: number; corpus_id: string;
  sources: { document_id: string; title: string }[]; steps: ResearchStep[];
  model_calls_used: number; tool_calls_used: number;
  budget: { max_steps: number; max_model_calls: number; max_context_chars: number };
  retry_events?: { failed_revision: number; tool_calls_used: number; model_calls_used: number; failed_step: ResearchStep }[];
  claim_reviews?: ClaimReviewEvent[];
  artifact: ResearchArtifact | null; verification: object | null;
}
export interface PartialArtifactView {
  view_id: string; task_id: string; task_revision: number; source_task_status: 'failed';
  artifact: ResearchArtifact; unverified_documents: string[];
  task_marked_completed: false; artifact_attached_to_task: false; quality_gate_passed: false;
}

export interface RetainedVersion {
  id: string; created_at: string; is_active: boolean;
  manifest_integrity: 'valid' | 'invalid'; document_count: number | null;
}
export interface VersionList { items: RetainedVersion[]; total: number; offset: number; limit: number }
export interface VersionDetail extends RetainedVersion { documents?: { id: string; file_name: string }[] }
/** Explicit UI policy, reviewed on the server; never implies research quality approval. */
export interface ResearchDraft {
  index_version_id: string; document_ids: string[]; goal: string;
  plan_version: 'research-comparison-v2'; context_policy: 'local-window-v3'; candidate_policy: 'source-role-v3';
  extraction_protocol: 'source-handles-v2'; response_format: 'text';
  verification_protocol: 'facet-handles-v5'; verification_context_policy: 'preceding-children-v1';
  result_condition_policy: 'explicit-row-v1';
}
export interface ResearchPreview {
  preview_id: string; goal: string; index_version_id: string;
  sources: { document_id: string; title: string }[]; steps: ResearchStep[];
  budget: { max_steps: number; max_model_calls: number; max_context_chars: number };
  plan_version: string; model_id: string; status: 'preview'; task_created: false; model_calls: 0;
}

export interface RetryDecision {
  task_id: string; task_revision: number; eligible: boolean;
  reason: 'available' | 'not_failed' | 'attempt_not_finished' | 'unaccounted_history' | 'not_network_failure' | 'insufficient_budget';
  failed_step_id: string | null; remaining_tools: number; required_tools: number;
  remaining_model_calls: number; required_model_calls: number; sources_validated: boolean;
}

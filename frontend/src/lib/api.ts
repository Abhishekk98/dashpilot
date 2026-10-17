/** Typed client for the FastAPI backend. Types mirror backend Pydantic models. */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  llm_provider: "gemini" | "claude";
  llm_model: string;
  llm_configured: boolean;
}

export interface TableRef {
  name: string;
  sheet: string | null;
  rows: number;
  columns: number;
}

export interface StoredFile {
  id: string;
  filename: string;
  extension: string;
  size_bytes: number;
  uploaded_at: string;
  tables: TableRef[];
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  files: StoredFile[];
}

export type DetectedType =
  | "id" | "uuid" | "currency" | "percentage" | "integer" | "decimal"
  | "date" | "datetime" | "boolean" | "email" | "location" | "category" | "text";

export type SemanticRole =
  | "primary_key" | "foreign_key" | "measure" | "time_dimension" | "geo_dimension"
  | "categorical_slicer" | "flag" | "attribute" | "identifier";

export interface ColumnProfile {
  name: string;
  detected_type: DetectedType;
  currency_symbol: string | null;
  null_count: number;
  null_pct: number;
  distinct_count: number;
  unique_pct: number;
  numeric: { min: number; max: number; mean: number; median: number; outliers: number } | null;
  dates: { min: string; max: string; span_days: number } | null;
  sample_values: string[];
  role: SemanticRole;
  role_target: string | null;
  confidence: number;
  role_source: "rules" | "ai";
  needs_casting: boolean;
  inconsistent_values: number;
}

export interface TableProfile {
  name: string;
  file_id: string;
  sheet: string | null;
  rows: number;
  columns: number;
  null_pct: number;
  duplicate_rows: number;
  quality_score: number;
  column_profiles: ColumnProfile[];
}

export interface QualityReport {
  score: number;
  label: "Good Quality" | "Fair Quality" | "Needs Attention";
  confidence: number;
  headline: string;
  detail: string;
  signal: string;
  tables: TableProfile[];
  total_rows: number;
  total_columns: number;
  ai_refined: boolean;
  /** off = no AI key, pending = AI refinement still to run, done = refined, failed = see ai_note. */
  ai_status: "off" | "pending" | "done" | "failed";
  ai_note: string | null;
}

export interface UploadResult {
  project: Project;
  errors: string[];
}

export type CleaningStepKind =
  | "remove_total_rows" | "clean_whitespace" | "remove_duplicates" | "standardise_categories" | "merge_synonyms"
  | "normalise_booleans" | "cast_numeric" | "cast_european" | "date_format" | "set_types" | "excel_serial_dates"
  | "date_outliers" | "sentinel_values" | "dedupe_key" | "orphan_keys" | "handle_nulls" | "unknown_member";
export type CleaningStatus = "pending" | "accepted" | "skipped";
/** Strategy ids per step kind, e.g. "fill_median", "latest", "day_first", "unknown_member". */
export type CleaningStrategy = string;

export interface ValueMerge {
  canonical: string;
  variants: Record<string, number>;
  total: number;
}

export interface CleaningStep {
  id: string;
  table: string;
  kind: CleaningStepKind;
  impact: "High" | "Medium" | "Low";
  category: string;
  title: string;
  description: string;
  columns: string[];
  rows_affected: number;
  affected_pct: number;
  status: CleaningStatus;
  strategy: CleaningStrategy | null;
  strategies: CleaningStrategy[];
  strategy_text: Record<string, [string, string]>;
  merges: ValueMerge[];
  types: Record<string, string>;
  params: Record<string, unknown>;
  fill_value: number | null;
  source: "rules" | "ai";
  /** Set when the step could not be applied ("Skipped: …" / "Failed: …"); the rest still ran. */
  error: string | null;
}

export interface TableCleaning {
  name: string;
  source: string;
  rows_before: number;
  rows_after: number;
  accepted: number;
  m_script: string;
  /** Structure repairs applied while reading (title rows, blank/repeated headers, encoding). */
  structure_notes: string[];
}

export interface CleaningPlan {
  steps: CleaningStep[];
  tables: TableCleaning[];
  accepted: number;
  total: number;
  score_before: number;
  score_after: number;
  rows_before: number;
  rows_after: number;
  warnings: string[];
  /** off = no AI key, available = scan not run yet, done / failed = see ai_note. */
  ai_synonyms: "off" | "available" | "done" | "failed";
  ai_note: string | null;
}

export interface CleaningDecision {
  step_id: string;
  status?: CleaningStatus;
  strategy?: CleaningStrategy;
}

export interface DiffCell {
  before: string | null;
  after: string | null;
  changed: boolean;
}

export interface DiffPreview {
  table: string;
  columns: string[];
  changed_columns: string[];
  rows: { row: number; status: "transformed" | "unchanged" | "duplicate" | "removed"; cells: DiffCell[] }[];
  transformed_rows: number;
  dropped_rows: number;
  accepted_steps: number;
}

export interface BrandPalette {
  accent: string;
  base: string;
  muted: string;
  canvas: string;
  growth: string;
}

export type Archetype = "dark_futuristic" | "light_elegant" | "glassmorphism" | "minimal_corporate" | "neon_tech";

export interface BusinessContext {
  company_name: string;
  industries: string[];
  audiences: string[];
  goals: string;
  palette: BrandPalette;
  mode: "light" | "dark";
  font_stack: string;
  archetype: Archetype;
  domain_score: number | null;
  logo: { filename: string; extension: string; content_type: string; size_bytes: number; uploaded_at: string } | null;
  /** null until the step has been saved once. */
  updated_at: string | null;
}

/** Shared by the three AI helpers: "rules" means no key or the AI call failed (see note). */
interface AiResult {
  source: "ai" | "rules";
  note: string | null;
}

export interface ContextSuggestion extends AiResult {
  industries: string[];
  audiences: string[];
  goals: string;
  domain_score: number;
}

export interface PaletteSuggestion extends AiResult {
  palette: BrandPalette;
  rationale: string;
}

export interface PolishedGoals extends AiResult {
  goals: string;
}

export type TableKind = "fact" | "dimension" | "date";

export interface ModelColumn {
  name: string;
  data_type: "string" | "int64" | "double" | "decimal" | "dateTime" | "boolean";
  detected_type: DetectedType;
  key: "pk" | "fk" | null;
  hidden: boolean;
  measure_candidate: boolean;
  derived: boolean;
}

export interface ModelTable {
  name: string;
  kind: TableKind;
  kind_source: "rules" | "ai" | "user";
  included: boolean;
  exclusion_reason: string | null;
  rows: number;
  source: string;
  grain: string | null;
  columns: ModelColumn[];
}

export interface RelationshipInput {
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
}

export interface Relationship extends RelationshipInput {
  id: string;
  cardinality: "many_to_one" | "one_to_one";
  cross_filter: "single" | "both";
  active: boolean;
  origin: "auto" | "user" | "date";
  valid: boolean;
  missing_keys: number;
  note: string | null;
}

export interface ModelSettings {
  table_overrides: Record<string, { included?: boolean | null; kind?: "fact" | "dimension" | null }>;
  removed_relationships: string[];
  added_relationships: RelationshipInput[];
  fiscal_year_start_month: number;
  hide_keys: boolean;
  date_table: boolean;
}

export interface ModelPlan {
  tables: ModelTable[];
  relationships: Relationship[];
  date_table: { enabled: boolean; name: string; start: string | null; end: string | null; fiscal_year_start_month: number; sources: string[] };
  settings: ModelSettings;
  facts: number;
  dimensions: number;
  ambiguities: number;
  hidden_columns: number;
  health_score: number;
  notes: { tone: "success" | "info" | "warning"; title: string; text: string }[];
  ai_status: "off" | "pending" | "done" | "failed";
  ai_note: string | null;
  tmdl_valid: boolean;
  tmdl_errors: string[];
}

export type MeasureFormat = "currency" | "whole" | "decimal" | "percent";

export interface MeasureInput {
  name: string;
  expression: string;
  format: MeasureFormat;
  folder: string;
  description: string;
}

export interface Measure extends MeasureInput {
  format_string: string;
  source: "library" | "rules" | "ai" | "user";
  edited: boolean;
  /** passed = valid and calculated; edge = valid but not computable here / blank; error = rejected by the validator. */
  status: "passed" | "edge" | "error";
  issues: string[];
  deps: string[];
  time_intelligence: boolean;
  value: number | null;
  value_text: string | null;
  test_context: string | null;
  industry: string | null;
}

export interface KpiCard {
  name: string;
  value_text: string;
  badge: string;
  accent: boolean;
  spark: number[];
}

export interface MeasurePlan {
  measures: Measure[];
  folders: Record<string, number>;
  cards: KpiCard[];
  passed: number;
  edge: number;
  errors: number;
  primary_fact: string | null;
  test_context: string | null;
  industries: string[];
  notes: string[];
  ai_status: "off" | "available";
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request("/api/health", { signal });
}

export function createProject(name: string): Promise<Project> {
  return request("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function getProject(id: string): Promise<Project> {
  return request(`/api/projects/${id}`);
}

export function uploadFiles(id: string, files: File[]): Promise<UploadResult> {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return request(`/api/projects/${id}/files`, { method: "POST", body: form });
}

export function deleteFile(id: string, fileId: string): Promise<Project> {
  return request(`/api/projects/${id}/files/${fileId}`, { method: "DELETE" });
}

/**
 * ai=false returns the fast rule-based report; ai=true waits for the AI role
 * refinement (can take a minute on wide workbooks with a free-tier key).
 */
export function getProfile(id: string, ai: boolean): Promise<QualityReport> {
  return request(`/api/projects/${id}/profile?ai=${ai}`);
}

export function profileCsvUrl(id: string): string {
  return `${API_BASE_URL}/api/projects/${id}/profile/columns.csv`;
}

export function getCleaningPlan(id: string): Promise<CleaningPlan> {
  return request(`/api/projects/${id}/cleaning`);
}

export function saveCleaningDecisions(id: string, decisions: CleaningDecision[]): Promise<CleaningPlan> {
  return request(`/api/projects/${id}/cleaning/decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisions }),
  });
}

export function getContext(id: string): Promise<BusinessContext> {
  return request(`/api/projects/${id}/context`);
}

export function saveContext(id: string, context: BusinessContext): Promise<BusinessContext> {
  return request(`/api/projects/${id}/context`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(context),
  });
}

export function uploadLogo(id: string, file: File): Promise<BusinessContext> {
  const form = new FormData();
  form.append("file", file);
  return request(`/api/projects/${id}/context/logo`, { method: "POST", body: form });
}

export function deleteLogo(id: string): Promise<BusinessContext> {
  return request(`/api/projects/${id}/context/logo`, { method: "DELETE" });
}

/** `version` (the upload time) busts the browser cache after a new upload. */
export function logoUrl(id: string, version: string): string {
  return `${API_BASE_URL}/api/projects/${id}/context/logo?v=${encodeURIComponent(version)}`;
}

function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  return request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function suggestContext(id: string): Promise<ContextSuggestion> {
  return postJson(`/api/projects/${id}/context/suggest`);
}

export function suggestPalette(id: string, accent: string, useLogo: boolean): Promise<PaletteSuggestion> {
  return postJson(`/api/projects/${id}/context/palette`, { accent, use_logo: useLogo });
}

export function polishGoals(id: string, goals: string): Promise<PolishedGoals> {
  return postJson(`/api/projects/${id}/context/polish`, { goals });
}

/** ai=false answers fast; ai=true also waits for the (cached) AI table classification. */
export function getModel(id: string, ai: boolean): Promise<ModelPlan> {
  return request(`/api/projects/${id}/model?ai=${ai}`);
}

export function saveModelSettings(id: string, settings: ModelSettings): Promise<ModelPlan> {
  return request(`/api/projects/${id}/model`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function tmdlZipUrl(id: string): string {
  return `${API_BASE_URL}/api/projects/${id}/model/tmdl.zip`;
}

/** AI pass that finds synonyms (M → Male, Bombay → Mumbai); results become reviewable suggestions. */
export function scanSynonyms(id: string): Promise<CleaningPlan> {
  return request(`/api/projects/${id}/cleaning/synonyms`, { method: "POST" });
}

export function getMeasures(id: string): Promise<MeasurePlan> {
  return request(`/api/projects/${id}/measures`);
}

/** Create a measure, or update one when `originalName` is given (generated measures keep their name). */
export function saveMeasure(id: string, measure: MeasureInput, originalName?: string): Promise<MeasurePlan> {
  return postJson(`/api/projects/${id}/measures`, { measure, original_name: originalName ?? null });
}

export function deleteMeasure(id: string, name: string): Promise<MeasurePlan> {
  return postJson(`/api/projects/${id}/measures/delete`, { name });
}

/** "Regenerate": drop the user's edits to a generated measure. */
export function resetMeasure(id: string, name: string): Promise<MeasurePlan> {
  return postJson(`/api/projects/${id}/measures/reset`, { name });
}

export function validateMeasures(id: string): Promise<MeasurePlan> {
  return postJson(`/api/projects/${id}/measures/validate`);
}

export function suggestMeasures(id: string): Promise<MeasurePlan> {
  return postJson(`/api/projects/${id}/measures/suggest`);
}

export function polishMeasure(id: string, name: string): Promise<MeasurePlan> {
  return postJson(`/api/projects/${id}/measures/polish`, { name });
}

export function measuresTmdlUrl(id: string): string {
  return `${API_BASE_URL}/api/projects/${id}/measures/export.tmdl`;
}

export function getCleaningPreview(id: string, table: string): Promise<DiffPreview> {
  return request(`/api/projects/${id}/cleaning/preview?table=${encodeURIComponent(table)}`);
}

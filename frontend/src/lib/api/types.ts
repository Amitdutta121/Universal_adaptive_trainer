/**
 * Readable aliases for the generated backend models.
 *
 * Import these instead of reaching into `schema.d.ts`, so that a rename on the
 * backend surfaces as a compile error in one file rather than fifty.
 */

import type { components } from "./schema";

export type Schemas = components["schemas"];

// Enumerations shared with the backend domain layer.
export type Difficulty = Schemas["Difficulty"];
export type QuestionStatus = Schemas["QuestionStatus"];
export type QuestionType = Schemas["QuestionType"];
export type QuestionKind = Schemas["QuestionKind"];

// Responses the starter pages already consume.
export type Counts = Schemas["CountsResponse"];
export type Health = Schemas["HealthResponse"];
export type Config = Schemas["ConfigResponse"];
export type QuestionListResponse = Schemas["QuestionListResponse"];
export type QuestionSummary = Schemas["QuestionSummary"];
export type QuestionDetail = Schemas["QuestionDetail"];
export type ReviewQueueResponse = Schemas["ReviewQueueResponse"];
export type CoverageReport = Schemas["CoverageReportResponse"];
export type StudentListResponse = Schemas["StudentListResponse"];
export type BookListResponse = Schemas["BookListResponse"];
export type CurriculumListResponse = Schemas["CurriculumListResponse"];
export type BatchRunListResponse = Schemas["BatchRunListResponse"];

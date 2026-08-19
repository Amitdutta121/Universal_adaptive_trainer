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
export type CurriculumStatus = Schemas["CurriculumStatus"];
export type CurriculumItemStatus = Schemas["CurriculumItemStatus"];
export type ConceptConfidence = Schemas["ConceptConfidence"];

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
export type StudentOut = Schemas["StudentOut"];
export type StudentProgressOut = Schemas["StudentProgressOut"];
export type TrainingSessionOut = Schemas["TrainingSessionOut"];
export type AttemptOut = Schemas["AttemptOut"];
export type AnsweredOut = Schemas["AnsweredOut"];
export type ServedQuestionOut = Schemas["ServedQuestionOut"];
export type QuestionSetListResponse = Schemas["QuestionSetListResponse"];
export type QuestionSetOut = Schemas["QuestionSetOut"];
export type BookListResponse = Schemas["BookListResponse"];
export type BookSummary = Schemas["BookSummary"];
export type BookDetail = Schemas["BookDetail"];
export type BookDocumentGuide = Schemas["BookDocumentGuide"];
export type BookStatus = Schemas["BookStatus"];
export type ChapterOut = Schemas["ChapterOut"];
export type SectionSummary = Schemas["SectionSummary"];
export type ExtractionWarning = Schemas["ExtractionWarning"];
export type CurriculumListResponse = Schemas["CurriculumListResponse"];
export type CurriculumVersionSummary = Schemas["CurriculumVersionSummary"];
export type CurriculumVersionDetail = Schemas["CurriculumVersionDetail"];
export type CurriculumVersionUsage = Schemas["CurriculumVersionUsage"];
export type TaxonomyDocumentGuide = Schemas["TaxonomyDocumentGuide"];
export type TopicOut = Schemas["TopicOut"];
export type SubtopicSummary = Schemas["SubtopicSummary"];
export type SubtopicDetail = Schemas["SubtopicDetail"];
export type SubtopicEvidence = Schemas["SubtopicEvidenceOut"];
export type ProposalWarning = Schemas["DisplayProposalWarning"];
export type ExtractionMetadata = Schemas["DisplayExtractionMetadata"];
export type BatchRunListResponse = Schemas["BatchRunListResponse"];
export type TypeInstructionListResponse = Schemas["TypeInstructionListResponse"];
export type TypeInstruction = Schemas["TypeInstructionOut"];
export type TypeInstructionRefreshResponse = Schemas["TypeInstructionRefreshResponse"];

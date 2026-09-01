export interface paths {
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Liveness plus a real database round-trip.
         */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Config
         * @description Enum vocabularies and limits, so a client never hard-codes them.
         */
        get: operations["config_api_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/counts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Counts
         * @description One count per section.
         */
        get: operations["counts_api_counts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Auth:Cookie.Login */
        post: operations["auth_cookie_login_api_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Auth:Cookie.Logout */
        post: operations["auth_cookie_logout_api_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Current User
         * @description The frontend's session check: 401 with no cookie, the professor's identity otherwise.
         */
        get: operations["read_current_user_api_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/books": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Books
         * @description Every imported book, newest first.
         *
         *     ``usable_only`` restricts the list to books that have sections to generate
         *     from, which is what a generation form needs.
         */
        get: operations["list_books_api_books_get"];
        put?: never;
        /**
         * Import Book
         * @description Validate and import an uploaded book JSON document.
         *
         *     Reading the spooled file synchronously is safe here: the route runs in a
         *     worker thread, so it does not block the event loop.
         */
        post: operations["import_book_api_books_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/books/document-guide": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Document Guide
         * @description What a valid book document is, and the prompt that produces one.
         *
         *     Rendered from the ingestion contract rather than written out here, so a
         *     client cannot describe a document this application would refuse. The prompt
         *     is advisory: it grants nothing, and every upload is still validated in full.
         */
        get: operations["document_guide_api_books_document_guide_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/books/{book_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Book
         * @description One book: import status, warnings and its chapter/section hierarchy.
         */
        get: operations["get_book_api_books__book_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Book
         * @description Delete a book, its structure and its retained document.
         *
         *     Refuses with 409 while questions cite the book, naming how many. ``force``
         *     proceeds anyway; the questions are kept and their citations are stranded.
         */
        delete: operations["delete_book_api_books__book_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Book
         * @description Edit a book's labels. Omitted fields are left as they are.
         */
        patch: operations["update_book_api_books__book_id__patch"];
        trace?: never;
    };
    "/api/books/{book_id}/source": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Book Source
         * @description The original PDF as uploaded, for in-browser rendering.
         *
         *     Only a book imported from a PDF (``SourceFormat.BOOK_PDF``) has a source
         *     file worth serving back -- a book declared directly as structured JSON has
         *     no PDF to render, even though it also retains its uploaded file.
         *
         *     Not a download: no ``filename`` is passed to ``FileResponse``, so no
         *     ``Content-Disposition: attachment`` header is sent, and a PDF-rendering
         *     client can fetch it inline.
         */
        get: operations["get_book_source_api_books__book_id__source_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/books/{book_id}/sections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Sections
         * @description Every section of one book in reading order, without section text.
         */
        get: operations["list_sections_api_books__book_id__sections_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/books/{book_id}/sections/{section_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Section
         * @description One section's verbatim text plus the citation that makes it traceable.
         */
        get: operations["get_section_api_books__book_id__sections__section_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/curriculum/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Versions
         * @description Every curriculum version, newest first, plus which one is approved.
         */
        get: operations["list_versions_api_curriculum_versions_get"];
        put?: never;
        /**
         * Import Taxonomy
         * @description Validate and import a fixed Topic -> Subtopic taxonomy document.
         */
        post: operations["import_taxonomy_api_curriculum_versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/curriculum/document-guide": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Document Guide
         * @description What a valid taxonomy document is, and the prompt that produces one.
         *
         *     Rendered from the taxonomy contract rather than written out here, so a client
         *     cannot describe a document this application would refuse. The prompt is
         *     advisory: it grants nothing, and every upload is still validated in full.
         */
        get: operations["document_guide_api_curriculum_document_guide_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/curriculum/approved": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Approved
         * @description The curriculum version question generation is allowed to use.
         */
        get: operations["get_approved_api_curriculum_approved_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/curriculum/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Version
         * @description One curriculum version with its full Topic -> Subtopic hierarchy.
         */
        get: operations["get_version_api_curriculum_versions__version_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Version
         * @description Delete a curriculum version, its topics and its subtopics.
         *
         *     Refuses with 409 while questions or students still name it, reporting every
         *     count. ``force`` proceeds anyway and the references are stranded. Two cases
         *     have no ``force`` path -- a frozen question set names the version, or it is
         *     the approved one -- because neither leaves a professor anything to decide.
         */
        delete: operations["delete_version_api_curriculum_versions__version_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Version
         * @description Rename a curriculum version. Its status and its tree are unchanged.
         */
        patch: operations["update_version_api_curriculum_versions__version_id__patch"];
        trace?: never;
    };
    "/api/curriculum/versions/{version_id}/activate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Activate Version
         * @description Make an already-approved curriculum version the live one again.
         */
        post: operations["activate_version_api_curriculum_versions__version_id__activate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/curriculum/topics/{topic_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update Topic
         * @description Edit a topic's display name. Its stable id is untouched (ADR-021).
         */
        patch: operations["update_topic_api_curriculum_topics__topic_id__patch"];
        trace?: never;
    };
    "/api/curriculum/subtopics/{subtopic_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Subtopic
         * @description One subtopic: its approved definition and any legacy textbook evidence.
         */
        get: operations["get_subtopic_api_curriculum_subtopics__subtopic_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update Subtopic
         * @description Edit a subtopic's display name.
         *
         *     The stable id is not recomputed, so any weakness a student has been measured
         *     for on this skill stays attached to it (ADR-021).
         */
        patch: operations["update_subtopic_api_curriculum_subtopics__subtopic_id__patch"];
        trace?: never;
    };
    "/api/questions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Questions
         * @description The question bank, newest first, with counts by lifecycle status.
         *
         *     ``status``, ``curriculum_version_id``, ``section_id`` and ``run_id`` narrow
         *     the listing; without them nothing is hidden. The API does not filter by
         *     default even though the page does, because a caller reading the bank over
         *     JSON has no way to discover rows an unrequested default removed.
         *     ``status_counts``, ``curriculum_version_counts`` and ``total`` always
         *     describe the whole bank, so a filtered listing still says how much it is
         *     showing of what.
         */
        get: operations["list_questions_api_questions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/generate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Questions
         * @description Generate and persist one question per selected source section.
         *
         *     Every spec is validated before the first model call, so an invalid id later
         *     in the list cannot leave a partially generated batch behind.
         */
        post: operations["generate_questions_api_questions_generate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/{question_id}/regenerate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Regenerate Question
         * @description Generate a new question from an existing one, with instructor feedback.
         *
         *     The source question is never modified: this returns a fresh row, grounded in
         *     the same section, type and difficulty, with the feedback threaded into the
         *     generation prompt. It writes no review and triggers no instruction relearn --
         *     that is the review endpoint's job, not this one.
         */
        post: operations["regenerate_question_api_questions__question_id__regenerate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/batch-plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Batch Plan
         * @description Compile a per-chunk spec sheet into the questions it would generate (ADR-044).
         *
         *     Read-only and free: it makes no model call and touches no row, so a professor
         *     can price a spec sheet and revise it as often as they like. The compilation
         *     lives here rather than in either UI because the rule that decides which format
         *     each question gets must not be restated by a client (ADR-027).
         */
        post: operations["batch_plan_api_questions_batch_plan_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/generate-batch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Batch
         * @description Generate the questions a per-chunk spec sheet asks for (ADR-044).
         *
         *     One chunk may produce several questions, at several difficulties, in several
         *     formats — which is what separates this from ``/generate``, where a run carries
         *     one difficulty and one format for every section in it.
         *
         *     The run is synchronous: each question costs one generation call plus one judge
         *     call per metric, made in sequence. A large sheet is therefore a long request,
         *     and the console warns before submitting one.
         */
        post: operations["generate_batch_api_questions_generate_batch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/generation-plan": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Generation Plan
         * @description What generating from this selection would produce, before it runs.
         *
         *     Read-only and free: it makes no model call, so a professor can price a run
         *     and revise it as often as they like. The arithmetic lives here rather than in
         *     the template because the page is only one client of it (ADR-027).
         */
        get: operations["generation_plan_api_questions_generation_plan_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/review-queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Review Queue
         * @description The next question awaiting a professor verdict, plus progress counts.
         *
         *     The queue holds no state. ``after`` is a plain cursor over question ids,
         *     which is what lets a professor skip a question -- and lets a submitted
         *     review advance to the next one -- without a stored position per professor.
         *
         *     Questions that failed deterministic validation are never offered (ADR-032),
         *     and ``total`` counts only reviewable ones, so a completed pass reads as
         *     ``remaining == 0`` rather than stalling on questions the queue excludes.
         */
        get: operations["review_queue_api_questions_review_queue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/{question_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Question
         * @description One question with its validation report, judge evaluation and provenance.
         */
        get: operations["get_question_api_questions__question_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/{question_id}/review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Review
         * @description Record a professor verdict, then act on the cell it lands in (ADR-037).
         */
        post: operations["create_review_api_questions__question_id__review_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reviews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Reviews
         * @description The professor's review history, newest first.
         */
        get: operations["list_reviews_api_reviews_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/reviews/stats": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Review Stats
         * @description Decision totals and the rejection-reason distribution.
         */
        get: operations["review_stats_api_reviews_stats_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instructions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Instructions
         * @description Every question type, with whatever has been learned for it.
         *
         *     Types with nothing learned are listed too, carrying the shipped instruction
         *     and a review count -- that is how a professor sees which types have enough
         *     feedback to be worth refreshing.
         */
        get: operations["list_instructions_api_instructions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instructions/{question_type}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Instruction
         * @description Delete one learned row so this type falls back to its shipped instruction.
         */
        delete: operations["delete_instruction_api_instructions__question_type__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instructions/{question_type}/rules/{rule_index}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Rule
         * @description Delete one learned rule and re-render the instruction from what remains.
         */
        delete: operations["delete_rule_api_instructions__question_type__rules__rule_index__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instructions/{question_type}/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh
         * @description Re-learn one type's instruction from its reviews. Requires a configured LLM.
         */
        post: operations["refresh_api_instructions__question_type__refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/judge-prompts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Judge Prompts
         * @description All four judges, each with the text it runs and the text it shipped with.
         */
        get: operations["list_judge_prompts_api_judge_prompts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/judge-prompts/{metric}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Save Judge Prompt
         * @description Replace one judge's system prompt, and re-name the panel.
         *
         *     Existing evaluations are left alone. Re-judging the bank under the new prompt
         *     is a separate, explicit act (ADR-030) -- rewriting stored verdicts here would
         *     destroy the very pairs the repair is supposed to be scored against.
         */
        put: operations["save_judge_prompt_api_judge_prompts__metric__put"];
        post?: never;
        /**
         * Revert Judge Prompt
         * @description Drop one override so the judge runs its shipped prompt again.
         */
        delete: operations["revert_judge_prompt_api_judge_prompts__metric__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/judge-prompts/{metric}/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh
         * @description Re-learn one judge's prompt from the questions it got wrong (ADR-039).
         *
         *     The mirror of ``POST /api/instructions/{question_type}/refresh``. Reads only
         *     the disagreements this judge is named in, minus the held-out third, so the
         *     reserved questions stay available to score the result.
         */
        post: operations["refresh_api_judge_prompts__metric__refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/calibration/results": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Calibration Results
         * @description Judge/professor agreement over every reviewed, judged question.
         */
        get: operations["calibration_results_api_calibration_results_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/calibration/pairs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Calibration Pairs
         * @description The questions behind the figures, so a rate can be checked against rows.
         */
        get: operations["calibration_pairs_api_calibration_pairs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/calibration/quadrant": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Calibration Quadrant
         * @description The four-cell breakdown per question type, with the questions in each.
         *
         *     ``rubric_version`` narrows the pairs to one judge. Without it the response
         *     reports every version it drew on, so a figure spanning two judges is
         *     visible rather than implied.
         */
        get: operations["calibration_quadrant_api_calibration_quadrant_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/calibration/trend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Agreement Trend
         * @description Agreement per judge panel, in the order the panels ran (ADR-041).
         *
         *     The measurement that can falsify ADR-039: a judge rewriting itself from its
         *     own mistakes is assumed to converge on the professor, and this is what says
         *     whether it did. Read-only, and built from the frozen ``review_outcomes``
         *     rows rather than from the live evaluations, which a re-judge overwrites.
         */
        get: operations["agreement_trend_api_calibration_trend_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/coverage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Coverage
         * @description The subtopic x difficulty grid over approved questions.
         *
         *     Without ``set_version_id`` this is the live bank -- what to generate next.
         *     With one it is that frozen set -- what a training run would actually serve.
         */
        get: operations["coverage_api_coverage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/coverage/generation-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Generation Run
         * @description Generate one grounded question for each selected coverage gap.
         *
         *     For every target: retrieve the top book section that teaches its subtopic,
         *     generate one multiple-choice question from that section at the requested
         *     difficulty, and report what the generator claimed it wrote for. A target
         *     with no confident section is skipped and the run continues; a provider
         *     failure on one target is reported beside the questions the run did produce
         *     (ADR-032). The new questions land in the review queue with no extra step.
         */
        post: operations["start_generation_run_api_coverage_generation_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/question-sets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Question Sets */
        get: operations["list_question_sets_api_question_sets_get"];
        put?: never;
        /**
         * Create Set
         * @description Freeze every approved question of the approved curriculum under a name.
         */
        post: operations["create_set_api_question_sets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/question-sets/prod/sync": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sync Prod Set
         * @description Freeze the approved bank now and repoint the stable prod classroom link.
         */
        post: operations["sync_prod_set_api_question_sets_prod_sync_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/retrieval/sections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Retrieve Sections
         * @description Rank sections for a query or a subtopic. Exactly one of the two is required.
         */
        get: operations["retrieve_sections_api_retrieval_sections_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/question-sets/prod": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Prod Classroom
         * @description The current production classroom snapshot behind the stable join link.
         */
        get: operations["get_prod_classroom_api_question_sets_prod_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/question-sets/{set_version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Question Set
         * @description One frozen set, public so an anonymous join link can describe itself.
         */
        get: operations["get_question_set_api_question_sets__set_version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/students": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Students
         * @description One page of the roster, filtered server-side (ADR-041 keeps it read-only).
         *
         *     The score, answered and activity filters run off one grouped pass over the
         *     attempt table -- :meth:`StudentAttemptRepository.stats_by_student` -- rather
         *     than a progress fetch per learner, so the cost no longer grows with the
         *     cohort. ``total`` is the count *after* filtering, so the client can size its
         *     page controls.
         */
        get: operations["list_students_api_students_get"];
        put?: never;
        /**
         * Create Student
         * @description Enrol a learner.
         *
         *     Takes a name and a contact email. Names are unique because the picker is by
         *     name, so a duplicate would attach one learner's mastery to another. That is
         *     reported as a rule violation rather than left to surface as a database error.
         *     The email is validated for shape only and not required to be distinct.
         *
         *     The response carries the learner's ``resume_token``: the browser that
         *     enrolled them stores it and presents it to ``POST /students/resume`` to come
         *     back as the same learner instead of colliding on the unique name.
         */
        post: operations["create_student_api_students_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/students/class-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Class Summary
         * @description Cohort-wide figures for the roster's aggregate cards.
         *
         *     Independent of which roster page is open: the class trend graph and the
         *     weakness heatmap are about the whole class, so they get their own request
         *     instead of being rebuilt from whatever page of learners happens to be loaded.
         */
        get: operations["class_summary_api_students_class_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/students/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume Student
         * @description Recognise a returning browser by its stored token (ADR-041).
         *
         *     Public, like enrolment: students have no login. An unknown token is a 404 so
         *     the caller can drop its stale copy and fall back to enrolling; a known token
         *     returns the learner, plus their one unfinished run if there is one -- against
         *     *any* classroom set, not only this link's, because a student runs a single
         *     session at a time (see :func:`start_training_session`) and the join screen has
         *     to be able to send them back to it whichever link they arrive on.
         */
        post: operations["resume_student_api_students_resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/students/{student_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Student */
        get: operations["get_student_api_students__student_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/students/{student_id}/progress": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Student Progress
         * @description Measured mastery, weakness and history for one learner.
         *
         *     Only what has been scored appears. State rows are created on first touch
         *     (ADR-041), so a subtopic nobody has been asked about is absent rather than
         *     shown at a starting value it was never actually assigned.
         */
        get: operations["student_progress_api_students__student_id__progress_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/training-sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Training Sessions */
        get: operations["list_training_sessions_api_training_sessions_get"];
        put?: never;
        /**
         * Start Training Session
         * @description Begin a run for one student against one frozen question set (ADR-036).
         *
         *     The seed is generated here and stored, which is what makes the run
         *     replayable: every roulette draw derives from it and the question's position.
         *
         *     A learner may hold only one unfinished session at a time. A second is
         *     refused with :class:`ActiveSessionExistsError` rather than created, because
         *     two attempt streams folding scores into the same per-student BKT state
         *     corrupt the mastery estimate (ADR-041) -- and an accidental double-join (a
         *     second tab, a re-followed link) is a routine event, not an edge case. The
         *     client recovers by resuming the session the error names.
         */
        post: operations["start_training_session_api_training_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/training-sessions/{training_session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Training Session */
        get: operations["get_training_session_api_training_sessions__training_session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/training-sessions/{training_session_id}/next": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Next Question
         * @description Serve the next question.
         *
         *     Not idempotent in the HTTP sense -- it writes an attempt row and lowers the
         *     served question's priority -- but it *is* idempotent while a question is
         *     outstanding: asking again returns the same one rather than drawing another.
         *     A GET is still the honest verb, because what a client wants here is the
         *     session's current question.
         */
        get: operations["next_question_api_training_sessions__training_session_id__next_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attempts/{attempt_id}/answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Answer Attempt
         * @description Score a submitted answer and fold it into the student's state.
         */
        post: operations["answer_attempt_api_attempts__attempt_id__answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/attempts/{attempt_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Attempt */
        get: operations["get_attempt_api_attempts__attempt_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/training-sessions/{training_session_id}/end": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** End Training Session */
        post: operations["end_training_session_api_training_sessions__training_session_id__end_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evaluation/batch-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Batch Runs
         * @description Recent re-runs, newest first.
         */
        get: operations["list_batch_runs_api_evaluation_batch_runs_get"];
        put?: never;
        /**
         * Submit Batch Run
         * @description Submit the eligible question bank for re-judging.
         *
         *     202 rather than 201: the run is accepted, not finished. Nothing has been
         *     evaluated when this returns, and results appear only after a poll.
         */
        post: operations["submit_batch_run_api_evaluation_batch_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evaluation/batch-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Batch Run
         * @description One re-run's stored status, without contacting the provider.
         */
        get: operations["get_batch_run_api_evaluation_batch_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/evaluation/batch-runs/{run_id}/poll": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Poll Batch Run
         * @description Ask the provider about a run and record whatever has finished.
         *
         *     Idempotent. Polling a run whose results are already recorded reports them as
         *     ``already_recorded`` and writes nothing.
         */
        post: operations["poll_batch_run_api_evaluation_batch_runs__run_id__poll_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/questions/{question_id}/evaluations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Question Evaluations
         * @description Every evaluation this question has received, newest first.
         *
         *     The newest row is flagged ``is_current`` because it is what
         *     ``questions.pedagogical_eval_json`` holds; the older rows are what the judge
         *     said before, retained rather than overwritten.
         */
        get: operations["question_evaluations_api_questions__question_id__evaluations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AgreementTrendResponse
         * @description Agreement panel by panel, oldest first (ADR-041).
         */
        AgreementTrendResponse: {
            /** Points */
            points: components["schemas"]["TrendPointOut"][];
            /** Total */
            total: number;
            /** Improved */
            improved: boolean | null;
            /** Min Panel Sample */
            min_panel_sample: number;
        };
        /** AnswerRequest */
        AnswerRequest: {
            /**
             * Answer
             * @default
             */
            answer: string;
        };
        /**
         * AnsweredOut
         * @description What one submitted answer was worth, and what it moved.
         */
        AnsweredOut: {
            /** Training Session Id */
            training_session_id: number;
            /** Attempt Id */
            attempt_id: number;
            /** Question Id */
            question_id: number;
            /** Score */
            score: number;
            /** Passed Tests */
            passed_tests: number | null;
            /** Total Tests */
            total_tests: number | null;
            /** Detail */
            detail: string | null;
            /** Mastery Before */
            mastery_before: number | null;
            /** Mastery After */
            mastery_after: number | null;
        };
        /**
         * AttemptOut
         * @description One question served to a student, answered or not.
         */
        AttemptOut: {
            /** Id */
            id: number;
            /** Session Id */
            session_id: number;
            /** Ordinal */
            ordinal: number;
            /** Question Id */
            question_id: number;
            question_type: components["schemas"]["QuestionType"] | null;
            /** Subtopic Id */
            subtopic_id: number | null;
            requested_difficulty: components["schemas"]["Difficulty"];
            served_difficulty: components["schemas"]["Difficulty"];
            /** Score */
            score: number | null;
            /** Passed Tests */
            passed_tests: number | null;
            /** Total Tests */
            total_tests: number | null;
            /** Answer */
            answer: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Answered At */
            answered_at: string | null;
        };
        /**
         * BatchPlanResponse
         * @description The compiled plan for a spec sheet. Read-only: no question is generated.
         */
        BatchPlanResponse: {
            /** Planned */
            planned: components["schemas"]["PlannedQuestionOut"][];
            totals: components["schemas"]["BatchPlanTotals"];
        };
        /**
         * BatchPlanTotals
         * @description What a compiled spec sheet costs, before any model call is made.
         */
        BatchPlanTotals: {
            /** Chunks Specified */
            chunks_specified: number;
            /** Questions To Create */
            questions_to_create: number;
            /** Generation Calls */
            generation_calls: number;
            /** Judge Calls */
            judge_calls: number;
            /** Easy */
            easy: number;
            /** Medium */
            medium: number;
            /** Hard */
            hard: number;
            /** Identical Repeats */
            identical_repeats: number;
        };
        /** BatchRunListResponse */
        BatchRunListResponse: {
            /** Runs */
            runs: components["schemas"]["JudgeBatchRunOut"][];
            /** Total */
            total: number;
        };
        /** Body_auth_cookie_login_api_auth_login_post */
        Body_auth_cookie_login_api_auth_login_post: {
            /** Grant Type */
            grant_type?: string | null;
            /** Username */
            username: string;
            /**
             * Password
             * Format: password
             */
            password: string;
            /**
             * Scope
             * @default
             */
            scope: string;
            /** Client Id */
            client_id?: string | null;
            /**
             * Client Secret
             * Format: password
             */
            client_secret?: string | null;
        };
        /** Body_import_book_api_books_post */
        Body_import_book_api_books_post: {
            /** File */
            file: string;
            /**
             * Title
             * @default
             */
            title: string;
        };
        /** Body_import_taxonomy_api_curriculum_versions_post */
        Body_import_taxonomy_api_curriculum_versions_post: {
            /** File */
            file: string;
        };
        /**
         * BookDeletion
         * @description What a completed delete removed, and what it cost.
         */
        BookDeletion: {
            /** Deleted Book Id */
            deleted_book_id: number;
            /** Stranded Question Count */
            stranded_question_count: number;
        };
        /**
         * BookDetail
         * @description One book with its chapter/section hierarchy and import warnings.
         */
        BookDetail: {
            book: components["schemas"]["BookSummary"];
            /** Section Count */
            section_count: number;
            /** Chapters */
            chapters: components["schemas"]["ChapterOut"][];
            /** Warnings */
            warnings: components["schemas"]["ExtractionWarning"][];
            /**
             * Grounded Question Count
             * @default 0
             */
            grounded_question_count: number;
        };
        /**
         * BookDocumentGuide
         * @description Everything a professor needs to obtain a valid book document.
         *
         *     The prompt and the example are rendered from the ingestion contract itself,
         *     so a client that shows them cannot describe a document the validator would
         *     refuse.
         */
        BookDocumentGuide: {
            /** Schema Version */
            schema_version: string;
            /** Supported Extensions */
            supported_extensions: string[];
            /** Max Upload Mb */
            max_upload_mb: number;
            /** Prompt */
            prompt: string;
            /** Example Json */
            example_json: string;
            /** Structure Sources */
            structure_sources: components["schemas"]["VocabularyTermOut"][];
            /** Warning Codes */
            warning_codes: components["schemas"]["VocabularyTermOut"][];
            /** Warning Severities */
            warning_severities: components["schemas"]["VocabularyTermOut"][];
        };
        /** BookListResponse */
        BookListResponse: {
            /** Books */
            books: components["schemas"]["BookSummary"][];
            /** Total */
            total: number;
        };
        /**
         * BookMetadataUpdate
         * @description A professor's edit to a book's labels.
         *
         *     Structure is declared by the imported document and is never edited here, so
         *     this carries only what the row is labelled with. An omitted field is left
         *     alone; an empty string clears ``author`` or ``notes``.
         */
        BookMetadataUpdate: {
            /** Title */
            title?: string | null;
            /** Author */
            author?: string | null;
            /** Notes */
            notes?: string | null;
        };
        /**
         * BookStatus
         * @description Lifecycle of an imported textbook.
         *
         *     A book document that fails validation is rejected before any row is written,
         *     so there is no ``FAILED`` state: a book in the database is always one whose
         *     structure validated. ``PARTIAL`` is a success-with-caveats state, used when
         *     the document itself declares defects or low-confidence units, so a professor
         *     is never told a caveated import was clean.
         * @enum {string}
         */
        BookStatus: "imported" | "partial";
        /**
         * BookSummary
         * @description One book, without its structure.
         */
        BookSummary: {
            /** Id */
            id: number;
            /** Title */
            title: string;
            /** Author */
            author: string | null;
            status: components["schemas"]["BookStatus"];
            source_format: components["schemas"]["SourceFormat"];
            /** Original Filename */
            original_filename: string;
            /** Source Filename */
            source_filename: string | null;
            /** Producer */
            producer: string | null;
            /** Page Count */
            page_count: number | null;
            /** File Size Bytes */
            file_size_bytes: number | null;
            /** Notes */
            notes: string | null;
            /** Warning Count */
            warning_count: number;
            /** Defect Count */
            defect_count: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Imported At */
            imported_at: string | null;
        };
        /**
         * CalibrationLabel
         * @description The shared vocabulary the judge gate and the professor verdict project onto.
         *
         *     Lives here rather than in :mod:`app.calibration` because a review outcome is
         *     now *stored* at review time (ADR-037), and persistence may not import a
         *     subsystem.
         * @enum {string}
         */
        CalibrationLabel: "accept" | "needs_review";
        /**
         * CalibrationPairOut
         * @description One counted question: what the judge said, what the professor said.
         *
         *     The evidence behind the rates, kept out of ``CalibrationResultsResponse`` so
         *     that response stays the fixed five-figure summary. Questions excluded from
         *     the measurement do not appear here at all.
         */
        CalibrationPairOut: {
            /** Question Id */
            question_id: number;
            judge: components["schemas"]["CalibrationLabel"];
            professor: components["schemas"]["CalibrationLabel"];
            /** Agrees */
            agrees: boolean;
            cell: components["schemas"]["QuadrantCell"];
            question_type: components["schemas"]["QuestionType"] | null;
            /** Rubric Version */
            rubric_version: string | null;
            /** Held Out */
            held_out: boolean;
            /** Missed Metrics */
            missed_metrics: components["schemas"]["JudgeMetricId"][];
            /** False Alarm Metrics */
            false_alarm_metrics: components["schemas"]["JudgeMetricId"][];
        };
        /** CalibrationPairsResponse */
        CalibrationPairsResponse: {
            /** Pairs */
            pairs: components["schemas"]["CalibrationPairOut"][];
            /** Total */
            total: number;
        };
        /**
         * CalibrationQuadrantResponse
         * @description The four-cell breakdown, whole-corpus and per question type.
         */
        CalibrationQuadrantResponse: {
            overall: components["schemas"]["CalibrationResultsResponse"];
            /** Types */
            types: components["schemas"]["TypeCalibrationOut"][];
            /** Unattributable Metrics */
            unattributable_metrics: components["schemas"]["JudgeMetricId"][];
            /** Held Out Divisor */
            held_out_divisor: number;
        };
        /**
         * CalibrationResultsResponse
         * @description How often the advisory judge agreed with the professor (ADR-029).
         *
         *     Every rate is ``null`` when its denominator is zero, so a client can tell
         *     "no data yet" from "agreed with nothing". ``n`` counts questions, not
         *     reviews, and ``judge_accept_count`` is published so a rate resting on two
         *     questions is not read as a property of the judge.
         */
        CalibrationResultsResponse: {
            /** N */
            n: number;
            /** Judge Accept Count */
            judge_accept_count: number;
            /** Agreement */
            agreement: number | null;
            /** Auto Accept Precision */
            auto_accept_precision: number | null;
            /** Unsafe Auto Accept Rate */
            unsafe_auto_accept_rate: number | null;
            quadrant: components["schemas"]["QuadrantCounts"];
            /** Rubric Versions */
            rubric_versions: string[];
            /** Metrics */
            metrics: components["schemas"]["MetricAgreement"][];
            /** Subtopic Confusions */
            subtopic_confusions: components["schemas"]["SubtopicConfusion"][];
            /** Difficulty Confusions */
            difficulty_confusions: components["schemas"]["DifficultyConfusion"][];
        };
        /**
         * ChapterOut
         * @description One chapter and the sections beneath it.
         */
        ChapterOut: {
            /** Id */
            id: number;
            /** Book Id */
            book_id: number;
            /** Number */
            number: string | null;
            /** Title */
            title: string | null;
            /** Position */
            position: number;
            /** Start Page */
            start_page: number | null;
            /** End Page */
            end_page: number | null;
            /** Location Label */
            location_label: string | null;
            /** Is Unlabelled */
            is_unlabelled: boolean;
            structure_source: components["schemas"]["StructureSource"];
            structure_confidence: components["schemas"]["StructureConfidence"];
            /** Sections */
            sections: components["schemas"]["SectionSummary"][];
        };
        /**
         * ChunkGenerationSpec
         * @description One chunk's instruction on the spec sheet (ADR-044).
         *
         *     ``easy`` / ``medium`` / ``hard`` are how many questions this chunk should
         *     produce at each difficulty. ``question_types`` is the set they are drawn from,
         *     not one question per format: two medium questions with three formats chosen is
         *     still two questions.
         */
        ChunkGenerationSpec: {
            /** Section Id */
            section_id: number;
            /**
             * Easy
             * @default 0
             */
            easy: number;
            /**
             * Medium
             * @default 0
             */
            medium: number;
            /**
             * Hard
             * @default 0
             */
            hard: number;
            /** Question Types */
            question_types?: components["schemas"]["QuestionType"][];
        };
        /**
         * ClaimViolation
         * @description Why a generator's taxonomy claim was refused (ADR-032).
         *
         *     Named rather than free text because the retry prompt, the deterministic
         *     check and any later "how does this generator fail?" count all read the same
         *     value. A claim can break more than one rule at once, so these accumulate.
         * @enum {string}
         */
        ClaimViolation: "unknown_topic" | "unknown_subtopics" | "no_subtopic" | "too_many_subtopics" | "foreign_subtopics";
        /**
         * ClassSummaryOut
         * @description Cohort-wide numbers the roster's aggregate cards need, computed over every
         *     learner regardless of which roster page is open.
         */
        ClassSummaryOut: {
            /** Student Count */
            student_count: number;
            /** Measured Students */
            measured_students: number;
            /** Average Score */
            average_score?: number | null;
            /** Scored Attempts */
            scored_attempts?: components["schemas"]["ClassTrendAttemptOut"][];
            /** Weakness Cells */
            weakness_cells?: components["schemas"]["ClassWeaknessCellOut"][];
        };
        /**
         * ClassTrendAttemptOut
         * @description One scored answer, cohort-wide, for the class trend graph.
         */
        ClassTrendAttemptOut: {
            /** Student Id */
            student_id: number;
            /** Score */
            score: number;
            /** Answered At */
            answered_at?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Ordinal */
            ordinal: number;
        };
        /** ClassWeaknessCellOut */
        ClassWeaknessCellOut: {
            /** Subtopic Id */
            subtopic_id: number;
            /** Subtopic Name */
            subtopic_name: string;
            /** Topic Name */
            topic_name: string;
            /** Average Weakness */
            average_weakness: number;
            /** Student Count */
            student_count: number;
            /** Affected */
            affected?: components["schemas"]["ClassWeaknessStudentOut"][];
        };
        /** ClassWeaknessStudentOut */
        ClassWeaknessStudentOut: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Weakness */
            weakness: number;
            /** Answered */
            answered: number;
        };
        /**
         * ConceptConfidence
         * @description How sure the analysis is about a proposed concept or grouping.
         *
         *     A coarse three-value band rather than a number: a model asked for "0.83"
         *     produces a figure with no calibration behind it, whereas high / medium / low
         *     is a judgement it can actually make and a professor can actually act on.
         *     Deliberately distinct from :class:`StructureConfidence`, which is about
         *     *boundaries declared by a book document*, not about instructional analysis.
         * @enum {string}
         */
        ConceptConfidence: "high" | "medium" | "low";
        /**
         * ConfigResponse
         * @description Everything a client needs to render forms without hard-coding enums.
         */
        ConfigResponse: {
            /** App Name */
            app_name: string;
            /** Version */
            version: string;
            /** Environment */
            environment: string;
            /** Llm Configured */
            llm_configured: boolean;
            /** Llm Status */
            llm_status: string;
            /** Llm Model */
            llm_model: string;
            /** Embedding Model */
            embedding_model: string;
            /** Book Schema Version */
            book_schema_version: string;
            /** Taxonomy Schema Version */
            taxonomy_schema_version: string;
            /** Supported Book Extensions */
            supported_book_extensions: string[];
            /** Max Book Upload Mb */
            max_book_upload_mb: number;
            /** Difficulties */
            difficulties: components["schemas"]["EnumOption"][];
            /** Question Types */
            question_types: components["schemas"]["EnumOption"][];
            /** Question Statuses */
            question_statuses: components["schemas"]["EnumOption"][];
            /** Review Decisions */
            review_decisions: components["schemas"]["EnumOption"][];
            /** Rejection Reasons */
            rejection_reasons: components["schemas"]["EnumOption"][];
            /** Judge Calls Per Question */
            judge_calls_per_question: number;
        };
        /**
         * CountsResponse
         * @description Dashboard counts, one per section.
         */
        CountsResponse: {
            /** Books */
            books: number;
            /** Curriculum Versions */
            curriculum_versions: number;
            /** Questions */
            questions: number;
            /** Reviews */
            reviews: number;
            /** Learned Instructions */
            learned_instructions: number;
            /** Students */
            students: number;
        };
        /**
         * CoverageCell
         * @description One (subtopic, difficulty) pair and how many questions cover it.
         */
        CoverageCell: {
            difficulty: components["schemas"]["Difficulty"];
            /** Count */
            count: number;
            state: components["schemas"]["CoverageState"];
            /**
             * Needed
             * @default 0
             */
            needed: number;
        };
        /**
         * CoverageReportResponse
         * @description The subtopic x difficulty grid, and what it means (ADR-036).
         *
         *     ``empty_cells`` and ``thin_cells`` stay separate: an empty cell is a request
         *     the adaptive engine cannot satisfy, a thin one is satisfied repetitively.
         *     ``is_servable`` is the blocking condition; ``is_ready`` is the comfortable
         *     one.
         */
        CoverageReportResponse: {
            /** Curriculum Version Id */
            curriculum_version_id: number | null;
            /** Curriculum Label */
            curriculum_label: string | null;
            /** Set Version Id */
            set_version_id: number | null;
            /** Minimum Per Cell */
            minimum_per_cell: number;
            /** Question Count */
            question_count: number;
            /** Total Cells */
            total_cells: number;
            /** Empty Cells */
            empty_cells: number;
            /** Thin Cells */
            thin_cells: number;
            /** Ready Cells */
            ready_cells: number;
            /** Gap Count */
            gap_count: number;
            /** Questions Needed */
            questions_needed: number;
            /** Is Servable */
            is_servable: boolean;
            /** Is Ready */
            is_ready: boolean;
            /** Topics */
            topics: components["schemas"]["TopicCoverage"][];
            /** Subtopics */
            subtopics: components["schemas"]["SubtopicCoverage"][];
            /** Active Run Topic Ids */
            active_run_topic_ids?: number[];
        };
        /**
         * CoverageState
         * @description What one cell of the grid means for a training run.
         * @enum {string}
         */
        CoverageState: "empty" | "thin" | "ready";
        /**
         * CoverageTargetRef
         * @description One cell a professor asked to have filled.
         */
        CoverageTargetRef: {
            /** Subtopic Id */
            subtopic_id: number;
            difficulty: components["schemas"]["Difficulty"];
        };
        /**
         * CreateQuestionSetRequest
         * @description Freeze the currently approved questions under a name.
         */
        CreateQuestionSetRequest: {
            /** Label */
            label: string;
            /** Notes */
            notes?: string | null;
        };
        /** CreateStudentRequest */
        CreateStudentRequest: {
            /** Display Name */
            display_name: string;
            /**
             * Email
             * Format: email
             */
            email: string;
        };
        /**
         * CurriculumItemLabelUpdate
         * @description A professor's edit to one topic's or subtopic's display name.
         *
         *     Only the two label fields exist here, so moving a subtopic between topics,
         *     reordering, or rewriting a stable id is not refused -- it is inexpressible.
         *     An omitted field is left alone; an empty description clears it.
         */
        CurriculumItemLabelUpdate: {
            /** Name */
            name?: string | null;
            /** Description */
            description?: string | null;
        };
        /**
         * CurriculumItemStatus
         * @description A professor's verdict on one proposed topic or subtopic.
         *
         *     Separate from :class:`CurriculumStatus`, which is the whole version's state:
         *     a professor works through a proposal item by item, so each item carries its
         *     own review status. Everything the proposer writes starts at ``PROPOSED``;
         *     nothing is ever persisted as though it had already been reviewed.
         * @enum {string}
         */
        CurriculumItemStatus: "proposed" | "accepted" | "edited" | "rejected";
        /** CurriculumListResponse */
        CurriculumListResponse: {
            /** Versions */
            versions: components["schemas"]["CurriculumVersionSummary"][];
            /** Approved Version Id */
            approved_version_id: number | null;
            /** Latest Version Id */
            latest_version_id: number | null;
            /** Total */
            total: number;
        };
        /**
         * CurriculumStatus
         * @description Lifecycle of a proposed Topic -> Subtopic curriculum.
         *
         *     Only an ``APPROVED`` curriculum version may ground question generation.
         * @enum {string}
         */
        CurriculumStatus: "proposed" | "under_review" | "approved" | "superseded";
        /**
         * CurriculumVersionDeletion
         * @description What a completed delete removed, and what it cost.
         */
        CurriculumVersionDeletion: {
            /** Deleted Version Id */
            deleted_version_id: number;
            /** Deleted Topic Count */
            deleted_topic_count: number;
            /** Deleted Subtopic Count */
            deleted_subtopic_count: number;
            stranded: components["schemas"]["CurriculumVersionUsage"];
        };
        /**
         * CurriculumVersionDetail
         * @description One curriculum version with its Topic -> Subtopic hierarchy.
         */
        CurriculumVersionDetail: {
            version: components["schemas"]["CurriculumVersionSummary"];
            /** Topic Count */
            topic_count: number;
            /** Subtopic Count */
            subtopic_count: number;
            /** Topics */
            topics: components["schemas"]["TopicOut"][];
            /** Books */
            books: components["schemas"]["BookSummary"][];
            extraction_metadata: components["schemas"]["DisplayExtractionMetadata"] | null;
            /** Warnings */
            warnings: components["schemas"]["DisplayProposalWarning"][];
            usage: components["schemas"]["CurriculumVersionUsage"];
        };
        /**
         * CurriculumVersionLabelUpdate
         * @description A professor's edit to a curriculum version's label.
         *
         *     The tree is declared by the uploaded document and is never edited here, and
         *     neither is the version's status: which taxonomy the product is grounded in
         *     changes by uploading one, not by editing a row (ADR-021).
         */
        CurriculumVersionLabelUpdate: {
            /** Label */
            label: string;
        };
        /**
         * CurriculumVersionSummary
         * @description One curriculum version, without its tree.
         */
        CurriculumVersionSummary: {
            /** Id */
            id: number;
            /** Label */
            label: string;
            status: components["schemas"]["CurriculumStatus"];
            /** Generated By */
            generated_by: string | null;
            /** Source Book Ids */
            source_book_ids: number[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Approved At */
            approved_at: string | null;
            /** Topic Count */
            topic_count: number;
            /** Subtopic Count */
            subtopic_count: number;
        };
        /**
         * CurriculumVersionUsage
         * @description What still points at a curriculum version, and how much is unrepairable.
         */
        CurriculumVersionUsage: {
            /** Question Count */
            question_count: number;
            /** Question Subtopic Link Count */
            question_subtopic_link_count: number;
            /** Question Set Count */
            question_set_count: number;
            /** Student Count */
            student_count: number;
            /** Attempt Count */
            attempt_count: number;
            /** Is Approved */
            is_approved: boolean;
        };
        /**
         * Difficulty
         * @description Question difficulty. Selected from student topic mastery.
         * @enum {string}
         */
        Difficulty: "easy" | "medium" | "hard";
        /**
         * DifficultyConfusion
         * @description One pair of disagreeing difficulties, and how often it occurred.
         */
        DifficultyConfusion: {
            requested: components["schemas"]["Difficulty"];
            judged: components["schemas"]["Difficulty"];
            /** Count */
            count: number;
        };
        /**
         * DisplayExtractionMetadata
         * @description Legacy LLM proposal metadata used only to render existing rows.
         */
        DisplayExtractionMetadata: {
            /** Generated By */
            generated_by: string;
            /** Stage A Version */
            stage_a_version: string;
            /** Stage B Version */
            stage_b_version: string;
            /**
             * Books Analysed
             * @default 0
             */
            books_analysed: number;
            /**
             * Sections Analysed
             * @default 0
             */
            sections_analysed: number;
            /**
             * Sections Skipped
             * @default 0
             */
            sections_skipped: number;
            /**
             * Candidates Extracted
             * @default 0
             */
            candidates_extracted: number;
            /**
             * Groups Returned
             * @default 0
             */
            groups_returned: number;
        };
        /**
         * DisplayProposalWarning
         * @description One warning retained on a legacy LLM-generated curriculum version.
         */
        DisplayProposalWarning: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Location */
            location?: string | null;
        };
        /**
         * EnumOption
         * @description One selectable enum value plus the label a UI should show for it.
         */
        EnumOption: {
            /** Value */
            value: string;
            /** Label */
            label: string;
        };
        /** ErrorModel */
        ErrorModel: {
            /** Detail */
            detail: string | {
                [key: string]: string;
            };
        };
        /**
         * EvaluationHistoryEntry
         * @description One retained evaluation of a question (ADR-030).
         *
         *     ``evaluation`` is the stored blob rather than a parsed
         *     :class:`PedagogicalEvaluation`, because history includes rows written under
         *     an older rubric that may no longer validate. Dropping them would be losing
         *     the record this table exists to keep, so the summary columns beside it are
         *     what a client should read first.
         */
        EvaluationHistoryEntry: {
            /** Id */
            id: number;
            /** Question Id */
            question_id: number;
            /** Run Id */
            run_id: string;
            trigger: components["schemas"]["EvaluationTrigger"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Judge Model */
            judge_model: string | null;
            /** Rubric Version */
            rubric_version: string | null;
            /** Eval Status */
            eval_status: string | null;
            /** Gate */
            gate: string | null;
            /** Passed Metrics */
            passed_metrics: number | null;
            /** Is Current */
            is_current: boolean;
            /** Evaluation */
            evaluation: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * EvaluationHistoryResponse
         * @description A question's judge history, newest first.
         */
        EvaluationHistoryResponse: {
            /** Question Id */
            question_id: number;
            /** Evaluations */
            evaluations: components["schemas"]["EvaluationHistoryEntry"][];
            /** Total */
            total: number;
        };
        /**
         * EvaluationTrigger
         * @description What caused a pedagogical evaluation to be recorded.
         *
         *     Every stored evaluation names its cause, so a bulk re-run's output stays
         *     distinguishable from the evaluation a question received when it was first
         *     generated (ADR-030).
         * @enum {string}
         */
        EvaluationTrigger: "generation" | "batch_rerun";
        /**
         * ExtractionWarning
         * @description One thing that went wrong, or could not be determined, during extraction.
         *
         *     Warnings are surfaced to the professor rather than logged and forgotten: an
         *     extraction that quietly dropped half a book is worse than one that says so.
         */
        ExtractionWarning: {
            code: components["schemas"]["ExtractionWarningCode"];
            /** Message */
            message: string;
            /** Location */
            location?: string | null;
            /** @default defect */
            severity: components["schemas"]["WarningSeverity"];
        };
        /**
         * ExtractionWarningCode
         * @description Machine-readable caveats a book document may declare about itself.
         *
         *     A closed vocabulary so the UI can group and explain them; ``OTHER`` is the
         *     escape hatch for a producer-specific caveat, whose detail lives in the
         *     warning's message.
         * @enum {string}
         */
        ExtractionWarningCode: "no_page_numbers" | "producer_inferred_structure" | "missing_heading" | "source_text_unreadable" | "section_text_truncated" | "metadata_unavailable" | "other";
        /**
         * FailedRunTarget
         * @description A gap target whose generation call reached the provider and failed.
         *
         *     The section was retrieved and the request was well formed; the model call
         *     itself did not return a usable question. What the run already produced is
         *     kept (ADR-032), so this is reported beside ``generated`` rather than raised.
         */
        FailedRunTarget: {
            /** Subtopic Id */
            subtopic_id: number;
            difficulty: components["schemas"]["Difficulty"];
            /** Section Id */
            section_id: number;
            /** Error */
            error: string;
        };
        /**
         * FieldLimitOut
         * @description One field of the taxonomy contract, and the bounds the validator enforces.
         *
         *     Published structurally as well as inside the prompt, so a form can bind its
         *     input limits to the contract rather than hard-coding them.
         */
        FieldLimitOut: {
            /** Path */
            path: string;
            /** Required */
            required: boolean;
            /** Kind */
            kind: string;
            /** Min Length */
            min_length: number | null;
            /** Max Length */
            max_length: number | null;
            /** Meaning */
            meaning: string;
        };
        /**
         * FillGapsRequest
         * @description The gaps a professor selected on the coverage page.
         *
         *     Deliberately a list of *targets*, not a question count. The generator picks
         *     its own topic and subtopics from the chunk it is given (ADR-031), so asking
         *     for "seven questions" would promise an aim the generator does not accept.
         */
        FillGapsRequest: {
            /** Targets */
            targets: components["schemas"]["CoverageTargetRef"][];
        };
        /**
         * GenerateBatchRequest
         * @description A per-chunk generation run: many chunks, each with its own instruction.
         */
        GenerateBatchRequest: {
            /** Curriculum Version Id */
            curriculum_version_id?: number | null;
            /** Chunks */
            chunks: components["schemas"]["ChunkGenerationSpec"][];
            /** Seed */
            seed?: string | null;
        };
        /**
         * GenerateBatchResponse
         * @description What a per-chunk run produced, and what it had planned to produce.
         *
         *     ``created`` may be short of ``planned`` when the provider failed part-way: each
         *     question commits on its own, so a partial batch is a real outcome (ADR-032).
         */
        GenerateBatchResponse: {
            /** Created */
            created: number;
            /** Question Ids */
            question_ids: number[];
            /** Questions */
            questions: components["schemas"]["QuestionSummary"][];
            /** Planned */
            planned: components["schemas"]["PlannedQuestionOut"][];
        };
        /**
         * GenerateQuestionsRequest
         * @description A generation request.
         *
         *     Exactly one source selection is required: either ``section_ids`` or
         *     ``all_sections_of_book``. One question is generated per resolved section.
         *
         *     No topic or subtopic: the generator reads the section and classifies its own
         *     question against the approved taxonomy (ADR-031).
         */
        GenerateQuestionsRequest: {
            /** Curriculum Version Id */
            curriculum_version_id?: number | null;
            question_type: components["schemas"]["QuestionType"];
            difficulty: components["schemas"]["Difficulty"];
            /** Book Id */
            book_id?: number | null;
            /** Section Ids */
            section_ids?: number[] | null;
            /**
             * All Sections Of Book
             * @default false
             */
            all_sections_of_book: boolean;
            /** Seed */
            seed?: string | null;
        };
        /** GenerateQuestionsResponse */
        GenerateQuestionsResponse: {
            /** Created */
            created: number;
            /** Question Ids */
            question_ids: number[];
            /** Questions */
            questions: components["schemas"]["QuestionSummary"][];
        };
        /**
         * GeneratedRunQuestion
         * @description One question a generation run produced, and how its aim landed.
         *
         *     ``requested_subtopic_id`` is the gap the professor picked; ``claimed_*`` is
         *     what the generator classified the question as after reading the section
         *     (ADR-031). ``aim_matched`` is the two agreeing at the topic level -- reported,
         *     never used to filter, so a drift is visible in the review queue instead.
         */
        GeneratedRunQuestion: {
            /** Question Id */
            question_id: number;
            /** Requested Subtopic Id */
            requested_subtopic_id: number;
            requested_difficulty: components["schemas"]["Difficulty"];
            /** Claimed Topic Id */
            claimed_topic_id: number | null;
            /** Claimed Subtopic Ids */
            claimed_subtopic_ids: number[];
            /** Section Id */
            section_id: number;
            status: components["schemas"]["QuestionStatus"];
            /** Aim Matched */
            aim_matched: boolean;
        };
        /**
         * GenerationAttempt
         * @description One model call that tried to produce this question (ADR-032).
         *
         *     A question that took three attempts is one question with three attempts, not
         *     three questions: separate rows would fill the bank with drafts that every
         *     later query would have to learn to exclude, and the adaptive engine has no
         *     use for a draft that was never valid.
         *
         *     The claim is recorded as the model made it, duplicates and non-existent ids
         *     included, because it is the evidence for how this generator fails. What
         *     actually reached the columns is narrower -- see
         *     :class:`~app.generation.spec.TaxonomyClaimOutcome`.
         */
        GenerationAttempt: {
            /** Number */
            number: number;
            /** Claimed Topic Id */
            claimed_topic_id?: number | null;
            /** Claimed Subtopic Ids */
            claimed_subtopic_ids?: number[];
            /** Violations */
            violations?: components["schemas"]["ClaimViolation"][];
            /** Detail */
            detail?: string | null;
            /** Failed Checks */
            failed_checks?: components["schemas"]["QuestionCheck"][];
            /**
             * Malformed
             * @default false
             */
            malformed: boolean;
            /** Accepted */
            accepted: boolean;
            /** Model */
            model?: string | null;
        };
        /**
         * GenerationPlanChapter
         * @description One chapter, and the candidate sections beneath it.
         */
        GenerationPlanChapter: {
            /** Id */
            id: number;
            /** Label */
            label: string;
            /** Location Label */
            location_label: string | null;
            /** Sections */
            sections: components["schemas"]["GenerationPlanSection"][];
        };
        /**
         * GenerationPlanResponse
         * @description The chunk plan: every candidate section, and the cost of the selection.
         */
        GenerationPlanResponse: {
            book: components["schemas"]["BookSummary"];
            /** Chapters */
            chapters: components["schemas"]["GenerationPlanChapter"][];
            totals: components["schemas"]["GenerationPlanTotals"];
            /** Blockers */
            blockers: string[];
        };
        /**
         * GenerationPlanSection
         * @description One candidate source section, and what generating from it would mean.
         */
        GenerationPlanSection: {
            section: components["schemas"]["SectionSummary"];
            /** Existing Question Count */
            existing_question_count: number;
            /** Selected */
            selected: boolean;
            /** Selectable */
            selectable: boolean;
        };
        /**
         * GenerationPlanTotals
         * @description What the selected run costs, before any model call is made.
         */
        GenerationPlanTotals: {
            /** Sections Available */
            sections_available: number;
            /** Sections Selected */
            sections_selected: number;
            /** Questions To Create */
            questions_to_create: number;
            /** Generation Calls */
            generation_calls: number;
            /** Judge Calls */
            judge_calls: number;
            /** Source Chars */
            source_chars: number;
        };
        /**
         * GenerationRunResponse
         * @description The outcome of one coverage "Generate" run.
         *
         *     Always 200, even when ``failed`` is non-empty: a run that produced some
         *     questions and lost others part-way is a real, reportable outcome, not an
         *     error to swallow the successes for.
         */
        GenerationRunResponse: {
            /** Run Id */
            run_id: string;
            /** Generated */
            generated: components["schemas"]["GeneratedRunQuestion"][];
            /** Skipped */
            skipped: components["schemas"]["SkippedRunTarget"][];
            /** Failed */
            failed: components["schemas"]["FailedRunTarget"][];
            /** Possible Duplicates */
            possible_duplicates: number;
        };
        /**
         * GeneratorKind
         * @description Which generator produced a question.
         *
         *     Base and personalized generators must stay distinguishable so their output
         *     quality can be compared over time.
         * @enum {string}
         */
        GeneratorKind: "base" | "personalized";
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthResponse
         * @description Liveness, including a real database round-trip.
         */
        HealthResponse: {
            /** Status */
            status: string;
            /** Version */
            version: string;
            /** Environment */
            environment: string;
            /** Database Ok */
            database_ok: boolean;
            /** Llm Configured */
            llm_configured: boolean;
            /** Llm Status */
            llm_status: string;
        };
        /**
         * InstructionStamp
         * @description Which type instruction produced a question (ADR-040).
         *
         *     ``generator_label`` names the code path and is always ``base@1``; this names
         *     the text. Two questions with the same label and different fingerprints were
         *     written from different instructions.
         */
        InstructionStamp: {
            /**
             * Source
             * @enum {string}
             */
            source: "learned" | "shipped";
            /** Fingerprint */
            fingerprint: string;
            /** Rule Count */
            rule_count: number;
            /** Review Count */
            review_count: number;
        };
        /**
         * JudgeBatchRunOut
         * @description One bulk re-run, as a professor needs to see it.
         *
         *     ``provider_batch_ids`` is a list because a bank larger than the per-job cap
         *     is split into several provider jobs that share this one run id.
         */
        JudgeBatchRunOut: {
            /** Run Id */
            run_id: string;
            status: components["schemas"]["JudgeBatchStatus"];
            /** Model */
            model: string;
            /** Rubric Version */
            rubric_version: string;
            /** Provider Batch Ids */
            provider_batch_ids: string[];
            /** Question Count */
            question_count: number;
            /** Completed Count */
            completed_count: number;
            /** Failed Count */
            failed_count: number;
            /** Submitted At */
            submitted_at: string | null;
            /** Completed At */
            completed_at: string | null;
            /** Error Detail */
            error_detail: string | null;
        };
        /**
         * JudgeBatchStatus
         * @description Lifecycle of one bulk judge re-run.
         *
         *     The provider reports a finer sequence (``validating``, ``finalizing``);
         *     those map onto ``IN_PROGRESS`` because they mean the same thing to a
         *     professor waiting for results. ``CANCELLED`` at the provider is recorded as
         *     ``FAILED`` with the cancellation named in ``error_detail``.
         * @enum {string}
         */
        JudgeBatchStatus: "submitted" | "in_progress" | "completed" | "failed" | "expired";
        /**
         * JudgeGate
         * @description The judge's overall suggestion, derived from how many metrics passed.
         *
         *     Advisory only. The professor's own :class:`ReviewDecision` is the authority;
         *     this is what the professor sees beside the question while deciding.
         * @enum {string}
         */
        JudgeGate: "approved" | "needs_review" | "reject";
        /**
         * JudgeMetricId
         * @description The four things the advisory judge is asked, one model call each.
         *
         *     Separate calls rather than one rubric: a single reviewer asked for four
         *     unrelated judgements at once lets a strong opinion on one bleed into the
         *     others, and a malformed answer costs all four.
         * @enum {string}
         */
        JudgeMetricId: "issues" | "subtopic" | "difficulty" | "generatability";
        /** JudgePromptListResponse */
        JudgePromptListResponse: {
            /** Prompts */
            prompts: components["schemas"]["JudgePromptOut"][];
            /** Rubric Version */
            rubric_version: string;
            /** Shipped Rubric Version */
            shipped_rubric_version: string;
        };
        /**
         * JudgePromptOut
         * @description One metric judge's system prompt, shipped or professor-edited (ADR-038).
         */
        JudgePromptOut: {
            metric: components["schemas"]["JudgeMetricId"];
            /** Label */
            label: string;
            /** System Prompt */
            system_prompt: string;
            /** Shipped Prompt */
            shipped_prompt: string;
            /** Edited */
            edited: boolean;
            /** Learned */
            learned: boolean;
            /** Rules */
            rules: string[];
            /** Evidence Count */
            evidence_count: number;
            /** Available Disagreements */
            available_disagreements: number;
            /** Revision */
            revision: number;
            /** Note */
            note: string | null;
            /** Updated At */
            updated_at: string | null;
        };
        /**
         * JudgePromptRefreshResponse
         * @description What one learned judge repair did (ADR-039).
         */
        JudgePromptRefreshResponse: {
            prompt: components["schemas"]["JudgePromptOut"];
            /** Rubric Version */
            rubric_version: string;
            /** Rubric Version Changed */
            rubric_version_changed: boolean;
            /** Learned */
            learned: boolean;
            /** Rule Count */
            rule_count: number;
            /** Evidence Count */
            evidence_count: number;
        };
        /**
         * JudgePromptRequest
         * @description A professor's replacement text for one judge.
         */
        JudgePromptRequest: {
            /** System Prompt */
            system_prompt: string;
            /** Note */
            note?: string | null;
        };
        /** JudgePromptSaveResponse */
        JudgePromptSaveResponse: {
            prompt: components["schemas"]["JudgePromptOut"];
            /** Rubric Version */
            rubric_version: string;
            /** Rubric Version Changed */
            rubric_version_changed: boolean;
        };
        /**
         * MasteryBand
         * @description Coarse band derived from a BKT mastery probability.
         * @enum {string}
         */
        MasteryBand: "low" | "medium" | "high";
        /**
         * MetricAgreement
         * @description How often one judge's answer matched the professor's on the same point.
         */
        MetricAgreement: {
            metric: components["schemas"]["JudgeMetricId"];
            /** N */
            n: number;
            /** Agreement */
            agreement: number | null;
            /** Missed */
            missed: number;
            /** False Alarms */
            false_alarms: number;
        };
        /**
         * MetricFaultsOut
         * @description How often one judge was at fault within one panel (ADR-041).
         */
        MetricFaultsOut: {
            metric: components["schemas"]["JudgeMetricId"];
            /** Label */
            label: string;
            /** Missed */
            missed: number;
            /** False Alarms */
            false_alarms: number;
            /** Faults */
            faults: number;
            /** Fault Rate */
            fault_rate: number | null;
        };
        /**
         * MetricResult
         * @description One judge's answer, reduced to a pass flag plus what it actually said.
         *
         *     ``passed`` is derived, never reported by the judge: three of the four judges
         *     return a value rather than a verdict, and whether that value counts as a pass
         *     is decided here by comparing it with what the generator claimed. A judge
         *     asked to grade itself would be answering a different question.
         */
        MetricResult: {
            metric: components["schemas"]["JudgeMetricId"];
            /** @default completed */
            status: components["schemas"]["MetricStatus"];
            /** Passed */
            passed?: boolean | null;
            /** Rationale */
            rationale?: string | null;
            /** Error Detail */
            error_detail?: string | null;
            /** Issue Codes */
            issue_codes?: components["schemas"]["RejectionReason"][];
            /** Custom Issue */
            custom_issue?: string | null;
            /** Proposed Topic Id */
            proposed_topic_id?: number | null;
            /** Proposed Subtopic Ids */
            proposed_subtopic_ids?: number[];
            proposed_difficulty?: components["schemas"]["Difficulty"] | null;
        };
        /**
         * MetricStatus
         * @description Whether one judge answered.
         * @enum {string}
         */
        MetricStatus: "completed" | "error";
        /**
         * ParsonsBlockOut
         * @description One draggable block, including the indentation it should display with.
         */
        ParsonsBlockOut: {
            /** Id */
            id: string;
            /** Text */
            text: string;
            /** Indent */
            indent: number;
        };
        /**
         * PedagogicalEvalStatus
         * @description Whether the judges ran at all, and how completely.
         * @enum {string}
         */
        PedagogicalEvalStatus: "completed" | "partial" | "skipped" | "error";
        /**
         * PedagogicalEvaluation
         * @description Every judge answer for one question, plus the gate derived from them.
         */
        PedagogicalEvaluation: {
            /** Question Id */
            question_id?: number | null;
            status: components["schemas"]["PedagogicalEvalStatus"];
            /** Skip Reason */
            skip_reason?: string | null;
            gate?: components["schemas"]["JudgeGate"] | null;
            /** Metrics */
            metrics?: components["schemas"]["MetricResult"][];
            /** Judge Model */
            judge_model?: string | null;
            /**
             * Rubric Version
             * @default question-metrics@1
             */
            rubric_version: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at?: string;
        };
        /**
         * PersonalizationEvidence
         * @description Which preferences and reviews shaped a personalized question (ADR-025).
         */
        PersonalizationEvidence: {
            /** Preference Ids */
            preference_ids: number[];
            /** Review Ids */
            review_ids: number[];
            /** Profile Version */
            profile_version?: string | null;
        };
        /**
         * PlannedQuestionOut
         * @description One question a compiled run will ask for, in the order it will be asked.
         */
        PlannedQuestionOut: {
            /** Section Id */
            section_id: number;
            difficulty: components["schemas"]["Difficulty"];
            question_type: components["schemas"]["QuestionType"];
        };
        /**
         * PollBatchRunResponse
         * @description What one poll collected.
         *
         *     ``already_recorded`` is published so that re-polling a finished run reads as
         *     "nothing new" rather than as a run that produced nothing.
         */
        PollBatchRunResponse: {
            run: components["schemas"]["JudgeBatchRunOut"];
            status: components["schemas"]["JudgeBatchStatus"];
            /** Ingested */
            ingested: number;
            /** Failed */
            failed: number;
            /** Already Recorded */
            already_recorded: number;
        };
        /**
         * PossibleDuplicateOut
         * @description One existing question a freshly generated one scored as a likely
         *     duplicate of (coverage Generate m3). A soft flag, never a gate.
         */
        PossibleDuplicateOut: {
            /** Question Id */
            question_id: number;
            /** Prompt Excerpt */
            prompt_excerpt: string;
            /** Score */
            score: number;
        };
        /**
         * QuadrantCell
         * @description Which of the four judge/professor outcomes a reviewed question fell into.
         *
         *     The two agreeing cells are not interchangeable and neither are the two
         *     disagreeing ones (ADR-034). Only :attr:`MISSED` makes auto-acceptance unsafe:
         *     it is the sole cell where the judge vouched for a question the professor
         *     would not have kept.
         * @enum {string}
         */
        QuadrantCell: "confirmed_good" | "missed" | "false_alarm" | "confirmed_bad";
        /**
         * QuadrantCounts
         * @description How many pairs fell into each of the four outcomes (ADR-034).
         *
         *     ``auto_accept_precision`` is ``confirmed_good / (confirmed_good + missed)``:
         *     the two cells where the judge did *not* accept are absent from it, because
         *     auto-acceptance would never have released those questions. Publishing all
         *     four makes that visible, so a professor can see which cell to work on rather
         *     than inferring it from a rate.
         */
        QuadrantCounts: {
            /**
             * Confirmed Good
             * @default 0
             */
            confirmed_good: number;
            /**
             * Missed
             * @default 0
             */
            missed: number;
            /**
             * False Alarm
             * @default 0
             */
            false_alarm: number;
            /**
             * Confirmed Bad
             * @default 0
             */
            confirmed_bad: number;
        };
        /**
         * QuestionCheck
         * @description One deterministic or LLM check performed on a question.
         */
        QuestionCheck: {
            /** Name */
            name: string;
            /** Passed */
            passed: boolean;
            /**
             * Deterministic
             * @default true
             */
            deterministic: boolean;
            /**
             * Severity
             * @default error
             * @constant
             */
            severity: "error";
            /** Detail */
            detail?: string | null;
            /** Evidence */
            evidence?: string | null;
        };
        /**
         * QuestionDetail
         * @description One question with everything the review screen needs.
         */
        QuestionDetail: {
            question: components["schemas"]["QuestionSummary"];
            /** Reference Solution */
            reference_solution: string | null;
            /** Tests */
            tests: string | null;
            /** Spec */
            spec: {
                [key: string]: unknown;
            } | null;
            /** Content */
            content: {
                [key: string]: unknown;
            } | null;
            /** Sources */
            sources: {
                [key: string]: unknown;
            }[];
            taxonomy: components["schemas"]["QuestionTaxonomy"];
            /** Validation Passed */
            validation_passed: boolean | null;
            /** Validation Checks */
            validation_checks: components["schemas"]["QuestionCheck"][];
            /** Generation Attempts */
            generation_attempts: components["schemas"]["GenerationAttempt"][];
            pedagogical_eval: components["schemas"]["PedagogicalEvaluation"] | null;
            /** Pedagogical Error Message */
            pedagogical_error_message: string | null;
            personalization: components["schemas"]["PersonalizationEvidence"] | null;
            /** Original Prompt */
            original_prompt: string | null;
            /** Original Reference Solution */
            original_reference_solution: string | null;
            /** Original Tests */
            original_tests: string | null;
            /** Reviews */
            reviews: components["schemas"]["ReviewOut"][];
        };
        /**
         * QuestionKind
         * @description How a question is scored.
         *
         *     ``TESTABLE_PROGRAM``: score = passed_tests / total_tests * 100.
         *     ``DISCRETE``: naturally discrete, scored 0 or 100.
         * @enum {string}
         */
        QuestionKind: "testable_program" | "discrete";
        /** QuestionListResponse */
        QuestionListResponse: {
            /** Questions */
            questions: components["schemas"]["QuestionSummary"][];
            /** Status Counts */
            status_counts: {
                [key: string]: number;
            };
            /** Curriculum Version Counts */
            curriculum_version_counts: {
                [key: string]: number;
            };
            /** Total */
            total: number;
            status?: components["schemas"]["QuestionStatus"] | null;
            /** Curriculum Version Id */
            curriculum_version_id?: number | null;
            /** Run Id */
            run_id?: string | null;
        };
        /** QuestionSetListResponse */
        QuestionSetListResponse: {
            /** Sets */
            sets: components["schemas"]["QuestionSetOut"][];
            /** Total */
            total: number;
        };
        /**
         * QuestionSetOut
         * @description One frozen set of approved questions.
         *
         *     ``question_count`` is what was frozen; ``member_count`` is what is still
         *     there. They differ only if a member question was deleted, and publishing
         *     both is what makes that visible rather than silently rewriting the set's
         *     size.
         */
        QuestionSetOut: {
            /** Id */
            id: number;
            /** Label */
            label: string;
            /** Notes */
            notes: string | null;
            /** Curriculum Version Id */
            curriculum_version_id: number | null;
            /** Question Count */
            question_count: number;
            /** Member Count */
            member_count: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Question Ids */
            question_ids: number[];
            /**
             * Is Prod
             * @default false
             */
            is_prod: boolean;
        };
        /**
         * QuestionStatus
         * @description Lifecycle of a generated question through validation and review.
         * @enum {string}
         */
        QuestionStatus: "generated" | "validation_passed" | "validation_failed" | "approved" | "rejected";
        /**
         * QuestionSummary
         * @description One generated question, without its solution, tests or reports.
         */
        QuestionSummary: {
            /** Id */
            id: number;
            /** Prompt */
            prompt: string;
            kind: components["schemas"]["QuestionKind"];
            question_type: components["schemas"]["QuestionType"] | null;
            difficulty: components["schemas"]["Difficulty"];
            status: components["schemas"]["QuestionStatus"];
            /** Curriculum Version Id */
            curriculum_version_id: number | null;
            /** Topic Id */
            topic_id: number | null;
            /** Subtopic Ids */
            subtopic_ids: number[];
            generator_kind: components["schemas"]["GeneratorKind"];
            /** Generator Name */
            generator_name: string;
            /** Generator Version */
            generator_version: string;
            /** Generator Label */
            generator_label: string;
            instruction: components["schemas"]["InstructionStamp"] | null;
            /** Validation Passed */
            validation_passed: boolean | null;
            /** Priority */
            priority: number;
            /** Times Used */
            times_used: number;
            /** Is Edited */
            is_edited: boolean;
            /** Regenerated From Question Id */
            regenerated_from_question_id: number | null;
            /** Possible Duplicate Of */
            possible_duplicate_of: components["schemas"]["PossibleDuplicateOut"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Updated At */
            updated_at: string | null;
        };
        /**
         * QuestionTaxonomy
         * @description Display names for the ids a question carries, resolved where possible.
         */
        QuestionTaxonomy: {
            /** Curriculum */
            curriculum: string;
            /** Topic */
            topic: string;
            /** Subtopics */
            subtopics: string[];
        };
        /**
         * QuestionType
         * @description Assessment format (independent of scoring mode).
         * @enum {string}
         */
        QuestionType: "multiple_choice" | "true_false" | "output_prediction" | "code_completion" | "debugging" | "parsons" | "coding";
        /** ReasonCount */
        ReasonCount: {
            code: components["schemas"]["RejectionReason"];
            /** Label */
            label: string;
            /** Count */
            count: number;
        };
        /**
         * RegenerateQuestionRequest
         * @description Regenerate one existing question with instructor feedback.
         *
         *     The feedback is threaded into the generation prompt. The source question is
         *     never modified -- a new question is produced (ADR-002).
         */
        RegenerateQuestionRequest: {
            /** Feedback */
            feedback: string;
            /** Professor Id */
            professor_id?: number | null;
        };
        /** RegenerateQuestionResponse */
        RegenerateQuestionResponse: {
            /** Question Id */
            question_id: number;
            /** Regenerated From Question Id */
            regenerated_from_question_id: number;
            question: components["schemas"]["QuestionSummary"];
        };
        /**
         * RejectionReason
         * @description Structured professor rationale for reject or edit decisions.
         * @enum {string}
         */
        RejectionReason: "technically_incorrect" | "incorrect_answer" | "incorrect_tests" | "not_grounded_in_source" | "wrong_topic_subtopic" | "too_easy" | "too_difficult" | "ambiguous" | "poor_wording" | "poor_distractors" | "poor_tests" | "not_pedagogically_useful" | "too_similar_repetitive" | "other";
        /**
         * ResumeStudentRequest
         * @description A returning browser identifying itself against one classroom link.
         */
        ResumeStudentRequest: {
            /** Resume Token */
            resume_token: string;
            /** Set Version Id */
            set_version_id: number;
        };
        /**
         * RetrievedSectionOut
         * @description One book section returned by semantic retrieval, with its citation.
         */
        RetrievedSectionOut: {
            /** Section Id */
            section_id: number;
            /** Book Id */
            book_id: number;
            /** Book Title */
            book_title: string;
            /** Chapter Title */
            chapter_title: string | null;
            /** Section Number */
            section_number: string | null;
            /** Section Title */
            section_title: string | null;
            /** Score */
            score: number;
            /** Snippet */
            snippet: string;
        };
        /**
         * ReviewDecision
         * @description A professor's verdict on a generated question.
         *
         *     ``EDIT`` means approved-with-changes; the generated original is always
         *     retained alongside the edit (see ``docs/DECISIONS.md``).
         * @enum {string}
         */
        ReviewDecision: "approve" | "reject" | "edit";
        /** ReviewListResponse */
        ReviewListResponse: {
            /** Reviews */
            reviews: components["schemas"]["ReviewOut"][];
            /** Total */
            total: number;
        };
        /**
         * ReviewOut
         * @description One immutable review record.
         */
        ReviewOut: {
            /** Id */
            id: number;
            /** Question Id */
            question_id: number;
            decision: components["schemas"]["ReviewDecision"];
            /** Reasons */
            reasons: components["schemas"]["RejectionReason"][];
            /** Reason Labels */
            reason_labels: string[];
            /** Comment */
            comment: string | null;
            /** Changed Fields */
            changed_fields: string[];
            /** Professor Id */
            professor_id: number | null;
            /** Reviewed Generator Name */
            reviewed_generator_name: string | null;
            /** Reviewed Generator Version */
            reviewed_generator_version: string | null;
            /** Generator Label */
            generator_label: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            outcome?: components["schemas"]["ReviewOutcomeOut"] | null;
        };
        /**
         * ReviewOutcomeOut
         * @description What the system did with one review the moment it landed (ADR-037).
         */
        ReviewOutcomeOut: {
            cell: components["schemas"]["QuadrantCell"];
            judge: components["schemas"]["CalibrationLabel"];
            professor: components["schemas"]["CalibrationLabel"];
            /** Attributed Metrics */
            attributed_metrics: components["schemas"]["JudgeMetricId"][];
            /** Attributed Labels */
            attributed_labels: string[];
            /** Held Out */
            held_out: boolean;
            /** Action */
            action: string;
            /**
             * Instruction Refreshed
             * @default false
             */
            instruction_refreshed: boolean;
            /** Refresh Error */
            refresh_error?: string | null;
            /** Refresh Rule Count */
            refresh_rule_count?: number | null;
            /** Judges Refreshed */
            judges_refreshed?: components["schemas"]["JudgeMetricId"][];
        };
        /**
         * ReviewQueueResponse
         * @description The next question to review, with enough counts to show progress.
         */
        ReviewQueueResponse: {
            /**
             * Mode
             * @enum {string}
             */
            mode: "all" | "scoreable";
            /** Total */
            total: number;
            /** Reviewed */
            reviewed: number;
            /** Remaining */
            remaining: number;
            /** Scoreable Remaining */
            scoreable_remaining: number;
            question: components["schemas"]["QuestionDetail"] | null;
        };
        /**
         * ReviewRequest
         * @description A professor verdict.
         *
         *     ``prompt`` / ``reference_solution`` / ``tests`` are only read for an ``edit``
         *     decision; the generated original is never overwritten (ADR-002).
         */
        ReviewRequest: {
            decision: components["schemas"]["ReviewDecision"];
            /** Reasons */
            reasons?: components["schemas"]["RejectionReason"][];
            /** Comment */
            comment?: string | null;
            /** Prompt */
            prompt?: string | null;
            /** Reference Solution */
            reference_solution?: string | null;
            /** Tests */
            tests?: string | null;
            /** Professor Id */
            professor_id?: number | null;
        };
        /** ReviewStatsResponse */
        ReviewStatsResponse: {
            /** Reviewed */
            reviewed: number;
            /** Approved */
            approved: number;
            /** Rejected */
            rejected: number;
            /** Edited */
            edited: number;
            /** Reason Distribution */
            reason_distribution: components["schemas"]["ReasonCount"][];
        };
        /**
         * SectionDetail
         * @description One section's full text plus the citation that makes it traceable.
         */
        SectionDetail: {
            section: components["schemas"]["SectionSummary"];
            /** Text */
            text: string;
            /** Warnings */
            warnings: components["schemas"]["ExtractionWarning"][];
            source: components["schemas"]["SectionSource"];
            /** Citation */
            citation: string;
        };
        /** SectionListResponse */
        SectionListResponse: {
            /** Sections */
            sections: components["schemas"]["SectionSummary"][];
            /** Total */
            total: number;
        };
        /**
         * SectionSource
         * @description Everything needed to cite a section back to the book it came from.
         *
         *     This is the traceability contract that later question generation depends on:
         *     given a section, a generated question can name the book, chapter, section and
         *     pages it was grounded in.
         */
        SectionSource: {
            /** Book Id */
            book_id: number;
            /** Book Title */
            book_title: string;
            /** Book Author */
            book_author?: string | null;
            /** Section Id */
            section_id: number;
            /** Chapter Id */
            chapter_id?: number | null;
            /** Chapter Number */
            chapter_number?: string | null;
            /** Chapter Title */
            chapter_title?: string | null;
            /** Section Number */
            section_number?: string | null;
            /** Section Title */
            section_title?: string | null;
            /** Start Page */
            start_page?: number | null;
            /** End Page */
            end_page?: number | null;
            structure_source: components["schemas"]["StructureSource"];
            structure_confidence: components["schemas"]["StructureConfidence"];
            /**
             * Location Label
             * @description Human-readable page location, or ``None`` if pages are unknown.
             */
            readonly location_label: string | null;
        };
        /**
         * SectionSummary
         * @description One section's identity and location, without its text.
         */
        SectionSummary: {
            /** Id */
            id: number;
            /** Book Id */
            book_id: number;
            /** Chapter Id */
            chapter_id: number | null;
            /** Number */
            number: string | null;
            /** Title */
            title: string | null;
            /** Display Title */
            display_title: string;
            /** Position */
            position: number;
            /** Char Count */
            char_count: number;
            /** Start Page */
            start_page: number | null;
            /** End Page */
            end_page: number | null;
            /** Location Label */
            location_label: string | null;
            /** Is Unlabelled */
            is_unlabelled: boolean;
            /** Is Empty */
            is_empty: boolean;
            structure_source: components["schemas"]["StructureSource"];
            structure_confidence: components["schemas"]["StructureConfidence"];
        };
        /**
         * ServedQuestionOut
         * @description One question as the student sees it.
         *
         *     Every presentable field is listed explicitly. The stored ``content`` is never
         *     published as-is, because it holds the answer -- ``correct_option_index``,
         *     ``correct_answer``, ``expected_output``, ``correct_order`` and
         *     ``reference_solution`` all live there. A whitelist per type is the only shape
         *     where adding a question format cannot leak its answer by default.
         */
        ServedQuestionOut: {
            /** Training Session Id */
            training_session_id: number;
            /** Attempt Id */
            attempt_id: number;
            /** Ordinal */
            ordinal: number;
            /** Resumed */
            resumed: boolean;
            /** Fallback Used */
            fallback_used: boolean;
            requested_difficulty: components["schemas"]["Difficulty"];
            served_difficulty: components["schemas"]["Difficulty"];
            /** Subtopic Id */
            subtopic_id: number | null;
            /** Subtopic Name */
            subtopic_name: string | null;
            /** Question Id */
            question_id: number;
            question_type: components["schemas"]["QuestionType"] | null;
            /** Prompt */
            prompt: string;
            /** Options */
            options?: string[] | null;
            /** Code */
            code?: string | null;
            /** Blocks */
            blocks?: components["schemas"]["ParsonsBlockOut"][] | null;
        };
        /**
         * SkippedRunTarget
         * @description A gap target the run did not generate for, and why.
         */
        SkippedRunTarget: {
            /** Subtopic Id */
            subtopic_id: number;
            difficulty: components["schemas"]["Difficulty"];
            /** Reason */
            reason: string;
        };
        /**
         * SourceFormat
         * @description Accepted upload formats.
         *
         *     Structured book JSON is declared directly. A PDF is turned into that same
         *     declared shape by ``app.ingestion.pdf`` before validation -- its own
         *     embedded outline stands in for a hand-authored declaration (ADR-048).
         * @enum {string}
         */
        SourceFormat: "book_json" | "book_pdf";
        /** StartTrainingSessionRequest */
        StartTrainingSessionRequest: {
            /** Student Id */
            student_id: number;
            /** Set Version Id */
            set_version_id: number;
        };
        /**
         * StructureConfidence
         * @description How much to trust a boundary.
         *
         *     ``LOW`` means the producer guessed; such units must never be presented as
         *     though the source document had declared them.
         * @enum {string}
         */
        StructureConfidence: "high" | "medium" | "low";
        /**
         * StructureSource
         * @description How a chapter or section boundary was determined.
         *
         *     Declared *by the book document*, never inferred by this application. It
         *     records what the producer of the JSON actually relied on, so the professor
         *     can tell a boundary the source document stated from one a producer guessed at.
         * @enum {string}
         */
        StructureSource: "pdf_outline" | "markdown_heading" | "manual" | "structured_json" | "producer_inferred";
        /**
         * StudentIdentityOut
         * @description A learner plus the token their browser keeps to come back as them.
         *
         *     Returned only from enrolment and resume -- the two calls a student's own
         *     browser makes. The professor-facing :class:`StudentOut` never carries the
         *     token.
         */
        StudentIdentityOut: {
            /** Id */
            id: number;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Resume Token */
            resume_token: string;
        };
        /**
         * StudentListResponse
         * @description A page of the roster. ``total`` counts the learners matching the filters,
         *     not the page, so the client can render page controls.
         */
        StudentListResponse: {
            /** Students */
            students: components["schemas"]["StudentRosterRowOut"][];
            /** Total */
            total: number;
            /**
             * Page
             * @default 1
             */
            page: number;
            /**
             * Page Size
             * @default 20
             */
            page_size: number;
        };
        /**
         * StudentOut
         * @description One learner. No credentials: there is no authentication (ADR-041).
         */
        StudentOut: {
            /** Id */
            id: number;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Answered Count
             * @default 0
             */
            answered_count: number;
        };
        /**
         * StudentProgressOut
         * @description Everything measured about one learner.
         *
         *     ``topics`` and ``subtopics`` list only what has actually been scored. State
         *     rows are created on first touch (ADR-041), so an untouched subtopic has no
         *     row and appears here as nothing rather than as a fabricated starting value.
         */
        StudentProgressOut: {
            student: components["schemas"]["StudentOut"];
            /** Answered */
            answered: number;
            /** Average Score */
            average_score: number | null;
            /** Topics */
            topics: components["schemas"]["TopicMasteryOut"][];
            /** Subtopics */
            subtopics: components["schemas"]["SubtopicWeaknessOut"][];
            /** Recent Attempts */
            recent_attempts: components["schemas"]["AttemptOut"][];
            /** Sessions */
            sessions: components["schemas"]["TrainingSessionOut"][];
        };
        /**
         * StudentResumeOut
         * @description Who a resume token belongs to, and the run to drop them back into if any.
         */
        StudentResumeOut: {
            student: components["schemas"]["StudentIdentityOut"];
            active_session: components["schemas"]["TrainingSessionOut"] | null;
        };
        /**
         * StudentRosterRowOut
         * @description One learner as the roster table shows them.
         *
         *     Carries the attempt aggregates the roster used to derive on the client from
         *     a per-student progress fetch: the average, the answered count, when they were
         *     last active, and the running-average series the row sparkline draws.
         */
        StudentRosterRowOut: {
            /** Id */
            id: number;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Answered Count
             * @default 0
             */
            answered_count: number;
            /** Average Score */
            average_score?: number | null;
            /** Last Activity At */
            last_activity_at?: string | null;
            /** Score Series */
            score_series?: number[];
        };
        /**
         * SubmitBatchRunRequest
         * @description Optional narrowing of a re-run to named questions.
         *
         *     Omitted means the whole eligible bank. Ineligible ids are dropped rather
         *     than rejected: the eligibility rule is ADR-024's, not the caller's to waive.
         */
        SubmitBatchRunRequest: {
            /** Question Ids */
            question_ids?: number[] | null;
        };
        /**
         * SubmitBatchRunResponse
         * @description What a submission did, including the one-off backfill it may have run.
         */
        SubmitBatchRunResponse: {
            run: components["schemas"]["JudgeBatchRunOut"];
            /** Submitted */
            submitted: number;
            /** Skipped */
            skipped: number;
            /** Backfilled */
            backfilled: number;
        };
        /**
         * SubtopicConfusion
         * @description One pair of disagreeing subtopic claims, and how often it occurred.
         */
        SubtopicConfusion: {
            /** Claimed Subtopic Ids */
            claimed_subtopic_ids: number[];
            /** Judge Subtopic Ids */
            judge_subtopic_ids: number[];
            /** Count */
            count: number;
        };
        /**
         * SubtopicCoverage
         * @description One subtopic's row of the grid, one cell per difficulty.
         */
        SubtopicCoverage: {
            /** Subtopic Id */
            subtopic_id: number;
            /** Subtopic Name */
            subtopic_name: string;
            /** Topic Id */
            topic_id: number;
            /** Topic Name */
            topic_name: string;
            /** Cells */
            cells?: components["schemas"]["CoverageCell"][];
        };
        /**
         * SubtopicDetail
         * @description One subtopic with its parent topic and any legacy evidence.
         */
        SubtopicDetail: {
            subtopic: components["schemas"]["SubtopicSummary"];
            topic: components["schemas"]["SubtopicParent"];
            /** Curriculum Version Id */
            curriculum_version_id: number;
            /** Is Taxonomy Upload */
            is_taxonomy_upload: boolean;
            /** Candidate Labels */
            candidate_labels: string[];
            /** Grouping Reason */
            grouping_reason: string | null;
            confidence: components["schemas"]["ConceptConfidence"] | null;
            /** Evidence */
            evidence: components["schemas"]["SubtopicEvidenceOut"][];
            /** Book Count */
            book_count: number;
        };
        /**
         * SubtopicEvidenceOut
         * @description Legacy textbook evidence for a subtopic. Taxonomy uploads carry none.
         */
        SubtopicEvidenceOut: {
            /** Id */
            id: number;
            /** Book Id */
            book_id: number;
            /** Section Id */
            section_id: number;
            /** Candidate Label */
            candidate_label: string;
            /** Definition */
            definition: string | null;
            /** Citation */
            citation: string;
            /** Quotes */
            quotes: string[];
        };
        /**
         * SubtopicParent
         * @description The topic a subtopic hangs from, without recursing into its siblings.
         */
        SubtopicParent: {
            /** Id */
            id: number;
            /** Name */
            name: string;
            /** Description */
            description: string | null;
            /** Stable Id */
            stable_id: string | null;
        };
        /**
         * SubtopicSummary
         * @description One approved subtopic: the unit the adaptive engine tracks weakness for.
         */
        SubtopicSummary: {
            /** Id */
            id: number;
            /** Topic Id */
            topic_id: number;
            /** Stable Id */
            stable_id: string | null;
            /** Name */
            name: string;
            /** Description */
            description: string | null;
            /** Position */
            position: number;
            review_status: components["schemas"]["CurriculumItemStatus"];
        };
        /**
         * SubtopicWeaknessOut
         * @description One subtopic's weakness -- its weight in the roulette.
         */
        SubtopicWeaknessOut: {
            /** Subtopic Id */
            subtopic_id: number;
            /** Subtopic Name */
            subtopic_name: string;
            /** Topic Name */
            topic_name: string;
            /** Weakness */
            weakness: number;
            /** Observations */
            observations: number;
        };
        /**
         * TaxonomyDocumentGuide
         * @description Everything a professor needs to obtain a valid taxonomy document.
         *
         *     The prompt, the example and the field reference are rendered from the
         *     taxonomy contract itself, so a client that shows them cannot describe a
         *     document the validator would refuse.
         */
        TaxonomyDocumentGuide: {
            /** Schema Version */
            schema_version: string;
            /** Supported Extensions */
            supported_extensions: string[];
            /** Max Upload Mb */
            max_upload_mb: number;
            /** Prompt */
            prompt: string;
            /** Example Json */
            example_json: string;
            /** Fields */
            fields: components["schemas"]["FieldLimitOut"][];
            /**
             * Retains Upload
             * @default false
             */
            retains_upload: boolean;
        };
        /**
         * TopicCoverage
         * @description One topic's rows, and what a professor would have to do about it.
         *
         *     The grouping the coverage page is read through. A professor decides what to
         *     write next a topic at a time -- a chunk teaches one topic, so a gap in
         *     another topic is not work they can act on in the same breath.
         */
        TopicCoverage: {
            /** Topic Id */
            topic_id: number;
            /** Topic Name */
            topic_name: string;
            /**
             * Approved Questions
             * @default 0
             */
            approved_questions: number;
            /** Subtopics */
            subtopics?: components["schemas"]["SubtopicCoverage"][];
        };
        /**
         * TopicMasteryOut
         * @description One topic's BKT state, and the difficulty it currently implies.
         */
        TopicMasteryOut: {
            /** Topic Id */
            topic_id: number;
            /** Topic Name */
            topic_name: string;
            /** P Known */
            p_known: number;
            band: components["schemas"]["MasteryBand"];
            next_difficulty: components["schemas"]["Difficulty"];
            /** Observations */
            observations: number;
        };
        /**
         * TopicOut
         * @description One topic: the unit BKT tracks mastery for.
         */
        TopicOut: {
            /** Id */
            id: number;
            /** Curriculum Version Id */
            curriculum_version_id: number;
            /** Stable Id */
            stable_id: string | null;
            /** Name */
            name: string;
            /** Description */
            description: string | null;
            /** Position */
            position: number;
            review_status: components["schemas"]["CurriculumItemStatus"];
            /** Subtopics */
            subtopics: components["schemas"]["SubtopicSummary"][];
        };
        /** TrainingSessionListResponse */
        TrainingSessionListResponse: {
            /** Sessions */
            sessions: components["schemas"]["TrainingSessionOut"][];
            /** Total */
            total: number;
        };
        /**
         * TrainingSessionOut
         * @description One run against one frozen question set (ADR-036).
         */
        TrainingSessionOut: {
            /** Id */
            id: number;
            /** Student Id */
            student_id: number;
            /** Student Name */
            student_name: string | null;
            /** Set Version Id */
            set_version_id: number | null;
            /** Set Label */
            set_label: string | null;
            /** Rng Seed */
            rng_seed: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Ended At */
            ended_at: string | null;
            /** Served Count */
            served_count: number;
            /** Answered Count */
            answered_count: number;
        };
        /**
         * TrendPointOut
         * @description One judge panel's agreement record.
         */
        TrendPointOut: {
            /** Rubric Version */
            rubric_version: string | null;
            /** N */
            n: number;
            /** First Seen */
            first_seen: string | null;
            /** Last Seen */
            last_seen: string | null;
            /** Confirmed Good */
            confirmed_good: number;
            /** Missed */
            missed: number;
            /** False Alarm */
            false_alarm: number;
            /** Confirmed Bad */
            confirmed_bad: number;
            /** Agreement */
            agreement: number | null;
            /** Auto Accept Precision */
            auto_accept_precision: number | null;
            /** Small Sample */
            small_sample: boolean;
            /** Metrics */
            metrics: components["schemas"]["MetricFaultsOut"][];
        };
        /**
         * TypeCalibrationOut
         * @description One question type's four-cell report (ADR-034).
         *
         *     The type is the unit a professor would authorise, because the instruction
         *     the generator follows is per type (ADR-033). A pooled figure describes a
         *     mixture of generators and authorises none of them.
         */
        TypeCalibrationOut: {
            question_type: components["schemas"]["QuestionType"] | null;
            report: components["schemas"]["CalibrationResultsResponse"];
            check_report: components["schemas"]["CalibrationResultsResponse"];
            /** Pairs */
            pairs: components["schemas"]["CalibrationPairOut"][];
        };
        /** TypeInstructionListResponse */
        TypeInstructionListResponse: {
            /** Instructions */
            instructions: components["schemas"]["TypeInstructionOut"][];
        };
        /**
         * TypeInstructionOut
         * @description What the generator is told for one question type (ADR-033).
         *
         *     ``learned`` distinguishes an instruction built from reviews from the shipped
         *     default, so a professor can see at a glance which types their feedback has
         *     actually reached. ``available_reviews`` is how many reviews a refresh would
         *     draw on now, which is what makes a stale instruction visible.
         */
        TypeInstructionOut: {
            question_type: components["schemas"]["QuestionType"];
            /** Instruction */
            instruction: string;
            /** Rules */
            rules: string[];
            /** Learned */
            learned: boolean;
            /** Review Count */
            review_count: number;
            /** Available Reviews */
            available_reviews: number;
            /** Updated At */
            updated_at: string | null;
        };
        /** TypeInstructionRefreshResponse */
        TypeInstructionRefreshResponse: {
            question_type: components["schemas"]["QuestionType"];
            /** Learned */
            learned: boolean;
            /** Rule Count */
            rule_count: number;
            /** Review Count */
            review_count: number;
            /** Instruction */
            instruction: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /**
         * VocabularyTermOut
         * @description One closed-vocabulary value, and what it means to a professor.
         */
        VocabularyTermOut: {
            /** Value */
            value: string;
            /** Meaning */
            meaning: string;
        };
        /**
         * WarningSeverity
         * @description Whether a warning describes a defect or merely states a fact.
         *
         *     Only ``DEFECT`` warnings make a book ``PARTIAL``. Without this split, a
         *     document that simply carries no page numbers would be flagged forever, and a
         *     badge that is always on teaches the professor to ignore it.
         * @enum {string}
         */
        WarningSeverity: "defect" | "info";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    config_api_config_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfigResponse"];
                };
            };
        };
    };
    counts_api_counts_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CountsResponse"];
                };
            };
        };
    };
    auth_cookie_login_api_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/x-www-form-urlencoded": components["schemas"]["Body_auth_cookie_login_api_auth_login_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description No Content */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorModel"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    auth_cookie_logout_api_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description No Content */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Missing token or inactive user. */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    read_current_user_api_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    list_books_api_books_get: {
        parameters: {
            query?: {
                limit?: number;
                usable_only?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_book_api_books_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_import_book_api_books_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookSummary"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    document_guide_api_books_document_guide_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookDocumentGuide"];
                };
            };
        };
    };
    get_book_api_books__book_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_book_api_books__book_id__delete: {
        parameters: {
            query?: {
                force?: boolean;
            };
            header?: never;
            path: {
                book_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookDeletion"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_book_api_books__book_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BookMetadataUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BookSummary"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_book_source_api_books__book_id__source_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_sections_api_books__book_id__sections_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SectionListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_section_api_books__book_id__sections__section_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                book_id: number;
                section_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SectionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_versions_api_curriculum_versions_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_taxonomy_api_curriculum_versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_import_taxonomy_api_curriculum_versions_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumVersionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    document_guide_api_curriculum_document_guide_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaxonomyDocumentGuide"];
                };
            };
        };
    };
    get_approved_api_curriculum_approved_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumVersionDetail"];
                };
            };
        };
    };
    get_version_api_curriculum_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumVersionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_version_api_curriculum_versions__version_id__delete: {
        parameters: {
            query?: {
                force?: boolean;
            };
            header?: never;
            path: {
                version_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumVersionDeletion"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_version_api_curriculum_versions__version_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CurriculumVersionLabelUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumVersionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    activate_version_api_curriculum_versions__version_id__activate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurriculumVersionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_topic_api_curriculum_topics__topic_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                topic_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CurriculumItemLabelUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TopicOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_subtopic_api_curriculum_subtopics__subtopic_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                subtopic_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubtopicDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_subtopic_api_curriculum_subtopics__subtopic_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                subtopic_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CurriculumItemLabelUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubtopicSummary"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_questions_api_questions_get: {
        parameters: {
            query?: {
                limit?: number;
                status?: components["schemas"]["QuestionStatus"] | null;
                curriculum_version_id?: number | null;
                section_id?: number | null;
                run_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_questions_api_questions_generate_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateQuestionsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerateQuestionsResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    regenerate_question_api_questions__question_id__regenerate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegenerateQuestionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RegenerateQuestionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    batch_plan_api_questions_batch_plan_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateBatchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_batch_api_questions_generate_batch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateBatchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerateBatchResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generation_plan_api_questions_generation_plan_get: {
        parameters: {
            query: {
                book_id: number;
                section_ids?: number[] | null;
                all_sections?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationPlanResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    review_queue_api_questions_review_queue_get: {
        parameters: {
            query?: {
                after?: number | null;
                mode?: "all" | "scoreable";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewQueueResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_question_api_questions__question_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_review_api_questions__question_id__review_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_reviews_api_reviews_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    review_stats_api_reviews_stats_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReviewStatsResponse"];
                };
            };
        };
    };
    list_instructions_api_instructions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TypeInstructionListResponse"];
                };
            };
        };
    };
    delete_instruction_api_instructions__question_type__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_type: components["schemas"]["QuestionType"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TypeInstructionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_rule_api_instructions__question_type__rules__rule_index__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_type: components["schemas"]["QuestionType"];
                rule_index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TypeInstructionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_api_instructions__question_type__refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_type: components["schemas"]["QuestionType"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TypeInstructionRefreshResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_judge_prompts_api_judge_prompts_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JudgePromptListResponse"];
                };
            };
        };
    };
    save_judge_prompt_api_judge_prompts__metric__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                metric: components["schemas"]["JudgeMetricId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JudgePromptRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JudgePromptSaveResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revert_judge_prompt_api_judge_prompts__metric__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                metric: components["schemas"]["JudgeMetricId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JudgePromptSaveResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_api_judge_prompts__metric__refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                metric: components["schemas"]["JudgeMetricId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JudgePromptRefreshResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    calibration_results_api_calibration_results_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CalibrationResultsResponse"];
                };
            };
        };
    };
    calibration_pairs_api_calibration_pairs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CalibrationPairsResponse"];
                };
            };
        };
    };
    calibration_quadrant_api_calibration_quadrant_get: {
        parameters: {
            query?: {
                rubric_version?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CalibrationQuadrantResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    agreement_trend_api_calibration_trend_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgreementTrendResponse"];
                };
            };
        };
    };
    coverage_api_coverage_get: {
        parameters: {
            query?: {
                set_version_id?: number | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CoverageReportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_generation_run_api_coverage_generation_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FillGapsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationRunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_question_sets_api_question_sets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionSetListResponse"];
                };
            };
        };
    };
    create_set_api_question_sets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateQuestionSetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionSetOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sync_prod_set_api_question_sets_prod_sync_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionSetOut"];
                };
            };
        };
    };
    retrieve_sections_api_retrieval_sections_get: {
        parameters: {
            query?: {
                /** @description Free-text query. */
                query?: string | null;
                /** @description Curriculum subtopic; its topic + name + description becomes the query. */
                subtopic_id?: number | null;
                top_k?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetrievedSectionOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_prod_classroom_api_question_sets_prod_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionSetOut"];
                };
            };
        };
    };
    get_question_set_api_question_sets__set_version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                set_version_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QuestionSetOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_students_api_students_get: {
        parameters: {
            query?: {
                search?: string;
                score?: string;
                answered?: string;
                activity?: string;
                page?: number;
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StudentListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_student_api_students_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateStudentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StudentIdentityOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    class_summary_api_students_class_summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ClassSummaryOut"];
                };
            };
        };
    };
    resume_student_api_students_resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeStudentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StudentResumeOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_student_api_students__student_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                student_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StudentOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    student_progress_api_students__student_id__progress_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                student_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StudentProgressOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_training_sessions_api_training_sessions_get: {
        parameters: {
            query: {
                student_id: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrainingSessionListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    start_training_session_api_training_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartTrainingSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrainingSessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_training_session_api_training_sessions__training_session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                training_session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrainingSessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    next_question_api_training_sessions__training_session_id__next_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                training_session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ServedQuestionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    answer_attempt_api_attempts__attempt_id__answer_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                attempt_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnswerRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnsweredOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_attempt_api_attempts__attempt_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                attempt_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttemptOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    end_training_session_api_training_sessions__training_session_id__end_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                training_session_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TrainingSessionOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_batch_runs_api_evaluation_batch_runs_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BatchRunListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_batch_run_api_evaluation_batch_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["SubmitBatchRunRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubmitBatchRunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_batch_run_api_evaluation_batch_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JudgeBatchRunOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    poll_batch_run_api_evaluation_batch_runs__run_id__poll_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PollBatchRunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    question_evaluations_api_questions__question_id__evaluations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                question_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvaluationHistoryResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}

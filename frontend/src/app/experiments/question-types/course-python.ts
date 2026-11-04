/**
 * The one course this prototype shows. Intro Python is the only subject with a style library,
 * so it is the only one the new-course dialog lets a professor pick (`ready` in
 * app/web/routes/api/courses.py).
 *
 * The taxonomy is the question-setup prototype's copy of the dev database's curriculum.
 */

import { PYTHON } from "../question-setup/mock-python";
import { PYTHON_LIBRARY } from "./library-python";
import type { Course } from "./setup-model";

export const PYTHON_COURSE: Course = {
  name: PYTHON.course,
  taxonomyLabel: PYTHON.taxonomy.label,
  questionTypes: PYTHON.questionTypes,
  library: PYTHON_LIBRARY,
  topics: PYTHON.topics,
};

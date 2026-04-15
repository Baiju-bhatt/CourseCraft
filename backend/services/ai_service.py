import json
import os
import re
from typing import Any, Dict, List

import requests


class CourseAIService:
    def __init__(self):
        self.hf_token = os.getenv('HUGGINGFACE_API_TOKEN', '')
        self.model = os.getenv('HF_MODEL', 'mistralai/Mistral-7B-Instruct-v0.3')
        self.api_url = f'https://router.huggingface.co/hf-inference/models/{self.model}'

    @property
    def llm_enabled(self) -> bool:
        return bool(self.hf_token)

    def _call_huggingface(self, prompt: str, max_new_tokens: int = 2200, temperature: float = 0.25) -> str:
        if not self.hf_token:
            raise ValueError('Hugging Face token not configured')

        headers = {
            'Authorization': f'Bearer {self.hf_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'inputs': prompt,
            'parameters': {
                'max_new_tokens': max_new_tokens,
                'temperature': temperature,
                'return_full_text': False,
            },
        }
        response = requests.post(self.api_url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and data and isinstance(data[0], dict) and 'generated_text' in data[0]:
            return data[0]['generated_text']
        if isinstance(data, dict) and 'generated_text' in data:
            return data['generated_text']
        return json.dumps(data)

    def _extract_json(self, text: str) -> Any:
        text = (text or '').strip()
        if not text:
            raise ValueError('Empty model response')

        fenced_match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if fenced_match:
            text = fenced_match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start_positions = [idx for idx in [text.find('{'), text.find('[')] if idx != -1]
        if not start_positions:
            raise ValueError('No JSON found in model response')
        start = min(start_positions)

        for end in range(len(text), start, -1):
            chunk = text[start:end].strip()
            try:
                return json.loads(chunk)
            except json.JSONDecodeError:
                continue

        raise ValueError('Unable to parse model response as JSON')

    # -------------------------------------------------------------------------
    # CHATBOT METHODS
    # -------------------------------------------------------------------------

    def _build_chat_prompt(
        self,
        message: str,
        history: List[Dict[str, str]],
        topic_context: str = '',
    ) -> str:
        """
        Build a Mistral-instruct-style prompt for the chatbot.

        Mistral format:
            <s>[INST] first_user_message [/INST] first_assistant_response </s>
            [INST] second_user_message [/INST] second_assistant_response </s>
            ...
            [INST] current_user_message [/INST]

        The system instruction is prepended to the first user message.
        """
        system_instruction = (
            "You are an expert educational AI assistant embedded inside an AI-powered "
            "course generation platform. Your sole purpose is to help learners gain a "
            "deep, accurate, and thorough understanding of any topic, concept, technology, "
            "skill, or subject they ask about.\n\n"
            "Guidelines you must follow for every response:\n"
            "1. Provide a comprehensive, well-structured explanation that addresses ALL "
            "important aspects of the question — what the topic is, why it matters, how "
            "it works, how it is applied in practice, and what mistakes or misconceptions "
            "to avoid.\n"
            "2. Structure your answer with clear logical progression: start with the core "
            "concept/definition, then build towards deeper understanding, practical usage, "
            "and advanced insights.\n"
            "3. Include concrete, real-world examples and practical scenarios wherever they "
            "help reinforce understanding.\n"
            "4. Every point you write must be directly relevant to the question — be "
            "detailed and thorough, but avoid padding with off-topic information.\n"
            "5. Write in a clear, precise, and educational tone suitable for learners of "
            "varying experience levels.\n"
            "6. When a question touches on related concepts that complete the picture, "
            "briefly address those connections as well.\n"
            "7. Format your answer for readability: use numbered or bulleted sub-points, "
            "clear section breaks, and short paragraphs where appropriate."
        )

        if topic_context and topic_context.strip():
            system_instruction += (
                f"\n\nCurrent learning context the learner is studying: {topic_context.strip()}"
            )

        # Limit conversation history to the last 8 messages (4 exchanges)
        # to keep the prompt within the model's context window.
        trimmed_history = history[-8:] if history else []

        prompt_parts: List[str] = []
        first_user_turn = True

        for turn in trimmed_history:
            role = turn.get('role', '')
            content = (turn.get('content') or '').strip()
            if not content:
                continue

            if role == 'user':
                if first_user_turn:
                    # Embed system instruction in the very first user turn
                    prompt_parts.append(
                        f'<s>[INST] {system_instruction}\n\nQuestion: {content} [/INST]'
                    )
                    first_user_turn = False
                else:
                    prompt_parts.append(f'[INST] {content} [/INST]')

            elif role == 'assistant':
                prompt_parts.append(f' {content} </s>')

        # Append the current user message
        if first_user_turn:
            # No prior history — system instruction goes here
            prompt_parts.append(
                f'<s>[INST] {system_instruction}\n\nQuestion: {message} [/INST]'
            )
        else:
            prompt_parts.append(f'[INST] {message} [/INST]')

        return ''.join(prompt_parts)

    def chat(
        self,
        message: str,
        history: List[Dict[str, str]] | None = None,
        topic_context: str = '',
    ) -> str:
        """
        Generate a detailed chatbot response for the given user message.

        Args:
            message: The user's current question or message.
            history: Optional list of previous turns, each as
                     {'role': 'user'|'assistant', 'content': '...'}.
            topic_context: Optional string describing the current learning
                           context (e.g., current lesson title / module).

        Returns:
            A plain-text string response from the LLM, or a fallback message
            if the LLM is not configured.
        """
        if not self.llm_enabled:
            return (
                "The AI assistant requires a Hugging Face API token to be configured "
                "on the server. Please ask your administrator to set the "
                "HUGGINGFACE_API_TOKEN environment variable to enable the chatbot."
            )

        safe_history = history if isinstance(history, list) else []
        prompt = self._build_chat_prompt(message, safe_history, topic_context)

        try:
            raw_response = self._call_huggingface(
                prompt,
                max_new_tokens=1800,
                temperature=0.45,
            )
            return (raw_response or '').strip()
        except Exception as exc:
            return (
                f"I encountered an error while generating a response: {exc}. "
                "Please try again in a moment."
            )

    # -------------------------------------------------------------------------
    # EXISTING PROMPT BUILDERS (unchanged)
    # -------------------------------------------------------------------------

    def _question_prompt(self, target_role: str) -> str:
        return f'''
You are generating a diagnostic assessment for a personalized learning platform.

Target role: {target_role}

Return ONLY valid JSON as an array of exactly 5 objects.
Each object must follow this schema:
{{
  "id": 1,
  "topic": "topic name",
  "question": "clear multiple choice question",
  "options": ["option A", "option B", "option C", "option D"],
  "correct_option_index": 0,
  "explanation": "one short explanation"
}}

Rules:
- Use realistic topics for the target role.
- Cover fundamentals, tooling, problem solving, best practices, and business impact.
- Exactly 4 options per question.
- correct_option_index must be 0, 1, 2, or 3.
- Keep the questions diagnostic, not trivial.
- Do not include markdown.
- JSON only.
'''.strip()

    def _course_prompt(
        self,
        target_role: str,
        experience_type: str,
        current_role: str,
        assessment_result: Dict[str, Any] | None,
    ) -> str:
        return f'''
You are generating a personalized, practical learning course for an AI learning platform.

Target role: {target_role}
Current role: {current_role or 'Not provided'}
Experience type: {experience_type}
Assessment summary: {json.dumps(assessment_result or {}, ensure_ascii=False)}

Return ONLY valid JSON using this schema:
{{
  "title": "course title",
  "overview": "3-5 sentence overview",
  "current_role_context": "string",
  "experience_type": "beginner or experienced",
  "focus_topics": ["topic 1", "topic 2", "topic 3", "topic 4"],
  "estimated_duration": "example: 4 weeks",
  "modules": [
    {{
      "module_number": 1,
      "title": "module title",
      "module_summary": "2-3 sentence summary",
      "learning_objectives": ["obj1", "obj2", "obj3"],
      "lessons": [
        {{
          "lesson_number": 1,
          "title": "lesson title",
          "format": "reading/lab/case study/workshop",
          "duration": "20 min",
          "summary": "2-3 sentence summary specific to this lesson",
          "key_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
          "content_sections": [
            {{"heading": "section heading", "body": "120-220 words teaching one distinct part of the lesson."}},
            {{"heading": "section heading", "body": "120-220 words teaching another distinct part of the lesson."}},
            {{"heading": "section heading", "body": "120-220 words explaining process, decisions, or workflow."}},
            {{"heading": "section heading", "body": "120-220 words covering mistakes, validation, metrics, or advanced insight."}}
          ],
          "example": {{
            "title": "realistic example title",
            "scenario": "3-5 sentence role-based example",
            "steps": ["step 1", "step 2", "step 3", "step 4"]
          }},
          "practice_task": "small but concrete practice task for the learner"
        }}
      ],
      "quiz": [
        {{
          "question": "question text",
          "options": ["A", "B", "C", "D"],
          "answer": "one exact option value",
          "explanation": "1-2 sentence explanation"
        }}
      ],
      "assignment": {{
        "title": "assignment title",
        "description": "clear hands-on assignment",
        "deliverables": ["deliverable 1", "deliverable 2", "deliverable 3"],
        "submission_type": "text / notebook / PDF / presentation"
      }}
    }}
  ],
  "capstone": {{
    "title": "capstone title",
    "description": "portfolio-ready final task",
    "deliverables": ["deliverable 1", "deliverable 2", "deliverable 3"]
  }},
  "certificate_criteria": ["criterion 1", "criterion 2", "criterion 3", "criterion 4"]
}}

Rules:
- Create exactly 4 modules.
- Create exactly 3 lessons per module.
- The 3 lessons inside a module must be clearly different from each other: one lesson for foundations, one for workflow/execution, and one for applied practice or case-based use.
- Do NOT repeat the same summary, same content, or same section text across lessons.
- Every lesson must teach enough detail so a learner can actually study from it.
- Each lesson must have exactly 4 content_sections, each with substantial explanation.
- Each module quiz must contain exactly 3 multiple-choice questions.
- Each quiz question must have exactly 4 options and a valid answer that matches one option exactly.
- Make content practical, beginner-friendly, and skill-building.
- Explain not only what the topic is, but why it matters, how it is used, how to do it correctly, and what mistakes to avoid.
- If assessment weaknesses exist, emphasize them in focus_topics and modules.
- Avoid vague filler statements like "learn more" or "practice more".
- Do not include markdown.
- JSON only.
'''.strip()

    def _normalize_questions(self, questions: Any, target_role: str) -> List[Dict[str, Any]]:
        if not isinstance(questions, list):
            raise ValueError('Questions payload must be a list')

        normalized: List[Dict[str, Any]] = []
        for idx, item in enumerate(questions[:5], start=1):
            if not isinstance(item, dict):
                continue
            options = item.get('options') if isinstance(item.get('options'), list) else []
            options = [str(option).strip() for option in options[:4] if str(option).strip()]
            while len(options) < 4:
                options.append(f'Option {len(options) + 1}')

            correct_index = item.get('correct_option_index', 0)
            try:
                correct_index = int(correct_index)
            except (TypeError, ValueError):
                correct_index = 0
            correct_index = max(0, min(3, correct_index))

            normalized.append({
                'id': idx,
                'topic': str(item.get('topic') or f'{target_role} Fundamentals').strip(),
                'question': str(item.get('question') or f'Question {idx} for {target_role}').strip(),
                'options': options,
                'correct_option_index': correct_index,
                'explanation': str(item.get('explanation') or '').strip(),
            })

        if len(normalized) < 5:
            fallback = self._fallback_questions(target_role)
            needed = 5 - len(normalized)
            normalized.extend(fallback[len(normalized):len(normalized) + needed])
            for idx, item in enumerate(normalized, start=1):
                item['id'] = idx

        return normalized

    def _default_content_sections(self, topic: str, target_role: str, lesson_title: str, lesson_number: int) -> List[Dict[str, str]]:
        lesson_focus = {
            1: {
                'purpose': 'core concepts, vocabulary, and mental models',
                'approach': 'definitions, building blocks, and when the concept appears in real work',
                'workflow': 'how to recognize the right moment to use the concept and what inputs are required',
                'pitfalls': 'confusing terms, weak assumptions, and skipping validation',
            },
            2: {
                'purpose': 'workflow, execution steps, and practical decision making',
                'approach': 'a repeatable sequence a practitioner can follow on the job',
                'workflow': 'how to move from requirement to execution, review, and communication',
                'pitfalls': 'breaking the process, rushing implementation, and failing quality checks',
            },
            3: {
                'purpose': 'applied practice, mini case work, and transfer of knowledge into realistic scenarios',
                'approach': 'hands-on execution, trade-offs, reflection, and communication of results',
                'workflow': 'how to produce an outcome, review it critically, and improve it based on findings',
                'pitfalls': 'surface-level work, weak documentation, and poor stakeholder translation',
            },
        }.get(lesson_number, {
            'purpose': 'practical learning and capability building',
            'approach': 'clear explanation followed by structured application',
            'workflow': 'step-by-step execution with checkpoints',
            'pitfalls': 'common mistakes, missed assumptions, and weak review',
        })

        return [
            {
                'heading': f'{lesson_title}: Why it matters',
                'body': (
                    f'{topic} matters in the {target_role} path because it influences how work is framed, executed, and trusted by other people. '
                    f'This lesson focuses on {lesson_focus["purpose"]}. A learner should understand the business reason behind {topic.lower()}, '
                    f'not just its definition. In strong real-world work, this topic helps teams reduce confusion, improve decision quality, and '
                    f'produce outputs that are easier to explain and reuse. When a learner understands why a topic matters first, they stop treating '
                    f'it like isolated theory and start recognizing where it creates value inside projects, reports, systems, or stakeholder conversations.'
                ),
            },
            {
                'heading': f'{lesson_title}: Deep explanation',
                'body': (
                    f'The best way to study {topic} is to connect concept to execution. This lesson emphasizes {lesson_focus["approach"]}. '
                    f'Start by identifying the purpose of the task, the inputs available, the expected output, and the standards used to judge success. '
                    f'In practice, a {target_role} often has to make choices under incomplete information, so understanding the reasoning behind each step '
                    f'is more valuable than memorizing commands or definitions. A strong learner should be able to explain the topic in simple language, '
                    f'outline its components, and describe how one decision in the process can affect quality, speed, trust, or downstream work.'
                ),
            },
            {
                'heading': f'{lesson_title}: Practical workflow',
                'body': (
                    f'In day-to-day execution, {topic.lower()} becomes useful when the learner can apply a repeatable workflow. That means clarifying the goal, '
                    f'checking constraints, preparing the right inputs, carrying out the work in the correct sequence, and validating the result before sharing it. '
                    f'This lesson specifically highlights {lesson_focus["workflow"]}. A learner should ask: What am I trying to achieve, what evidence shows it worked, '
                    f'what could go wrong, and how will I communicate the outcome clearly? This mindset helps convert theory into reliable execution and creates habits '
                    f'that scale beyond a single example or assignment.'
                ),
            },
            {
                'heading': f'{lesson_title}: Mistakes and quality checks',
                'body': (
                    f'One of the fastest ways to improve with {topic} is to study failure patterns. This lesson addresses {lesson_focus["pitfalls"]}. '
                    f'Beginners often move too quickly, assume their first answer is correct, or skip the validation and explanation stage. A stronger approach is to '
                    f'document assumptions, test edge cases, compare results against expectations, and explain the final output in business or operational language. '
                    f'Quality is not only about getting a correct answer once. It is about being able to repeat the work, defend the logic, and make the result useful '
                    f'for another person who depends on it.'
                ),
            },
        ]

    def _normalize_lesson(self, lesson: Any, target_role: str, topic: str, lesson_number: int) -> Dict[str, Any]:
        fallback = self._fallback_lesson(target_role, topic, lesson_number)
        if not isinstance(lesson, dict):
            return fallback

        sections = lesson.get('content_sections') if isinstance(lesson.get('content_sections'), list) else []
        normalized_sections = []
        for section in sections[:4]:
            if not isinstance(section, dict):
                continue
            heading = str(section.get('heading') or '').strip()
            body = str(section.get('body') or '').strip()
            if heading and body and len(body.split()) >= 45:
                normalized_sections.append({'heading': heading, 'body': body})
        if len(normalized_sections) < 4:
            normalized_sections = fallback['content_sections']

        example = lesson.get('example') if isinstance(lesson.get('example'), dict) else {}
        example_steps = example.get('steps') if isinstance(example.get('steps'), list) else []
        cleaned_steps = [str(step).strip() for step in example_steps[:4] if str(step).strip()] or fallback['example']['steps']

        takeaways = lesson.get('key_takeaways') if isinstance(lesson.get('key_takeaways'), list) else []
        cleaned_takeaways = [str(item).strip() for item in takeaways[:4] if str(item).strip()] or fallback['key_takeaways']

        return {
            'lesson_number': lesson_number,
            'title': str(lesson.get('title') or fallback['title']).strip(),
            'format': str(lesson.get('format') or fallback['format']).strip(),
            'duration': str(lesson.get('duration') or fallback['duration']).strip(),
            'summary': str(lesson.get('summary') or fallback['summary']).strip(),
            'key_takeaways': cleaned_takeaways,
            'content_sections': normalized_sections,
            'example': {
                'title': str(example.get('title') or fallback['example']['title']).strip(),
                'scenario': str(example.get('scenario') or fallback['example']['scenario']).strip(),
                'steps': cleaned_steps,
            },
            'practice_task': str(lesson.get('practice_task') or fallback['practice_task']).strip(),
        }

    def _normalize_quiz(self, quiz_items: Any, target_role: str, topic: str) -> List[Dict[str, Any]]:
        fallback = self._fallback_quiz(target_role, topic)
        if not isinstance(quiz_items, list):
            return fallback

        normalized = []
        for quiz_item in quiz_items[:3]:
            if not isinstance(quiz_item, dict):
                continue
            options = quiz_item.get('options') if isinstance(quiz_item.get('options'), list) else []
            options = [str(option).strip() for option in options[:4] if str(option).strip()]
            while len(options) < 4:
                options.append(f'Option {len(options) + 1}')
            answer = str(quiz_item.get('answer') or options[0]).strip()
            if answer not in options:
                answer = options[0]
            question = str(quiz_item.get('question') or '').strip()
            if not question:
                continue
            normalized.append({
                'question': question,
                'options': options,
                'answer': answer,
                'explanation': str(quiz_item.get('explanation') or '').strip() or 'Review the lesson summary and example to understand the correct choice.',
            })

        while len(normalized) < 3:
            normalized.append(fallback[len(normalized)])
        return normalized[:3]

    def _normalize_assignment(self, assignment: Any, target_role: str, topic: str) -> Dict[str, Any]:
        fallback = self._fallback_assignment(target_role, topic)
        if not isinstance(assignment, dict):
            return fallback
        deliverables = assignment.get('deliverables') if isinstance(assignment.get('deliverables'), list) else []
        cleaned = [str(item).strip() for item in deliverables[:4] if str(item).strip()] or fallback['deliverables']
        return {
            'title': str(assignment.get('title') or fallback['title']).strip(),
            'description': str(assignment.get('description') or fallback['description']).strip(),
            'deliverables': cleaned,
            'submission_type': str(assignment.get('submission_type') or fallback['submission_type']).strip(),
        }

    def _normalize_course(
        self,
        course_data: Any,
        target_role: str,
        experience_type: str,
        current_role: str,
        assessment_result: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        if not isinstance(course_data, dict):
            raise ValueError('Course payload must be an object')

        focus_topics = course_data.get('focus_topics')
        if not isinstance(focus_topics, list) or not focus_topics:
            focus_topics = self._derive_focus_topics(target_role, assessment_result)
        focus_topics = [str(topic).strip() for topic in focus_topics if str(topic).strip()][:4]
        while len(focus_topics) < 4:
            focus_topics.append(f'{target_role} Topic {len(focus_topics) + 1}')

        normalized_modules = []
        modules = course_data.get('modules') if isinstance(course_data.get('modules'), list) else []
        for index, module in enumerate(modules[:4], start=1):
            topic = focus_topics[index - 1]
            fallback_module = self._fallback_module(target_role, topic, index)
            if not isinstance(module, dict):
                normalized_modules.append(fallback_module)
                continue

            lesson_items = module.get('lessons') if isinstance(module.get('lessons'), list) else []
            lessons = [
                self._normalize_lesson(lesson, target_role, topic, lesson_index)
                for lesson_index, lesson in enumerate(lesson_items[:3], start=1)
            ]
            while len(lessons) < 3:
                lessons.append(self._fallback_lesson(target_role, topic, len(lessons) + 1))

            normalized_modules.append({
                'module_number': index,
                'title': str(module.get('title') or fallback_module['title']).strip(),
                'module_summary': str(module.get('module_summary') or fallback_module['module_summary']).strip(),
                'learning_objectives': [
                    str(objective).strip()
                    for objective in (module.get('learning_objectives') or fallback_module['learning_objectives'])[:4]
                    if str(objective).strip()
                ] or fallback_module['learning_objectives'],
                'lessons': lessons,
                'quiz': self._normalize_quiz(module.get('quiz'), target_role, topic),
                'assignment': self._normalize_assignment(module.get('assignment'), target_role, topic),
            })

        while len(normalized_modules) < 4:
            index = len(normalized_modules) + 1
            normalized_modules.append(self._fallback_module(target_role, focus_topics[index - 1], index))

        capstone = course_data.get('capstone') if isinstance(course_data.get('capstone'), dict) else {}
        capstone_deliverables = capstone.get('deliverables') if isinstance(capstone.get('deliverables'), list) else []
        capstone_deliverables = [str(item).strip() for item in capstone_deliverables[:4] if str(item).strip()] or [
            'Problem statement and assumptions',
            'Solution workflow or architecture',
            'Final deliverable with explanation',
        ]

        certificate_criteria = course_data.get('certificate_criteria')
        if not isinstance(certificate_criteria, list) or not certificate_criteria:
            certificate_criteria = [
                'Complete all lessons',
                'Score at least 70% across quizzes',
                'Submit every module assignment',
                'Finish the capstone project',
            ]

        return {
            'title': str(course_data.get('title') or f'{target_role} Learning Track').strip(),
            'overview': str(course_data.get('overview') or f'AI-generated learning journey for {target_role}.').strip(),
            'current_role_context': str(course_data.get('current_role_context') or current_role).strip(),
            'experience_type': experience_type,
            'focus_topics': focus_topics,
            'estimated_duration': str(course_data.get('estimated_duration') or '4 weeks').strip(),
            'modules': normalized_modules,
            'capstone': {
                'title': str(capstone.get('title') or f'{target_role} Capstone Project').strip(),
                'description': str(capstone.get('description') or f'Build a portfolio-ready project aligned with {target_role}.').strip(),
                'deliverables': capstone_deliverables,
            },
            'certificate_criteria': [str(item).strip() for item in certificate_criteria[:4] if str(item).strip()],
            'generation_source': 'llm' if self.llm_enabled else 'fallback',
            'model_name': self.model if self.llm_enabled else 'deterministic-fallback',
        }

    def _derive_focus_topics(self, target_role: str, assessment_result: Dict[str, Any] | None) -> List[str]:
        weak_topics = (assessment_result or {}).get('weaknesses') or []
        if weak_topics:
            topics = [str(topic).strip() for topic in weak_topics if str(topic).strip()]
            while len(topics) < 4:
                topics.append(f'{target_role} Improvement Area {len(topics) + 1}')
            return topics[:4]

        role_lower = target_role.lower()
        if 'data engineer' in role_lower:
            return ['Data Pipelines', 'SQL & Data Modeling', 'Cloud Data Platforms', 'Data Quality & Reliability']
        if 'data analyst' in role_lower:
            return ['SQL Analysis', 'Business Metrics', 'Dashboards & Storytelling', 'Experimentation & Insights']
        if 'software' in role_lower or 'developer' in role_lower:
            return ['Programming Foundations', 'APIs & Integration', 'Testing & Quality', 'Deployment & Collaboration']
        if 'machine learning' in role_lower or 'ai' in role_lower:
            return ['Data Preparation', 'Model Building', 'Evaluation & Tuning', 'Deployment & Monitoring']
        if 'product manager' in role_lower:
            return ['Customer Problems', 'Prioritization', 'Metrics & Experiments', 'Execution & Communication']
        return ['Foundations', 'Tools & Workflow', 'Execution', 'Communication & Impact']

    def _fallback_questions(self, target_role: str) -> List[Dict[str, Any]]:
        role_lower = target_role.lower()
        if 'data engineer' in role_lower:
            raw = [
                ('ETL', 'What is the main purpose of an ETL pipeline?', ['Encrypt text', 'Move and transform data', 'Train a model', 'Compress files'], 1),
                ('Databases', 'Which database is best described as relational?', ['MongoDB', 'PostgreSQL', 'Redis', 'Neo4j'], 1),
                ('Big Data', 'Which tool is widely used for distributed data processing?', ['Flask', 'Spark', 'Figma', 'TensorFlow'], 1),
                ('Cloud', 'What is object storage commonly used for?', ['Running CSS', 'Storing large files and data', 'Compiling Java', 'Drawing dashboards'], 1),
                ('Data Modeling', 'Why are partitioning strategies important?', ['They improve color design', 'They help query performance', 'They replace indexes', 'They eliminate schemas'], 1),
            ]
        elif 'data analyst' in role_lower:
            raw = [
                ('SQL', 'Which SQL clause is best for filtering aggregated results?', ['WHERE', 'GROUP BY', 'HAVING', 'ORDER BY'], 2),
                ('Excel', 'Which Excel function is most suitable to look up a value in a table?', ['SUMIF', 'VLOOKUP/XLOOKUP', 'COUNTIF', 'TEXTJOIN'], 1),
                ('Statistics', 'Which measure is most sensitive to outliers?', ['Median', 'Mode', 'Mean', 'Range'], 2),
                ('Visualization', 'Which chart is usually best for showing trends over time?', ['Pie chart', 'Line chart', 'Scatter plot', 'Treemap'], 1),
                ('Business Thinking', 'What should a good KPI primarily do?', ['Look pretty', 'Drive decisions', 'Reduce storage', 'Eliminate stakeholders'], 1),
            ]
        elif 'software' in role_lower or 'developer' in role_lower:
            raw = [
                ('Programming', 'What does version control primarily help with?', ['Cooking code', 'Tracking changes', 'Designing logos', 'Running SQL'], 1),
                ('APIs', 'REST APIs commonly exchange data in which format?', ['PNG', 'CSV', 'JSON', 'MP3'], 2),
                ('Testing', 'Unit tests are meant to validate:', ['Entire production servers', 'Small isolated pieces of code', 'Network cabling', 'UI color palettes'], 1),
                ('Architecture', 'Which principle improves maintainability?', ['Tight coupling', 'Single responsibility', 'Hard-coded secrets', 'No documentation'], 1),
                ('Security', 'Which is the safest place for API secrets?', ['Frontend code', 'GitHub README', 'Environment variables', 'CSS files'], 2),
            ]
        else:
            core_topics = self._derive_focus_topics(target_role, None)
            raw = [
                (core_topics[0], f'Which activity is most important in {target_role}?', ['Ignoring feedback', 'Structured problem solving', 'Skipping documentation', 'Avoiding tools'], 1),
                (core_topics[1], f'Which practice improves learning in {target_role}?', ['No projects', 'Hands-on practice', 'Only memorization', 'Random guessing'], 1),
                (core_topics[2], f'Why is measurement important in {target_role}?', ['It looks technical', 'It helps evaluate results', 'It replaces planning', 'It removes stakeholders'], 1),
                ('Collaboration', f'What improves teamwork in {target_role}?', ['Hidden work', 'Clear communication', 'No documentation', 'Avoiding review'], 1),
                ('Problem Solving', f'What is a strong approach for solving problems in {target_role}?', ['Jump directly to production', 'Break down the problem', 'Ignore requirements', 'Skip validation'], 1),
            ]

        return [
            {
                'id': idx,
                'topic': topic,
                'question': question,
                'options': options,
                'correct_option_index': correct_option_index,
                'explanation': 'This option best matches the concept used in realistic job scenarios.',
            }
            for idx, (topic, question, options, correct_option_index) in enumerate(raw, start=1)
        ]

    def _fallback_lesson(self, target_role: str, topic: str, lesson_number: int) -> Dict[str, Any]:
        lesson_titles = {
            1: f'{topic}: Core Concepts',
            2: f'{topic}: Workflow and Execution',
            3: f'{topic}: Applied Practice',
        }
        lesson_summaries = {
            1: f'This lesson explains the foundations of {topic.lower()} so the learner can understand the vocabulary, purpose, and core building blocks before moving into execution.',
            2: f'This lesson breaks {topic.lower()} into a repeatable workflow so the learner can understand how the topic is used step by step in realistic {target_role} work.',
            3: f'This lesson turns {topic.lower()} into hands-on practice using a realistic scenario, reflection, and quality review so the learner can apply the skill with confidence.',
        }
        lesson_takeaways = {
            1: [
                f'Define {topic.lower()} in practical language and connect it to real work.',
                f'Distinguish core parts, inputs, and outputs related to {topic.lower()}.',
                f'Identify where {topic.lower()} fits in the overall {target_role} workflow.',
            ],
            2: [
                f'Follow a structured workflow for executing {topic.lower()} tasks.',
                f'Understand the checkpoints that improve quality and reduce rework.',
                f'Explain how execution choices affect delivery, trust, and downstream use.',
            ],
            3: [
                f'Apply {topic.lower()} to a realistic task or mini case.',
                f'Evaluate output quality, assumptions, and communication points.',
                f'Reflect on how to improve the work in a real project setting.',
            ],
        }
        practice_tasks = {
            1: f'Create a one-page explanation of {topic.lower()} for a new team member, including purpose, inputs, outputs, and one common misunderstanding.',
            2: f'Write a step-by-step workflow for completing a {topic.lower()} task in a realistic {target_role} scenario. Include validation checkpoints and communication steps.',
            3: f'Complete a mini case using {topic.lower()}, then write a reflection explaining your decisions, assumptions, and what you would improve next.',
        }
        example_titles = {
            1: f'{topic}: foundation example',
            2: f'{topic}: execution example',
            3: f'{topic}: applied case example',
        }
        example_scenarios = {
            1: f'Imagine you have joined a team as an aspiring {target_role} and need to explain {topic.lower()} before touching any tools. Your goal is to show that you understand what the topic is, why it matters, and what a correct result should look like. This kind of conceptual clarity reduces mistakes later in the workflow.',
            2: f'Imagine you are assigned a live task that depends on {topic.lower()}. You need to move from business or technical requirement into a clear execution sequence, review the output, and communicate the result. This scenario focuses on operational discipline rather than memorization.',
            3: f'Imagine you are given a realistic assignment where {topic.lower()} must be applied to produce a useful output. You need to complete the work, inspect the result, note limitations, and explain the final recommendation in language another stakeholder can understand.',
        }
        example_steps = {
            1: [
                'Define the concept and the business or technical problem it helps solve.',
                'List the inputs, outputs, and dependencies tied to the topic.',
                'Describe how the topic connects to other work in the larger workflow.',
                'Summarize one misconception and how to avoid it.',
            ],
            2: [
                'Clarify the objective, success criteria, and constraints.',
                'Prepare the required inputs and choose the right method or tool.',
                'Execute the workflow in a repeatable sequence and inspect the output.',
                'Document the result and communicate what changed, why it matters, and any follow-up actions.',
            ],
            3: [
                'Review the case prompt, assumptions, and desired outcome.',
                'Apply the concept using a clear sequence of actions.',
                'Check the output for correctness, usefulness, and possible weaknesses.',
                'Write a short reflection covering trade-offs, risks, and next improvements.',
            ],
        }
        lesson_title = lesson_titles.get(lesson_number, f'{topic}: Practice')
        return {
            'lesson_number': lesson_number,
            'title': lesson_title,
            'format': 'reading + guided practice' if lesson_number != 3 else 'lab + reflection',
            'duration': '18 min' if lesson_number == 1 else '22 min' if lesson_number == 2 else '25 min',
            'summary': lesson_summaries.get(lesson_number, f'This lesson teaches {topic.lower()} in a practical way for an aspiring {target_role}.'),
            'key_takeaways': lesson_takeaways.get(lesson_number, lesson_takeaways[1]),
            'content_sections': self._default_content_sections(topic, target_role, lesson_title, lesson_number),
            'example': {
                'title': example_titles.get(lesson_number, f'{topic} example'),
                'scenario': example_scenarios.get(lesson_number, example_scenarios[1]),
                'steps': example_steps.get(lesson_number, example_steps[1]),
            },
            'practice_task': practice_tasks.get(lesson_number, practice_tasks[1]),
        }

    def _fallback_quiz(self, target_role: str, topic: str) -> List[Dict[str, Any]]:
        return [
            {
                'question': f'Why is {topic.lower()} important for a {target_role}?',
                'options': [
                    'It replaces communication and planning',
                    'It helps produce reliable and useful outcomes',
                    'It removes the need for validation',
                    'It only matters for senior executives',
                ],
                'answer': 'It helps produce reliable and useful outcomes',
                'explanation': 'Strong work happens when the concept improves decision quality, execution quality, or delivery quality.',
            },
            {
                'question': f'What is a good first step when working on {topic.lower()}?',
                'options': [
                    'Skip requirements and start building immediately',
                    'Clarify the goal and define the expected output',
                    'Wait until every detail is perfect',
                    'Avoid stakeholder feedback',
                ],
                'answer': 'Clarify the goal and define the expected output',
                'explanation': 'A clear objective prevents wasted effort and helps you choose the right workflow.',
            },
            {
                'question': f'Which behavior usually improves quality in {topic.lower()} work?',
                'options': [
                    'Document assumptions and validate the result',
                    'Hide intermediate work',
                    'Ignore edge cases',
                    'Avoid peer review',
                ],
                'answer': 'Document assumptions and validate the result',
                'explanation': 'Validation and documentation make the work easier to trust, improve, and hand off.',
            },
        ]

    def _fallback_assignment(self, target_role: str, topic: str) -> Dict[str, Any]:
        return {
            'title': f'{topic} mini project',
            'description': (
                f'Create a small but realistic deliverable that demonstrates how you would apply {topic.lower()} '
                f'in a {target_role} scenario. The emphasis should be on structured thinking, decision quality, and communication.'
            ),
            'deliverables': [
                'Problem statement and assumptions',
                'Step-by-step solution or workflow',
                'Short reflection on what you would improve next',
            ],
            'submission_type': 'text / notebook / PDF',
        }

    def _fallback_module(self, target_role: str, topic: str, module_number: int) -> Dict[str, Any]:
        return {
            'module_number': module_number,
            'title': f'{topic} for {target_role}',
            'module_summary': (
                f'This module builds practical understanding of {topic.lower()} and shows how the concept fits into the daily workflow '
                f'of a {target_role}. The lessons move from concept, to workflow, to applied execution.'
            ),
            'learning_objectives': [
                f'Understand the purpose and vocabulary of {topic.lower()}.',
                f'Apply {topic.lower()} using a clear and repeatable workflow.',
                f'Evaluate quality, risks, and communication points in {topic.lower()} work.',
            ],
            'lessons': [self._fallback_lesson(target_role, topic, lesson_number) for lesson_number in range(1, 4)],
            'quiz': self._fallback_quiz(target_role, topic),
            'assignment': self._fallback_assignment(target_role, topic),
        }

    def generate_assessment_questions(self, target_role: str) -> List[Dict[str, Any]]:
        if self.llm_enabled:
            try:
                response_text = self._call_huggingface(self._question_prompt(target_role), max_new_tokens=1200, temperature=0.2)
                parsed = self._extract_json(response_text)
                return self._normalize_questions(parsed, target_role)
            except Exception:
                pass

        return self._fallback_questions(target_role)

    def evaluate_assessment(
        self,
        target_role: str,
        answers: List[Dict[str, Any]],
        questions: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        source_questions = self._normalize_questions(questions, target_role) if questions else self.generate_assessment_questions(target_role)
        question_lookup = {q['id']: q for q in source_questions}
        correct_count = 0
        topic_scores: Dict[str, Dict[str, int]] = {}

        for answer in answers:
            question_id = answer.get('question_id')
            selected_index = answer.get('selected_option_index')
            question = question_lookup.get(question_id)
            if not question:
                continue

            topic = question['topic']
            topic_scores.setdefault(topic, {'correct': 0, 'total': 0})
            topic_scores[topic]['total'] += 1

            if selected_index == question['correct_option_index']:
                correct_count += 1
                topic_scores[topic]['correct'] += 1

        total_questions = max(len(source_questions), 1)
        score = round((correct_count / total_questions) * 100, 2)

        strengths: List[str] = []
        weaknesses: List[str] = []
        for topic, metrics in topic_scores.items():
            accuracy = metrics['correct'] / max(metrics['total'], 1)
            if accuracy >= 0.75:
                strengths.append(topic)
            else:
                weaknesses.append(topic)

        if not strengths:
            strengths = ['Learning motivation']
        if not weaknesses:
            weaknesses = ['Advanced optimization']

        recommendation = 'Beginner crash course' if score < 50 else 'Intermediate personalized course' if score < 80 else 'Advanced upskilling course'
        return {
            'score': score,
            'strengths': strengths,
            'weaknesses': weaknesses,
            'recommendation': recommendation,
        }

    def generate_course(
        self,
        target_role: str,
        experience_type: str,
        current_role: str = '',
        assessment_result: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if self.llm_enabled:
            try:
                response_text = self._call_huggingface(
                    self._course_prompt(target_role, experience_type, current_role, assessment_result),
                    max_new_tokens=3600,
                    temperature=0.3,
                )
                parsed = self._extract_json(response_text)
                return self._normalize_course(parsed, target_role, experience_type, current_role, assessment_result)
            except Exception:
                pass

        focus_topics = self._derive_focus_topics(target_role, assessment_result)
        fallback_course = {
            'title': f"{target_role} {'Crash Course' if experience_type == 'beginner' else 'Personalized Upskilling Track'}",
            'overview': (
                f'This course is designed to help a learner move toward the {target_role} role through structured lessons, '
                f'practical examples, quizzes, and assignments. The sequence starts with core concepts, then moves into workflow, '
                f'tooling, and applied execution so the learner can build useful job-ready thinking rather than memorize isolated facts.'
            ),
            'current_role_context': current_role,
            'experience_type': experience_type,
            'focus_topics': focus_topics,
            'estimated_duration': '4 to 6 weeks',
            'modules': [self._fallback_module(target_role, topic, index) for index, topic in enumerate(focus_topics[:4], start=1)],
            'capstone': {
                'title': f'{target_role} Final Challenge',
                'description': f'Build a realistic portfolio-ready project that demonstrates planning, execution, and communication expected from a {target_role}.',
                'deliverables': [
                    'Project brief and assumptions',
                    'Working solution or prototype',
                    'Final summary explaining decisions, trade-offs, and next steps',
                ],
            },
            'certificate_criteria': [
                'Complete all lessons',
                'Score at least 70% across quizzes',
                'Submit every module assignment',
                'Finish the capstone project',
            ],
        }
        return self._normalize_course(fallback_course, target_role, experience_type, current_role, assessment_result)

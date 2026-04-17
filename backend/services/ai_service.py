import json
import math
import os
import random
import re
from typing import Any, Dict, List, Optional

try:
    from huggingface_hub import InferenceClient
except Exception:  # pragma: no cover
    InferenceClient = None


class CourseAIService:
    def __init__(self):
        self.hf_token = os.getenv('HUGGINGFACE_API_TOKEN') or os.getenv('HF_TOKEN', '')
        self.model = os.getenv('HF_MODEL', 'Qwen/Qwen2.5-7B-Instruct')
        self.system_prompt = os.getenv(
            'SYSTEM_PROMPT',
            'You are a helpful educational assistant that generates practical, structured learning content.'
        )
        self.max_tokens = int(os.getenv('MAX_TOKENS', '1800'))
        self.temperature = float(os.getenv('TEMPERATURE', '0.4'))
        self.client = InferenceClient(api_key=self.hf_token, timeout=90) if (InferenceClient and self.hf_token) else None

    @property
    def llm_enabled(self) -> bool:
        return bool(self.client and self.hf_token)

    def _slug(self, value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')

    def _stable_random(self, *parts: str) -> random.Random:
        seed = '|'.join(str(part) for part in parts)
        return random.Random(seed)

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

    def _call_huggingface(self, prompt: str, max_new_tokens: int, temperature: float) -> str:
        if not self.llm_enabled:
            raise ValueError('Hugging Face client not configured')

        errors: List[str] = []
        if hasattr(self.client, 'chat'):
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {'role': 'system', 'content': self.system_prompt},
                        {'role': 'user', 'content': prompt},
                    ],
                    max_tokens=max_new_tokens,
                    temperature=temperature,
                )
                if completion and getattr(completion, 'choices', None):
                    content = completion.choices[0].message.content
                    if isinstance(content, str) and content.strip():
                        return content.strip()
                    if isinstance(content, list):
                        flattened = ''.join(str(part.get('text') or '') for part in content if isinstance(part, dict)).strip()
                        if flattened:
                            return flattened
            except Exception as exc:  # pragma: no cover
                errors.append(str(exc))

        try:
            generated = self.client.text_generation(
                prompt=prompt,
                model=self.model,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                return_full_text=False,
            )
            if isinstance(generated, str) and generated.strip():
                return generated.strip()
        except Exception as exc:  # pragma: no cover
            errors.append(str(exc))

        raise ValueError('; '.join(errors) or 'Model call failed')

    def chat(self, message: str, history: Optional[List[Dict[str, str]]] = None, topic_context: str = '') -> str:
        history_text = ''
        if history:
            trimmed = history[-6:]
            history_text = '\n'.join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in trimmed)
        prompt = (
            f'Current learning context: {topic_context or "General learning support"}\n\n'
            f'Conversation so far:\n{history_text}\n\n'
            f'User request: {message}\n\n'
            'Respond in clear Markdown with a concise answer followed by one example when useful.'
        )
        if self.llm_enabled:
            try:
                return self._call_huggingface(prompt, max_new_tokens=min(self.max_tokens, 900), temperature=self.temperature)
            except Exception:
                pass
        return (
            '## Quick explanation\n\n'
            'I could not reach the language model right now, so the live assistant is temporarily unavailable. '
            'Please try again after confirming the backend token and model settings.'
        )

    def _role_blueprint(self, target_role: str) -> Dict[str, Any]:
        role_lower = target_role.lower().strip()

        if 'aeronautical' in role_lower or 'aerospace' in role_lower:
            return {
                'estimated_duration': '5 to 7 weeks',
                'intro': 'aeronautical design, performance analysis, structural reasoning, certification awareness, and engineering communication',
                'focus_topics': [
                    'Aircraft Structures and Materials',
                    'Propulsion and Flight Mechanics',
                    'Aerodynamics Fundamentals',
                    'Testing, Certification, and Safety',
                ],
                'topic_profiles': {
                    'Aircraft Structures and Materials': {
                        'concepts': ['load paths', 'stress and strain', 'fatigue and fracture', 'material selection', 'weight-efficiency trade-offs'],
                        'workflow': ['translate requirements into load cases', 'estimate critical stresses and margins', 'compare candidate materials', 'review manufacturability and inspection concerns', 'document assumptions and structural risks'],
                        'tools': ['hand calculations', 'finite element reasoning', 'material property tables', 'margin tracking sheets'],
                        'pitfalls': ['treating static strength as enough', 'ignoring fatigue hot spots', 'choosing material by strength alone', 'forgetting inspection and repair implications'],
                        'scenario_bank': [
                            'A wing rib redesign must reduce weight without creating a fatigue concern near the fastener line.',
                            'A fuselage bracket is failing inspection because the current alloy cracks under repeated vibration loading.',
                            'A supplier proposes a composite substitution and the team needs a quick structural reasoning note before approving it.',
                        ],
                        'practice_bank': [
                            'Draft a comparison table for two candidate materials for a wing component, including weight, fatigue behavior, corrosion risk, and maintainability.',
                            'Write a short load-path explanation for a simple aircraft bracket and identify one location where failure is most likely to begin.',
                            'Review a hypothetical service bulletin and explain what structural evidence would justify a redesign recommendation.',
                        ],
                        'assignment_title': 'Structural trade-off note for an aircraft component',
                        'assignment_description': 'Prepare a concise engineering note that justifies a material and structural choice for a selected aircraft component under realistic loading and maintenance constraints.',
                        'deliverables': ['assumptions and load cases', 'material comparison with rationale', 'recommended design choice and risk notes'],
                    },
                    'Propulsion and Flight Mechanics': {
                        'concepts': ['thrust generation', 'drag and required power', 'climb and cruise performance', 'stability and control coupling', 'mission profile trade-offs'],
                        'workflow': ['define mission segment and constraints', 'estimate thrust, drag, and weight state', 'compare configuration or engine choices', 'check performance margins across phases of flight', 'communicate operational consequences'],
                        'tools': ['performance charts', 'mission spreadsheets', 'engine deck summaries', 'stability references'],
                        'pitfalls': ['evaluating cruise only', 'forgetting altitude or mass changes', 'confusing stability with controllability', 'ignoring off-design conditions'],
                        'scenario_bank': [
                            'A regional aircraft concept must meet a climb requirement from a hot-and-high airport with limited runway length.',
                            'A propulsion upgrade looks attractive for cruise efficiency, but the team is worried about takeoff and go-around margins.',
                            'A flight test report shows unexpected pitch sensitivity after a payload redistribution across the cabin.',
                        ],
                        'practice_bank': [
                            'Build a simple mission-phase reasoning table that explains how weight, thrust margin, and drag evolve from takeoff to cruise.',
                            'Explain how a propulsion decision would change climb performance and what secondary checks the team must perform.',
                            'Review a short scenario involving mass redistribution and describe its likely effect on stability and controllability.',
                        ],
                        'assignment_title': 'Mission performance review for a conceptual aircraft',
                        'assignment_description': 'Create a performance analysis for a conceptual aircraft mission profile and explain how propulsion choices interact with flight mechanics and operational requirements.',
                        'deliverables': ['mission assumptions and constraints', 'performance reasoning across flight phases', 'recommendation with trade-offs and risks'],
                    },
                    'Aerodynamics Fundamentals': {
                        'concepts': ['lift generation', 'drag breakdown', 'pressure distribution', 'flow separation', 'stability implications of aerodynamic choices'],
                        'workflow': ['identify the flight condition', 'translate shape or angle changes into aerodynamic effects', 'compare competing configurations', 'check whether the effect helps performance or handling', 'state the trade-off in plain engineering language'],
                        'tools': ['airfoil polars', 'wind-tunnel data', 'CFD summaries', 'performance comparison plots'],
                        'pitfalls': ['assuming more lift is always better', 'ignoring Reynolds-number effects', 'forgetting induced drag penalties', 'describing results without the flight condition'],
                        'scenario_bank': [
                            'Two wing concepts are being compared for a surveillance aircraft that must loiter efficiently without losing handling quality.',
                            'A flap setting improves takeoff distance but causes a new concern about approach drag and energy management.',
                            'A test team reports early flow separation in a maneuver where the baseline analysis predicted smooth airflow.',
                        ],
                        'practice_bank': [
                            'Compare two airfoil choices and explain which one you would prefer for a mission that values endurance over top speed.',
                            'Write a short note explaining how angle of attack, pressure distribution, and separation are linked in a realistic flight condition.',
                            'Review a lift-versus-drag trade-off and recommend one design adjustment, including what new risk it might introduce.',
                        ],
                        'assignment_title': 'Aerodynamic trade-off review for a wing concept',
                        'assignment_description': 'Evaluate a candidate wing or airfoil concept and explain how lift, drag, and handling trade-offs affect mission performance and design quality.',
                        'deliverables': ['comparison of aerodynamic options', 'effect on performance or handling', 'recommended next test or analysis step'],
                    },
                    'Testing, Certification, and Safety': {
                        'concepts': ['verification versus validation', 'compliance evidence', 'hazard identification', 'failure modes', 'traceable documentation'],
                        'workflow': ['define the requirement and compliance basis', 'map evidence to tests or analyses', 'review gaps or unsafe assumptions', 'record anomalies and corrective actions', 'communicate readiness and residual risk'],
                        'tools': ['test plans', 'requirements matrices', 'hazard logs', 'compliance checklists'],
                        'pitfalls': ['treating a test as compliance by default', 'writing vague pass criteria', 'ignoring traceability', 'under-communicating residual risk'],
                        'scenario_bank': [
                            'A subsystem is approaching certification review, but the evidence package is incomplete and several pass criteria are ambiguous.',
                            'A test campaign found a vibration issue that is not catastrophic yet, but it affects safety margin and certification confidence.',
                            'A program manager wants to accelerate testing, while the safety team is worried the current validation scope is too narrow.',
                        ],
                        'practice_bank': [
                            'Create a mini evidence matrix that links one requirement to a test, an analysis artifact, and a pass criterion.',
                            'Review a short hazard scenario and explain what additional evidence would be needed before declaring readiness.',
                            'Write a brief test-readiness note that states open risks, what has been validated, and what must happen next.',
                        ],
                        'assignment_title': 'Test and safety plan for a critical aeronautical subsystem',
                        'assignment_description': 'Draft a focused validation and safety plan for a critical subsystem, showing how requirements, evidence, and residual risks should be managed before approval.',
                        'deliverables': ['requirement-to-evidence mapping', 'test strategy and pass criteria', 'risk summary with follow-up actions'],
                    },
                },
            }

        if 'data engineer' in role_lower:
            return {
                'estimated_duration': '4 to 6 weeks',
                'intro': 'data ingestion, modeling, reliability, orchestration, and platform-minded delivery',
                'focus_topics': ['Data Pipelines', 'SQL and Data Modeling', 'Cloud Data Platforms', 'Data Quality and Reliability'],
                'topic_profiles': {
                    'Data Pipelines': {
                        'concepts': ['batch versus streaming', 'source-to-target flow', 'idempotency', 'schema evolution', 'dependency management'],
                        'workflow': ['clarify source and freshness needs', 'design extraction and transformation steps', 'orchestrate dependencies', 'monitor runs and failures', 'communicate downstream impact'],
                        'tools': ['Airflow', 'Spark', 'Kafka', 'Python ETL jobs'],
                        'pitfalls': ['hard-coding assumptions', 'ignoring late-arriving data', 'skipping retry strategy', 'omitting lineage'],
                        'scenario_bank': ['A daily sales pipeline is missing late transactions and finance is losing trust in the dashboard.', 'A new upstream API changed its schema and the ingestion job started silently dropping records.', 'A workflow now takes too long and blocks downstream ML feature generation each morning.'],
                        'practice_bank': ['Sketch a resilient pipeline flow for one operational dataset and list where validation checks should run.', 'Explain how you would make an ETL job idempotent so reruns do not duplicate records.', 'Review a failed orchestration run and describe the first three checks you would perform.'],
                        'assignment_title': 'Reliable pipeline design memo',
                        'assignment_description': 'Design a robust ingestion-to-consumption pipeline for a business dataset, including orchestration, validation, and failure handling.',
                        'deliverables': ['pipeline architecture diagram or outline', 'data quality checkpoints', 'incident or rerun strategy'],
                    },
                    'SQL and Data Modeling': {
                        'concepts': ['grain', 'primary and foreign keys', 'fact and dimension tables', 'normalization versus denormalization', 'query performance'],
                        'workflow': ['identify business entities and grain', 'map relationships and measures', 'design tables and keys', 'test query patterns', 'document assumptions for analysts'],
                        'tools': ['SQL', 'dbt', 'warehouse query planners', 'data dictionaries'],
                        'pitfalls': ['mixing grains', 'storing derived metrics without control', 'ignoring join cardinality', 'optimizing one query at the expense of model clarity'],
                        'scenario_bank': ['Marketing and finance define “active customer” differently, causing metric drift across reports.', 'A dashboard query is slow because the underlying model mixes transaction and monthly summary grain.', 'A team wants to add campaign attributes to a sales fact table without understanding dimensional modeling impact.'],
                        'practice_bank': ['Choose a grain for a revenue model and justify it in one paragraph.', 'Explain why a star schema may be more useful than a heavily normalized design for a reporting workload.', 'Review a join scenario and identify where double counting could appear.'],
                        'assignment_title': 'Analytics-ready warehouse model proposal',
                        'assignment_description': 'Propose a data model for a reporting or analytics use case, with clear grain, key relationships, and performance considerations.',
                        'deliverables': ['entity and grain definition', 'table design with joins', 'example analyst query and performance note'],
                    },
                    'Cloud Data Platforms': {
                        'concepts': ['object storage patterns', 'warehouse layers', 'compute-storage separation', 'security and access control', 'cost-performance trade-offs'],
                        'workflow': ['choose storage and processing services', 'define environment separation', 'set permissions and secrets handling', 'optimize workloads for cost and scale', 'monitor platform health'],
                        'tools': ['S3 or Azure Blob', 'BigQuery or Snowflake', 'IAM', 'Terraform'],
                        'pitfalls': ['overspending on always-on compute', 'broad permissions', 'no lifecycle policy', 'treating staging and production the same'],
                        'scenario_bank': ['A warehouse bill doubled after a new transformation schedule was deployed without cost controls.', 'An analytics team needs secure self-service access to curated data without seeing raw sensitive fields.', 'A platform migration is planned and the team must decide what should remain in object storage versus the warehouse.'],
                        'practice_bank': ['Design a medallion-style flow and explain which layer should host raw, cleaned, and business-ready data.', 'Write a short note on how compute-storage separation affects scaling and cost decisions.', 'Review a permissions scenario and explain the least-privilege approach you would recommend.'],
                        'assignment_title': 'Cloud data platform blueprint',
                        'assignment_description': 'Create a platform design for storing, transforming, and serving data securely in the cloud with attention to cost, access, and operational scale.',
                        'deliverables': ['service choices with rationale', 'security or access model', 'cost and monitoring strategy'],
                    },
                    'Data Quality and Reliability': {
                        'concepts': ['freshness', 'completeness', 'validity', 'observability', 'incident response'],
                        'workflow': ['define critical quality rules', 'instrument pipelines with checks and alerts', 'triage anomalies', 'communicate business impact', 'prevent recurrence through fixes and documentation'],
                        'tools': ['Great Expectations', 'dbt tests', 'monitoring dashboards', 'incident tickets'],
                        'pitfalls': ['tracking only row counts', 'alert fatigue', 'unclear ownership', 'treating quality as an afterthought'],
                        'scenario_bank': ['A null spike in customer IDs breaks a downstream segmentation workflow before an executive review.', 'A supposedly successful pipeline delivered stale data because freshness checks were missing.', 'An alert fired overnight, but no one knew which team owned the broken transformation.'],
                        'practice_bank': ['Define three high-value data quality checks for a customer orders table and explain why they matter.', 'Write a short incident summary for a stale-data event, including root cause and prevention actions.', 'Explain how you would separate noisy alerts from truly business-critical reliability problems.'],
                        'assignment_title': 'Data reliability playbook',
                        'assignment_description': 'Build a lightweight reliability and quality plan for a key dataset, including checks, alerting logic, and incident communication.',
                        'deliverables': ['quality rules and thresholds', 'alerting and ownership model', 'post-incident prevention actions'],
                    },
                },
            }


        if 'data scientist' in role_lower:
            return {
                'estimated_duration': '5 to 7 weeks',
                'intro': 'statistics, experimentation, machine learning, model evaluation, and business-focused data storytelling',
                'focus_topics': ['Python for Data Science', 'Statistics and Experimentation', 'Machine Learning Foundations', 'Model Evaluation and Deployment Readiness'],
                'topic_profiles': {
                    'Python for Data Science': {
                        'concepts': ['data wrangling', 'feature exploration', 'numerical computing', 'visualization', 'reproducible notebooks'],
                        'workflow': ['inspect raw data quality', 'clean and transform variables', 'explore distributions and relationships', 'document findings in notebooks', 'prepare a modeling-ready dataset'],
                        'tools': ['Python', 'Pandas', 'NumPy', 'Matplotlib or Seaborn'],
                        'pitfalls': ['ignoring missing values', 'mixing training and test logic', 'over-trusting defaults', 'failing to document assumptions'],
                        'scenario_bank': ['A churn dataset has duplicated rows, mixed date formats, and missing values before model training can begin.', 'A notebook gives different answers each run because preprocessing steps are not applied consistently.', 'An analyst needs to explain which variables deserve attention before building a predictive model.'],
                        'practice_bank': ['Outline a cleaning plan for a messy dataset and explain which checks you would run first.', 'Describe how you would separate exploratory work from reusable preprocessing logic.', 'Review a notebook workflow and identify where reproducibility could break.'],
                        'assignment_title': 'Exploratory analysis and data preparation brief',
                        'assignment_description': 'Prepare a clean, analysis-ready dataset and document the transformation, exploration, and reproducibility choices that support downstream modeling.',
                        'deliverables': ['cleaning and transformation summary', 'exploratory findings with visuals', 'reproducible preparation workflow'],
                    },
                    'Statistics and Experimentation': {
                        'concepts': ['sampling', 'hypothesis testing', 'confidence intervals', 'bias and variance', 'experiment design'],
                        'workflow': ['frame the decision question', 'choose a metric and hypothesis', 'check assumptions and sample quality', 'run the statistical test', 'communicate practical meaning and risk'],
                        'tools': ['SciPy', 'statsmodels', 'A/B testing plans', 'metric dashboards'],
                        'pitfalls': ['p-hacking', 'confusing correlation with causation', 'ignoring sample bias', 'over-reporting significance without impact'],
                        'scenario_bank': ['A product team wants to declare a new onboarding flow better after only a few days of noisy experiment data.', 'A model improvement looks promising, but the sample was drawn from only one customer segment.', 'A stakeholder asks whether a result is statistically significant and practically meaningful.'],
                        'practice_bank': ['Explain the difference between statistical significance and business significance in one example.', 'Draft a simple A/B test plan including hypothesis, metric, and sample concerns.', 'Review an experiment summary and identify one bias or validity risk.'],
                        'assignment_title': 'Experiment design and interpretation memo',
                        'assignment_description': 'Design and interpret a small experiment or statistical study, showing how evidence supports or limits the final recommendation.',
                        'deliverables': ['hypothesis and metric definition', 'test design and validity checks', 'interpretation of results and limitations'],
                    },
                    'Machine Learning Foundations': {
                        'concepts': ['supervised learning', 'feature engineering', 'overfitting', 'regularization', 'model selection'],
                        'workflow': ['define the prediction target', 'select features and baseline approach', 'train and compare candidate models', 'analyze errors and overfitting', 'summarize model trade-offs'],
                        'tools': ['scikit-learn', 'Python pipelines', 'feature stores', 'notebook experiments'],
                        'pitfalls': ['data leakage', 'optimizing one metric blindly', 'ignoring class imbalance', 'using complex models before baselines'],
                        'scenario_bank': ['A fraud model performs well in validation but fails after deployment because leakage was hidden in a derived feature.', 'A team wants to jump to XGBoost before establishing a simple baseline model.', 'An imbalanced classification problem shows high accuracy but poor recall on the class that matters most.'],
                        'practice_bank': ['Describe how you would build a trustworthy baseline model before testing advanced algorithms.', 'Explain how class imbalance changes metric choice and threshold reasoning.', 'Review a feature list and identify one likely leakage risk.'],
                        'assignment_title': 'Baseline-to-model-selection report',
                        'assignment_description': 'Build a small machine learning decision flow from target definition to candidate model comparison, emphasizing trustworthy feature and evaluation choices.',
                        'deliverables': ['target and feature design', 'baseline and candidate model comparison', 'risk analysis for overfitting or leakage'],
                    },
                    'Model Evaluation and Deployment Readiness': {
                        'concepts': ['evaluation metrics', 'threshold selection', 'monitoring', 'drift', 'explainability'],
                        'workflow': ['match metrics to business risk', 'evaluate across validation scenarios', 'set decision thresholds', 'define monitoring and retraining signals', 'communicate deployment readiness'],
                        'tools': ['confusion matrices', 'ROC/PR curves', 'MLflow', 'monitoring dashboards'],
                        'pitfalls': ['treating accuracy as enough', 'ignoring drift', 'no monitoring plan', 'deploying without stakeholder-readable explanations'],
                        'scenario_bank': ['A classifier has good aggregate metrics but fails badly for one high-risk subgroup.', 'A team wants to deploy a model without a monitoring or retraining plan.', 'A stakeholder needs a plain-language explanation of why a model recommendation should be trusted.'],
                        'practice_bank': ['Choose appropriate metrics for a model where false negatives are much more costly than false positives.', 'Outline a lightweight monitoring plan for a production model.', 'Explain what model drift means and how you would detect it.'],
                        'assignment_title': 'Model readiness review',
                        'assignment_description': 'Prepare a deployment-readiness review for a machine learning model, including metrics, monitoring, explainability, and operational risk controls.',
                        'deliverables': ['metric and threshold rationale', 'monitoring and drift plan', 'stakeholder-facing readiness summary'],
                    },
                },
            }

        if 'ai developer' in role_lower or re.search(r'ai', role_lower):
            return {
                'estimated_duration': '5 to 7 weeks',
                'intro': 'python application building, llm workflows, prompt design, retrieval systems, and responsible AI delivery',
                'focus_topics': ['Python Application Foundations', 'Prompt Engineering and LLM Workflows', 'RAG and Knowledge Integration', 'Evaluation, Safety, and AI Product Delivery'],
                'topic_profiles': {
                    'Python Application Foundations': {
                        'concepts': ['modular Python code', 'API integration', 'state management', 'testing basics', 'error handling'],
                        'workflow': ['define the user flow', 'design the application modules', 'integrate external APIs safely', 'test failure paths', 'prepare maintainable code for iteration'],
                        'tools': ['Python', 'FastAPI or Flask', 'requests', 'dotenv'],
                        'pitfalls': ['hard-coding secrets', 'mixing business logic with UI logic', 'no error handling', 'not testing integration failures'],
                        'scenario_bank': ['An AI assistant app works locally but fails in production because API keys and settings are not handled safely.', 'A prototype grows quickly and becomes difficult to extend because the codebase has no modular structure.', 'A user-facing AI feature crashes when the model API returns an empty or malformed response.'],
                        'practice_bank': ['Outline a clean Python app structure for an AI product with backend, service, and UI layers.', 'Explain how you would handle a model API timeout without breaking the user experience.', 'Review a small Python integration and identify one maintainability or safety risk.'],
                        'assignment_title': 'Python AI app architecture memo',
                        'assignment_description': 'Design the backend structure for a small AI application, including API calls, error handling, and separation of concerns.',
                        'deliverables': ['application module layout', 'integration and error-handling plan', 'maintainability and security notes'],
                    },
                    'Prompt Engineering and LLM Workflows': {
                        'concepts': ['instruction design', 'context windows', 'structured outputs', 'tool use', 'prompt iteration'],
                        'workflow': ['define the desired output contract', 'write system and task prompts', 'test edge cases and failures', 'refine for structure and quality', 'document prompt assumptions'],
                        'tools': ['LLM APIs', 'JSON schemas', 'prompt templates', 'evaluation logs'],
                        'pitfalls': ['overly vague prompts', 'no output validation', 'prompt injection blind spots', 'trusting first outputs without testing'],
                        'scenario_bank': ['A course generator keeps returning malformed JSON because the prompt does not enforce a strong output contract.', 'A chatbot gives inconsistent answers because context handling changes across requests.', 'A model follows the prompt for one role but produces generic content for another because prompt grounding is weak.'],
                        'practice_bank': ['Rewrite a weak prompt so it requests structured JSON and role-specific constraints.', 'Explain why output validation matters even when the prompt looks clear.', 'Review a prompt workflow and identify one likely source of inconsistency.'],
                        'assignment_title': 'Structured LLM workflow design',
                        'assignment_description': 'Create a prompt and validation strategy for an LLM-powered feature that must return stable, structured outputs.',
                        'deliverables': ['prompt design with constraints', 'output validation strategy', 'failure and retry plan'],
                    },
                    'RAG and Knowledge Integration': {
                        'concepts': ['embeddings', 'retrieval quality', 'chunking', 'grounding', 'citation or evidence traceability'],
                        'workflow': ['prepare the knowledge source', 'chunk and index documents', 'retrieve relevant context', 'ground generation in evidence', 'evaluate answer faithfulness'],
                        'tools': ['vector databases', 'embedding models', 'retrievers', 'document parsers'],
                        'pitfalls': ['poor chunking', 'retrieving irrelevant context', 'hallucinating beyond evidence', 'no source traceability'],
                        'scenario_bank': ['A support bot answers confidently from irrelevant retrieved chunks and users lose trust.', 'A knowledge base was indexed quickly, but retrieval quality is poor because chunks are too large and generic.', 'An internal assistant needs answers grounded only in approved company documents.'],
                        'practice_bank': ['Explain how chunk size affects retrieval quality and answer accuracy.', 'Sketch a simple RAG flow from ingestion to grounded answer generation.', 'Review a retrieval failure and identify what should be checked first.'],
                        'assignment_title': 'Grounded AI knowledge flow blueprint',
                        'assignment_description': 'Design a retrieval-augmented generation workflow that improves answer grounding, relevance, and traceability.',
                        'deliverables': ['knowledge ingestion and chunking plan', 'retrieval and grounding flow', 'evaluation criteria for relevance and faithfulness'],
                    },
                    'Evaluation, Safety, and AI Product Delivery': {
                        'concepts': ['quality evaluation', 'guardrails', 'hallucination risk', 'user feedback loops', 'release readiness'],
                        'workflow': ['define evaluation criteria', 'test normal and adversarial cases', 'add guardrails and fallback logic', 'collect user feedback', 'decide launch readiness'],
                        'tools': ['test suites', 'moderation rules', 'analytics dashboards', 'human review checklists'],
                        'pitfalls': ['shipping without evaluation', 'ignoring unsafe outputs', 'no fallback plan', 'optimizing demos over reliability'],
                        'scenario_bank': ['An AI feature looks impressive in demos but fails on edge cases and unsafe prompts.', 'A team wants to launch a generative feature without a clear evaluation rubric.', 'User feedback reveals that the model is helpful but too unpredictable for operational use.'],
                        'practice_bank': ['List evaluation checks you would run before releasing an AI feature to real users.', 'Explain how fallback logic improves trust in an AI product.', 'Review a generated response and identify one safety or reliability concern.'],
                        'assignment_title': 'AI feature launch readiness review',
                        'assignment_description': 'Prepare an evaluation and guardrail plan for an AI feature, showing how you would test quality, safety, and release readiness.',
                        'deliverables': ['evaluation rubric', 'guardrails and fallback design', 'release-readiness recommendation'],
                    },
                },
            }

        if 'ml engineer' in role_lower or 'machine learning engineer' in role_lower:
            return {
                'estimated_duration': '5 to 7 weeks',
                'intro': 'model training pipelines, feature workflows, deployment systems, and production reliability for machine learning',
                'focus_topics': ['Python and ML Pipeline Foundations', 'Feature Engineering and Training Workflows', 'Model Serving and Deployment', 'Monitoring, Drift, and ML System Reliability'],
                'topic_profiles': {
                    'Python and ML Pipeline Foundations': {
                        'concepts': ['modular ML code', 'data pipeline structure', 'experiment tracking', 'environment control', 'reproducibility'],
                        'workflow': ['define the ML problem and data contract', 'build reusable preprocessing steps', 'track experiments consistently', 'package code for repeatable runs', 'document assumptions and dependencies'],
                        'tools': ['Python', 'scikit-learn', 'virtual environments', 'MLflow'],
                        'pitfalls': ['not versioning data assumptions', 'not tracking experiments', 'mixing notebook-only logic with production code', 'reproducibility gaps'],
                        'scenario_bank': ['Two engineers train the same model and get different results because the pipeline is not reproducible.', 'A prototype model performs well but cannot be rerun reliably after package updates.', 'A training workflow is spread across notebooks and ad hoc scripts, making handoff difficult.'],
                        'practice_bank': ['Outline a reproducible ML project structure that separates data prep, training, and evaluation.', 'Explain what experiment tracking should capture for a model development workflow.', 'Review a notebook-heavy project and identify one production-readiness weakness.'],
                        'assignment_title': 'Reproducible ML workflow brief',
                        'assignment_description': 'Design a reproducible machine learning workflow in Python, including preprocessing, tracking, and repeatable execution logic.',
                        'deliverables': ['project structure and dependency plan', 'experiment tracking approach', 'reproducibility controls'],
                    },
                    'Feature Engineering and Training Workflows': {
                        'concepts': ['feature pipelines', 'training-validation splits', 'data leakage', 'hyperparameter search', 'error analysis'],
                        'workflow': ['design the feature pipeline', 'protect validation integrity', 'train baseline and candidate models', 'analyze errors and feature impact', 'decide what to improve next'],
                        'tools': ['feature pipelines', 'cross-validation', 'scikit-learn', 'training scripts'],
                        'pitfalls': ['leakage through preprocessing', 'optimizing metrics without context', 'skipping baseline models', 'weak error analysis'],
                        'scenario_bank': ['A model scores highly in validation because a future-looking field leaked into training.', 'A team tunes hyperparameters aggressively but cannot explain failure modes on real data.', 'A baseline model was skipped, so no one knows whether complexity improved the system meaningfully.'],
                        'practice_bank': ['Describe how you would prevent leakage in a feature pipeline.', 'Explain why baseline models and error analysis should come before complex tuning.', 'Review a training setup and identify one weak validation choice.'],
                        'assignment_title': 'Training pipeline review',
                        'assignment_description': 'Prepare a machine learning training workflow that emphasizes feature integrity, baseline comparison, and disciplined evaluation.',
                        'deliverables': ['feature and split strategy', 'baseline-to-candidate training plan', 'error analysis and improvement path'],
                    },
                    'Model Serving and Deployment': {
                        'concepts': ['batch versus online inference', 'latency budgets', 'API serving', 'containerization', 'release strategy'],
                        'workflow': ['define inference requirements', 'choose serving pattern', 'package model artifacts and dependencies', 'test deployment behavior', 'plan rollback and release controls'],
                        'tools': ['FastAPI', 'Docker', 'model registries', 'serving endpoints'],
                        'pitfalls': ['ignoring latency', 'no rollback plan', 'breaking feature parity between training and inference', 'deploying without load testing'],
                        'scenario_bank': ['A recommender model works offline but fails online because feature generation differs at inference time.', 'A team wants real-time predictions, but the service cannot meet latency requirements under load.', 'A model release is pushed without a rollback path and causes downstream failures.'],
                        'practice_bank': ['Compare when batch inference is better than online inference for one business problem.', 'Outline a simple deployment path for a Python model service.', 'Explain why feature parity matters between training and serving.'],
                        'assignment_title': 'ML deployment blueprint',
                        'assignment_description': 'Design a deployment-ready serving approach for a machine learning model, covering latency, packaging, rollout, and rollback thinking.',
                        'deliverables': ['serving architecture', 'release and rollback plan', 'latency and dependency considerations'],
                    },
                    'Monitoring, Drift, and ML System Reliability': {
                        'concepts': ['data drift', 'concept drift', 'performance monitoring', 'alerting', 'retraining criteria'],
                        'workflow': ['define health metrics', 'monitor live data and predictions', 'triage performance drops', 'investigate drift causes', 'decide retraining or rollback actions'],
                        'tools': ['monitoring dashboards', 'prediction logs', 'alerting rules', 'drift reports'],
                        'pitfalls': ['monitoring only uptime', 'no ownership for model failures', 'unclear retraining triggers', 'ignoring subgroup performance'],
                        'scenario_bank': ['A model remains live, but its prediction quality drops because customer behavior changed after launch.', 'An alert fires for model performance, but no one knows whether the issue is drift, data quality, or service failure.', 'A retraining pipeline runs regularly but no one can justify whether the new model is truly better.'],
                        'practice_bank': ['Explain the difference between data drift and concept drift using one example.', 'List the first checks you would run after a model performance alert.', 'Outline a sensible retraining trigger policy for a production model.'],
                        'assignment_title': 'ML reliability playbook',
                        'assignment_description': 'Create a monitoring and response plan for a production machine learning system, covering drift, reliability, and retraining decisions.',
                        'deliverables': ['monitoring metrics and thresholds', 'incident triage process', 'retraining or rollback criteria'],
                    },
                },
            }

        if 'physics' in role_lower:
            return {
                'estimated_duration': '5 to 6 weeks',
                'intro': 'physical intuition, mathematical modeling, experimental reasoning, and interpretation of evidence',
                'focus_topics': ['Classical Mechanics', 'Electricity and Magnetism', 'Waves and Quantum Ideas', 'Experimental Methods and Data Interpretation'],
                'topic_profiles': {
                    'Classical Mechanics': {
                        'concepts': ['forces and free-body thinking', 'energy methods', 'momentum', 'rotational dynamics', 'model assumptions'],
                        'workflow': ['define the system boundary', 'choose the governing principles', 'represent variables and constraints', 'solve and sanity-check the result', 'interpret the physical meaning'],
                        'tools': ['algebraic modeling', 'calculus', 'graphs', 'dimensional analysis'],
                        'pitfalls': ['mixing vectors and scalars carelessly', 'using formulas without assumptions', 'ignoring conservation checks', 'forgetting units'],
                        'scenario_bank': ['A lab cart system behaves differently from the frictionless model and students must explain the discrepancy.', 'A rotating platform problem can be solved using either torque or energy, but each method highlights different assumptions.', 'A projectile scenario looks simple until air resistance and reference frame choices are discussed.'],
                        'practice_bank': ['Explain when an energy method is more efficient than direct force summation.', 'Create a free-body narrative for a system with two connected masses.', 'Solve a mechanics problem and then check the result with units and a limiting-case sanity test.'],
                        'assignment_title': 'Mechanics modeling report',
                        'assignment_description': 'Build and explain a physics model for a realistic motion problem, including assumptions, equations, and interpretation.',
                        'deliverables': ['problem setup and assumptions', 'solution with checks', 'physical interpretation and limitations'],
                    },
                    'Electricity and Magnetism': {
                        'concepts': ['field and potential', 'circuit behavior', 'Gauss and Faraday intuition', 'magnetic force', 'energy storage'],
                        'workflow': ['identify symmetry or circuit structure', 'select a governing law', 'track sign conventions and reference directions', 'check whether the result is physically plausible', 'connect the math back to the field behavior'],
                        'tools': ['circuit diagrams', 'field sketches', 'vector reasoning', 'graph interpretation'],
                        'pitfalls': ['memorizing laws without geometry', 'sign mistakes', 'mixing field and force language', 'ignoring boundary conditions'],
                        'scenario_bank': ['A capacitor discharge circuit seems straightforward until time constants are compared against measurement noise.', 'A field problem is easier after noticing spherical symmetry, but students often miss that observation.', 'A magnetic-force setup requires careful right-hand-rule reasoning to avoid a sign error.'],
                        'practice_bank': ['Describe the difference between electric field and electric potential using one concrete example.', 'Explain how symmetry helps decide whether Gauss’s law is useful in a given setup.', 'Review a simple RL or RC response and identify what the time constant means physically.'],
                        'assignment_title': 'E&M concept-to-calculation brief',
                        'assignment_description': 'Analyze an electricity or magnetism problem by combining physical intuition, equations, and a clear interpretation of the result.',
                        'deliverables': ['diagram and assumptions', 'governing law selection', 'interpreted result and error checks'],
                    },
                    'Waves and Quantum Ideas': {
                        'concepts': ['superposition', 'interference', 'standing waves', 'probability interpretation', 'discrete states'],
                        'workflow': ['describe the wave or quantum system', 'identify what is measurable', 'use the governing relation or model', 'compare qualitative and quantitative behavior', 'state what the mathematics means physically'],
                        'tools': ['wave sketches', 'phasor reasoning', 'probability plots', 'boundary-condition thinking'],
                        'pitfalls': ['treating amplitude and intensity as the same', 'speaking about quantum states as if they were classical trajectories', 'ignoring phase', 'losing track of measurement meaning'],
                        'scenario_bank': ['Two-slit data shows a pattern shift and the team must explain what changed in terms of phase and path difference.', 'A standing-wave mode problem requires boundary conditions before any equation can be trusted.', 'A quantum-state explanation sounds correct mathematically but fails to connect to what a measurement would reveal.'],
                        'practice_bank': ['Explain why interference depends on phase rather than only amplitude.', 'Describe the physical meaning of a standing-wave boundary condition.', 'Write a short conceptual answer distinguishing a probability amplitude from a classical path description.'],
                        'assignment_title': 'Wave or quantum interpretation exercise',
                        'assignment_description': 'Work through a wave or introductory quantum scenario and explain both the mathematics and the physical interpretation.',
                        'deliverables': ['system description and assumptions', 'calculation or reasoning sequence', 'physical interpretation and misconception check'],
                    },
                    'Experimental Methods and Data Interpretation': {
                        'concepts': ['measurement uncertainty', 'signal versus noise', 'calibration', 'model-data comparison', 'error sources'],
                        'workflow': ['define the measurement goal', 'set up controls and calibration', 'collect data consistently', 'analyze uncertainty and fit quality', 'state what conclusions are justified'],
                        'tools': ['plots', 'regression', 'uncertainty propagation', 'lab notebooks'],
                        'pitfalls': ['reporting precision without accuracy', 'overfitting sparse data', 'ignoring systematic error', 'drawing conclusions broader than the evidence'],
                        'scenario_bank': ['A measured gravitational constant differs from expectation and the issue may be systematic rather than random.', 'A resonance experiment shows a noisy peak that tempts students to over-interpret the exact maximum.', 'A model fits the data visually, but residual patterns reveal an unaccounted physical effect.'],
                        'practice_bank': ['Write a short explanation of the difference between random and systematic error.', 'Review a plotted dataset and describe what residuals can tell you beyond the main fit line.', 'Design one calibration or control step that would improve trust in a lab result.'],
                        'assignment_title': 'Experimental analysis summary',
                        'assignment_description': 'Produce an evidence-based analysis of a physics experiment, including uncertainty, model comparison, and justified conclusions.',
                        'deliverables': ['measurement plan and assumptions', 'analysis with uncertainty or fit discussion', 'conclusion with limitations'],
                    },
                },
            }

        generic_topics = self._generic_focus_topics(target_role)
        return {
            'estimated_duration': '4 to 6 weeks',
            'intro': 'role fundamentals, execution workflow, practical problem solving, and professional communication',
            'focus_topics': generic_topics,
            'topic_profiles': {topic: self._generic_topic_profile(target_role, topic) for topic in generic_topics},
        }

    def _generic_focus_topics(self, target_role: str) -> List[str]:
        role = target_role.strip() or 'Professional'
        role_words = [part for part in re.split(r'\s+', role) if part]
        lead = ' '.join(role_words[:2])
        return [
            f'{lead} Core Concepts and Domain Vocabulary',
            f'{lead} Methods, Workflows, and Quality Checks',
            f'{lead} Applied Scenarios and Decision-Making',
            f'{lead} Communication, Ethics, and Professional Judgment',
        ]

    def _generic_topic_profile(self, target_role: str, topic: str) -> Dict[str, Any]:
        slug = self._slug(topic)
        if 'communication' in slug:
            concepts = ['stakeholder needs', 'clear summaries', 'decision rationale', 'handoffs', 'evidence-based recommendations']
            workflow = ['understand the audience', 'gather the right evidence', 'structure the message', 'check clarity and completeness', 'close with next actions']
            pitfalls = ['overloading detail', 'skipping the recommendation', 'using jargon without context', 'hiding risks']
        elif 'workflow' in slug or 'tools' in slug:
            concepts = ['repeatable process', 'tool choice', 'quality checks', 'handoffs', 'time management']
            workflow = ['clarify the task', 'choose method and tools', 'execute in a repeatable sequence', 'review the result', 'communicate outcome and next step']
            pitfalls = ['tool-first thinking', 'no quality gate', 'poor documentation', 'ignoring constraints']
        elif 'problem-solving' in slug:
            concepts = ['problem framing', 'root-cause reasoning', 'trade-offs', 'validation', 'iteration']
            workflow = ['frame the problem', 'generate candidate approaches', 'test assumptions', 'compare solutions', 'recommend and refine']
            pitfalls = ['guessing too early', 'treating symptoms as causes', 'not comparing alternatives', 'stopping before validation']
        else:
            concepts = ['core vocabulary', 'goals and outputs', 'common patterns', 'quality expectations', 'role context']
            workflow = ['define the objective', 'prepare inputs', 'apply a structured method', 'review output quality', 'document what was learned']
            pitfalls = ['memorizing without application', 'unclear success criteria', 'weak validation', 'poor explanation']
        return {
            'concepts': concepts,
            'workflow': workflow,
            'tools': ['notes', 'checklists', 'examples', 'reflection prompts'],
            'pitfalls': pitfalls,
            'scenario_bank': [
                f'A learner targeting the {target_role} path needs to use {topic.lower()} to solve a realistic workplace problem with limited time and imperfect information.',
                f'A teammate asks for a clear explanation of how {topic.lower()} should be handled so that the result is reliable and easy to review.',
                f'A project depends on {topic.lower()}, but the first attempt is weak because assumptions and quality checks were not made explicit.',
            ],
            'practice_bank': [
                f'Write a short structured note explaining how {topic.lower()} helps a {target_role} make better decisions.',
                f'Create a step-by-step workflow for completing a {topic.lower()} task and include at least two quality checks.',
                f'Review one realistic scenario and explain what evidence or validation would make the result trustworthy.',
            ],
            'assignment_title': f'{topic} applied mini project',
            'assignment_description': f'Produce a practical deliverable that shows how {topic.lower()} would be applied in realistic {target_role} work.',
            'deliverables': ['problem statement and assumptions', 'workflow or solution outline', 'reflection on quality and next improvements'],
        }

    def _derive_focus_topics(self, target_role: str, assessment_result: Optional[Dict[str, Any]]) -> List[str]:
        blueprint = self._role_blueprint(target_role)
        baseline = list(blueprint['focus_topics'])
        if assessment_result and assessment_result.get('weaknesses'):
            weaknesses = [str(item).strip() for item in assessment_result.get('weaknesses', []) if str(item).strip()]
            ordered = []
            for topic in weaknesses + baseline:
                if topic and topic not in ordered:
                    ordered.append(topic)
            while len(ordered) < 4:
                ordered.append(f'{target_role} Improvement Area {len(ordered) + 1}')
            return ordered[:4]
        return baseline[:4]

    def _question_templates(self, topic: str, role: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        concepts = profile['concepts']
        workflow = profile['workflow']
        pitfalls = profile['pitfalls']
        tools = profile['tools']
        scenario = profile['scenario_bank'][0]
        return [
            {
                'difficulty': 'Easy',
                'question': f'In {topic.lower()}, what is the strongest reason to begin by clarifying the objective before touching tools or formulas?',
                'options': [
                    'It avoids all documentation',
                    'It helps choose the right method and success criteria',
                    'It removes the need for validation',
                    'It guarantees the fastest result in every case',
                ],
                'correct_option_index': 1,
                'explanation': 'A clear objective helps you select the right approach, judge whether the result is useful, and avoid solving the wrong problem.',
            },
            {
                'difficulty': 'Easy',
                'question': f'Which choice best reflects the core meaning of {topic.lower()} for a {role}?',
                'options': [
                    f'A structured capability involving {concepts[0]}, {concepts[1]}, and informed decision-making',
                    'A one-time checklist that replaces judgment',
                    'Only a software tool with no conceptual component',
                    'A topic relevant only to senior management',
                ],
                'correct_option_index': 0,
                'explanation': f'{topic} is not only terminology. It combines concepts, reasoning, and practical execution in realistic work.',
            },
            {
                'difficulty': 'Medium',
                'question': f'When executing {topic.lower()} work, which sequence is usually the most reliable?',
                'options': [
                    f'{workflow[0].capitalize()} -> {workflow[1]} -> {workflow[2]} -> {workflow[3]}',
                    'Start with the final recommendation -> gather evidence later -> skip review -> present immediately',
                    'Choose a favorite tool -> produce output -> define the problem afterward -> communicate only if asked',
                    'Collect every possible detail -> wait for perfect certainty -> avoid iteration -> skip documentation',
                ],
                'correct_option_index': 0,
                'explanation': 'Strong execution moves from a clear objective into structured work, then validates the result before communication.',
            },
            {
                'difficulty': 'Medium',
                'question': f'Which situation best shows a conceptual weakness in {topic.lower()} rather than a simple clerical mistake?',
                'options': [
                    f'Someone uses {tools[0]} but forgets to rename a file',
                    f'Someone ignores {pitfalls[0]} and cannot explain whether the output actually supports the requirement',
                    'A typo appears in a status message',
                    'A presentation uses the wrong font size',
                ],
                'correct_option_index': 1,
                'explanation': 'Conceptual weakness appears when a learner cannot connect method, assumptions, and quality checks to the actual goal.',
            },
            {
                'difficulty': 'Hard',
                'question': f'A learner is working on this scenario: {scenario} What makes the final recommendation trustworthy?',
                'options': [
                    'It sounds confident and uses advanced terminology',
                    'It is the first solution produced, so it preserves time',
                    'It states assumptions, compares trade-offs, and shows how the result was checked',
                    'It avoids discussing risks so stakeholders stay calm',
                ],
                'correct_option_index': 2,
                'explanation': 'Trustworthy work explains assumptions, validates the reasoning, and shows what trade-offs or residual risks remain.',
            },
        ]

    def _build_assessment_questions(self, target_role: str) -> List[Dict[str, Any]]:
        blueprint = self._role_blueprint(target_role)
        topics = blueprint['focus_topics']
        questions: List[Dict[str, Any]] = []
        question_id = 1
        for topic in topics:
            profile = blueprint['topic_profiles'][topic]
            templates = self._question_templates(topic, target_role, profile)
            for item in templates[:2 if len(questions) < 8 else 1]:
                questions.append({
                    'id': question_id,
                    'topic': topic,
                    'difficulty': item['difficulty'],
                    'question': item['question'],
                    'options': item['options'],
                    'correct_option_index': item['correct_option_index'],
                    'explanation': item['explanation'],
                })
                question_id += 1
        # ensure 10 questions with 4-topic spread and different complexity
        extra_order = [
            (topics[0], 2),
            (topics[1], 2),
            (topics[2], 3),
            (topics[3], 4),
            (topics[0], 4),
            (topics[1], 3),
        ]
        for topic, template_index in extra_order:
            if len(questions) >= 10:
                break
            profile = blueprint['topic_profiles'][topic]
            item = self._question_templates(topic, target_role, profile)[template_index]
            questions.append({
                'id': question_id,
                'topic': topic,
                'difficulty': item['difficulty'],
                'question': item['question'],
                'options': item['options'],
                'correct_option_index': item['correct_option_index'],
                'explanation': item['explanation'],
            })
            question_id += 1
        return questions[:10]

    def _normalize_questions(self, questions: Any, target_role: str) -> List[Dict[str, Any]]:
        fallback = self._build_assessment_questions(target_role)
        if not isinstance(questions, list):
            return fallback
        cleaned: List[Dict[str, Any]] = []
        for index, item in enumerate(questions[:10], start=1):
            if not isinstance(item, dict):
                continue
            options = item.get('options') if isinstance(item.get('options'), list) else []
            options = [str(option).strip() for option in options[:4] if str(option).strip()]
            if len(options) != 4:
                continue
            correct_idx = item.get('correct_option_index', 0)
            try:
                correct_idx = int(correct_idx)
            except Exception:
                correct_idx = 0
            if correct_idx < 0 or correct_idx > 3:
                correct_idx = 0
            question_text = str(item.get('question') or '').strip()
            topic = str(item.get('topic') or '').strip() or fallback[min(index - 1, len(fallback) - 1)]['topic']
            difficulty = str(item.get('difficulty') or 'Medium').strip().title()
            if not question_text:
                continue
            cleaned.append({
                'id': index,
                'topic': topic,
                'difficulty': difficulty if difficulty in {'Easy', 'Medium', 'Hard'} else 'Medium',
                'question': question_text,
                'options': options,
                'correct_option_index': correct_idx,
                'explanation': str(item.get('explanation') or '').strip() or fallback[min(index - 1, len(fallback) - 1)]['explanation'],
            })
        if len(cleaned) < 10:
            for question in fallback[len(cleaned):10]:
                cleaned.append(question)
        return cleaned[:10]

    def _assessment_prompt(self, target_role: str) -> str:
        blueprint = self._role_blueprint(target_role)
        return (
            f'Generate 10 multiple-choice diagnostic questions for the target role: {target_role}.\n'
            f'Use these focus topics: {json.dumps(blueprint["focus_topics"])}.\n'
            'Return JSON only as an array. Each item must include: id, topic, difficulty (Easy/Medium/Hard), question, options (4), correct_option_index, explanation.\n'
            'The questions must be conceptual, realistic, and suitable for identifying strengths and weaknesses. Avoid trivia.'
        )

    def generate_assessment_questions(self, target_role: str) -> List[Dict[str, Any]]:
        if self.llm_enabled:
            try:
                response_text = self._call_huggingface(self._assessment_prompt(target_role), max_new_tokens=2200, temperature=0.25)
                return self._normalize_questions(self._extract_json(response_text), target_role)
            except Exception:
                pass
        return self._build_assessment_questions(target_role)

    def evaluate_assessment(self, target_role: str, answers: List[Dict[str, Any]], questions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        source_questions = self._normalize_questions(questions, target_role) if questions else self.generate_assessment_questions(target_role)
        question_lookup = {item['id']: item for item in source_questions}
        topic_scores: Dict[str, Dict[str, Any]] = {}
        correct_count = 0

        for answer in answers:
            question = question_lookup.get(answer.get('question_id'))
            if not question:
                continue
            topic = question['topic']
            difficulty = question.get('difficulty', 'Medium')
            weight = 1 if difficulty == 'Easy' else 2 if difficulty == 'Medium' else 3
            stats = topic_scores.setdefault(topic, {'correct': 0, 'total': 0, 'weighted_correct': 0, 'weighted_total': 0})
            stats['total'] += 1
            stats['weighted_total'] += weight
            if answer.get('selected_option_index') == question['correct_option_index']:
                correct_count += 1
                stats['correct'] += 1
                stats['weighted_correct'] += weight

        total_questions = max(len(source_questions), 1)
        score = round((correct_count / total_questions) * 100, 2)
        ranked_topics = []
        for topic, stats in topic_scores.items():
            accuracy = stats['correct'] / max(stats['total'], 1)
            weighted_accuracy = stats['weighted_correct'] / max(stats['weighted_total'], 1)
            ranked_topics.append({
                'topic': topic,
                'accuracy': round(accuracy, 3),
                'weighted_accuracy': round(weighted_accuracy, 3),
            })
        ranked_topics.sort(key=lambda item: (item['weighted_accuracy'], item['accuracy']))

        weaknesses = [item['topic'] for item in ranked_topics[:2]]
        strengths = [item['topic'] for item in sorted(ranked_topics, key=lambda item: (item['weighted_accuracy'], item['accuracy']), reverse=True)[:2]]

        if not weaknesses:
            weaknesses = [self._derive_focus_topics(target_role, None)[0]]
        if not strengths:
            strengths = [self._derive_focus_topics(target_role, None)[-1]]

        if score < 45:
            recommendation = 'Start with the structured foundations path and spend extra time on the weakest topics before moving into applied work.'
        elif score < 75:
            recommendation = 'Use a balanced upskilling path: strengthen weak areas first, then move into workflow and scenario-based practice.'
        else:
            recommendation = 'Use an advanced upskilling path with more case-based practice, trade-off analysis, and communication-heavy tasks.'

        return {
            'score': score,
            'strengths': strengths,
            'weaknesses': weaknesses,
            'recommendation': recommendation,
            'topic_breakdown': ranked_topics,
        }

    def _lesson_blueprint(self, target_role: str, topic: str, lesson_number: int, profile: Dict[str, Any]) -> Dict[str, Any]:
        concepts = profile['concepts']
        workflow = profile['workflow']
        pitfalls = profile['pitfalls']
        scenario_bank = profile['scenario_bank']
        practice_bank = profile['practice_bank']

        if lesson_number == 1:
            return {
                'title': f'{topic}: Core Concepts',
                'format': 'reading',
                'duration': '25 min',
                'summary': f'Build a conceptual foundation in {topic.lower()} by learning the key variables, vocabulary, and why this topic matters in real {target_role} work.',
                'key_takeaways': [
                    f'Explain {topic.lower()} using the core ideas of {concepts[0]}, {concepts[1]}, and {concepts[2]}.',
                    f'Recognize how {topic.lower()} influences quality, safety, performance, or trust in {target_role} decisions.',
                    f'Identify one common failure pattern in {topic.lower()} before moving into hands-on execution.',
                ],
                'content_sections': [
                    {
                        'heading': 'Why this topic matters',
                        'body': (
                            f'{topic} matters because a {target_role} is rarely judged only by effort. They are judged by whether the result is reliable, explainable, and aligned to constraints. '
                            f'In this module, the learner studies how {topic.lower()} shapes decision quality, downstream risk, and the confidence that teammates or stakeholders place in the work. '
                            f'Instead of memorizing isolated terms, the goal is to form a working mental model: what questions this topic helps answer, what signals indicate good work, and what kind of mistake becomes expensive when the basics are weak. '
                            f'Learners should leave this section able to connect the topic to real deliverables, whether that means design choices, analysis output, or operational readiness.'
                        ),
                    },
                    {
                        'heading': 'Core concepts',
                        'body': (
                            f'The conceptual backbone of {topic.lower()} includes {concepts[0]}, {concepts[1]}, {concepts[2]}, {concepts[3]}, and {concepts[4]}. '
                            f'A strong learner should understand not only what each concept means, but also when it becomes the dominant factor in a decision. '
                            f'For example, one concept may shape feasibility, another may drive trade-offs, and another may expose hidden risk. '
                            f'The important habit is to move from surface vocabulary toward causal reasoning: what changes when an assumption changes, why one variable matters more in a given context, and how the concepts connect rather than sit in separate boxes.'
                        ),
                    },
                    {
                        'heading': 'How experts think about it',
                        'body': (
                            f'Experienced practitioners usually organize {topic.lower()} around questions, not definitions. They ask what the requirement really is, what evidence would prove the answer is good enough, and what trade-off must be made visible before a recommendation is accepted. '
                            f'This way of thinking turns raw knowledge into judgment. It is also why conceptual learning should include short comparisons, edge cases, and “what if” variations. '
                            f'When the learner can explain how one concept influences another and how the topic affects a real project, they are moving beyond book knowledge into role-ready understanding.'
                        ),
                    },
                    {
                        'heading': 'Starter mistakes to avoid',
                        'body': (
                            f'Common beginner mistakes in {topic.lower()} include {pitfalls[0]}, {pitfalls[1]}, {pitfalls[2]}, and {pitfalls[3]}. '
                            f'Notice that these are usually reasoning mistakes rather than simple clerical errors. They happen when someone jumps to output before establishing the objective, the assumptions, and the quality check. '
                            f'A better pattern is to define the goal, note the operating conditions, compare at least one alternative, and explain what evidence would make the final answer trustworthy. '
                            f'That discipline keeps the learner from sounding confident while actually being fragile.'
                        ),
                    },
                ],
                'example': {
                    'title': f'{topic} workplace scenario',
                    'scenario': scenario_bank[0],
                    'steps': [
                        'Clarify the requirement, operating conditions, and success criteria.',
                        f'Identify which concepts from {topic.lower()} matter most in this scenario and why.',
                        'Compare at least one alternative or assumption instead of trusting the first idea.',
                        'Explain the final reasoning in language a teammate could review quickly.',
                    ],
                },
                'practice_task': practice_bank[0],
            }

        if lesson_number == 2:
            return {
                'title': f'{topic}: Workflow and Execution',
                'format': 'workshop',
                'duration': '30 min',
                'summary': f'Learn the repeatable workflow behind {topic.lower()} so you can move from requirement to execution, review, and communication without guessing.',
                'key_takeaways': [
                    f'Use a stepwise workflow for {topic.lower()} rather than jumping directly to output.',
                    f'Understand where trade-offs and review checkpoints appear in {topic.lower()} work.',
                    f'Communicate what was done, why it was done, and what remains uncertain.',
                ],
                'content_sections': [
                    {
                        'heading': 'Workflow overview',
                        'body': (
                            f'In practical {target_role} work, {topic.lower()} follows a chain of decisions rather than one giant leap. A typical sequence is to {workflow[0]}, then {workflow[1]}, then {workflow[2]}, followed by {workflow[3]}, and finally {workflow[4]}. '
                            f'This matters because skipping one stage usually creates rework somewhere else. A learner who understands the workflow can break a vague task into manageable pieces, choose evidence at the right time, and avoid treating review as an afterthought. '
                            f'The workflow is also a communication tool, because it lets another teammate see where the work stands and what kind of feedback is needed next.'
                        ),
                    },
                    {
                        'heading': 'Decision points and trade-offs',
                        'body': (
                            f'Workflow alone is not enough. Good execution also requires knowing where the hard decisions sit. In {topic.lower()}, learners often balance speed against quality, simplicity against accuracy, or local optimization against system-level impact. '
                            f'The point is not to remove trade-offs. The point is to surface them early. That means naming what is being optimized, what evidence supports the choice, and which constraint is most likely to change the recommendation. '
                            f'When learners document those decision points, their work becomes far easier to review and far less likely to break under scrutiny.'
                        ),
                    },
                    {
                        'heading': 'Validation and communication',
                        'body': (
                            f'Execution is incomplete without validation. For {topic.lower()}, validation asks whether the output is correct enough, useful enough, and explainable enough for the next person in the chain. '
                            f'That usually means checking assumptions, reviewing edge cases, and asking whether the recommendation still makes sense if one major input shifts. '
                            f'Communication then turns that review into action. A strong summary does not merely restate what was done. It explains the logic, the confidence level, and any follow-up action required before the work should be trusted or deployed.'
                        ),
                    },
                    {
                        'heading': 'Execution habits that scale',
                        'body': (
                            f'What separates a repeatable performer from a lucky one is habit quality. Strong habits in {topic.lower()} include keeping assumptions visible, recording intermediate decisions, using checklists only where they clarify rather than replace thinking, and leaving enough context for a handoff. '
                            f'These habits become critical when projects grow more complex or when several people contribute to the same result. '
                            f'A learner who trains these habits early will not only solve the immediate task more effectively, but will also produce work that can survive review, reuse, and iteration.'
                        ),
                    },
                ],
                'example': {
                    'title': f'{topic} workflow scenario',
                    'scenario': scenario_bank[1],
                    'steps': [
                        'Translate the request into a clear workflow with named checkpoints.',
                        'List the inputs, constraints, and evidence needed before execution begins.',
                        'Complete the task while logging one important trade-off and one review gate.',
                        'Summarize the outcome, residual risk, and recommended next action.',
                    ],
                },
                'practice_task': practice_bank[1],
            }

        return {
            'title': f'{topic}: Applied Practice',
            'format': 'case study',
            'duration': '35 min',
            'summary': f'Apply {topic.lower()} in a realistic scenario, make decisions under constraints, and reflect on what would strengthen the result in a real project.',
            'key_takeaways': [
                f'Apply {topic.lower()} under realistic constraints rather than in an idealized textbook setting.',
                f'Judge whether your output would stand up in a real review conversation.',
                f'Reflect on how the approach should improve in the next iteration.',
            ],
            'content_sections': [
                {
                    'heading': 'Applied scenario',
                    'body': (
                        f'This lesson places {topic.lower()} inside a believable work context where information is incomplete and trade-offs are unavoidable. The learner must decide what matters most, what evidence is missing, and what can still be recommended responsibly. '
                        f'This is where conceptual understanding becomes judgment. It is easy to sound correct when the exercise is clean and every variable is obvious. It is much harder when priorities compete and the learner must decide how much confidence the current evidence actually deserves. '
                        f'Applied practice builds exactly that judgment.'
                    ),
                },
                {
                    'heading': 'Hands-on execution',
                    'body': (
                        f'A useful applied exercise should move through setup, execution, review, and revision. In {topic.lower()}, that means defining the scenario clearly, selecting the most relevant concepts and workflow steps, producing a first-pass answer, and then stress-testing that answer. '
                        f'The learner should ask: what assumption is doing the most work here, what trade-off might a reviewer challenge first, and what evidence would strengthen the recommendation? '
                        f'This process helps the learner move from “I completed the task” to “I can defend the task.”'
                    ),
                },
                {
                        'heading': 'Reflection and improvement',
                        'body': (
                            f'Reflection should not be vague. In a strong {topic.lower()} reflection, the learner identifies what was handled well, what risk was underestimated, and what they would do differently with more time or data. '
                            f'This reflection matters because real projects rarely end with a perfect answer. They end with the best answer available under current constraints. '
                            f'The ability to improve the next iteration is therefore part of role readiness, not an optional extra.'
                        ),
                },
                {
                    'heading': 'From exercise to workplace readiness',
                    'body': (
                        f'To make applied practice count, the final output should be framed as something another person could actually use. That may be a recommendation, a short analysis note, a comparison table, or a structured explanation of why one path is safer than another. '
                        f'The learner should aim for clarity, not theatrical complexity. If a teammate can follow the logic, see the risks, and understand the next action, the practice task has done its job. '
                            f'That is how {topic.lower()} becomes a transferable capability instead of a one-time classroom exercise.'
                    ),
                },
            ],
            'example': {
                'title': f'{topic} applied workplace scenario',
                'scenario': scenario_bank[2],
                'steps': [
                    'Review the prompt and identify the most decision-critical variables.',
                    'Create a first-pass recommendation with explicit assumptions.',
                    'Test the recommendation against one challenge, edge case, or stakeholder concern.',
                    'Produce a final recommendation and a short reflection on what should happen next.',
                ],
            },
            'practice_task': practice_bank[2],
        }

    def _quiz_templates(self, target_role: str, topic: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        concepts = [str(item).strip() for item in profile['concepts']]
        workflow = [str(item).strip() for item in profile['workflow']]
        pitfalls = [str(item).strip() for item in profile['pitfalls']]
        scenario = str(profile['scenario_bank'][0]).strip()
        wrong_concepts = [pitfalls[0].capitalize(), pitfalls[1].capitalize(), 'Skipping validation', 'Hiding assumptions']
        questions = [
            {
                'difficulty': 'Easy',
                'question': f'Which idea is central to understanding {topic.lower()}?',
                'options': [concepts[0].capitalize(), wrong_concepts[0], wrong_concepts[1], wrong_concepts[2]],
                'answer': concepts[0].capitalize(),
                'explanation': f'{concepts[0].capitalize()} is one of the anchor ideas used to reason about {topic.lower()} correctly.',
            },
            {
                'difficulty': 'Easy',
                'question': f'Why does {topic.lower()} matter in real {target_role} work?',
                'options': [
                    'It improves the quality, clarity, and trustworthiness of outcomes',
                    'It removes the need for review and communication',
                    'It matters only when a project is already failing',
                    'It is mostly theoretical and rarely affects real decisions',
                ],
                'answer': 'It improves the quality, clarity, and trustworthiness of outcomes',
                'explanation': f'{topic} matters because it changes the quality of the final decision, handoff, or deliverable.',
            },
            {
                'difficulty': 'Easy',
                'question': f'Which of the following is a common risk pattern in {topic.lower()}?',
                'options': [pitfalls[0].capitalize(), 'Making assumptions explicit', 'Comparing alternatives', 'Checking trade-offs'],
                'answer': pitfalls[0].capitalize(),
                'explanation': 'Risk patterns are habits that weaken the reasoning chain before the work is reviewed.',
            },
            {
                'difficulty': 'Medium',
                'question': f'What is the strongest first step when starting a {topic.lower()} task?',
                'options': [workflow[0].capitalize(), 'Jump to tooling immediately', 'Wait for perfect certainty', 'Write the final answer before framing the problem'],
                'answer': workflow[0].capitalize(),
                'explanation': 'Strong execution begins by framing the task and success criteria before method or tool decisions.',
            },
            {
                'difficulty': 'Medium',
                'question': f'Which sequence best reflects a reliable workflow for {topic.lower()}?',
                'options': [
                    f"{workflow[0].capitalize()} -> {workflow[1]} -> {workflow[2]} -> {workflow[3]}",
                    'Choose a favorite tool -> produce output -> define the task later -> skip review',
                    'Collect endless detail -> avoid assumptions -> delay communication forever',
                    'Write a recommendation -> gather evidence later -> remove uncertainty from the summary',
                ],
                'answer': f"{workflow[0].capitalize()} -> {workflow[1]} -> {workflow[2]} -> {workflow[3]}",
                'explanation': 'A dependable workflow makes the reasoning reviewable instead of relying on intuition alone.',
            },
            {
                'difficulty': 'Medium',
                'question': f'Which choice would most likely weaken the quality of {topic.lower()} work?',
                'options': ['Reviewing assumptions at checkpoints', pitfalls[1].capitalize(), 'Explaining trade-offs clearly', 'Comparing alternatives before deciding'],
                'answer': pitfalls[1].capitalize(),
                'explanation': f'{pitfalls[1].capitalize()} usually weakens the final result because the logic becomes harder to trust.',
            },
            {
                'difficulty': 'Medium',
                'question': f'What should a strong learner be able to explain after studying {topic.lower()}?',
                'options': [
                    f'How {concepts[0]}, {concepts[1]}, and {concepts[2]} influence a real decision',
                    'Only definitions, not application',
                    'Only tool names without reasoning',
                    'Only one rigid method for every scenario',
                ],
                'answer': f'How {concepts[0]}, {concepts[1]}, and {concepts[2]} influence a real decision',
                'explanation': 'Good learning connects concepts to consequences, not just vocabulary to memory.',
            },
            {
                'difficulty': 'Hard',
                'question': f'In this scenario: {scenario} What makes the recommendation trustworthy?',
                'options': [
                    'It uses advanced wording and sounds confident',
                    'It names assumptions, trade-offs, and evidence used to justify the recommendation',
                    'It avoids discussing uncertainty',
                    'It chooses the fastest answer regardless of context',
                ],
                'answer': 'It names assumptions, trade-offs, and evidence used to justify the recommendation',
                'explanation': 'Trustworthy reasoning is transparent, reviewable, and tied to evidence rather than confidence alone.',
            },
            {
                'difficulty': 'Hard',
                'question': f'Which response best shows mature judgment in {topic.lower()}?',
                'options': [
                    'Select the most complex method to look advanced',
                    'Hide trade-offs so the recommendation feels simpler',
                    'State what is known, what is uncertain, and what evidence would strengthen the next decision',
                    'Delay any recommendation until uncertainty disappears completely',
                ],
                'answer': 'State what is known, what is uncertain, and what evidence would strengthen the next decision',
                'explanation': 'Mature judgment makes limits visible and still moves the work forward responsibly.',
            },
            {
                'difficulty': 'Hard',
                'question': f'Which option best distinguishes a role-ready answer from a classroom-only answer in {topic.lower()}?',
                'options': [
                    'A role-ready answer shows decision rationale, review logic, and practical next actions',
                    'A role-ready answer avoids documenting assumptions',
                    'A role-ready answer always chooses the lowest-risk option without explanation',
                    'A role-ready answer focuses on terminology more than consequences',
                ],
                'answer': 'A role-ready answer shows decision rationale, review logic, and practical next actions',
                'explanation': 'Real work requires a recommendation that another person can review, challenge, and use.',
            },
        ]
        return questions

    def _assignment_for_topic(self, topic: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'title': profile['assignment_title'],
            'description': profile['assignment_description'],
            'deliverables': profile['deliverables'],
            'submission_type': 'document or notebook',
        }

    def _module_for_topic(self, target_role: str, topic: str, module_number: int) -> Dict[str, Any]:
        blueprint = self._role_blueprint(target_role)
        profile = blueprint['topic_profiles'].get(topic, self._generic_topic_profile(target_role, topic))
        lessons = [self._lesson_blueprint(target_role, topic, lesson_number, profile) for lesson_number in range(1, 4)]
        quiz = self._quiz_templates(target_role, topic, profile)
        module_summary = (
            f'This module develops practical confidence in {topic.lower()} for the {target_role} role. '
            f'It starts with conceptual understanding, then moves into workflow thinking, and finally into a realistic scenario where the learner must justify decisions under constraints.'
        )
        learning_objectives = [
            f'Explain the central ideas behind {topic.lower()} using practical language.',
            f'Apply a structured workflow for {topic.lower()} tasks and identify key review checkpoints.',
            f'Evaluate trade-offs, risks, and communication needs in realistic {topic.lower()} work.',
        ]
        return {
            'module_number': module_number,
            'title': topic,
            'module_summary': module_summary,
            'learning_objectives': learning_objectives,
            'lessons': lessons,
            'quiz': quiz,
            'assignment': self._assignment_for_topic(topic, profile),
        }

    def _course_fallback(self, target_role: str, experience_type: str, current_role: str, assessment_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        blueprint = self._role_blueprint(target_role)
        focus_topics = self._derive_focus_topics(target_role, assessment_result)
        modules = [self._module_for_topic(target_role, topic, idx) for idx, topic in enumerate(focus_topics, start=1)]
        weaknesses = ', '.join((assessment_result or {}).get('weaknesses', [])[:2])
        weakness_note = f' Assessment weaknesses such as {weaknesses} receive extra emphasis.' if weaknesses else ''
        course_type = 'Crash Course' if experience_type == 'beginner' else 'Personalized Upskilling Track'
        return {
            'title': f'{target_role} {course_type}',
            'overview': (
                f'This course prepares the learner for the {target_role} path by combining foundations, workflow knowledge, role-based examples, quizzes, and assignments. '
                f'The sequence starts with high-value topics and builds toward realistic execution. Because the selected experience type is {experience_type}, the course balances explanation with applied practice and communication.'
                f'{weakness_note} Each module is deliberately different so the learner builds breadth and depth rather than reading repeated content.'
            ),
            'current_role_context': current_role,
            'experience_type': experience_type,
            'focus_topics': focus_topics,
            'estimated_duration': blueprint['estimated_duration'],
            'modules': modules,
            'capstone': {
                'title': f'{target_role} Capstone: Build and Defend a Practical End-to-End Solution',
                'description': (
                    f'You are acting in a real {target_role} role. Build a practical end-to-end project that pulls together the course modules into one believable scenario. '
                    'The work should show both theoretical understanding and hands-on execution. Your final PDF must explain what problem you solved, how you designed the solution, how you validated it, and what trade-offs you managed.'
                ),
                'project_goal': 'Produce a professional portfolio-quality project brief and evidence pack that another reviewer can audit.',
                'scenario': f'A realistic organization needs a {target_role.lower()} solution that improves quality, reliability, and decision-making under real constraints.',
                'required_sections': [
                    'Business problem, assumptions, stakeholders, and success criteria',
                    'Architecture or workflow design with clearly named stages',
                    'Implementation approach, tools, and major design decisions',
                    'Validation checks, error handling, quality controls, or testing logic',
                    'Results summary, limitations, and recommended next improvements',
                ],
                'deliverables': [
                    'One PDF report with diagrams, tables, screenshots, code excerpts, or evidence where useful',
                    'A clear explanation of why your design choices fit the scenario',
                    'Evidence that you validated, tested, or stress-checked the solution',
                ],
                'submission_rules': [
                    'Do not submit a copied tutorial solution',
                    'Do not hide assumptions or missing information',
                    'Make your reasoning clear enough for a reviewer to audit',
                ],
                'evaluation_rubric': [
                    'Problem framing and requirement clarity',
                    'Technical correctness and role relevance',
                    'Quality of reasoning, trade-off handling, and validation',
                    'Professional communication and presentation quality',
                ],
            },
            'final_capstone': None,
            'final_capstone': {
                'title': f'{target_role} Capstone: Build and Defend a Practical End-to-End Solution',
                'description': (
                    f'You are acting in a real {target_role} role. Build a practical end-to-end project that pulls together the course modules into one believable scenario. '
                    'The work should show both theoretical understanding and hands-on execution. Your final PDF must explain what problem you solved, how you designed the solution, how you validated it, and what trade-offs you managed.'
                ),
                'project_goal': 'Produce a professional portfolio-quality project brief and evidence pack that another reviewer can audit.',
                'scenario': f'A realistic organization needs a {target_role.lower()} solution that improves quality, reliability, and decision-making under real constraints.',
                'required_sections': [
                    'Business problem, assumptions, stakeholders, and success criteria',
                    'Architecture or workflow design with clearly named stages',
                    'Implementation approach, tools, and major design decisions',
                    'Validation checks, error handling, quality controls, or testing logic',
                    'Results summary, limitations, and recommended next improvements',
                ],
                'deliverables': [
                    'One PDF report with diagrams, tables, screenshots, code excerpts, or evidence where useful',
                    'A clear explanation of why your design choices fit the scenario',
                    'Evidence that you validated, tested, or stress-checked the solution',
                ],
                'submission_rules': [
                    'Do not submit a copied tutorial solution',
                    'Do not hide assumptions or missing information',
                    'Make your reasoning clear enough for a reviewer to audit',
                ],
                'evaluation_rubric': [
                    'Problem framing and requirement clarity',
                    'Technical correctness and role relevance',
                    'Quality of reasoning, trade-off handling, and validation',
                    'Professional communication and presentation quality',
                ],
            },
            'certificate_criteria': [
                'Complete all lessons and practice tasks',
                'Score at least 70% across module quizzes',
                'Submit every module assignment',
                'Finish the integrative capstone',
            ],
            'generation_source': 'deterministic-role-generator',
            'model_name': 'deterministic-role-generator',
        }

    def _course_prompt(self, target_role: str, experience_type: str, current_role: str, assessment_result: Optional[Dict[str, Any]]) -> str:
        blueprint = self._role_blueprint(target_role)
        return (
            f'Generate a personalized course for the target role {target_role}.\n'
            f'Experience type: {experience_type}. Current role: {current_role or "Not provided"}.\n'
            f'Focus topics: {json.dumps(self._derive_focus_topics(target_role, assessment_result))}.\n'
            f'Assessment result: {json.dumps(assessment_result or {}, ensure_ascii=False)}.\n'
            'Return JSON only with this structure: title, overview, current_role_context, experience_type, focus_topics (4 items), estimated_duration, '\
            'modules (4 items). Each module must include module_number, title, module_summary, learning_objectives (3), lessons (3), quiz (5), assignment. '\
            'Each lesson must include lesson_number, title, format, duration, summary, key_takeaways (3), content_sections (4 objects with heading and body), example (title, scenario, steps 4), practice_task. '\
            'Each quiz item must include difficulty, question, options (4), answer, explanation. '\
            'Make every module, scenario, practice task, and takeaway distinct and role-specific. Avoid repeated wording.'
        )

    def _normalize_course(self, course_data: Any, target_role: str, experience_type: str, current_role: str, assessment_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        fallback = self._course_fallback(target_role, experience_type, current_role, assessment_result)
        if not isinstance(course_data, dict):
            return fallback
        try:
            focus_topics = course_data.get('focus_topics') if isinstance(course_data.get('focus_topics'), list) else fallback['focus_topics']
            focus_topics = [str(item).strip() for item in focus_topics if str(item).strip()][:4]
            while len(focus_topics) < 4:
                focus_topics.append(fallback['focus_topics'][len(focus_topics)])
            modules = course_data.get('modules') if isinstance(course_data.get('modules'), list) else []
            normalized_modules = []
            for idx, topic in enumerate(focus_topics, start=1):
                module = modules[idx - 1] if idx - 1 < len(modules) else None
                module_fallback = self._module_for_topic(target_role, topic, idx)
                if not isinstance(module, dict):
                    normalized_modules.append(module_fallback)
                    continue
                lessons = module.get('lessons') if isinstance(module.get('lessons'), list) else []
                normalized_lessons = []
                profile = self._role_blueprint(target_role)['topic_profiles'].get(topic, self._generic_topic_profile(target_role, topic))
                for lesson_number in range(1, 4):
                    lesson = lessons[lesson_number - 1] if lesson_number - 1 < len(lessons) else None
                    lesson_fallback = self._lesson_blueprint(target_role, topic, lesson_number, profile)
                    if not isinstance(lesson, dict):
                        normalized_lessons.append(lesson_fallback)
                        continue
                    sections = lesson.get('content_sections') if isinstance(lesson.get('content_sections'), list) else []
                    cleaned_sections = []
                    for section in sections[:4]:
                        if not isinstance(section, dict):
                            continue
                        heading = str(section.get('heading') or '').strip()
                        body = str(section.get('body') or '').strip()
                        if heading and len(body.split()) >= 35:
                            cleaned_sections.append({'heading': heading, 'body': body})
                    if len(cleaned_sections) < 4:
                        cleaned_sections = lesson_fallback['content_sections']
                    takeaways = lesson.get('key_takeaways') if isinstance(lesson.get('key_takeaways'), list) else []
                    takeaways = [str(item).strip() for item in takeaways[:3] if str(item).strip()] or lesson_fallback['key_takeaways']
                    example = lesson.get('example') if isinstance(lesson.get('example'), dict) else {}
                    steps = example.get('steps') if isinstance(example.get('steps'), list) else []
                    steps = [str(item).strip() for item in steps[:4] if str(item).strip()] or lesson_fallback['example']['steps']
                    normalized_lessons.append({
                        'lesson_number': lesson_number,
                        'title': str(lesson.get('title') or lesson_fallback['title']).strip(),
                        'format': str(lesson.get('format') or lesson_fallback['format']).strip(),
                        'duration': str(lesson.get('duration') or lesson_fallback['duration']).strip(),
                        'summary': str(lesson.get('summary') or lesson_fallback['summary']).strip(),
                        'key_takeaways': takeaways,
                        'content_sections': cleaned_sections,
                        'example': {
                            'title': str(example.get('title') or lesson_fallback['example']['title']).strip(),
                            'scenario': str(example.get('scenario') or lesson_fallback['example']['scenario']).strip(),
                            'steps': steps,
                        },
                        'practice_task': str(lesson.get('practice_task') or lesson_fallback['practice_task']).strip(),
                    })
                quiz_items = module.get('quiz') if isinstance(module.get('quiz'), list) else []
                quiz = []
                quiz_fallback = self._quiz_templates(target_role, topic, profile)
                for item in quiz_items[:5]:
                    if not isinstance(item, dict):
                        continue
                    options = item.get('options') if isinstance(item.get('options'), list) else []
                    options = [str(opt).strip() for opt in options[:4] if str(opt).strip()]
                    answer = str(item.get('answer') or '').strip()
                    if len(options) != 4 or answer not in options:
                        continue
                    quiz.append({
                        'difficulty': str(item.get('difficulty') or 'Medium').strip().title(),
                        'question': str(item.get('question') or '').strip(),
                        'options': options,
                        'answer': answer,
                        'explanation': str(item.get('explanation') or '').strip() or 'Review the scenario and lesson reasoning for the correct choice.',
                    })
                while len(quiz) < 5:
                    quiz.append(quiz_fallback[len(quiz)])
                assignment = module.get('assignment') if isinstance(module.get('assignment'), dict) else {}
                assignment_fallback = self._assignment_for_topic(topic, profile)
                deliverables = assignment.get('deliverables') if isinstance(assignment.get('deliverables'), list) else []
                deliverables = [str(item).strip() for item in deliverables[:4] if str(item).strip()] or assignment_fallback['deliverables']
                normalized_modules.append({
                    'module_number': idx,
                    'title': str(module.get('title') or module_fallback['title']).strip(),
                    'module_summary': str(module.get('module_summary') or module_fallback['module_summary']).strip(),
                    'learning_objectives': [str(item).strip() for item in (module.get('learning_objectives') or module_fallback['learning_objectives'])[:3] if str(item).strip()] or module_fallback['learning_objectives'],
                    'lessons': normalized_lessons,
                    'quiz': quiz,
                    'assignment': {
                        'title': str(assignment.get('title') or assignment_fallback['title']).strip(),
                        'description': str(assignment.get('description') or assignment_fallback['description']).strip(),
                        'deliverables': deliverables,
                        'submission_type': str(assignment.get('submission_type') or assignment_fallback['submission_type']).strip(),
                    },
                })
            course = {
                'title': str(course_data.get('title') or fallback['title']).strip(),
                'overview': str(course_data.get('overview') or fallback['overview']).strip(),
                'current_role_context': str(course_data.get('current_role_context') or current_role).strip(),
                'experience_type': experience_type,
                'focus_topics': focus_topics,
                'estimated_duration': str(course_data.get('estimated_duration') or fallback['estimated_duration']).strip(),
                'modules': normalized_modules,
                'capstone': course_data.get('capstone') if isinstance(course_data.get('capstone'), dict) else fallback['capstone'],
                'final_capstone': course_data.get('final_capstone') if isinstance(course_data.get('final_capstone'), dict) else fallback['capstone'],
                'certificate_criteria': fallback['certificate_criteria'],
                'generation_source': 'llm',
                'model_name': self.model,
            }
            return course
        except Exception:
            return fallback

    def generate_course(self, target_role: str, experience_type: str, current_role: str = '', assessment_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.llm_enabled:
            try:
                response_text = self._call_huggingface(
                    self._course_prompt(target_role, experience_type, current_role, assessment_result),
                    max_new_tokens=min(max(self.max_tokens, 2800), 4200),
                    temperature=0.35,
                )
                parsed = self._extract_json(response_text)
                return self._normalize_course(parsed, target_role, experience_type, current_role, assessment_result)
            except Exception:
                pass
        return self._course_fallback(target_role, experience_type, current_role, assessment_result)

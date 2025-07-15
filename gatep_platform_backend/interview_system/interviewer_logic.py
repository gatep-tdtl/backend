# interview_system/interviewer_logic.py

import json
import re
import time
import os
from datetime import datetime

# Assuming config, llm_utils, timer_utils are in the same 'interview_system' directory
from . import config
from .llm_utils import call_llm_api
from .timer_utils import RoundTimer


# Define constants for file paths (for backend-side report saving)
PRE_GENERATED_QUESTIONS_FILE = "pre_generated_questions.json"
INTERVIEW_RESULTS_DIR = "interview_results" # Directory to save reports

class AIInterviewer:
    """
    Manages the AI interview logic, including question generation, round progression,
    answer evaluation, and report generation. Designed to be stateless across
    individual API requests, with its state being passed/persisted by the caller (Django views).
    """
    def __init__(self, job_desc, user_skills, position, interview_state=None):
        """
        Initializes the AI Interviewer.
        Args:
            job_desc (str): Description of the job role.
            user_skills (list): List of skills provided by the user.
            position (str): The specific job position.
            interview_state (dict, optional): Dictionary representing the current state of the interview.
                                             If None, a new interview session is initialized.
        """
        self.job_desc = job_desc
        self.user_skills = user_skills
        self.position = position
        self.round_time_limits = config.ROUND_TIME_LIMITS

        # Initialize or load interview state
        if interview_state:
            self.answers = interview_state.get('answers', [])
            self.round_detailed_results = interview_state.get('round_detailed_results', {})
            self.conversation_history = interview_state.get('conversation_history', [])
            self.current_round_name = interview_state.get('current_round_name', None)
            self.current_question_index = interview_state.get('current_question_index', -1) # -1 means before first question
            self.interview_status = interview_state.get('interview_status', 'SCHEDULED')
            self.malpractice_detected = interview_state.get('malpractice_detected', False)
            self.malpractice_reason = interview_state.get('malpractice_reason', "")
            self.overall_interview_score = interview_state.get('overall_interview_score', 0)
            self.overall_interview_analysis = interview_state.get('overall_interview_analysis', "")
            self.technical_specializations = interview_state.get('technical_specializations', [])
            self.all_generated_questions = interview_state.get('all_generated_questions', {})
            self.interview_plan = interview_state.get('interview_plan', {})
            self.timers = self._reconstruct_timers(interview_state.get('timers_state', {}))
            self.previous_round_timed_out = interview_state.get('previous_round_timed_out', False)
        else:
            # Default state for a new interview
            self.answers = []
            self.round_detailed_results = {}
            self.conversation_history = []
            self.current_round_name = None
            self.current_question_index = -1
            self.interview_status = 'SCHEDULED' # Initial status
            self.malpractice_detected = False
            self.malpractice_reason = ""
            self.overall_interview_score = 0
            self.overall_interview_analysis = ""
            self.technical_specializations = []
            self.all_generated_questions = {}
            self.interview_plan = {}
            self.timers = {
                "communication": RoundTimer(self.round_time_limits.get("communication", 300)),
                "psychometric": RoundTimer(self.round_time_limits.get("psychometric", 300)),
                "coding": RoundTimer(self.round_time_limits.get("coding", 300)),
                "technical": RoundTimer(self.round_time_limits.get("technical", 300))
            }
            self.previous_round_timed_out = False
            # Initial LLM call to generate questions and plan
            self._load_or_generate_questions()


        # Ensure conversation history always starts with job/user details for LLM context
        if not self.conversation_history or self.conversation_history[0].get("role") != "system":
            # If history is empty or first item isn't system, re-initialize system message
            self.conversation_history = [{"role": "system", "content": f"Job Description: {self.job_desc}\nUser Skills: {', '.join(self.user_skills)}\nPosition: {self.position}"}]
        
        print(f"DEBUG: AIInterviewer initialized/loaded for position='{self.position}' with status='{self.interview_status}'")


    def _reconstruct_timers(self, timers_state):
        """Reconstructs RoundTimer objects from their serialized state."""
        reconstructed_timers = {}
        for round_name, state in timers_state.items():
            timer = RoundTimer(state['duration'])
            timer.start_time = state['start_time']
            reconstructed_timers[round_name] = timer
        return reconstructed_timers

    def get_state(self):
        """
        Returns the current state of the AIInterviewer instance as a dictionary
        suitable for serialization (e.g., to JSON or database).
        """
        timers_state = {
            round_name: {"duration": timer.duration, "start_time": timer.start_time}
            for round_name, timer in self.timers.items()
        }

        return {
            'job_desc': self.job_desc,
            'user_skills': self.user_skills,
            'position': self.position,
            'answers': self.answers,
            'round_detailed_results': self.round_detailed_results,
            'conversation_history': self.conversation_history,
            'current_round_name': self.current_round_name,
            'current_question_index': self.current_question_index,
            'interview_status': self.interview_status,
            'malpractice_detected': self.malpractice_detected,
            'malpractice_reason': self.malpractice_reason,
            'overall_interview_score': self.overall_interview_score,
            'overall_interview_analysis': self.overall_interview_analysis,
            'technical_specializations': self.technical_specializations,
            'all_generated_questions': self.all_generated_questions,
            'interview_plan': self.interview_plan,
            'timers_state': timers_state, # Store timer states
            'previous_round_timed_out': self.previous_round_timed_out,
        }

    def _add_to_chat_history(self, role, text):
        """Adds a message to the internal chat history and manages its size."""
        self.conversation_history.append({"role": role, "content": text})

        # Keep the initial system message (index 0) and then only the last N turns
        if len(self.conversation_history) > config.MAX_CHAT_HISTORY_TURNS + 1:
            self.conversation_history = [self.conversation_history[0]] + self.conversation_history[-(config.MAX_CHAT_HISTORY_TURNS):]


    def _load_or_generate_questions(self):
        """
        Forces the generation of new interview questions and plan using the LLM.
        This method is now designed to always generate, rather than load existing.
        """
        print(f"DEBUG: Forcing generation of new questions and plan for a new interview session.")
        self._generate_new_questions_and_plan()


    def _generate_new_questions_and_plan(self):
        """
        Generates new interview questions and a structured plan for the interview using the LLM.
        Populates self.all_generated_questions and then calls _generate_interview_plan.
        """
        print("DEBUG: Starting LLM call for question generation...")
        prompt = (
            f"You are an AI Interviewer specialized in AI/Machine Learning roles. "
            f"Based on the following job description and user skills, "
            f"generate a comprehensive interview plan including various rounds (e.g., Communication, Psychometric, Technical, Coding) "
            f"and a set of detailed questions for each. Also, provide templates for interview introduction, round introductions, "
            f"malpractice warnings (though handled by frontend, include a template for consistency), and an interview conclusion, "
            f"and a message for saving the report. \n\n"
            f"For the 'Technical' round, specifically identify 2-3 key specializations within AI/Machine Learning "
            f"(e.g., 'Machine Learning Algorithms', 'Deep Learning Architectures', 'Natural Language Processing', 'Computer Vision') "
            f"that are most relevant to the provided job description and user skills. Generate detailed questions for each identified specialization.\n\n"
            f"For 'Coding' round, include specific sub-topics/stages relevant to AI/ML programming (e.g., 'Data Structures for ML', 'Algorithm Optimization', 'Model Implementation').\n\n"
            f"Job Description: {self.job_desc}\n\n"
            f"User Skills: {', '.join(self.user_skills)}\n\n"
            f"Position: {self.position}\n\n"
            f"Structure your response as a JSON object with the following keys:\n"
            f" - 'introduction_template': 'Welcome message to the candidate.'\n"
            f" - 'conclusion_template': 'Farewell message.'\n"
            f" - 'round_intro_templates': {{'communication': 'Intro for comms round', 'technical': 'Intro for technical round', 'psychometric': 'Intro for psychometric round', 'coding': 'Intro for coding round'}}\n"
            f" - 'malpractice_warning_template': 'Warning: Please focus on the interview.'\n" # Template for consistency
            f" - 'interview_termination_template': 'This interview has been terminated due to {{reason}}.'\n"
            f" - 'final_report_saved_message_template': 'Your interview has concluded. A detailed report has been saved to {{report_filename}}. You did your best, now leave the rest to us.'\n"
            f" - 'error_report_save_message_template': 'Error: Could not save the interview report to file. Please check permissions.'\n"
            f" - 'time_up_message': 'Time\\'s up for this round! Moving to the next round.'\n"
            f" - 'no_questions_available_template': 'No questions available for {{round_or_stage}}. Skipping.'\n"
            f" - 'question_intro_template': 'Question {{number}}: {{question_text}}'\n"
            f" - 'coding_question_intro_template': 'Here is your question {{number}} for {{stage_display_name}} stage.'\n"
            f" - 'rounds': [\n"
            f"    {{'name': 'communication', 'description': '...', 'questions': ['Q1', 'Q2']}},\n"
            f"    {{'name': 'psychometric', 'description': '...', 'questions': ['Q1', 'Q2']}},\n"
            f"    {{'name': 'technical', 'description': '...', 'specializations': {{\n"
            f"        'Machine Learning Algorithms': ['Q1', 'Q2'],\n"
            f"        'Deep Learning Architectures': ['Q1', 'Q2']\n"
            f"    }}}}\n"
            f"    {{'name': 'coding', 'description': '...', 'stages': {{\n"
            f"        'Data Structures for ML': ['Code 1\\nWhat is the output?', 'Code 2\\nWhat is the output?'],\n"
            f"        'Algorithm Optimization': ['Code with error 1\\nFix the error.', 'Code with error 2\\nFix the error.'],\n"
            f"        'Model Implementation': ['Problem 1\\nWrite a program.', 'Problem 2\\nWrite a program.']\n"
            f"    }}}}\n"
            f" ]\n\n"
            f"Ensure questions are relevant to the skills and job description. Provide sufficient depth."
        )

        try:
            llm_response = call_llm_api(prompt, current_conversation_history=self.conversation_history, output_max_tokens=3000)
            if llm_response:
                print(f"DEBUG: LLM Response received. Attempting to parse JSON...")
                try:
                    json_match = re.search(r"```json\s*(.*?)\s*```", llm_response, re.DOTALL)
                    if json_match:
                        json_string = json_match.group(1).strip()
                        print(f"DEBUG: Extracted JSON String:\n{json_string[:500]}...") # Print first 500 chars for debug
                        self.all_generated_questions = json.loads(json_string)
                        print("DEBUG: Questions and plan generated successfully and parsed.")
                        
                        # Save to file (optional, but good for debugging and re-use if needed)
                        try:
                            with open(PRE_GENERATED_QUESTIONS_FILE, "w", encoding='utf-8') as f:
                                json.dump(self.all_generated_questions, f, indent=4)
                            print(f"DEBUG: Generated questions and plan saved to {PRE_GENERATED_QUESTIONS_FILE}")
                        except IOError as e:
                            print(f"WARNING: Could not save generated questions to file {PRE_GENERATED_QUESTIONS_FILE}: {e}")

                        self._generate_interview_plan()
                    else:
                        print(f"ERROR: Could not find JSON block in LLM response. Raw response:\n{llm_response}")
                        self.interview_status = 'ERROR'
                except json.JSONDecodeError as e:
                    print(f"ERROR: Error decoding JSON from LLM response: {e}. Raw response:\n{llm_response}")
                    self.interview_status = 'ERROR'
            else:
                print("ERROR: Failed to get a response from the LLM for question generation (response was None).")
                self.interview_status = 'ERROR'
        except Exception as e:
            print(f"CRITICAL ERROR: An unexpected exception occurred during LLM call for question generation: {e}")
            self.interview_status = 'ERROR'

    def _generate_interview_plan(self):
        """
        Creates the structured interview plan from self.all_generated_questions.
        This separates templates from the actual interview flow.
        """
        if "rounds" in self.all_generated_questions:
            self.interview_plan = {
                item['name']: item for item in self.all_generated_questions['rounds']
            }
            if 'technical' in self.interview_plan and 'specializations' in self.interview_plan['technical']:
                self.technical_specializations = list(self.interview_plan['technical']['specializations'].keys())
            else:
                self.technical_specializations = []
            print("Interview plan structured.")
        else:
            print("Warning: 'rounds' key not found in generated questions. Interview plan might be incomplete.")
            self.interview_plan = {}
            self.technical_specializations = []

    def _get_current_round_data(self):
        """Returns the data for the current active round."""
        if self.current_round_name and self.current_round_name in self.interview_plan:
            return self.interview_plan[self.current_round_name]
        return None

    def _get_questions_for_current_round(self):
        """Extracts and flattens questions for the current round."""
        round_data = self._get_current_round_data()
        if not round_data:
            return []

        questions = []
        if self.current_round_name == "technical" and "specializations" in round_data:
            for spec, q_list in round_data["specializations"].items():
                questions.extend([{"question": q, "specialization": spec} for q in q_list[:config.TECHNICAL_QUESTIONS_PER_SPECIALIZATION_COUNT]])
        elif self.current_round_name == "coding" and "stages" in round_data:
            if "Predict Output" in round_data["stages"]:
                questions.extend([{"question": q, "stage": "Predict Output"} for q in round_data["stages"]["Predict Output"][:config.CODING_PREDICT_OUTPUT_QUESTIONS_COUNT]])
            if "Fix Error" in round_data["stages"]:
                questions.extend([{"question": q, "stage": "Fix Error"} for q in round_data["stages"]["Fix Error"][:config.CODING_FIX_ERROR_QUESTIONS_COUNT]])
            if "Write Program" in round_data["stages"]:
                questions.extend([{"question": q, "stage": "Write Program"} for q in round_data["stages"]["Write Program"][:config.CODING_WRITE_PROGRAM_QUESTIONS_COUNT]])
        elif "questions" in round_data:
            if self.current_round_name == "communication":
                questions = [{"question": q} for q in round_data["questions"][:config.COMMUNICATION_QUESTIONS_COUNT]]
            elif self.current_round_name == "psychometric":
                questions = [{"question": q} for q in round_data["questions"][:config.PSYCHOMETRIC_QUESTIONS_COUNT]]
            else:
                questions = [{"question": q} for q in round_data["questions"]]
        return questions

    def _advance_to_next_round(self):
        """Advances the interview to the next round."""
        ordered_round_names = [r['name'] for r in self.all_generated_questions.get('rounds', [])]
        try:
            current_index = ordered_round_names.index(self.current_round_name)
            if current_index + 1 < len(ordered_round_names):
                self.current_round_name = ordered_round_names[current_index + 1]
                self.current_question_index = -1 # Reset question index for new round
                if self.current_round_name in self.timers:
                    self.timers[self.current_round_name].start()
                return True
            else:
                self.current_round_name = "completed" # No more rounds
                return False
        except ValueError:
            self.current_round_name = "completed" # Current round not found, assume end
            return False

    def start_interview_session(self):
        """
        Initializes a new interview session and returns the first prompt.
        This method is called once when the interview begins.
        Returns:
            dict: A dictionary containing the initial prompt text and interview status.
        """
        if self.interview_status != 'SCHEDULED':
            return {"status": "error", "prompt": "Interview is not in a scheduled state to start.", "interview_status": self.interview_status}

        if not self.interview_plan:
            print("Error: Interview plan not loaded or generated during initialization. Cannot start.")
            self.interview_status = 'ERROR'
            return {"status": "error", "prompt": "Interview plan could not be generated. Please check backend logs.", "interview_status": self.interview_status}

        self.interview_status = 'IN_PROGRESS'
        self.current_round_name = self.all_generated_questions['rounds'][0]['name'] # Start with the first round
        self.current_question_index = -1 # Before the first question of the round

        if self.current_round_name in self.timers:
            self.timers[self.current_round_name].start()

        intro_message = self.all_generated_questions.get("introduction_template", "Welcome to the AI Interview.")
        self._add_to_chat_history("assistant", intro_message)
        
        return {"status": "in_progress", "prompt": intro_message, "interview_status": self.interview_status}

    def get_next_prompt(self):
        """
        Determines and returns the next prompt (question or round intro) for the candidate.
        Ensures that if the previous question was not explicitly answered, it's recorded.
        Returns:
            dict: A dictionary with 'status' ('question', 'round_intro', 'completed', 'terminated'),
                  'prompt_text', and 'round_name' (if applicable).
        """
        if self.interview_status in ['COMPLETED', 'TERMINATED_MALPRACTICE', 'ERROR']:
            final_message = self.overall_interview_analysis or "Interview concluded."
            return {"status": self.interview_status, "prompt_text": final_message, "round_name": None}

        if self.malpractice_detected:
            termination_message = self.all_generated_questions.get("interview_termination_template", "The interview has been terminated.")
            return {"status": "terminated", "prompt_text": termination_message.format(reason=self.malpractice_reason), "round_name": self.current_round_name}

        questions_in_current_round = self._get_questions_for_current_round()
        
        # --- Record unanswered previous question (no change) ---
        if self.interview_status == 'IN_PROGRESS' and \
           self.current_question_index >= 0 and \
           len(self.answers) <= self.current_question_index:
            
            prev_q_obj = questions_in_current_round[self.current_question_index]
            prev_question_text = prev_q_obj["question"]

            q_a_detail = {
                "question": prev_question_text,
                "answer": "No answer provided.",
                "score": 0,
                "analysis": "Candidate did not provide an answer for this question.",
                "feedback": "No answer received.",
                "round": self.current_round_name,
                "specialization": prev_q_obj.get("specialization"),
                "stage": prev_q_obj.get("stage")
            }
            self.answers.append(q_a_detail)

            if self.current_round_name not in self.round_detailed_results:
                self.round_detailed_results[self.current_round_name] = {
                    "round_summary": "",
                    "overall_score": 0,
                    "question_details": []
                }
            
            if self.current_round_name == "technical" and "specialization" in prev_q_obj:
                spec = prev_q_obj["specialization"]
                if spec not in self.round_detailed_results[self.current_round_name]:
                    self.round_detailed_results[self.current_round_name][spec] = {"overall_score": 0, "round_summary": "", "question_details": []}
                self.round_detailed_results[self.current_round_name][spec]["question_details"].append(q_a_detail)
                self.round_detailed_results[self.current_round_name][spec]["overall_score"] += 0
            elif self.current_round_name == "coding" and "stage" in prev_q_obj:
                stage = prev_q_obj["stage"]
                if stage not in self.round_detailed_results[self.current_round_name]:
                    self.round_detailed_results[self.current_round_name][stage] = {"overall_score": 0, "round_summary": "", "question_details": []}
                self.round_detailed_results[self.current_round_name][stage]["question_details"].append(q_a_detail)
                self.round_detailed_results[self.current_round_name][stage]["overall_score"] += 0
            else:
                self.round_detailed_results[self.current_round_name]["question_details"].append(q_a_detail)
                self.round_detailed_results[self.current_round_name]["overall_score"] += 0
        # --- End record unanswered previous question ---


        # Initialize round_detailed_results structure if it's the first time entering this round
        if self.current_round_name not in self.round_detailed_results:
            self.round_detailed_results[self.current_round_name] = {
                "round_summary": "",
                "overall_score": 0,
                "question_details": []
            }
            round_data = self._get_current_round_data()
            if round_data:
                if self.current_round_name == "technical" and "specializations" in round_data:
                    for spec in round_data["specializations"].keys():
                        self.round_detailed_results[self.current_round_name][spec] = {
                            "overall_score": 0,
                            "round_summary": "",
                            "question_details": []
                        }
                elif self.current_round_name == "coding" and "stages" in round_data:
                    for stage in round_data["stages"].keys():
                        self.round_detailed_results[self.current_round_name][stage] = {
                            "overall_score": 0,
                            "round_summary": "",
                            "question_details": []
                        }

        # Check if current round is complete or time is up
        if self.current_round_name and self.current_round_name in self.timers and self.timers[self.current_round_name].is_time_up():
            self.previous_round_timed_out = True # Set flag for next prompt
            self._generate_round_summary(self.current_round_name)
            if self._advance_to_next_round():
                intro_message = self.all_generated_questions['round_intro_templates'].get(self.current_round_name, f"Starting the {self.current_round_name.replace('_', ' ').title()} round.")
                # Prepend message if previous round timed out
                if self.previous_round_timed_out:
                    intro_message = "Time's up for the previous round. " + intro_message
                    self.previous_round_timed_out = False # Reset flag after use
                return {"status": "round_intro", "prompt_text": intro_message, "round_name": self.current_round_name}
            else:
                self.interview_status = 'COMPLETED'
                self._generate_final_analysis()
                self._save_interview_results()
                conclusion_message = self.all_generated_questions.get("conclusion_template", "All interview rounds are complete. I am now generating your final report.")
                return {"status": "completed", "prompt_text": conclusion_message, "overall_score": self.overall_interview_score, "overall_analysis": self.overall_interview_analysis}
        
        # If not time up, check if all questions in current round are asked
        if self.current_question_index >= len(questions_in_current_round) -1:
             self._generate_round_summary(self.current_round_name)
             if self._advance_to_next_round():
                intro_message = self.all_generated_questions['round_intro_templates'].get(self.current_round_name, f"Starting the {self.current_round_name.replace('_', ' ').title()} round.")
                # Prepend message if previous round timed out (though this path is less likely for time-out, keep for consistency)
                if self.previous_round_timed_out:
                    intro_message = "Time's up for the previous round. " + intro_message
                    self.previous_round_timed_out = False # Reset flag after use
                return {"status": "round_intro", "prompt_text": intro_message, "round_name": self.current_round_name}
             else:
                self.interview_status = 'COMPLETED'
                self._generate_final_analysis()
                self._save_interview_results()
                conclusion_message = self.all_generated_questions.get("conclusion_template", "All interview rounds are complete. I am now generating your final report.")
                return {"status": "completed", "prompt_text": conclusion_message, "overall_score": self.overall_interview_score, "overall_analysis": self.overall_interview_analysis}


        # If still in progress and questions remain in current round
        self.current_question_index += 1
        q_obj = questions_in_current_round[self.current_question_index]
        question_text = q_obj["question"]

        prompt_text_for_frontend = ""
        if self.current_round_name == "coding":
            stage_display_name = q_obj.get("stage", "Coding").replace('_', ' ').title()
            prompt_text_for_frontend = self.all_generated_questions["coding_question_intro_template"].format(number=self.current_question_index + 1, stage_display_name=stage_display_name)
        else:
            prompt_text_for_frontend = self.all_generated_questions["question_intro_template"].format(number=self.current_question_index + 1, question_text=question_text)
        
        self._add_to_chat_history("assistant", question_text)
        
        return {
            "status": "question",
            "prompt_text": prompt_text_for_frontend,
            "raw_question_text": question_text,
            "round_name": self.current_round_name,
            "question_index": self.current_question_index,
            "remaining_time": int(self.timers[self.current_round_name].get_remaining_time()) if self.current_round_name in self.timers else None
        }


    def process_answer(self, raw_question_text, user_answer_text: str):
        """
        Processes the candidate's answer for the current question.
        Evaluates the answer, updates internal state, and returns feedback.
        Args:
            raw_question_text (str): The exact question text that was asked.
            user_answer_text (str): The transcribed text of the candidate's answer, provided by frontend.
        Returns:
            dict: A dictionary containing feedback, score, and updated interview status.
        """
        if self.interview_status != 'IN_PROGRESS':
            return {"status": "error", "feedback": "Interview is not in progress.", "interview_status": self.interview_status}

        if self.malpractice_detected:
            return {"status": "terminated", "feedback": self.all_generated_questions.get("interview_termination_template", "Interview terminated.").format(reason=self.malpractice_reason), "interview_status": self.interview_status}

        if user_answer_text is None:
             user_answer_text = "No answer provided."

        print(f"You said: {user_answer_text}")
        self._add_to_chat_history("user", user_answer_text)

        questions_in_current_round = self._get_questions_for_current_round()
        if not (0 <= self.current_question_index < len(questions_in_current_round)):
            print(f"ERROR: current_question_index {self.current_question_index} out of bounds for round {self.current_round_name} with {len(questions_in_current_round)} questions.")
            return {"status": "error", "feedback": "Internal error: Question index mismatch.", "interview_status": 'ERROR'}

        q_obj = questions_in_current_round[self.current_question_index]
        
        score_and_analysis = self._evaluate_answer(
            raw_question_text,
            user_answer_text,
            self.current_round_name,
            q_obj.get("specialization"),
            q_obj.get("stage")
        )
        question_score = score_and_analysis.get('score', 0)
        analysis = score_and_analysis.get('analysis', 'No specific analysis provided.')
        feedback_message = score_and_analysis.get('feedback', 'Thank you for your answer.')

        q_a_detail = {
            "question": raw_question_text,
            "answer": user_answer_text,
            "score": question_score,
            "analysis": analysis,
            "feedback": feedback_message,
            "round": self.current_round_name,
            "specialization": q_obj.get("specialization"),
            "stage": q_obj.get("stage")
        }
        self.answers.append(q_a_detail)

        if self.current_round_name not in self.round_detailed_results:
            self.round_detailed_results[self.current_round_name] = {
                "round_summary": "",
                "overall_score": 0,
                "question_details": []
            }

        if self.current_round_name == "technical" and "specialization" in q_obj:
            if q_obj["specialization"] not in self.round_detailed_results[self.current_round_name]:
                self.round_detailed_results[self.current_round_name][q_obj["specialization"]] = {"overall_score": 0, "round_summary": "", "question_details": []}
            self.round_detailed_results[self.current_round_name][q_obj["specialization"]]["question_details"].append(q_a_detail)
            self.round_detailed_results[self.current_round_name][q_obj["specialization"]]["overall_score"] += question_score
        elif self.current_round_name == "coding" and "stage" in q_obj:
            if q_obj["stage"] not in self.round_detailed_results[self.current_round_name]:
                self.round_detailed_results[self.current_round_name][q_obj["stage"]] = {"overall_score": 0, "round_summary": "", "question_details": []}
            self.round_detailed_results[self.current_round_name][q_obj["stage"]]["question_details"].append(q_a_detail)
            self.round_detailed_results[self.current_round_name][q_obj["stage"]]["overall_score"] += question_score
        else:
            self.round_detailed_results[self.current_round_name]["question_details"].append(q_a_detail)
            self.round_detailed_results[self.current_round_name]["overall_score"] += question_score

        return {"status": "answer_processed", "interview_status": self.interview_status, "feedback_text": feedback_message}


    def _evaluate_answer(self, question, answer, round_name, specialization=None, coding_stage=None):
        prompt = (
            f"You are an expert interviewer. Evaluate the following candidate's answer for a '{round_name}' round question."
        )
        if specialization:
            prompt += f" focusing on the '{specialization}' specialization."
        if coding_stage:
            prompt += f" for the '{coding_stage}' coding stage."

        prompt += (
            f"\nJob Description: {self.job_desc}\n"
            f"User Skills: {', '.join(self.user_skills)}\n"
            f"Position: {self.position}\n"
            f"Question: {question}\n"
            f"Candidate's Answer: {answer}\n\n"
            f"Provide a score out of 100, a concise analysis of the answer, and a brief, encouraging feedback message "
            f"(e.g., 'Good answer', 'That's interesting', 'Let's move on').\n"
            f"If the answer is empty, nonsensical, contains gibberish, is off-topic, explicitly states 'I don't know', or is clearly incorrect/incomplete, assign a score of 0. "
            f"Format your response as a JSON object with keys: 'score' (integer), 'analysis' (string), 'feedback' (string)."
        )

        evaluation_response = call_llm_api(prompt, current_conversation_history=self.conversation_history, output_max_tokens=300)
        if evaluation_response:
            try:
                if evaluation_response.strip().startswith("```json") and evaluation_response.strip().endswith("```"):
                    evaluation_response = evaluation_response.strip()[len("```json"):-len("```")].strip()

                parsed_response = json.loads(evaluation_response)
                score = max(0, min(100, int(parsed_response.get('score', 0))))
                analysis = parsed_response.get('analysis', 'No analysis provided.')
                feedback = parsed_response.get('feedback', 'Thank you for your answer.')
                
                return {"score": score, "analysis": analysis, "feedback": feedback}
            except json.JSONDecodeError as e:
                print(f"Error decoding evaluation JSON: {e}. Raw response: {evaluation_response}")
                return {"score": 0, "analysis": f"Evaluation failed: Invalid JSON response ({e}).", "feedback": "Thank you for your answer."}
            except Exception as e:
                print(f"An unexpected error occurred during answer evaluation: {e}. Raw response: {evaluation_response}")
                return {"score": 0, "analysis": f"Evaluation failed: Unexpected error ({e}).", "feedback": "Thank you for your answer."}
        else:
            print("Failed to get evaluation from LLM.")
            return {"score": 0, "analysis": "Evaluation failed: No LLM response.", "feedback": "Thank you for your answer."}

    def _generate_round_summary(self, round_name):
        # Initialize round_detailed_results structure if it's the first time entering this round
        if round_name not in self.round_detailed_results:
            self.round_detailed_results[round_name] = {
                "round_summary": "",
                "overall_score": 0,
                "question_details": []
            }
            round_data = self._get_current_round_data()
            if round_data:
                if round_name == "technical" and "specializations" in round_data:
                    for spec in round_data["specializations"].keys():
                        self.round_detailed_results[round_name][spec] = {
                            "overall_score": 0,
                            "round_summary": "",
                            "question_details": []
                        }
                elif round_name == "coding" and "stages" in round_data:
                    for stage in round_data["stages"].keys():
                        self.round_detailed_results[round_name][stage] = {
                            "overall_score": 0,
                            "round_summary": "",
                            "question_details": []
                        }

        # Collect all question details for the current round, including from sub-sections
        all_round_q_details = []
        if round_name in ["technical", "coding"]:
            # Iterate through specializations/stages and collect their question_details
            current_round_data = self.round_detailed_results[round_name]
            for key, sub_details in current_round_data.items():
                if isinstance(sub_details, dict) and "question_details" in sub_details:
                    all_round_q_details.extend(sub_details["question_details"])
        else:
            # For other rounds (communication, psychometric), details are directly under 'question_details'
            all_round_q_details.extend(self.round_detailed_results[round_name].get("question_details", []))

        if all_round_q_details:
            conversation_snippet = ""
            for qa in all_round_q_details:
                conversation_snippet += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"

            prompt = (
                f"Based on the following conversation snippet from the '{round_name}' round of an interview for a '{self.position}' role, "
                f"provide a concise summary of the candidate's performance in this round. "
                f"Focus on key strengths, weaknesses, and overall impression. "
                f"DO NOT mention any numerical scores or specific question-level feedback in this summary. "
                f"Provide summary in 100-150 words."
            )
            summary_response = call_llm_api(prompt, output_max_tokens=200)
            if summary_response:
                self.round_detailed_results[round_name]["round_summary"] = summary_response
                print(f"Summary generated for {round_name} round.")
            else:
                self.round_detailed_results[round_name]["round_summary"] = "Could not generate summary for this round."
                print(f"Failed to generate summary for {round_name} round.")
        else:
            self.round_detailed_results[round_name]["round_summary"] = "No questions asked in this round."
            print(f"No questions asked in {round_name} round, skipping main summary.")

        # Generate summaries for sub-sections (technical/coding) - this part was already correct
        if round_name == "technical":
            for spec in list(self.round_detailed_results[round_name].keys()):
                if spec in ["question_details", "overall_score", "round_summary"]:
                    continue # Skip top-level keys

                spec_data = self.round_detailed_results[round_name].get(spec)
                if spec_data and spec_data.get("question_details"):
                    spec_conversation_snippet = ""
                    for qa in spec_data["question_details"]:
                        spec_conversation_snippet += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
                    spec_prompt = (
                        f"Based on the following conversation snippet from the '{round_name} - {spec}' section of an interview, "
                        f"provide a concise summary of the candidate's performance in this specific area. "
                        f"DO NOT mention any numerical scores or specific question-level feedback in this summary. "
                        f"Provide summary in 50-100 words."
                    )
                    spec_summary_response = call_llm_api(spec_prompt, output_max_tokens=150)
                    if spec_summary_response:
                        self.round_detailed_results[round_name][spec]["round_summary"] = spec_summary_response
                        print(f"Summary generated for {round_name} - {spec}.")
                    else:
                        self.round_detailed_results[round_name][spec]["round_summary"] = "Could not generate summary for this specialization."
        elif round_name == "coding":
            for stage in list(self.round_detailed_results[round_name].keys()):
                if stage in ["question_details", "overall_score", "round_summary"]:
                    continue # Skip top-level keys

                stage_data = self.round_detailed_results[round_name].get(stage)
                if stage_data and stage_data.get("question_details"):
                    stage_conversation_snippet = ""
                    for qa in stage_data["question_details"]:
                        stage_conversation_snippet += f"Q: {qa['question']}\nA: {qa['answer']}\n\n"
                    stage_prompt = (
                        f"Based on the following conversation snippet from the '{round_name} - {stage}' section of an interview, "
                        f"provide a concise summary of the candidate's performance in this specific area. "
                        f"DO NOT mention any numerical scores or specific question-level feedback in this summary. "
                        f"Provide summary in 50-100 words."
                    )
                    stage_summary_response = call_llm_api(stage_prompt, output_max_tokens=150)
                    if stage_summary_response:
                        self.round_detailed_results[round_name][stage]["round_summary"] = stage_summary_response
                        print(f"Summary generated for {round_name} - {stage}.")
                    else:
                        self.round_detailed_results[round_name][stage]["round_summary"] = "Could not generate summary for this stage."


    def _generate_final_analysis(self):
        print("Generating final comprehensive analysis and job match score...")
        
        # Calculate a preliminary performance score based on round averages
        # This will serve as a quantitative input for the LLM's job match assessment
        prelim_performance_score_sum = 0
        prelim_performance_round_count = 0

        # Ensure all technical specializations from the initial plan are represented
        if "technical" in self.interview_plan and "specializations" in self.interview_plan["technical"]:
            if "technical" not in self.round_detailed_results:
                self.round_detailed_results["technical"] = {
                    "round_summary": "",
                    "overall_score": 0,
                    "question_details": []
                }
            for spec in self.interview_plan["technical"]["specializations"].keys():
                if spec not in self.round_detailed_results["technical"]:
                    self.round_detailed_results["technical"][spec] = {
                        "overall_score": 0,
                        "round_summary": "Not assessed in detail during this interview.",
                        "question_details": []
                    }
        
        # Ensure all coding stages from the initial plan are represented
        if "coding" in self.interview_plan and "stages" in self.interview_plan["coding"]:
            if "coding" not in self.round_detailed_results:
                self.round_detailed_results["coding"] = {
                    "round_summary": "",
                    "overall_score": 0,
                    "question_details": []
                }
            for stage in self.interview_plan["coding"]["stages"].keys():
                if stage not in self.round_detailed_results["coding"]:
                    self.round_detailed_results["coding"][stage] = {
                        "overall_score": 0,
                        "round_summary": "Not assessed in detail during this interview.",
                        "question_details": []
                    }


        for round_name, details in self.round_detailed_results.items():
            current_round_average_score = 0
            questions_in_round = []

            if round_name in ["communication", "psychometric"]:
                questions_in_round = details.get("question_details", [])
            elif round_name in ["technical", "coding"]:
                sub_section_scores = []
                for key, sub_details in details.items():
                    if isinstance(sub_details, dict) and "question_details" in sub_details:
                        sub_total_q_score = sum(q['score'] for q in sub_details["question_details"])
                        sub_num_q = len(sub_details["question_details"])
                        if sub_num_q > 0:
                            sub_average_score = round(sub_total_q_score / sub_num_q, 2)
                            self.round_detailed_results[round_name][key]["overall_score"] = min(100, sub_average_score)
                            sub_section_scores.append(sub_average_score)
                        else:
                            self.round_detailed_results[round_name][key]["overall_score"] = 0

                if sub_section_scores:
                    current_round_average_score = sum(sub_section_scores) / len(sub_section_scores)
                else:
                    current_round_average_score = 0
            
            if round_name not in ["technical", "coding"] and questions_in_round:
                total_q_score = sum(q['score'] for q in questions_in_round)
                num_q = len(questions_in_round)
                current_round_average_score = round(total_q_score / num_q, 2)
            
            self.round_detailed_results[round_name]["overall_score"] = min(100, current_round_average_score)

            if current_round_average_score > 0:
                prelim_performance_score_sum += current_round_average_score
                prelim_performance_round_count += 1

        # This is the calculated performance score, used as context for LLM
        calculated_performance_score = (prelim_performance_score_sum / prelim_performance_round_count) if prelim_performance_round_count > 0 else 0
        calculated_performance_score = round(min(100, calculated_performance_score), 2)


        round_summaries_text = ""
        for round_name, details in self.round_detailed_results.items():
            round_summaries_text += f"\n--- {round_name.replace('_', ' ').title()} Round ---\n"
            round_summaries_text += f"Summary: {details.get('round_summary', 'No summary available.')}\n"
            if round_name == "technical" or round_name == "coding":
                source_sub_sections = {}
                if round_name == "technical" and "specializations" in self.interview_plan.get("technical", {}):
                    source_sub_sections = self.interview_plan["technical"]["specializations"]
                elif round_name == "coding" and "stages" in self.interview_plan.get("coding", {}):
                    source_sub_sections = self.interview_plan["coding"]["stages"]

                for sub_key in source_sub_sections.keys():
                    sub_details = self.round_detailed_results[round_name].get(sub_key)
                    if isinstance(sub_details, dict):
                        round_summaries_text += f"  - {sub_key.replace('_', ' ').title()} Section: {sub_details.get('round_summary', 'No summary available.')}\n"
                    else:
                         round_summaries_text += f"  - {sub_key.replace('_', ' ').title()} Section: Not assessed in detail during this interview.\n"


        # NEW PROMPT for Job Match Score and Analysis
        prompt = (
            f"You are an expert HR professional and AI Interviewer. Based on the following job description, user skills, "
            f"and the detailed round-by-round summaries from the interview, provide a comprehensive final analysis "
            f"and a numerical Job Match Score.\n"
            f"The Job Match Score should be an integer between 0 and 100, representing how well the candidate's skills, "
            f"performance, and potential align with the '{self.position}' role, considering the '{self.job_desc}' job description.\n"
            f"A score of 100 means a perfect match, 0 means no match.\n\n"
            f"Your analysis should include:\n"
            f"1. An overall assessment of the candidate's performance, highlighting strengths and areas for improvement relevant to the job.\n"
            f"2. A final recommendation (e.g., 'Strongly Recommend', 'Recommend with Reservations', 'Do Not Recommend').\n"
            f"3. General observations about their communication, problem-solving, and AI/ML specific technical aptitude.\n"
            f"4. Explicitly state the numerical Job Match Score.\n"
            f"DO NOT include individual round scores or question-level scores in the final analysis text.\n\n"
            f"Job Description: {self.job_desc}\n"
            f"User Skills: {', '.join(self.user_skills)}\n"
            f"Position: {self.position}\n"
            f"Round Summaries:\n{round_summaries_text}\n"
            f"Preliminary Performance Score (for context, not the final job match score): {calculated_performance_score}/100\n\n"
            f"Format your response as a JSON object with two keys: 'job_match_score' (integer 0-100) and 'job_match_analysis' (string, comprehensive text)."
        )

        final_analysis_response = call_llm_api(prompt, current_conversation_history=self.conversation_history, output_max_tokens=1000) # Increased output tokens
        if final_analysis_response:
            try:
                # Extract JSON from potential markdown block
                json_match = re.search(r"```json\s*(.*?)\s*```", final_analysis_response, re.DOTALL)
                if json_match:
                    json_string = json_match.group(1).strip()
                else:
                    json_string = final_analysis_response.strip() # Assume it's just JSON if no markdown block

                parsed_response = json.loads(json_string)
                
                # Set the overall_interview_score to the LLM-generated job_match_score
                self.overall_interview_score = max(0, min(100, int(parsed_response.get('job_match_score', 0))))
                self.overall_interview_analysis = parsed_response.get('job_match_analysis', "Failed to generate comprehensive final analysis.")
                print("Final analysis and job match score generated.")
            except json.JSONDecodeError as e:
                print(f"ERROR: Error decoding final analysis JSON: {e}. Raw response: {final_analysis_response}")
                self.overall_interview_score = calculated_performance_score # Fallback to calculated score
                self.overall_interview_analysis = f"Failed to generate comprehensive final analysis due to JSON parsing error: {e}. Raw LLM response: {final_analysis_response}"
            except Exception as e:
                print(f"An unexpected error occurred during final analysis generation: {e}. Raw response: {final_analysis_response}")
                self.overall_interview_score = calculated_performance_score # Fallback to calculated score
                self.overall_interview_analysis = f"Failed to generate comprehensive final analysis due to unexpected error: {e}. Raw LLM response: {final_analysis_response}"
        else:
            print("Failed to get final analysis from LLM.")
            self.overall_interview_score = calculated_performance_score # Fallback to calculated score
            self.overall_interview_analysis = "Failed to generate comprehensive final analysis: No LLM response."


# talent_management/interview_bot/interviewer_logic.py

import json
import re
import time
import os
# Relative imports for other bot modules
from .llm_utils import call_llm_api
from .speech_utils import speak_text
from . import config # Import config from the same package
from .timer_utils import RoundTimer

# NEW: Import Django models and timezone for database interaction
from django.utils import timezone
# IMPORTANT: This import is placed inside methods to avoid circular dependency
# from talent_management.models import MockInterviewResult


# Define a constant for the pre-generated questions file (no longer used for file IO, but as a conceptual reference)
PRE_GENERATED_QUESTIONS_FILE = "pre_generated_questions.json" # Kept for consistency, but not for file operations
# Define a constant for the interview results file (no longer used for file IO)
INTERVIEW_RESULTS_FILE = "interview_results.json"


class AIInterviewer:
    # UPDATED __init__ signature to accept mock_interview_result_instance
    def __init__(self, position, experience, aiml_specialization=None, mock_interview_result_instance=None):
        print(f"DEBUG: AIInterviewer initialized with position='{position}', experience='{experience}', aiml_specialization='{aiml_specialization}'")

        self.position = position
        self.experience = experience
        self.aiml_specialization = aiml_specialization # This is list input
        self.all_interview_answers = [] # Stores ALL Q&A pairs for the entire interview, for language scoring
        self.round_detailed_results = {} # Stores detailed scoring results per round (e.g., communication, psychometric)
        self.round_scores = { # Stores just the overall score for each major round/stage
            "communication": 0,
            "psychometric": 0,
            "coding": {}, # Will store scores for each coding stage
            "technical": {}, # Will store scores for each technical specialization
        }
        self.chat_history = [] # Stores conversation history for LLM context
        self.MAX_CHAT_HISTORY_TURNS = 10 # Limit chat history size
        self.round_time_limits = config.ROUND_TIME_LIMITS
        self.malpractice_detected = False
        self.malpractice_reason = ""
        self.read_malpractice_status_func = None # Will be set by views.py

        # NEW: Store the MockInterviewResult instance directly
        self.mock_interview_db_instance = mock_interview_result_instance

        self.global_readiness_score = 0
        self.language_score = 0
        self.language_analysis = "N/A"

        # Initialize current round state (will be managed by views and updated here)
        self.current_round_name = None
        self.current_round_questions = [] # Questions for the current round being asked
        self.current_question_index = 0
        self.technical_specializations = [] # Determined during pre-generation (list of strings)
        self.technical_current_specialization_index = 0 # For iterating through tech specializations
        self.coding_current_stage_index = 0 # For iterating through coding stages

        # Default structure for pre-generated questions (will be populated or loaded)
        self.all_generated_questions = {
            "welcome_message": "......Welcome to the AI Interviewer.......",
            "interview_start_message_template": "Starting the AI Interview for {position} role.",
            "communication": {
                "intro_message": "Starting Communication Skills round.",
                "questions": []
            },
            "psychometric": {
                "intro_message": "Starting Psychometric Assessment round.",
                "questions": []
            },
            "coding": {
                "intro_message": "Starting the Coding Skills round. This round requires text input only.",
                "predict_output": {
                    "intro_message": "Moving to Coding Stage: Predict Output.",
                    "questions": []
                },
                "fix_error": {
                    "intro_message": "Moving to Coding Stage: Fix Error.",
                    "questions": []
                },
                "write_program": {
                    "intro_message": "Moving to Coding Stage: Write Program.",
                    "questions": []
                }
            },
            "technical": {
                "intro_message": "Starting Technical Skills round, focusing on your specializations.",
                "specializations": {}
            },
            "no_specializations_message": "Could not identify technical specializations. Technical sub-rounds will be skipped.",
            "interview_complete_message": "The interview is complete. Generating your final comprehensive analysis now.",
            "final_report_saved_message_template": "Your interview has concluded. A detailed report has been saved to {report_filename}. You did your best, now leave the rest to us.",
            "error_report_save_message_template": "Error: Could not save the interview report to file. Please check permissions.",
            "malpractice_terminated_message_template": "The interview was terminated due to {reason}.",
            "question_intro_template": "Question {number}: {question_text}",
            "coding_question_intro_template": "Here is your question {number} for {stage_display_name} stage.",
            "answer_acknowledgement_template": "Thank you for your answer." # Added for smoother flow
        }

    def _add_to_chat_history(self, role, text):
        """Adds a message to the internal chat history and manages its size."""
        self.chat_history.append({"role": role, "parts": [{"text": text}]})

        if len(self.chat_history) > self.MAX_CHAT_HISTORY_TURNS + 1:
            self.chat_history = [self.chat_history[0]] + self.chat_history[-(self.MAX_CHAT_HISTORY_TURNS):]

    # UPDATED: This function now also updates the database instance
    def _check_malpractice_status(self, read_status_func):
        """
        Checks the malpractice status file and updates internal flag and DB instance.
        Returns True if interview should terminate due to malpractice, False otherwise.
        """
        status = read_status_func()
        if status.startswith("TERMINATED") and status != "TERMINATED_NORMAL_EXIT":
            self.malpractice_detected = True
            self.malpractice_reason = status
            print(f"\n[INTERVIEWER]: Malpractice detected: {status}. Terminating interview.")
            speak_text(self.all_generated_questions["malpractice_terminated_message_template"].format(reason=status))
            
            # NEW: Update the database instance
            if self.mock_interview_db_instance:
                from talent_management.models import MockInterviewResult # Import here to avoid circular dependency
                self.mock_interview_db_instance.malpractice_detected = True
                self.mock_interview_db_instance.malpractice_reason = status
                self.mock_interview_db_instance.status = MockInterviewResult.InterviewStatus.TERMINATED_MALPRACTICE
                self.mock_interview_db_instance.interview_end_time = timezone.now()
                self.mock_interview_db_instance.save()
            return True
        return False

    def _score_single_qa(self, question_text, answer_text, round_name, specialization=None, coding_stage=None):
        """
        Scores a single question-answer pair using the _score_round method and extracts
        the score and analysis for that specific question.
        Returns (score, analysis) or (0, "N/A") if scoring fails.
        """
        if not answer_text:
            return 0, "No answer provided."

        # The relevant_answers now need to include speak_text for _score_round
        relevant_answers = [{
            "question_text": question_text,
            "speak_text": self._get_speak_text_for_question_fallback(question_text, round_name, specialization, coding_stage), # Fallback speak_text
            "answer": answer_text
        }]

        scoring_results = self._score_round(round_name, relevant_answers, specialization, coding_stage)

        if scoring_results and scoring_results['questions']: # Changed from 'question_details' to 'questions'
            qa_detail = scoring_results['questions'][0] # Changed from 'question_details' to 'questions'
            # Only return score, as analysis is not needed for this specific use case
            return qa_detail.get('score', 0), qa_detail.get('analysis', "No specific analysis provided.") # Still return analysis for internal consistency
        else:
            return 0, "Scoring failed or no analysis found."

    def _generate_questions(self, round_name, num_questions, specialization=None, coding_stage=None):
        """
        Generates ALL questions for a given round/specialization/coding stage at once.
        Stores them in self.all_generated_questions and returns the list of question dictionaries.
        """
        if num_questions <= 0:
            print(f"DEBUG: Skipping question generation for {round_name}" + (f" - {specialization}" if specialization else "") + (f" - {coding_stage}" if coding_stage else "") + " as num_questions is 0.")
            # Ensure the structure is initialized even if no questions are generated
            if round_name == "coding":
                self.all_generated_questions["coding"][f"{coding_stage}"]["questions"] = []
            elif specialization:
                if specialization not in self.all_generated_questions["technical"]["specializations"]:
                    self.all_generated_questions["technical"]["specializations"][specialization] = {"intro_message": self.all_generated_questions["technical"]["intro_message"].replace("your specializations", specialization), "questions": []}
                self.all_generated_questions["technical"]["specializations"][specialization]["questions"] = []
            else:
                self.all_generated_questions[round_name]["questions"] = []
            return []

        prompt = ""
        output_tokens = 500
        generated_question_dicts = []

        if round_name == "coding":
            prompt = (
                f"Generate EXACTLY {num_questions} unique Python code snippet(s) for a {self.position} role, considering the candidate's experience: \"{self.experience}\". "
                f"The questions should primarily focus on the '{self.position}' role, but also leverage the candidate's stated experience. "
                f"Present ONLY the JSON array of strings, no other text or conversational filler. "
            )
            if coding_stage == "predict_output":
                prompt += (
                    f"Each code snippet should be around 5-10 lines and ask the candidate to predict its output. "
                    f"Focus on basic to intermediate Python concepts (e.g., loops, conditionals, list operations, string manipulation, functions, classes). "
                    f"Format them as a JSON array of strings: [\"Code Snippet 1\\nWhat is the output of this code?\", \"Code Snippet 2\\nWhat is the output of this code?\"]"
                )
            elif coding_stage == "fix_error":
                prompt += (
                    f"Each code snippet should be around 5-10 lines with a single, subtle logical or runtime error. "
                    f"The error should be identifiable without extensive debugging tools. "
                    f"Format them as a JSON array of strings: [\"Code Snippet 1 (buggy)\\nIdentify and fix the error in this code.\", \"Code Snippet 2 (buggy)\\nIdentify and fix the error in this code.\"]"
                )
            elif coding_stage == "write_program":
                prompt += (
                    f"Each problem should require writing a short Python program (e.g., a function to solve a specific task). "
                    f"Format them as a JSON array of strings: [\"Problem Statement 1\", \"Problem Statement 2\"]"
                )
            else:
                raise ValueError(f"Unknown coding stage: {coding_stage}")
            output_tokens = 1000
        elif specialization:
            prompt = (
                f"Generate EXACTLY {num_questions} unique technical interview questions for a {self.position} role, "
                f"focusing primarily on \"{specialization}\", while also considering the candidate's experience: \"{self.experience}\". "
                f"The questions should emphasize the '{self.position}' role. "
                f"Present ONLY the JSON array of strings, no other text or conversational filler. "
                f"Ensure questions are straightforward and can can be understood without visual aids. "
                f"The expected answers should be conceptual and easy to articulate verbally, focusing on 'how you would approach', 'explain the concept', 'describe your strategy', or 'share your experience'. "
                f"Format them as a JSON array of strings: [\"Question 1\", \"Question 2\", ..., \"Question {num_questions}\"]."
            )
        else:
            prompt_map = {
                "communication": (f"Generate EXACTLY {num_questions} unique communication skill interview questions for a {self.position} role. "
                                  f"The questions should be relevant to the '{self.position}' role. "
                                  f"Present ONLY the JSON array of strings, no other text or conversational filler. "
                                  f"Focus on general professional communication scenarios such as teamwork, conflict resolution, presenting ideas, or receiving feedback. "
                                  f"Ensure questions are straightforward and can be understood without visual aids. "
                                  f"The expected answers should be conceptual and easy to articulate verbally. "
                                  f"Do NOT ask technical questions or questions requiring specific domain knowledge, coding, or detailed implementation steps. "
                                  f"Format them as a JSON array of strings: [\"Question 1\", \"Question 2\", ..., \"Question {num_questions}\"]."),
                "psychometric": (f"Generate EXACTLY {num_questions} unique psychometric interview questions relevant for a {self.position} role, considering the candidate's experience: \"{self.experience}\". "
                                 f"The questions should emphasize the '{self.position}' role. "
                                 f"Present ONLY the JSON array of strings, no other text or conversational filler. "
                                 f"Ensure questions are straightforward and can be understood without visual aids. "
                                 f"The expected answers should be conceptual and easy to articulate verbally. "
                                 f"Do NOT ask technical questions or questions requiring specific domain knowledge, coding, or detailed implementation steps. "
                                 f"Focus on behavioral, situational, or personality-based questions. "
                                 f"Format them as a JSON array of strings: [\"Question 1\", \"Question 2\", ..., \"Question {num_questions}\"]."),
            }
            prompt = prompt_map.get(round_name)

        if not prompt:
            raise ValueError(f"Unknown round name: {round_name} or specialization: {specialization}")

        response_text = call_llm_api(prompt, self.chat_history, output_max_tokens=output_tokens)

        if response_text:
            self._add_to_chat_history("model", response_text)
            
            # Attempt to extract JSON using a more robust regex first
            # This regex aims to capture a full JSON array of strings, handling escaped quotes
            json_match = re.search(r'\[\s*\"(?:[^\"\\]|\\.)*\"(?:\s*,\s*\"(?:[^\"\\]|\\.)*\")*\s*\]', response_text, re.DOTALL)
            
            
            # Fallback to stripped text
            if json_match:
                json_string_to_parse = json_match.group(0)
            else:
                # Fallback to stripped text, but ensure response_text is a string
                if isinstance(response_text, str):
                    json_string_to_parse = response_text.strip()
                else:
                    # This is an unexpected case where response_text is not a string.
                    # Convert to string to avoid crash, but log a warning.
                    print(f"Warning: Expected LLM response to be a string, but received type {type(response_text)}. Attempting conversion to string. Value: {response_text}")
                    json_string_to_parse = str(response_text) # Attempt conversion to string
 

            try:
                parsed_json = json.loads(json_string_to_parse)
                raw_questions = []
                if isinstance(parsed_json, list):
                    raw_questions = parsed_json
                elif isinstance(parsed_json, dict) and "questions" in parsed_json and isinstance(parsed_json["questions"], list):
                    raw_questions = parsed_json["questions"]
                else:
                    print(f"Warning: LLM response for {round_name} did not parse as a list or a dict with 'questions' key. Raw: {json_string_to_parse}")
                    # Fallback to a more robust regex if JSON structure is unexpected
                    raw_questions = re.findall(r'\"(.*?)(?<!\\)\"', response_text, re.DOTALL) # Use original response_text here

                # STRICTLY enforce num_questions here
                raw_questions = raw_questions[:num_questions]

                for i, q_text in enumerate(raw_questions):
                    speak_text_for_q = ""
                    if round_name == "coding":
                        stage_display_name = coding_stage.replace('_', ' ').title()
                        speak_text_for_q = self.all_generated_questions["coding_question_intro_template"].format(number=i+1, stage_display_name=stage_display_name)
                    else:
                        speak_text_for_q = self.all_generated_questions["question_intro_template"].format(number=i+1, question_text=q_text)

                    generated_question_dicts.append({
                        "question_text": q_text,
                        "speak_text": speak_text_for_q
                    })

            except json.JSONDecodeError as e:
                print(f"Warning: Failed to decode JSON for {round_name} questions after robust regex search: {e}. Attempting simpler regex extraction. Raw: {json_string_to_parse}")
                raw_questions = re.findall(r'\"(.*?)(?<!\\)\"', response_text, re.DOTALL) # Robust regex for fallback
                # STRICTLY enforce num_questions here for regex fallback too
                raw_questions = raw_questions[:num_questions]
                for i, q_text in enumerate(raw_questions):
                    speak_text_for_q = ""
                    if round_name == "coding":
                        stage_display_name = coding_stage.replace('_', ' ').title()
                        speak_text_for_q = self.all_generated_questions["coding_question_intro_template"].format(number=i+1, stage_display_name=stage_display_name)
                    else:
                        speak_text_for_q = self.all_generated_questions["question_intro_template"].format(number=i+1, question_text=q_text)
                    generated_question_dicts.append({
                        "question_text": q_text,
                        "speak_text": speak_text_for_q
                    })
            except Exception as e:
                print(f"Unexpected error processing response for {round_name} / {specialization}: {e}")
                print(f"Raw response: '{response_text}'") # Log original response for debugging

        if round_name == "coding":
            self.all_generated_questions["coding"][f"{coding_stage}"]["questions"] = generated_question_dicts
        elif specialization:
            if specialization not in self.all_generated_questions["technical"]["specializations"]:
                self.all_generated_questions["technical"]["specializations"][specialization] = {"intro_message": self.all_generated_questions["technical"]["intro_message"].replace("your specializations", specialization), "questions": []}
                self.all_generated_questions["technical"]["specializations"][specialization]["questions"] = [] # Initialize questions list
            self.all_generated_questions["technical"]["specializations"][specialization]["questions"] = generated_question_dicts
        else:
            self.all_generated_questions[round_name]["questions"] = generated_question_dicts

        return generated_question_dicts

    # NEW METHOD: To pre-generate all questions at the start of the interview
    def _pre_generate_all_questions(self):
        """
        Pre-generates all questions for all rounds and stages at the beginning of the interview.
        This populates self.all_generated_questions.
        """
        print("\n[AI]: Pre-generating all interview questions...")
        speak_text("Please wait while I generate the interview questions.")

        try:
            # Generate Communication Questions
            self._generate_questions("communication", config.NUM_COMMUNICATION_QUESTIONS)

            # Generate Psychometric Questions
            self._generate_questions("psychometric", config.NUM_PSYCHOMETRIC_QUESTIONS)

            # Identify and Generate Technical Specialization Questions
            # If aiml_specialization is provided, prioritize it and add it to technical_specializations
            if self.aiml_specialization: # Check if the list is not empty
                for spec in self.aiml_specialization:
                    # Only add if it's a non-empty string after stripping
                    if isinstance(spec, str) and spec.strip():
                        self.technical_specializations.append(spec.strip())
            
            # Ensure only unique specializations and limit to top N
            self.technical_specializations = list(set(self.technical_specializations))[:3] # Limit to top 3

            if not self.technical_specializations:
                print(self.all_generated_questions["no_specializations_message"])
                speak_text(self.all_generated_questions["no_specializations_message"])
            else:
                for specialization in self.technical_specializations:
                    self._generate_questions("technical", config.NUM_TECHNICAL_QUESTIONS_PER_SPECIALIZATION, specialization=specialization)

            # Generate Coding Questions (for each stage)
            self._generate_questions("coding", config.NUM_CODING_PREDICT_OUTPUT_QUESTIONS, coding_stage="predict_output")
            self._generate_questions("coding", config.NUM_CODING_FIX_ERROR_QUESTIONS, coding_stage="fix_error")
            self._generate_questions("coding", config.NUM_CODING_WRITE_PROGRAM_QUESTIONS, coding_stage="write_program")

            # Save the generated questions to the database instance
            if self.mock_interview_db_instance:
                self.mock_interview_db_instance.pre_generated_questions_data = self.all_generated_questions
                # This save will happen in MockInterviewStartView.post after pre-generation
                # self.mock_interview_db_instance.save(update_fields=['pre_generated_questions_data'])
                print(f"DEBUG: Pre-generated questions saved to DB for interview ID: {self.mock_interview_db_instance.id}")

            print("\n[AI]: All questions pre-generated successfully!")
            speak_text("All questions have been generated. We can start the interview now.")

        except Exception as e:
            print(f"Error during question pre-generation: {e}")
            speak_text(f"An error occurred during question generation: {e}. The interview cannot proceed.")
            self.malpractice_detected = True
            self.malpractice_reason = f"Question generation failed: {e}"
            # Update DB status if pre-generation fails
            if self.mock_interview_db_instance:
                from talent_management.models import MockInterviewResult # Import here
                self.mock_interview_db_instance.status = MockInterviewResult.InterviewStatus.TERMINATED_ERROR
                self.mock_interview_db_instance.malpractice_detected = True
                self.mock_interview_db_instance.malpractice_reason = self.malpractice_reason
                self.mock_interview_db_instance.interview_end_time = timezone.now()
                self.mock_interview_db_instance.save()


    # NEW: Class method to reconstruct AIInterviewer from a DB instance
    @classmethod
    def load_from_db_instance(cls, mock_interview_db_instance):
        """
        Reconstructs an AIInterviewer instance from a saved MockInterviewResult database object.
        """
        if not mock_interview_db_instance:
            return None
        # Determine the AIML specialization list to pass to __init__
        # Prioritize the JSONField (list) if available, otherwise default to empty list+






        loaded_aiml_specializations_list = mock_interview_db_instance.aiml_specialization
        if not isinstance(loaded_aiml_specializations_list, list):
            # Fallback for old data or if JSONField was somehow not a list, try to parse string
            if mock_interview_db_instance.aiml_specialization_input:
                loaded_aiml_specializations_list = [s.strip() for s in mock_interview_db_instance.aiml_specialization_input.split(',') if s.strip()]
            else:
                loaded_aiml_specializations_list = [] #+ Default to empty list if no source
 







        # Create a new AIInterviewer instance
        interviewer = cls(
            position=mock_interview_db_instance.position_applied,
            experience=mock_interview_db_instance.candidate_experience,




            #- aiml_specialization=mock_interview_db_instance.aiml_specialization_input,




            aiml_specialization=loaded_aiml_specializations_list, #+ CORRECT: Pass the list here # Use input string for init
            
            
            mock_interview_result_instance=mock_interview_db_instance
        )

        # Load all_generated_questions from the database instance
        if mock_interview_db_instance.pre_generated_questions_data:
            interviewer.all_generated_questions = mock_interview_db_instance.pre_generated_questions_data
            print(f"DEBUG: AIInterviewer loaded pre-generated questions from DB for interview ID: {mock_interview_db_instance.id}")
        else:
            print(f"WARNING: No pre-generated questions found in DB for interview ID: {mock_interview_db_instance.id}. AIInterviewer will attempt to regenerate.")
            # If not found, a new generation will occur on run_interview, but this might be problematic
            # if the interview is already in progress. This scenario should ideally be prevented.
            interviewer.all_generated_questions = {} # Initialize empty if none found


        # Load chat history and all_interview_answers from full_qa_transcript
        reconstructed_chat_history = []
        reconstructed_all_interview_answers = []
        if mock_interview_db_instance.full_qa_transcript:
            for qa_pair in mock_interview_db_instance.full_qa_transcript:
                q_text = qa_pair.get('question_text', 'N/A')
                s_text = qa_pair.get('speak_text', q_text) # Use speak_text if available, else question_text
                answer = qa_pair.get('answer', '')

                reconstructed_chat_history.append({"role": "model", "parts": [{"text": q_text}]})
                reconstructed_all_interview_answers.append({
                    "question_text": q_text,
                    "speak_text": s_text,
                    "answer": answer
                })
                if answer: # Only add user answer to chat history if it's not empty
                    reconstructed_chat_history.append({"role": "user", "parts": [{"text": answer}]})
            interviewer.chat_history = reconstructed_chat_history
            interviewer.all_interview_answers = reconstructed_all_interview_answers
            print(f"DEBUG: Reconstructed chat history with {len(reconstructed_chat_history)} entries.")
            print(f"DEBUG: Reconstructed all_interview_answers with {len(reconstructed_all_interview_answers)} entries.")
        else:
            print(f"DEBUG: No full Q&A transcript found in DB for interview ID: {mock_interview_db_instance.id}.")
        


        # Reconstruct round scores and detailed results from round_analysis_json


       # Initialize round_scores for reconstruction, especially for nested structures+
        interviewer.round_scores = {
            "communication": 0,
            "psychometric": 0,
            "technical": {}, # Initialize technical as a dict for specialization scores
            "coding": {}     # Initialize coding as a dict for stage scores
        }
        interviewer.round_detailed_results = mock_interview_db_instance.round_analysis_json if mock_interview_db_instance.round_analysis_json else {}
        #+-interviewer.round_detailed_results = mock_interview_db_instance.round_analysis_json
        
        # Reconstruct round_scores from round_detailed_results
        for round_key, round_data in interviewer.round_detailed_results.items():
            if round_key == "coding" and isinstance(round_data, dict):
                for stage_key, stage_data in round_data.items():
                    if 'overall_score' in stage_data:
                        interviewer.round_scores["coding"][stage_key] = stage_data['overall_score']
            elif round_key == "technical" and isinstance(round_data, dict):
                for spec_key, spec_data in round_data.items():
                    if 'overall_score' in spec_data:
                        interviewer.round_scores["technical"][spec_key] = spec_data['overall_score']
            elif 'overall_score' in round_data:
                interviewer.round_scores[round_key] = round_data['overall_score']


        interviewer.global_readiness_score = mock_interview_db_instance.global_readiness_score
        interviewer.language_score = mock_interview_db_instance.language_proficiency_score
        interviewer.language_analysis = mock_interview_db_instance.language_analysis
        
        # Reconstruct technical_specializations from the database field (aiml_specialization JSONField)
        #if mock_interview_db_instance.aiml_specialization:
        #    interviewer.technical_specializations = mock_interview_db_instance.aiml_specialization
        #elif interviewer.aiml_specialization and interviewer.aiml_specialization.strip():
        #    interviewer.technical_specializations.append(interviewer.aiml_specialization.strip())



        interviewer.technical_specializations = loaded_aiml_specializations_list # CRITICAL: Directly set from the list
        





        


        # Ensure only top 3 specializations are kept, and that they are unique
        interviewer.technical_specializations = list(set(interviewer.technical_specializations))[:3]
        print(f"DEBUG: Reconstructed technical specializations: {interviewer.technical_specializations}")

        return interviewer

    def _score_language_proficiency(self, all_qa_pairs):
        """
        Scores the candidate's language proficiency based on their answers throughout the interview.
        This method should be called at the end of the interview.
        It updates self.language_score and self.language_analysis.
        """
        if not all_qa_pairs:
            self.language_score = 0
            self.language_analysis = "No substantive answers provided for language assessment."
            print("DEBUG: No answers available for language proficiency scoring.")
            return

        # Concatenate all candidate answers into a single string for language analysis
        all_answers_text = " ".join([qa.get('answer', '') for qa in all_qa_pairs if qa.get('answer')])

        if not all_answers_text.strip():
            self.language_score = 0
            self.language_analysis = "No substantive answers provided for language assessment."
            print("DEBUG: All answers were empty for language proficiency scoring.")
            return

        prompt = (
            f"Analyze the following text for language proficiency (grammar, vocabulary, fluency, clarity, coherence, pronunciation if applicable). "
            f"Provide an overall score out of 100 and a concise qualitative analysis. "
            f"Your ONLY output MUST be a JSON object with the following structure. Do NOT include any other text, explanations, or conversational filler outside of the JSON:\n"
            f"{{\n"
            f" \"language_score\": <integer 0-100>,\n"
            f" \"language_analysis\": \"<Concise qualitative analysis of language proficiency. ENSURE THIS STRING DOES NOT CONTAIN UNESCAPED DOUBLE QUOTES OR NEWLINES.>\"\n" # Added explicit instruction
            f"}}\n"
            f"Text to analyze: \"{all_answers_text}\""
        )

        print("\n[AI Scoring Language Proficiency]...")
        response_text = call_llm_api(prompt, current_conversation_history=[], output_max_tokens=300)

        # --- MODIFIED LANGUAGE SCORING PARSING START ---
        if response_text:
            print(f"DEBUG: Raw LLM response for language scoring: '{response_text}'")
            
            # Step 1: Extract the JSON object using the most robust regex
            json_match = re.search(r'(\{.*?\})', response_text, re.DOTALL)
            json_string_candidate = json_match.group(1) if json_match else response_text.strip()

            # Step 2: Aggressively clean the JSON string candidate
            # Remove all literal newlines and tabs from the entire string
            json_string_candidate = json_string_candidate.replace('\n', '').replace('\t', '')
            # Remove any non-printable ASCII characters
            json_string_candidate = re.sub(r'[^\x20-\x7E]', '', json_string_candidate)

            print(f"DEBUG: Extracted JSON string for language scoring (after robust cleaning): '{json_string_candidate}'")

            try:
                # Attempt to parse the cleaned string directly
                parsed_json = json.loads(json_string_candidate)
                
                # Validate structure
                if isinstance(parsed_json, dict) and 'language_score' in parsed_json and 'language_analysis' in parsed_json:
                    self.language_score = int(parsed_json.get('language_score', 0))
                    self.language_analysis = parsed_json.get('language_analysis', "Could not generate language analysis.")
                    print(f"DEBUG: Language Score: {self.language_score}, Analysis: {self.language_analysis}")
                else:
                    print(f"Warning: LLM response for language scoring did not match expected JSON structure after parsing. Raw: {json_string_candidate} | Parsed Type: {type(parsed_json)}")
                    self.language_score = 0
                    self.language_analysis = "Failed to parse language analysis from AI response (unexpected JSON structure)."

            except json.JSONDecodeError as e:
                print(f"Warning: Initial JSON decode failed for language scoring: {e}. Raw (after cleaning attempt): '{json_string_candidate}'")
                
                # Fallback: If direct parsing fails, try to manually extract and clean 'language_analysis'
                # This is a highly specific fallback for the most common LLM JSON errors.
                try:
                    # Find language_score first
                    score_match = re.search(r'"language_score":\s*(\d+)', json_string_candidate)
                    temp_score = int(score_match.group(1)) if score_match else 0

                    # Find language_analysis string content, being tolerant to unescaped quotes
                    # This regex tries to capture everything between the double quotes after "language_analysis":
                    # It's non-greedy and looks for the next unescaped quote to close the string.
                    analysis_content_match = re.search(r'"language_analysis":\s*"(.*?)(?<!\\)"', json_string_candidate)
                    
                    temp_analysis = "Failed to extract language analysis content."
                    if analysis_content_match:
                        # Get the raw content of the analysis string
                        raw_analysis_value = analysis_content_match.group(1)
                        # Re-escape any double quotes within this content
                        # This replaces " with \" only if it's not already escaped
                        temp_analysis = re.sub(r'(?<!\\)"', '\\"', raw_analysis_value)
                        # Also replace any literal newlines/tabs that might still be there (should be caught by earlier cleaning, but as a double-check)
                        temp_analysis = temp_analysis.replace('\n', '\\n').replace('\t', '\\t')
                    else:
                        print("DEBUG: Could not extract 'language_analysis' content using regex.")
                        # As a last resort, try to extract any text after "language_analysis":
                        fallback_analysis_match = re.search(r'"language_analysis":\s*(.*)', json_string_candidate)
                        if fallback_analysis_match:
                            temp_analysis = fallback_analysis_match.group(1).strip().strip('"').strip("'")
                            # Clean up any remaining quotes or braces that might be part of the malformed string
                            temp_analysis = re.sub(r'[\}\]]', '', temp_analysis) # Remove trailing braces/brackets
                            temp_analysis = temp_analysis.replace('\\n', '\n').replace('\\t', '\t') # Convert escaped back to literal for storage
                            print(f"DEBUG: Fallback extracted analysis: '{temp_analysis}'")

                    self.language_score = temp_score
                    self.language_analysis = temp_analysis
                    print(f"DEBUG: Language Score (Fallback): {self.language_score}, Analysis (Fallback): {self.language_analysis}")

                except Exception as e_fallback:
                    print(f"Warning: Fallback parsing for language scoring failed: {e_fallback}. Raw: '{json_string_candidate}'")
                    self.language_score = 0
                    self.language_analysis = "Failed to parse language analysis from AI response (fallback failed)."
            
            except Exception as e_general:
                print(f"Unexpected error during language scoring processing: {e_general}. Raw response: '{response_text}'")
                self.language_score = 0
                self.language_analysis = "An unexpected error occurred during language analysis."
        else:
            self.language_score = 0
            self.language_analysis = "No response from AI for language analysis."
            print("DEBUG: No AI response for language proficiency scoring.")
        # --- MODIFIED LANGUAGE SCORING PARSING END ---


    def _score_round(self, round_name, relevant_answers_for_scoring, specialization=None, coding_stage=None):
        """
        Scores a given round or technical specialization, returning overall score, per-question scores, and analyses.
        This version is made more robust to handle unexpected LLM responses and ensures correct data mapping.
        It now takes `relevant_answers_for_scoring` as an explicit parameter, which should contain
        all Q&A pairs for the current round.
        """
        if not relevant_answers_for_scoring:
            print(f"No answers provided for {round_name}" + (f" - {specialization}" if specialization else "") + ". Score 0.")
            return {
                'overall_score': 0,
                'questions': [], # Changed from 'question_details' to 'questions'
                'round_summary': f"No answers were provided for the {round_name}" + (f" ({specialization})" if specialization else "") + " round."
            }

        base_scoring_rules = (
            f"Your ONLY output MUST be a JSON object with the following structure. Do NOT include any other text, explanations, or conversational filler outside of the JSON:\n"
            f"{{\n"
            f" \"overall_score\": <integer 0-100>,\n"
            f" \"round_summary\": \"<Overall qualitative assessment. Be concise.>\",\n"
            f" \"question_details\": [\n" # LLM still outputs 'question_details'
            f" {{\n"
            f" \"question\": \"<The original question text.>\",\n" # LLM receives 'question'
            f" \"answer\": \"<The candidate's original answer.>\",\n"
            f" \"score\": <integer 0-100>,\n"
            f" \"analysis\": \"<Specific analysis for this question's answer, highlighting strengths/weaknesses. Be concise.>\"\n"
            f" }}\n"
            f" // ... repeat for each question\n"
            f" ]\n"
            f"}}\n"
            f"IMPORTANT SCORING RULES: "
            f"1. Every 'score' field must be an integer between 0 and 100. "
            f"2. For each 'score' within 'question_details', if an answer is empty, nonsensical, contains gibberish, is off-topic, explicitly states 'I don't know', or is clearly incorrect/incomplete, you MUST assign a score of 0. "
            f"3. If a score is 0, provide a clear, concise reason in the 'analysis' why it received 0 (e.g., 'No answer provided.', 'Answer was off-topic.', 'Incorrect output.')."
            f"4. For 'overall_score', calculate the STRICT average of all 'score' values in 'question_details'. Ensure this average is an integer. "
            f"5. All analysis must be concise, direct, and professional."
        )

        # The LLM prompt expects 'question' and 'answer'.
        # We need to map our 'question_text' from relevant_answers_for_scoring to 'question' for the prompt.
        prompt_relevant_answers = []
        for qa_pair in relevant_answers_for_scoring:
            prompt_relevant_answers.append({
                "question": qa_pair.get('question_text', 'N/A'),
                "answer": qa_pair.get('answer', '')
            })

        if round_name == "coding":
            scoring_prompt = (
                f"As a strict and unbiased AI interviewer, evaluate the candidate's performance for the \"Coding - {coding_stage.replace('_', ' ').title()}\" stage out of 100. "
                f"Consider the candidate's experience: \"{self.experience}\" and the target position: \"{self.position}\". "
                f"The scoring should primarily consider the '{self.position}' role. "
                f"Here are the coding question and the candidate's answer:\n{json.dumps(prompt_relevant_answers, indent=2)}\n" + base_scoring_rules
            )
        elif specialization:
            scoring_prompt = (
                f"As a strict and unbiased AI interviewer, evaluate the candidate's performance for the \"{specialization}\" specialization out of 100. "
                f"Consider the candidate's experience: \"{self.experience}\" and the target position: \"{self.position}\". "
                f"The scoring should primarily consider the '{self.position}' role. "
                f"Here are the questions and their corresponding answers:\n{json.dumps(prompt_relevant_answers, indent=2)}\n" + base_scoring_rules
            )
        else:
            scoring_prompt = (
                f"As a strict and unbiased AI interviewer, evaluate the candidate's performance for the \"{round_name}\" round out of 100. "
                f"Consider the candidate's experience: \"{self.experience}\" and the target position: \"{self.position}\". "
                f"Here are the questions and their corresponding answers:\n{json.dumps(prompt_relevant_answers, indent=2)}\n" + base_scoring_rules
            )

        print(f"\n[AI Scoring {round_name}" + (f" - {specialization}" if specialization else "") + (f" - {coding_stage}" if coding_stage else "") + "]...")
        response_text = call_llm_api(scoring_prompt, current_conversation_history=[], output_max_tokens=1500)

        # --- MODIFIED ERROR HANDLING FOR LLM RESPONSE PARSING ---
        scoring_results = None
        if response_text:
            # Attempt to extract JSON using regex first, in case of conversational filler
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            json_string = json_match.group(0) if json_match else response_text

            try:
                parsed_json = json.loads(json_string)
                # Ensure the parsed_json is a dictionary and has the expected top-level keys
                # AND ensure 'question_details' is a list
                if isinstance(parsed_json, dict) and \
                   'overall_score' in parsed_json and \
                   'round_summary' in parsed_json and \
                   'question_details' in parsed_json and \
                   isinstance(parsed_json['question_details'], list): 
                    scoring_results = parsed_json
                else:
                    print(f"Warning: LLM response for scoring did not match expected JSON structure. Raw: {json_string} | Parsed Type: {type(parsed_json)}")
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to decode JSON for scoring response: {e}. Raw: {json_string}")
            except Exception as e: # Catch any other unexpected parsing errors
                print(f"Unexpected error during JSON parsing for scoring: {e}. Raw: {json_string}")
        
        # If scoring_results is still None after attempts, create a default error structure
        if scoring_results is None:
            default_questions_for_report = []
            # Create default details based on original relevant_answers_for_scoring (which has speak_text)
            for ans in relevant_answers_for_scoring:
                default_questions_for_report.append({
                    "question_text": ans.get('question_text', 'N/A'),
                    "speak_text": ans.get('speak_text', ans.get('question_text', 'N/A')), # Use original speak_text
                    "score": 0,
                    "answer": ans.get('answer', '') # Keep answer in report for completeness
                })
            return {
                'overall_score': 0,
                'questions': default_questions_for_report, # Changed key
                'round_summary': f"Scoring failed for this round due to an issue with AI response parsing.",
            }
        # --- END MODIFIED ERROR HANDLING ---

        # Post-processing for stricter scoring and ensuring keys (only runs if scoring_results is valid dict)
        final_questions_for_report = [] # This will be the list for the report
        
        # Create a mapping from LLM's question text to its score/analysis
        # Use a normalized version of the question text as the key for matching
        llm_scored_questions_map = {}
        if isinstance(scoring_results.get('question_details'), list):
            for qa_detail_from_llm in scoring_results['question_details']:
                # Normalize the question text from LLM's response for robust matching
                normalized_llm_question = re.sub(r'\s+', ' ', qa_detail_from_llm.get('question', '').strip().lower())
                if normalized_llm_question:
                    llm_scored_questions_map[normalized_llm_question] = qa_detail_from_llm

        # Iterate through the original relevant_answers_for_scoring to build the final report structure
        # This ensures we use the original question_text and speak_text
        for original_qa_pair in relevant_answers_for_scoring:
            q_text = original_qa_pair.get('question_text', 'N/A')
            s_text = original_qa_pair.get('speak_text', self._get_speak_text_for_question_fallback(q_text, round_name, specialization, coding_stage))
            answer_text = original_qa_pair.get('answer', '')

            score = 0
            # Try to find the corresponding score from the LLM's response using normalized text
            normalized_original_question = re.sub(r'\s+', ' ', q_text.strip().lower())
            llm_score_detail = llm_scored_questions_map.get(normalized_original_question)

            if llm_score_detail:
                score = llm_score_detail.get('score', 0)
                llm_analysis = llm_score_detail.get('analysis', "N/A").lower()
                
                # Apply 0 score rule based on LLM's analysis
                if not answer_text or \
                   "no answer provided" in llm_analysis or \
                   "nonsensical" in llm_analysis or \
                   "off-topic" in llm_analysis or \
                   "irrelevant" in llm_analysis or \
                   "incorrect" in llm_analysis or \
                   "incomplete" in llm_analysis:
                    score = 0
            else:
                # If LLM didn't return a score for this specific question, default to 0
                print(f"WARNING: LLM did not provide score for question: '{q_text[:50]}...'. Defaulting to 0.")
                score = 0

            final_questions_for_report.append({
                "question_text": q_text,
                "speak_text": s_text,
                "score": score,
                "answer": answer_text # Keep answer in report for completeness
            })

        # Use final_questions_for_report for subsequent calculations
        total_score_sum = 0
        num_scored_questions = 0
        for qa_detail in final_questions_for_report: # USE THE PROCESSED LIST
            total_score_sum += qa_detail['score']
            num_scored_questions += 1
        
        # Recalculate overall_score based on adjusted individual scores
        if num_scored_questions > 0:
            scoring_results['overall_score'] = int(total_score_sum / num_scored_questions)
        else:
            scoring_results['overall_score'] = 0
        
        # Update question_details to match the desired output format (only question_text, speak_text, score)
        scoring_results['questions'] = final_questions_for_report # Changed from 'question_details' to 'questions'


        print(f"Scoring Results for {round_name}" + (f" - {specialization}" if specialization else "") + ":")
        print(f"  Overall Score: {scoring_results['overall_score']}")
        for qa in scoring_results.get('questions', []): # Changed from 'question_details' to 'questions'
            print(f"    Q: {qa.get('question_text')[:50]}...")
            print(f"    Score: {qa.get('score')}")
        return scoring_results

    def _get_speak_text_for_question_fallback(self, question_text, round_name, specialization=None, coding_stage=None):
        """
        Helper to reconstruct speak_text for a given question when original is not directly available.
        This is a fallback and should ideally be avoided by ensuring speak_text is always carried through.
        It now attempts to look up the original speak_text from the pre_generated_questions_data.
        """
        # Determine the correct question list to search in self.all_generated_questions
        questions_list = []
        if round_name == "coding" and coding_stage:
            questions_list = self.all_generated_questions.get("coding", {}).get(coding_stage, {}).get("questions", [])
        elif specialization:
            questions_list = self.all_generated_questions.get("technical", {}).get("specializations", {}).get(specialization, {}).get("questions", [])
        elif round_name in ["communication", "psychometric"]:
            questions_list = self.all_generated_questions.get(round_name, {}).get("questions", [])

        # Search for the question_text and return its speak_text if found
        # Normalize for matching
        normalized_question_text = re.sub(r'\s+', ' ', question_text.strip().lower())

        for q_dict in questions_list:
            if re.sub(r'\s+', ' ', q_dict.get("question_text", "").strip().lower()) == normalized_question_text:
                return q_dict.get("speak_text", question_text) # Return original speak_text if found

        # Fallback if not found in pre-generated questions
        if round_name == "coding" and coding_stage:
            stage_display_name = coding_stage.replace('_', ' ').title()
            return self.all_generated_questions["coding_question_intro_template"].format(number="?", stage_display_name=stage_display_name)
        elif round_name in ["communication", "psychometric", "technical"] or specialization:
            return f"Question ?: {question_text}" # General fallback for non-coding
        return question_text # Final fallback


    # MODIFIED: This function now only retrieves the question. The answer capture is moved to views.py
    def _process_single_question(self, round_name, question_index, specialization=None, coding_stage=None):
        """
        Retrieves a single question and its speak_text. Does NOT prompt for an answer.
        Returns the q_dict for the current question or None if invalid.
        """
        questions_for_round = []
        if round_name == "coding" and coding_stage:
            questions_for_round = self.all_generated_questions["coding"][coding_stage]["questions"]
        elif specialization:
            questions_for_round = self.all_generated_questions["technical"]["specializations"].get(specialization, {}).get("questions", [])
        else:
            questions_for_round = self.all_generated_questions[round_name]["questions"]

        # IMPORTANT: Ensure questions_for_round is not empty before accessing
        if not questions_for_round or question_index >= len(questions_for_round):
            print(f"ERROR: No valid question found for {round_name}" + (f" - {specialization}" if specialization else "") + (f" - {coding_stage}" if coding_stage else "") + f" at index {question_index}.")
            return None # Indicate no question processed

        q_dict = questions_for_round[question_index]
        question_text = q_dict["question_text"]
        speak_text_for_q = q_dict["speak_text"]

        display_round_name = round_name.replace('_', ' ').title()
        if specialization:
            display_round_name = specialization
        elif coding_stage:
            display_round_name = f"Coding - {coding_stage.replace('_', ' ').title()}"

        print(f"\n[AI]: {speak_text_for_q}")
        print(f"Question {question_index+1}: {question_text}")

        self._add_to_chat_history("model", question_text)

        if self._check_malpractice_status(self.read_malpractice_status_func):
            return None # Indicate malpractice

        # REMOVED: No longer calling listen_and_confirm_answer() here.
        # The answer will be provided externally by the API call in views.py.
        
        # Return the question details for views.py to handle the answer
        return {
            "question_text": question_text,
            "speak_text": speak_text_for_q
        }

    # NEW METHOD: To record the answer received from the API
    def record_answer(self, question_text, speak_text, answer_text):
        """
        Records a question and its corresponding answer into the all_interview_answers transcript.
        This method is called by views.py after receiving the answer from the frontend.
        """
        q_a_pair = {
            "question_text": question_text,
            "speak_text": speak_text,
            "answer": answer_text if answer_text else ""
        }
        self.all_interview_answers.append(q_a_pair)
        self._add_to_chat_history("user", answer_text if answer_text else "[No answer detected]")
        print(f"DEBUG: Recorded answer for question: '{question_text[:50]}...'")


    def run_interview(self, read_malpractice_status_func):
        """
        Runs the full interview process, including all rounds.
        This method is primarily for initial setup and final report generation.
        The actual question-by-question progression and scoring for each round
        will be managed by the views.py in response to submit_answer calls.
        """
        self.read_malpractice_status_func = read_malpractice_status_func # Store the function
        print(self.all_generated_questions["welcome_message"])
        speak_text(self.all_generated_questions["welcome_message"])

        # Add initial context to chat history
        initial_context = (
            f"Mock Interview for: {self.position} role.\n"
            f"Candidate's Experience: {self.experience}"
        )
        if self.aiml_specialization:
            initial_context += f"\nSpecific AIML Specialization for focus: {self.aiml_specialization}"
        self._add_to_chat_history("user", initial_context) # Use 'user' role for initial context setting

        # Try to load pre-generated questions from DB, otherwise generate them
        if self.mock_interview_db_instance and self.mock_interview_db_instance.pre_generated_questions_data:
            self.all_generated_questions = self.mock_interview_db_instance.pre_generated_questions_data
            print(f"[AI]: Loaded pre-generated questions from DB for interview ID: {self.mock_interview_db_instance.id}.")
            speak_text("Loaded pre-generated questions. Starting the interview now.")
            
            # Re-determine specializations from the loaded questions to ensure consistency
            # and include the user-provided AIML specialization
            self.technical_specializations = [] # Re-initialize to ensure a clean list
            if self.aiml_specialization: # Check if the list is not empty
                for spec in self.aiml_specialization:
                    if isinstance(spec, str) and spec.strip():
                        self.technical_specializations.append(spec.strip())

            if "technical" in self.all_generated_questions and "specializations" in self.all_generated_questions["technical"]:
                for spec_key in self.all_generated_questions["technical"]["specializations"].keys():
                    if spec_key not in self.technical_specializations:
                        self.technical_specializations.append(spec_key)
            
            # Ensure only top 3 specializations are kept
            self.technical_specializations = list(set(self.technical_specializations))[:3]
            print(f"Final determined technical specializations for interview: {self.technical_specializations}")

        else:
            print(f"No pre-generated questions found in DB for interview ID: {self.mock_interview_db_instance.id if self.mock_interview_db_instance else 'N/A'}. Generating new questions.")
            self._pre_generate_all_questions() # Generate if not found in DB

        if self.malpractice_detected: # Check if question generation failed
            return

        # Start the interview rounds
        print(self.all_generated_questions["interview_start_message_template"].format(position=self.position))
        speak_text(self.all_generated_questions["interview_start_message_template"].format(position=self.position))

        # The actual question progression and scoring will happen via API calls to submit_answer
        # This method primarily sets up the initial state and then hands off to the API.
        # It will only be responsible for the FINAL report generation once all rounds are implicitly completed.

    # UPDATED: This function now updates the MockInterviewResult instance directly
    def _generate_final_report(self):
        """
        Generates a comprehensive final report and saves it to the MockInterviewResult instance.
        """
        if not self.mock_interview_db_instance:
            print("Error: No MockInterviewResult instance provided to save the final report.")
            speak_text(self.all_generated_questions["error_report_save_message_template"])
            return

        from talent_management.models import MockInterviewResult # Import here to avoid circular dependency

        # Populate the database instance with final scores and analysis
        self.mock_interview_db_instance.global_readiness_score = self.global_readiness_score
        self.mock_interview_db_instance.language_proficiency_score = self.language_score
        self.mock_interview_db_instance.language_analysis = self.language_analysis
        self.mock_interview_db_instance.round_analysis_json = self.round_detailed_results # Store full detailed results

        # NEW: Save communication and psychometric overall scores
        self.mock_interview_db_instance.communication_overall_score = self.round_scores.get("communication", 0)
        self.mock_interview_db_instance.psychometric_overall_score = self.round_scores.get("psychometric", 0)
        
        # NEW: Save the structured AIML specializations (list of strings)
        # The model field is JSONField, so a list is fine.
        self.mock_interview_db_instance.aiml_specialization = self.technical_specializations 

        # NEW: Save the full Q&A transcript
        self.mock_interview_db_instance.full_qa_transcript = self.all_interview_answers

        # NEW: Save individual technical specialization scores
        self.mock_interview_db_instance.technical_specialization_scores = self.round_scores["technical"]

        self.mock_interview_db_instance.interview_end_time = timezone.now()
        self.mock_interview_db_instance.status = MockInterviewResult.InterviewStatus.COMPLETED
        
        try:
            self.mock_interview_db_instance.save()
            print(f"Final comprehensive interview report saved to database for interview ID: {self.mock_interview_db_instance.id}")
            # The frontend will fetch this via the report API.
            speak_text(self.all_generated_questions["final_report_saved_message_template"].format(report_filename=f"database record ID {self.mock_interview_db_instance.id}"))
        except Exception as e:
            print(f"Error: Could not save final interview report to database: {e}")
            speak_text(self.all_generated_questions["error_report_save_message_template"])


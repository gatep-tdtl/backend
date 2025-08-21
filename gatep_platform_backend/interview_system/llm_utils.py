# # llm_utils.py
# import requests
# import json
# # import config # Import config
# from . import config # Import config
# def call_llm_api(prompt_text, current_conversation_history=None, output_max_tokens=500):
#     """
#     Calls the OpenAI Chat Completions API with the given prompt and an optional conversation history.
#     Args:
#         prompt_text (str): The current user prompt to send to the LLM.
#         current_conversation_history (list, optional): A list of dictionaries representing the conversation history
#                                                       (internal format: {'role': 'user'/'model', 'parts': [{'text': '...'}]}).
#                                                       If None or empty, only the prompt_text is sent.
#         output_max_tokens (int): The maximum number of tokens the model should generate in its response.
#     Returns:
#         str: The generated text response from the AI, or None if an error occurs.
#     """
#     if not config.OPENAI_API_KEY:
#         print("Error: OPENAI_API_KEY environment variable is not set. Please set it before running.")
#         return None

#     # Convert internal chat_history format to OpenAI API 'messages' format
#     messages_for_api = []
#     if current_conversation_history:
#         for entry in current_conversation_history:
#             if "parts" in entry and len(entry["parts"]) > 0:
#                 # OpenAI expects 'user' and 'assistant' roles
#                 role = "user" if entry["role"] == "user" else "assistant"
#                 messages_for_api.append({"role": role, "content": entry["parts"][0]["text"]})

#     # Add the current user prompt
#     messages_for_api.append({"role": "user", "content": prompt_text})

#     payload = {
#         "model": config.OPENAI_MODEL_NAME,
#         "messages": messages_for_api,
#         "temperature": 0.7, # Adjust temperature for creativity/randomness
#         "max_tokens": output_max_tokens, # Use the dynamic max_tokens
#     }

#     headers = {
#         'Content-Type': 'application/json',
#         'Authorization': f'Bearer {config.OPENAI_API_KEY}'
#     }

#     print(f"\n[AI Processing with OpenAI ({config.OPENAI_MODEL_NAME})...]")
#     try:
#         response = requests.post(config.OPENAI_API_URL, headers=headers, json=payload)
#         response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

#         result = response.json()
#         if result and result.get('choices') and len(result['choices']) > 0 and \
#            result['choices'][0].get('message') and result['choices'][0]['message'].get('content'):
#             text_response = result['choices'][0]['message']['content']
#             return text_response
#         else:
#             print(f"Error: Unexpected API response structure or no content. Response: {result}")
#             return None
#     except requests.exceptions.RequestException as e:
#         print(f"Error calling OpenAI API: {e}")
#         return None
#     except json.JSONDecodeError as e:
#         print(f"Error decoding JSON response from API: {e}")
#         print(f"Response content: {response.text}")
#         return None





# llm_utils.py
import requests
import json
from .import config

def call_llm_api(prompt_text, current_conversation_history=None, output_max_tokens=500):
    if not config.OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY environment variable is not set. Please set it before running.")
        return None

    messages_for_api = []
    if current_conversation_history:
        for entry in current_conversation_history:
            if "parts" in entry and len(entry["parts"]) > 0:
                role = "user" if entry["role"] == "user" else "assistant"
                messages_for_api.append({"role": role, "content": entry["parts"][0]["text"]})
    messages_for_api.append({"role": "user", "content": prompt_text})

    payload = {
        "model": config.OPENAI_MODEL_NAME,
        "messages": messages_for_api,
        "temperature": 0.7,
        "max_tokens": output_max_tokens,
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {config.OPENAI_API_KEY}'
    }

    print(f"\n[AI Processing with OpenAI ({config.OPENAI_MODEL_NAME})...]")
    try:
        response = requests.post(config.OPENAI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        if (result and result.get('choices') and len(result['choices']) > 0 and 
           result['choices'][0].get('message') and result['choices'][0]['message'].get('content')):
            text_response = result['choices'][0]['message']['content']
            return text_response
        else:
            print(f"Error: Unexpected API response structure or no content. Response: {result}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling OpenAI API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from API: {e}")
        print(f"Response content: {response.text}")
        return None
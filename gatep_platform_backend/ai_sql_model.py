import json
import os
import uuid
import mysql.connector
from datetime import datetime, date
from groq import Groq
import re # Added for extracting location from user query
from decimal import Decimal
import sys # For exiting if critical environment variables are missing
language=input("Enter the language you prefer:")
# --- Configuration and Setup ---

# IMPORTANT: API keys and database credentials are hardcoded as per user request.
# In a production environment, these should be loaded from environment variables
# or a secure configuration management system.

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Groq client for conversational and tool use
groq_client = Groq(api_key=GROQ_API_KEY)

# Define dangerous SQL keywords for safety checks
DANGEROUS_KEYWORDS = ['UPDATE', 'DELETE', 'DROP', 'ALTER', 'INSERT', 'TRUNCATE', 'RENAME', 'CREATE', 'EXECUTE', 'CALL', 'GRANT', 'REVOKE']

# Define max history length and max tokens for history to prevent hitting token limits
# These values are approximate and may need tuning based on average message length
MAX_HISTORY_LENGTH = 5 # Reduced to keep fewer messages
MAX_TOKENS_FOR_HISTORY = 2000 # Reduced for a safer token limit

# --- Database Utility Functions ---

def get_db_schema(host, user, password, database, port):
    """
    Connects to the MySQL database and retrieves the schema (table names and their columns).
    This schema is crucial for the AI to understand the database structure.
    """
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=int(port)
        )
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()

        schema = {}
        for table in tables:
            table_name = table[0]
            try:
                cursor.execute(f"SHOW COLUMNS FROM `{table_name}`;") # Use backticks for table names
                columns = cursor.fetchall()
                schema[table_name] = [column[0] for column in columns]
            except mysql.connector.Error as e:
                print(f"Warning: Could not retrieve columns for table '{table_name}': {e}", file=sys.stderr)
                schema[table_name] = [] # Add empty list if columns can't be fetched

        cursor.close()
        connection.close()
        return schema
    except mysql.connector.Error as e:
        return {"error": f"Database schema retrieval error: {e}. Please check database connection and credentials."}
    except Exception as e:
        return {"error": f"An unexpected error occurred during schema retrieval: {e}"}

def get_sql_from_groq(prompt):
    """
    Sends a prompt to Groq specifically for SQL query generation.
    This is an internal helper for the tool function.
    """
    try:
        chat_completion = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": "You are an expert SQL query generator. Generate only safe SELECT queries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0 # Keep low for deterministic SQL
        )
        sql_query = chat_completion.choices[0].message.content.strip()
        # Ensure only the SQL query is returned, remove markdown if present
        if sql_query.startswith("```sql"):
            sql_query = sql_query.strip("```sql").strip("```").strip()
        return sql_query
    except Exception as e:
        return {"error": f"Groq SQL generation error: {e}. Check API key and network connection."}

def execute_sql(sql, host, user, password, database, port):
    """
    Executes a given SQL query on the specified MySQL database.
    Returns the fetched rows and column descriptions.
    """
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=int(port)
        )
        cursor = connection.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        description = cursor.description
        return rows, description
    except mysql.connector.Error as e:
        return {"error": f"SQL execution error: {e}. Query: '{sql}'"}, None
    except Exception as e:
        return {"error": f"An unexpected error occurred during SQL execution: {e}. Query: '{sql}'"}, None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_user_name(user_id, db_config):
    """
    Fetches the user's name from the database based on their user ID.
    Assumes a 'talent_management_customuser' table with 'id' and 'first_name' columns.
    Uses parameterized query to prevent SQL injection.
    """
    if user_id == "anonymous":
        return "Anonymous"

    host = db_config.get("HOST")
    user = db_config.get("USER")
    password = db_config.get("PASSWORD")
    database = db_config.get("NAME")
    port = db_config.get("PORT")

    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=int(port)
        )
        cursor = connection.cursor()
        # IMPORTANT: Use parameterized query to prevent SQL injection
        sql_query = "SELECT first_name FROM talent_management_customuser WHERE id = %s;"
        cursor.execute(sql_query, (user_id,)) # Pass user_id as a tuple for parameterization

        rows = cursor.fetchall()
        if rows and rows[0] and rows[0][0]:
            return str(rows[0][0]) # Convert to string in case it's not already
        else:
            return f"User {user_id}" # Fallback if name not found
    except mysql.connector.Error as e:
        print(f"Warning: Database error fetching user name for ID {user_id}: {e}", file=sys.stderr)
        return f"User {user_id}"
    except Exception as e:
        print(f"Warning: An unexpected error occurred fetching user name for ID {user_id}: {e}", file=sys.stderr)
        return {"error": f"An unexpected error occurred fetching user name: {e}"}
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_talent_profile(user_id, db_config):
    """
    Fetches the talent's profile information from the database.
    Attempts to retrieve common profile fields; adapts if some are missing.
    """
    host = db_config.get("HOST")
    user = db_config.get("USER")
    password = db_config.get("PASSWORD")
    database = db_config.get("NAME")
    port = int(db_config.get("PORT")) # Ensure port is int

    profile_data = {}
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        cursor = connection.cursor(dictionary=True) # Return rows as dictionaries
        # Fetch all columns from the resume table to be resilient to schema variations
        sql_query = """
            SELECT *
            FROM talent_management_resume
            WHERE talent_id_id = %s;
        """
        cursor.execute(sql_query, (user_id,))
        profile_row = cursor.fetchone()

        if profile_row:
            # Only include fields if they actually exist in the fetched row and are not None/empty
            if "preferred_tech_stack" in profile_row and profile_row["preferred_tech_stack"] is not None and profile_row["preferred_tech_stack"] != '':
                try:
                    # Attempt to parse as JSON array, then join to comma-separated string
                    parsed_tech_stack = json.loads(profile_row["preferred_tech_stack"])
                    if isinstance(parsed_tech_stack, list):
                        profile_data["preferred_tech_stack"] = ", ".join(parsed_tech_stack)
                    else:
                        profile_data["preferred_tech_stack"] = profile_row["preferred_tech_stack"]
                except json.JSONDecodeError:
                    profile_data["preferred_tech_stack"] = profile_row["preferred_tech_stack"] # Not JSON, keep as is

            if "current_location" in profile_row and profile_row["current_location"] is not None and profile_row["current_location"] != '':
                profile_data["current_location"] = profile_row["current_location"]

            if "skills" in profile_row and profile_row["skills"] is not None and profile_row["skills"] != '':
                try:
                    # Attempt to parse as JSON array, then join to comma-separated string
                    parsed_skills = json.loads(profile_row["skills"])
                    if isinstance(parsed_skills, list):
                        profile_data["skills"] = ", ".join(parsed_skills)
                    else:
                        profile_data["skills"] = profile_row["skills"] # Not JSON, keep as is
                except json.JSONDecodeError:
                    profile_data["skills"] = profile_row["skills"] # Not JSON, keep as is

            if "industry" in profile_row and profile_row["industry"] is not None and profile_row["industry"] != '':
                profile_data["industry"] = profile_row["industry"]
            if "experience_years" in profile_row and profile_row["experience_years"] is not None and profile_row["experience_years"] != '':
                profile_data["experience_years"] = profile_row["experience_years"]
            if "education_level" in profile_row and profile_row["education_level"] is not None and profile_row["education_level"] != '':
                profile_data["education_level"] = profile_row["education_level"]

        return profile_data
    except mysql.connector.Error as e:
        print(f"Warning: Database error fetching talent profile for ID {user_id}: {e}", file=sys.stderr)
        return {"error": f"Database error fetching talent profile: {e}"}
    except Exception as e:
        print(f"Warning: An unexpected error occurred fetching talent profile for ID {user_id}: {e}", file=sys.stderr)
        return {"error": f"An unexpected error occurred fetching talent profile: {e}"}
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


# --- Smart Conversational Bot Class ---

class SmartConversationalBot:
    """
    A smart conversational bot that can answer general questions and
    also fetch data from a MySQL database using SQL queries,
    with strict safety measures and user-role awareness.
    """
    def __init__(self, db_config):
        self.db_config = db_config
        self.chat_history = [] # To maintain conversation context

    def _get_data_from_database(self, user_query: str, user_id: str = None, user_role: str = None):
        """
        Internal tool function to generate and execute SQL queries.
        This function is called by the LLM when it determines a database query is needed.
        It encapsulates the schema retrieval, SQL generation, safety, and execution.
        """
        host = self.db_config.get("HOST")
        user = self.db_config.get("USER")
        password = self.db_config.get("PASSWORD")
        database = self.db_config.get("NAME")
        port = self.db_config.get("PORT")

        if not all([host, user, database, port]):
            return json.dumps({"error": "Database credentials (HOST, USER, PASSWORD, NAME, PORT) missing in configuration."})

        print(f"DEBUG: Attempting to retrieve DB schema for {database}...")
        # Get DB schema
        schema = get_db_schema(host, user, password, database, port)
        if "error" in schema:
            print(f"ERROR: Schema retrieval failed: {schema['error']}", file=sys.stderr)
            return json.dumps({"error": schema["error"]})

        schema_info = "\n".join([f"Table: `{table}`, Columns: {', '.join(columns)}" for table, columns in schema.items()])
        print(f"DEBUG: Retrieved schema: {schema_info[:200]}...") # Print first 200 chars

        talent_profile_info = {}
        talent_profile_str = 'No specific talent profile information available.'
        if user_role == 'TALENT' and user_id != 'anonymous':
            fetched_profile = get_talent_profile(user_id, self.db_config)
            if "error" in fetched_profile:
                print(f"ERROR: Talent profile retrieval failed: {fetched_profile['error']}", file=sys.stderr)
                # If there's an error fetching profile, talent_profile_info remains empty, and talent_profile_str remains default
            else:
                talent_profile_info = fetched_profile
                try:
                    profile_details = []
                    for k, v in talent_profile_info.items():
                        if v is not None and v != '': # Only include non-empty values
                            # Escape single quotes within values for SQL string literals
                            escaped_v = str(v).replace("'", "''")
                            profile_details.append(f'{k}: "{escaped_v}"')
                    if profile_details:
                        talent_profile_str = 'The talent\'s profile information is: {' + ', '.join(profile_details) + '}.'
                    else:
                        talent_profile_str = 'The talent\'s profile information is available but all fields are empty.'
                except Exception as e:
                    print(f"Warning: Could not stringify talent profile info for prompt: {e}", file=sys.stderr)
                    talent_profile_str = 'Error retrieving talent profile information.'

            print(f"DEBUG: Retrieved talent profile: {talent_profile_info}")


        # Construct prompt for SQL generation (internal to the tool)
        sql_gen_prompt = f"""
        You are an expert MySQL SELECT query generator.You have to conversate in '{language}' language. Your goal is to translate user questions into safe and accurate SQL queries based on the provided schema.

Database Schema:
{schema_info}

Current User Context:
- User ID: '{user_id if user_id else "anonymous"}'
- User Role: '{user_role if user_role else "anonymous"}'
- Talent Profile: {talent_profile_str}

SQL Generation Rules:
- Generate ONLY valid SELECT queries.
- DO NOT invent table/column names; use only those in the schema.
- AVOID DDL/DML statements (e.g., UPDATE, DELETE, DROP, INSERT).
- Respond with ONLY the SQL query, no explanations or markdown.
- Ensure MySQL syntax correctness.

Specific Query Handling:
1.  **User Profile**: For queries about the user's own profile (e.g., "my experience", "rate my profile"), query `talent_management_resume` using `talent_id_id = {user_id}`. Return all columns.
2.  **Skills for Role**: For skills needed for a role (e.g., "skills for data scientist"), query `employer_management_jobposting` for `required_skills`. Filter by keywords in `title`, `description`, or `requirements`.
3.  **Companies Hiring**: For companies hiring specific roles/locations (e.g., "AI companies in Bangalore"), JOIN `employer_management_jobposting` (jp) with `employer_management_company` (comp) on `jp.company_id = comp.id`. Select `DISTINCT comp.company_name`, `jp.title`, `jp.location`. Filter by role keywords in job fields and/or `jp.location LIKE '%<city>%'`.
4.  **General Job Postings**:
    * For "all job postings", use `SELECT * FROM employer_management_jobposting ORDER BY id DESC LIMIT 10;`.
    * For "jobs matching my profile" or "recommendations", use `talent_profile_info` to filter `employer_management_jobposting` by `preferred_tech_stack`, `skills`, `current_location`, and `experience_years` (mapping to `experience_level`). Apply `LIKE` conditions for text fields. Order by `id` DESC.

User question: {user_query}

        User question: {user_query}
        """
        print(f"DEBUG: Sending SQL generation prompt to Groq. Prompt length: {len(sql_gen_prompt)} chars.")
        sql_query = get_sql_from_groq(sql_gen_prompt)
        if isinstance(sql_query, dict) and "error" in sql_query:
            print(f"ERROR: SQL generation failed: {sql_query['error']}", file=sys.stderr)
            return json.dumps({"error": f"SQL generation failed: {sql_query['error']}"})

        print(f"DEBUG: Generated SQL: {sql_query}")

        # Safety filter
        if not sql_query.upper().startswith("SELECT"):
            print(f"SECURITY ALERT: Blocked non-SELECT query: {sql_query}", file=sys.stderr)
            return json.dumps({"error": "Blocked: Only SELECT queries are allowed."})
        if any(word in sql_query.upper() for word in DANGEROUS_KEYWORDS):
            print(f"SECURITY ALERT: Blocked query with forbidden keywords: {sql_query}", file=sys.stderr)
            return json.dumps({"error": "Blocked: Query contains forbidden keywords."})

        print(f"DEBUG: Executing SQL: {sql_query}")
        # Execute SQL
        query_result, description = execute_sql(sql_query, host, user, password, database, port)
        if isinstance(query_result, dict) and "error" in query_result:
            print(f"ERROR: SQL execution failed: {query_result['error']}", file=sys.stderr)
            return json.dumps({"error": f"SQL execution failed: {query_result['error']}"})

        # Format result
        formatted_result = []
        if description:
            column_names = [col_desc[0] for col_desc in description]
            for row in query_result:
                item = {}
                for col_name, value in zip(column_names, row):
                    if isinstance(value, (datetime, date)):
                        item[col_name] = value.isoformat()
                    elif isinstance(value, Decimal):
                        item[col_name] = float(value)
                    else:
                        item[col_name] = value
                formatted_result.append(item)

        print(f"DEBUG: Query result (first 5 rows): {formatted_result[:5]}")
        return json.dumps({
            "generated_sql": sql_query,
            "query_result": formatted_result,
            "message": "Data retrieved successfully."
        })
    

    def handle_conversation(self, user_query: str, user_id: str = None, user_role: str = None):
        """
        Handles the main conversational flow, deciding whether to respond directly
        or to call the database query tool.
        """
        # Add user query to chat history
        self.chat_history.append({"role": "user", "content": user_query})

        # --- History Management to prevent hitting token limits ---
        # Calculate current token usage for history (very rough estimate)
        history_tokens = sum(len(m['content'].split()) for m in self.chat_history if 'content' in m) # Count words as proxy for tokens

        # If history is too long or too many tokens, trim it
        if len(self.chat_history) > MAX_HISTORY_LENGTH or history_tokens > MAX_TOKENS_FOR_HISTORY:
            # Trim from the beginning until it fits
            while len(self.chat_history) > MAX_HISTORY_LENGTH or history_tokens > MAX_TOKENS_FOR_HISTORY:
                if len(self.chat_history) > 1: # Always keep at least the current turn
                    self.chat_history.pop(0)
                    history_tokens = sum(len(m['content'].split()) for m in self.chat_history if 'content' in m)
                else:
                    break # Cannot trim further if only one message
            print(f"DEBUG: Trimmed chat history. New length: {len(self.chat_history)}, Estimated tokens: {history_tokens} (after trimming)")
        # --- End History Management ---

        # Define the tool for the LLM
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_data_from_database",
                    "description": "Retrieve specific data from the MySQL database based on a natural language query. Use this for questions asking for lists, details, counts, or specific facts from the database (e.g., 'show me all employees', 'what are my tasks', 'how many jobs are posted').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_query": {
                                "type": "string",
                                "description": "The user's original natural language query that needs database access."
                            },
                            "user_id": {
                                "type": "string",
                                "description": "The ID of the current user. Pass None if the user is anonymous.",
                                "nullable": True
                            },
                            "user_role": {
                                "type": "string",
                                "description": "The role of the current user (e.g., 'ADMIN', 'EMPLOYER', 'TALENT'). Pass None if the user is anonymous.",
                                "nullable": True
                            }
                        },
                        "required": ["user_query"]
                    }
                }
            }
        ]

        # Prepare messages for the conversational LLM
        messages_for_llm = [
            {"role": "system", "content": f"""
            You are a helpful and smart conversational AI assistant for a talent management application.You respond in '{language}' language.
            You can answer general questions and also retrieve specific information from the database.
            Your current user's ID is '{user_id if user_id else "anonymous"}' and their role is '{user_role if user_role else "anonymous"}'.

            **Crucial Instruction for Database Queries:**
            If the user is a 'TALENT' and asks for job recommendations (e.g., "which job will suit my profile", "jobs matching my profile", "recommended jobs", "find jobs for me") OR if the user asks for information about their own profile (e.g., "how much will you rate my profile", "show me my profile", "what is my experience"), you MUST call the `get_data_from_database` tool. Pass the user's original query, user ID, and user role to the tool.

            For general conversational questions or if you cannot find relevant data in the database, respond conversationally.
            Always maintain a helpful and professional tone.
            Do not make up data. If you cannot find information, state that clearly.
            **Crucially, never suggest or mention any SQL operations that modify the database (like INSERT, UPDATE, DELETE, CREATE, DROP, etc.), even if a query returns no results.**
            """}
        ] + self.chat_history

        try:
            print("DEBUG: Sending conversational prompt to Groq (tool_choice auto)...")
            chat_completion = groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=messages_for_llm,
                tools=tools,
                tool_choice="auto", # Allow the LLM to decide whether to call a tool
                temperature=0.7 # Allow more creativity for conversation
            )

            response_message = chat_completion.choices[0].message
            self.chat_history.append(response_message) # Add AI's response to history

            if response_message.tool_calls:
                # The LLM wants to call a tool
                tool_call = response_message.tool_calls[0]
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                if function_name == "get_data_from_database":
                    print(f"\n--- AI Calling Tool: {function_name} with args: {function_args} ---")
                    # Call the internal tool function
                    tool_response_json = self._get_data_from_database(
                        user_query=function_args.get("user_query"),
                        user_id=user_id, # Pass actual user_id from context
                        user_role=user_role # Pass actual user_role from context
                    )
                    tool_response = json.loads(tool_response_json)
                    print(f"--- Tool Response: {tool_response} ---\n")

                    # Add tool response to history
                    self.chat_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_response_json,
                        }
                    )

                    print("DEBUG: Getting final conversational response from Groq based on tool output...")
                    # Get the final conversational response from the LLM based on tool output
                    final_response_completion = groq_client.chat.completions.create(
                        model="llama3-70b-8192",
                        messages=self.chat_history,
                        temperature=0.7
                    )
                    final_response_content = final_response_completion.choices[0].message.content

                    # Check if the tool output contained an error or no results
                    if "error" in tool_response:
                        final_response_content = (
                            f"I apologize, but I encountered an error when trying to retrieve that information from the database: "
                            f"{tool_response['error']}. Please try rephrasing your request or ask a different question."
                        )
                    elif not tool_response['query_result']: # Check if query_result is empty
                        generated_sql = tool_response['generated_sql'].lower()
                        if "select required_skills" in generated_sql and "from employer_management_jobposting" in generated_sql:
                            final_response_content = (
                                f"I couldn't find specific required skills for that role in the available job postings. "
                                f"This might be because there are no current postings for that exact role, or the skills are not explicitly listed. "
                                f"Would you like me to try searching for all available jobs, or perhaps refine your search with different criteria?"
                            )
                        elif "from employer_management_jobposting" in generated_sql and "distinct comp.company_name" in generated_sql:
                            # Check if the query specifically looked for a location
                            if "jp.location like" in generated_sql:
                                # Extract location from the original user query if possible, or use a generic phrase
                                import re
                                location_match = re.search(r"in\s+([a-zA-Z\s]+)", user_query, re.IGNORECASE)
                                location_name = location_match.group(1).strip() if location_match else "that specific location"
                                final_response_content = (
                                    f"I couldn't find any companies with job openings in {location_name} at the moment. "
                                    f"Would you like me to try searching for all available jobs, or perhaps broaden the search with different criteria?"
                                )
                            else:
                                final_response_content = (
                                    f"I couldn't find any companies hiring for that specific role at the moment. "
                                    f"Would you like me to try searching for all available jobs, or perhaps broaden the search with different criteria?"
                                )
                        elif "from employer_management_jobposting" in generated_sql:
                            final_response_content = (
                                f"I couldn't find any jobs matching your specific criteria in the database. "
                                f"Would you like me to try searching for all available jobs, "
                                f"or perhaps broaden the search with different criteria?"
                            )
                        else:
                            # Generic no results message for other query types
                            final_response_content = (
                                f"I couldn't find any information matching your request in the database. "
                                f"The query returned no results. Would you like me to try searching for all available jobs, "
                                f"or perhaps refine your search with different criteria?"
                            )
                    else:
                        # Determine the type of query result and format accordingly
                        generated_sql = tool_response['generated_sql'].lower()
                        query_result = tool_response['query_result']

                        if "from talent_management_resume" in generated_sql and query_result:
                            # This is a profile query
                            profile = query_result[0] # Assuming only one profile per user ID

                            # Construct a new prompt for the LLM to "rate" the profile
                            rating_prompt = f"""
                            You are an AI assistant specialized in career profiles.
                            The user has asked you to "rate their profile".
                            Here is the user's profile data retrieved from the database:
                            {json.dumps(profile, indent=2)}

                            Based on the completeness and content of this profile, provide a concise, encouraging, and helpful rating or evaluation.
                            Highlight strengths and suggest areas for improvement if applicable.
                            Do not use numerical ratings unless explicitly asked. Focus on qualitative assessment.
                            For example, if a profile has many skills, good experience, and a summary, you can say it's "strong" or "well-rounded."
                            If some key fields are missing (like LinkedIn, projects, or certifications), you can gently suggest adding them.
                            Keep the response conversational and professional.
                            """
                            print("DEBUG: Sending profile rating prompt to Groq...")
                            rating_completion = groq_client.chat.completions.create(
                                model="llama3-70b-8192",
                                messages=[
                                    {"role": "system", "content": rating_prompt}
                                ],
                                temperature=0.7
                            )
                            final_response_content = rating_completion.choices[0].message.content

                        elif "select required_skills" in generated_sql and "from employer_management_jobposting" in generated_sql and query_result:
                            # This is a query for skills needed for a specific role
                            all_skills = set()
                            for row in query_result:
                                skills_json = row.get('required_skills')
                                if skills_json:
                                    try:
                                        # Assuming required_skills is a JSON string of a list
                                        skills_list = json.loads(skills_json)
                                        if isinstance(skills_list, list):
                                            for skill in skills_list:
                                                all_skills.add(skill.strip())
                                    except json.JSONDecodeError:
                                        # If not JSON, treat as a single string and add
                                        all_skills.add(skills_json.strip())

                            if all_skills:
                                final_response_content = (
                                    f"Based on current job postings, to become a Computer Vision Engineer, "
                                    f"you would typically need skills such as: {', '.join(sorted(list(all_skills)))}.\n\n"
                                    f"It's always good to also have a strong foundation in related areas like "
                                    f"mathematics, statistics, and general programming."
                                )
                            else:
                                final_response_content = (
                                    f"I couldn't find specific required skills for a Computer Vision Engineer "
                                    f"in the available job postings. This might be because there are no "
                                    f"current postings for that exact role, or the skills are not explicitly listed. "
                                    f"Generally, Computer Vision roles often require strong skills in Python, "
                                    f"deep learning frameworks (like TensorFlow or PyTorch), image processing libraries (like OpenCV), "
                                    f"and a solid understanding of machine learning concepts."
                                )

                        elif "distinct comp.company_name" in generated_sql and "from employer_management_jobposting" in generated_sql and query_result:
                            # This is a query for companies hiring for specific roles
                            company_jobs = {}
                            for row in query_result:
                                company_name = row.get('company_name', 'Unknown Company')
                                job_title = row.get('title', 'Unknown Job Title')
                                job_location = row.get('location', 'Unknown Location')
                                if company_name not in company_jobs:
                                    company_jobs[company_name] = []
                                company_jobs[company_name].append(f"{job_title} ({job_location})")

                            response_lines = ["Here are some companies hiring for AI-related roles:"]
                            for company, jobs in company_jobs.items():
                                response_lines.append(f"\n**{company}** is hiring for:")
                                for job in jobs:
                                    response_lines.append(f"- {job}")
                            final_response_content = "\n".join(response_lines)
                            final_response_content += "\n\nLet me know if you'd like more details on any of these companies or jobs!"

                        elif "from employer_management_jobposting" in generated_sql:
                            # This is a general job posting query
                            job_list_items = []
                            for job in query_result:
                                title = job.get('title', 'N/A')
                                location = job.get('location', 'N/A')
                                description = job.get('description', 'N/A')
                                status = job.get('status', 'N/A')
                                job_list_items.append(
                                    f"- **Title**: {title}\n"
                                    f"  **Location**: {location}\n"
                                    f"  **Status**: {status}\n"
                                    f"  **Description**: {description[:100]}...\n" # Truncate description for brevity
                                )
                            job_list_str = "\n".join(job_list_items)
                            final_response_content = (
                                f"Here are some job postings I found:\n\n"
                                f"{job_list_str}\n\n"
                                f"Let me know if you'd like to see more details about a specific job or search for something else!"
                            )
                        else:
                            # Fallback for other query types or unexpected results
                            final_response_content = (
                                "I retrieved some data from the database, but I'm not sure how to best present it. "
                                "Here's the raw data for your reference:\n" + json.dumps(query_result, indent=2)
                            )


                    self.chat_history.append({"role": "assistant", "content": final_response_content})
                    return {"response": final_response_content, "tool_output": tool_response}
                else:
                    return {"response": "Sorry, I tried to use an unknown tool.", "tool_output": None}
            else:
                # The LLM responded conversationally
                self.chat_history.append({"role": "assistant", "content": response_message.content})
                return {"response": response_message.content, "tool_output": None}

        except json.JSONDecodeError as e:
            print(f"ERROR: JSON decoding error: {e}. Raw tool arguments: {tool_call.function.arguments}", file=sys.stderr)
            return {"response": f"An internal error occurred while processing the tool's arguments: {str(e)}", "tool_output": None}
        except Exception as e:
            print(f"ERROR: An unexpected error occurred in conversation: {e}", file=sys.stderr)
            return {"response": f"An error occurred: {str(e)}. Please try again.", "tool_output": None}

# --- New Function to Convert Response to JSON ---
def convert_response_to_json(response_data: dict) -> str:
    """
    Converts the bot's response dictionary into a formatted JSON string.

    Args:
        response_data (dict): The dictionary containing the bot's conversational
                              response and any tool output.

    Returns:
        str: A JSON string representation of the response_data.
    """
    try:
        # The 'tool_output' field is already a JSON string, so we need to parse it
        # back into a Python object before dumping the whole dictionary to JSON.
        # This ensures proper nesting and formatting of the tool output.
        if 'tool_output' in response_data and isinstance(response_data['tool_output'], str):
            try:
                response_data['tool_output'] = json.loads(response_data['tool_output'])
            except json.JSONDecodeError:
                # If tool_output is a string but not valid JSON, keep it as is
                pass
        return json.dumps(response_data, indent=2)
    except Exception as e:
        print(f"ERROR: Failed to convert response to JSON: {e}", file=sys.stderr)
        # Fallback if conversion fails, return a simple error JSON
        return json.dumps({"error": f"Failed to convert response to JSON: {str(e)}"}, indent=2)


# --- Main Execution Block ---

if __name__ == "__main__":
    # Database - Using user's provided values and explicit request
    DATABASE_CONFIG = {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'gatep_platform_db',
        'USER': 'dbmasteruser',
        'PASSWORD': 'database9014',
        'HOST': 'ls-f8259bafe38561c18d0d411f37aefbfabc0ff7bf.citdgny2wnek.ap-south-1.rds.amazonaws.com',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'"
        },
    }

    # Test database connection before starting the bot
    print("Attempting to connect to the database to verify credentials...")
    test_connection = None
    try:
        test_connection = mysql.connector.connect(
            host=DATABASE_CONFIG['HOST'],
            user=DATABASE_CONFIG['USER'],
            password=DATABASE_CONFIG['PASSWORD'],
            database=DATABASE_CONFIG['NAME'],
            port=int(DATABASE_CONFIG['PORT'])
        )
        print("Successfully connected to the database!")
        test_connection.close()
    except mysql.connector.Error as e:
        print(f"Error: Could not connect to the database. Please check your DB credentials and ensure MySQL server is running.", file=sys.stderr)
        print(f"MySQL Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during database connection test: {e}", file=sys.stderr)
        sys.exit(1)

    bot = SmartConversationalBot(DATABASE_CONFIG)

    # Initial user settings
    current_user_id = "2" # Changed from "3" to "2" as requested
    current_user_role = "TALENT" # Use uppercase for consistency as per prompt instructions

    # Fetch initial user name using the get_user_name function
    current_user_name = get_user_name(current_user_id, DATABASE_CONFIG)

    print("\n--- Gatep Personal Assistant ---")
    print(f"Hello {current_user_name}! I'm your Gatep Personal Assistant. How can I assist you today?") # Dynamic greeting
    print("Type 'exit' to quit.")
    print("Type 'clear' to clear chat history.")
    print("Type 'set user <id> <role>' to change user ID and role during the session.")
    print("Example: 'set user 2 TALENT' or 'set user anonymous ANONYMOUS'")
    print("--------------------------------")

    while True:
        # Update current_user_name in the loop to reflect any changes via 'set user'
        # This will re-fetch the name if user_id changes
        updated_user_name = get_user_name(current_user_id, DATABASE_CONFIG)
        if updated_user_name != current_user_name:
            current_user_name = updated_user_name
            print(f"Greeting updated: Hello {current_user_name}!")

        user_input = input(f"\n{current_user_name} ({current_user_role}): ").strip()
        # Corrected: Call translate_to_english as a function, not a method
        # user_input = translate_to_english(user_input)

        if user_input.lower() == 'exit':
            break
        elif user_input.lower() == 'clear':
            bot.chat_history = []
            print("Chat history cleared.")
            continue
        elif user_input.lower().startswith('set user '):
            parts = user_input.split(' ')
            if len(parts) == 4:
                new_user_id = parts[2]
                new_user_role = parts[3].upper() # Ensure role is uppercase
                current_user_id = new_user_id
                current_user_role = new_user_role
                print(f"User set to ID: '{current_user_id}', Role: '{current_user_role}'")
            else:
                print("Invalid 'set user' command. Use 'set user <id> <role>'.")
            continue

        response_data = bot.handle_conversation(user_input, current_user_id, current_user_role)

        print("\n--- Bot Response ---")
        print(f"Gatep Personal Assistant: {response_data['response']}")

        # Convert the entire response_data to JSON and print it
        json_output = convert_response_to_json(response_data)
        print("\n--- Full Bot Response (JSON) ---")
        print(json_output)
        print("----------------------")

    print("\nExiting Gatep Personal Assistant Test.")


def translate_to_english(user_input): # Changed parameter name from 'text' to 'user_input'
    prompt = f"Translate the following text to English:\n\n\"{user_input}\"" # Used user_input here

    response = groq_client.chat.completions.create(
        model="llama2-70b-4096",  # You can use llama3-70b-8192 if needed
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    translation = response.choices[0].message.content.strip()
    return translation

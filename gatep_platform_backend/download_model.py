# download_model.py
from transformers import AutoTokenizer, AutoModel
import os

# --- IMPORTANT ---
# Look inside your utils/ai_match.py file and find the exact model_id.
# Replace the line below with the correct one from your file.
# It is probably "sentence-transformers/all-MiniLM-L6-v2" or something similar.
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"  # <-- MAKE SURE THIS IS CORRECT

# This part of the code is needed to fix the SSL issue for this script too.
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context


print(f"--- Starting download for model: {MODEL_ID} ---")
print("This may take several minutes. Please be patient.")

# These two lines will download the model and save it to your computer.
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModel.from_pretrained(MODEL_ID)

print("\n--- ✅ SUCCESS! ---")
print("Model has been downloaded and saved successfully.")
print("You can now start your Django server.")
# speech_utils.py
import speech_recognition as sr # Speech-to-Text library
import pyttsx3 # Text-to-Speech library

# --- Speech Engine Initialization ---
# This block initializes the Text-to-Speech engine for the bot's voice.
try:
    engine = pyttsx3.init()
    # Set properties for a slow and clear voice
    engine.setProperty('rate', 150)  # Speed of speech (words per minute)
    engine.setProperty('volume', 1.0) # Volume (0.0 to 1.0)
    # Default voice will be used as language selection is removed
except Exception as e:
    print(f"Warning: Could not initialize pyttsx3 engine for Text-to-Speech: {e}")
    engine = None

# This block initializes the Speech-to-Text recognizer.
recognizer = sr.Recognizer()

def speak_text(text):
    """Converts text to speech using pyttsx3."""
    if engine:
        # Voice selection based on language is removed; default voice will be used.
        engine.say(text)
        engine.runAndWait()
    else:
        print(f"Bot says: {text}")

def listen_for_answer():
    """Listens for audio input from the microphone and converts it to text."""
    with sr.Microphone() as source:
        print("Listening for your answer...")
        speak_text("Please speak your answer now.")
        recognizer.adjust_for_ambient_noise(source) # Adjust for ambient noise
        recognizer.pause_threshold = 2  # Stop after 3 seconds of silence
        try:
            audio = recognizer.listen(source, timeout=4) # Wait up to 10 seconds to start speaking
            print("Recognizing...")
            text = recognizer.recognize_google(audio) # Using Google Web Speech API (default language)
            print(f"You said: {text}")
            return text
        except sr.WaitTimeoutError:
            print("No speech detected. Please try again.")
            speak_text("I didn't hear anything. Please try speaking again.")
            return None
        except sr.UnknownValueError:
            print("Could not understand audio.")
            speak_text("I'm sorry, I couldn't understand what you said. Please try again.")
            return None
        except sr.RequestError as e:
            print(f"Could not request results from Google Speech Recognition service; {e}")
            speak_text(f"Speech service error: {e}. Please check your internet connection.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during speech recognition: {e}")
            speak_text("An unexpected error occurred with speech recognition. Please try again.")
            return
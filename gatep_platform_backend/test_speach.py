import whisper

file_path = r"E:\TDTL Internship\gatep\delete_this_folder\backend\gatep_platform_backend\media\uploads\harvard.wav"

try:
    model = whisper.load_model("base")
    result = model.transcribe(file_path)
    print("Transcription:", result["text"])
except Exception as e:
    import traceback
    print("Error while transcribing:")
    traceback.print_exc()

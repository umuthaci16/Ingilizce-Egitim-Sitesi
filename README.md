Requirements
- Python 3.10+ recommended
- ffmpeg installed and in PATH (https://ffmpeg.org/download.html)
- On Windows, install matching PyTorch package for your system from https://pytorch.org/get-started/locally/

Quick start (Windows PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# If pip fails for torch, install torch separately per instructions on pytorch.org
# Ensure ffmpeg is on PATH (download the build and add its bin folder to PATH)
python app.py
```

Open http://127.0.0.1:5000 in your browser, allow microphone access, record and stop to upload and see the transcription (forced to English in the server code).


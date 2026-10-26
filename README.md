# SyncSpace

**SyncSpace** is an AI-powered desktop smart notepad and workspace application built with Python and Tkinter (`ttkbootstrap`). It brings together rich text editing, cloud synchronization via Google Drive, encrypted credential management, and local machine learning models for intelligent writing assistance.

---

## Features

- 📝 **Rich Text Editor**:
  - Full text manipulation: New, Open, Save, Cut, Copy, Paste, Find.
  - Image insertion directly into document canvas.
  - Custom font scaling (zoom in/out or select font size) and dynamic theme switching (Dark Mode / Light Mode / Custom color palettes).
  - One-click **PDF Export** with automatic layout formatting.

- ☁️ **Google Drive Cloud Sync**:
  - OAuth 2.0 Google Drive authorization.
  - Seamless file upload and download directly within the editor with integrated progress tracking.

- 🔒 **Encrypted Password Manager**:
  - Secure credential storage using Fernet symmetric encryption (`cryptography`).
  - Store and retrieve sensitive credentials locally with auto-generated encryption keys.

- 🤖 **AI & Writing Assistance**:
  - **Local Text Generation**: Integrated GPT-Neo causal language model for context-aware completion.
  - **Text Summarization**: T5 summarization model to generate concise abstracts from lengthy notes.
  - **Sentiment Analysis**: Transformer-based text classification with confidence scoring.
  - **Note Recommendations**: TF-IDF vectorization and Cosine Similarity to discover related notes.

- ✍️ **Grammar & Spell Checking**:
  - Integrated `language_tool_python` engine to highlight grammatical errors and suggest corrections inline.

---

## Requirements & Prerequisites

- **Python 3.10+** (Tested on Python 3.11)
- Java Runtime Environment (JRE) recommended for full `language_tool_python` offline engine support.

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/<your-username>/syncspace.git
   cd syncspace
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

### Google Drive Integration (Optional)
To enable Google Drive sync:
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Drive API**.
3. Create OAuth 2.0 Desktop Application credentials and download the client secret JSON.
4. Rename it to `bruh.json` (or `credentials.json`) and place it in the application root directory (see `bruh.example.json` for structure).

### Hugging Face Token (Optional)
To use Hugging Face hosted models:
```bash
# Windows PowerShell
$env:HUGGINGFACE_TOKEN = "your_hf_token_here"

# Linux / macOS
export HUGGINGFACE_TOKEN="your_hf_token_here"
```

---

## Running the Application

Launch the desktop interface:
```bash
python syncspace.py
```

---

## Project Structure

```
syncspace/
├── syncspace.py          # Main application entry point & GUI
├── requirements.txt      # Python dependencies
├── bruh.example.json     # Template for Google OAuth credentials
├── .gitignore            # Excludes venv, binaries, and private keys
└── README.md             # Project documentation
```

---

## License

This project is licensed under the MIT License.

import io
import json
import mimetypes
import os
import pickle
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from cryptography.fernet import Fernet
from fpdf import FPDF
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from huggingface_hub import login
import language_tool_python
from PIL import Image, ImageTk
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import ttkbootstrap as ttkb

# Asynchronously attempt Hugging Face login without blocking application startup
def _async_hf_login():
    token = os.getenv("HUGGINGFACE_TOKEN")
    if token:
        try:
            login(token)
            print("Hugging Face authenticated.")
        except Exception as e:
            print(f"Hugging Face login skipped or offline: {e}")

import threading
threading.Thread(target=_async_hf_login, daemon=True).start()


# ===================== RECOMMENDATION SYSTEM =====================
class RecommendationSystem:
    def __init__(self, notes):
        self.notes = notes
        self.vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=5000)
        self.tfidf_matrix = self.vectorizer.fit_transform(notes)

    def recommend(self, new_note, top_n=1):
        if not self.notes:
            return []
        new_note_tfidf = self.vectorizer.transform([new_note])
        similarity = cosine_similarity(new_note_tfidf, self.tfidf_matrix)
        top_indices = similarity.argsort()[0][-top_n:][::-1]
        return [self.notes[i] for i in top_indices]


# ===================== MODEL MANAGER (LAZY LOADING) =====================
class ModelManager:
    _text_generator = None
    _summarizer = None
    _sentiment_analyzer = None

    @classmethod
    def get_text_generator(cls):
        if cls._text_generator is None:
            print("Loading GPT-Neo model...")
            tokenizer = AutoTokenizer.from_pretrained("EleutherAI/gpt-neo-125M")
            model = AutoModelForCausalLM.from_pretrained("EleutherAI/gpt-neo-125M")
            cls._text_generator = pipeline("text-generation", model=model, tokenizer=tokenizer)
        return cls._text_generator

    @classmethod
    def get_summarizer(cls):
        if cls._summarizer is None:
            print("Loading T5 summarization model...")
            cls._summarizer = pipeline("summarization", model="t5-small")
        return cls._summarizer

    @classmethod
    def get_sentiment_analyzer(cls):
        if cls._sentiment_analyzer is None:
            print("Loading sentiment analysis model...")
            cls._sentiment_analyzer = pipeline("sentiment-analysis")
        return cls._sentiment_analyzer


# ===================== SENTIMENT ANALYZER =====================
class SentimentAnalyzer:
    def __init__(self):
        self._analyzer = None

    @property
    def analyzer(self):
        if self._analyzer is None:
            self._analyzer = ModelManager.get_sentiment_analyzer()
        return self._analyzer

    def analyze(self, text):
        result = self.analyzer(text)[0]
        label = result['label']
        score = result['score']
        return f"Sentiment: {label} (Confidence: {score:.2f})"


# ===================== PASSWORD MANAGER =====================
class PasswordManager:
    def __init__(self, filename='passwords.json', key_file='key.key'):
        self.filename = filename
        self.key_file = key_file
        self.key = self.load_key()
        self.fernet = Fernet(self.key)
        self.passwords = self.load_passwords()

    def load_key(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            return key

    def load_passwords(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    encrypted_data = f.read()
                    if not encrypted_data.strip():
                        return {}
                    decrypted_data = self.fernet.decrypt(encrypted_data.encode()).decode()
                    return json.loads(decrypted_data)
            except Exception as e:
                print(f"Error loading passwords: {e}")
                return {}
        return {}

    def save_passwords(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                encrypted_data = self.fernet.encrypt(json.dumps(self.passwords).encode()).decode()
                f.write(encrypted_data)
        except Exception as e:
            print(f"Error saving passwords: {e}")

    def add_password(self, site, password):
        self.passwords[site] = password
        self.save_passwords()

    def get_password(self, site):
        return self.passwords.get(site, None)


# ===================== GRAMMAR CHECKER =====================
class GrammarChecker:
    def __init__(self, text_widget, tool=None):
        self.text = text_widget
        self.tool = tool

    def get_tool(self):
        if self.tool is None:
            self.tool = language_tool_python.LanguageTool('en-US')
        return self.tool

    def check_grammar(self):
        tool = self.get_tool()
        text = self.text.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo("Grammar Check", "No text to check.")
            return

        matches = tool.check(text)
        self.text.tag_remove('error', '1.0', 'end')
        for match in matches:
            start = match.offset
            end = start + match.errorLength
            self.text.tag_add('error', f'1.0 + {start} chars', f'1.0 + {end} chars')

        self.text.tag_config('error', background='red', foreground='white')

        if matches:
            suggestions = "\n".join(f"- {m.message} (Suggestion: {', '.join(m.replacements[:3])})" for m in matches[:10])
            messagebox.showinfo("Grammar Check", f"Found {len(matches)} issues:\n\n{suggestions}")
        else:
            messagebox.showinfo("Grammar Check", "No grammatical errors found.")


# ===================== GOOGLE DRIVE HANDLER =====================
class GoogleDriveHandler:
    def __init__(self, progress_bar=None):
        self.drive_service = None
        self.progress = progress_bar
        self.creds = None

    def get_secrets_file(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, 'bruh.json'),
            os.path.join(script_dir, 'credentials.json'),
            'bruh.json',
            r'D:\syncspace\bruh.json'
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return 'bruh.json'

    def connect_to_drive(self):
        try:
            secrets_file = self.get_secrets_file()
            if not os.path.exists(secrets_file):
                messagebox.showerror(
                    "Connection Error",
                    f"OAuth credentials file not found.\nPlease place 'bruh.json' or 'credentials.json' in: {os.path.dirname(os.path.abspath(__file__))}"
                )
                return

            flow = InstalledAppFlow.from_client_secrets_file(
                secrets_file,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            creds = flow.run_local_server(port=0)
            self.creds = creds
            self.drive_service = build('drive', 'v3', credentials=creds)
            user_info = self.drive_service.about().get(fields='user(emailAddress)').execute()
            user_email = user_info.get('user', {}).get('emailAddress', 'Unknown')
            messagebox.showinfo("Connection Successful", f"Connected to Drive as: {user_email}")
        except Exception as e:
            messagebox.showerror("Connection Error", f"An error occurred: {e}")

    def upload_to_drive(self):
        if not self.drive_service:
            messagebox.showwarning("Upload Error", "You must be connected to Google Drive first.")
            return

        file_path = filedialog.askopenfilename(title="Select a file to upload")
        if not file_path:
            return

        file_name = os.path.basename(file_path)
        file_metadata = {'name': file_name}
        mime, _ = mimetypes.guess_type(file_path)
        if not mime:
            mime = 'application/octet-stream'

        media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

        if self.progress:
            self.progress.pack(pady=10)
            self.progress.start()
            self.progress['value'] = 0

        try:
            request = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id')
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status and self.progress:
                    self.progress['value'] = int(status.progress() * 100)

            messagebox.showinfo("Upload Successful", f"File uploaded successfully.\nFile ID: {response.get('id')}")
        except Exception as e:
            messagebox.showerror("Upload Error", f"An error occurred: {e}")
        finally:
            if self.progress:
                self.progress.stop()
                self.progress.pack_forget()

    def download_from_drive(self):
        if not self.drive_service:
            messagebox.showwarning("Warning", "You must connect to Drive first.")
            return

        file_id = simpledialog.askstring("Download", "Enter the file ID to download:")
        if not file_id:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Documents", "*.txt"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        if self.progress:
            self.progress.pack(pady=10)
            self.progress.start()
            self.progress['value'] = 0

        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            with io.FileIO(file_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status and self.progress:
                        self.progress['value'] = int(status.progress() * 100)

            messagebox.showinfo("Download Successful", f"File downloaded successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Download Error", f"An error occurred: {e}")
        finally:
            if self.progress:
                self.progress.stop()
                self.progress.pack_forget()


# ===================== MAIN GUI APPLICATION =====================
class SYNCSPACE(ttkb.Window):
    def __init__(self, *args, **kwargs):
        super().__init__(themename="darkly", *args, **kwargs)
        self.title("SYNCSPACE")
        self.geometry("1200x800")

        # Color defaults
        self.bg_color = "#1e1e1e"
        self.fg_color = "#ffff66"

        # Sample notes for recommendation
        self.notes = [
            "Python is great for data science.",
            "I love coding in Python.",
            "Machine learning is amazing."
        ]
        self.recommender = RecommendationSystem(self.notes)

        # Main text widget with scrollbar
        self.text = tk.Text(self, wrap="word", font=("Arial", 12), bg=self.bg_color, fg=self.fg_color)
        self.scroll = ttk.Scrollbar(self, command=self.text.yview)
        self.text.config(yscrollcommand=self.scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        # Progress bar
        self.progress = ttk.Progressbar(self, orient="horizontal", length=300, mode="determinate")

        # Handlers and helper classes
        self.password_manager = PasswordManager()
        self.drive_handler = GoogleDriveHandler(progress_bar=self.progress)
        self.grammar_checker = GrammarChecker(self.text)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.images = []

        # Context menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Insert Image", command=self.insert_image)
        self.text.bind("<Button-3>", self.show_context_menu)

        # Build application menu bar
        self.create_all_menus()

    def create_all_menus(self):
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)

        # File Menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_file)
        file_menu.add_command(label="Open", command=self.open_file)
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_command(label="Export as PDF", command=self.export_as_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="Logout", command=self.logout)
        file_menu.add_command(label="Exit", command=self.quit)

        # Edit Menu
        edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Cut", command=self.cut)
        edit_menu.add_command(label="Copy", command=self.copy)
        edit_menu.add_command(label="Paste", command=self.paste)
        edit_menu.add_command(label="Find", command=self.find)
        edit_menu.add_command(label="Check Grammar", command=self.check_grammar)

        # View Menu
        view_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Light Mode", command=self.light_mode)
        view_menu.add_command(label="Dark Mode", command=self.dark_mode)
        view_menu.add_command(label="Zoom In", command=self.zoom_in)
        view_menu.add_command(label="Zoom Out", command=self.zoom_out)
        view_menu.add_separator()

        font_size_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Font Size", menu=font_size_menu)
        for size in range(8, 40, 2):
            font_size_menu.add_command(label=str(size), command=lambda s=size: self.change_font_size(s))

        view_menu.add_command(label="Text Color", command=self.change_text_color)

        # Drive Menu
        drive_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Drive", menu=drive_menu)
        drive_menu.add_command(label="Connect to Drive", command=self.connect_to_drive)
        drive_menu.add_command(label="Upload to Drive", command=self.upload_to_drive)
        drive_menu.add_command(label="Download from Drive", command=self.download_from_drive)

        # Password Manager Menu
        password_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Password Manager", menu=password_menu)
        password_menu.add_command(label="Add Password", command=self.add_password)
        password_menu.add_command(label="Retrieve Password", command=self.retrieve_password)

        # AI Features Menu
        ai_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="AI Features", menu=ai_menu)
        ai_menu.add_command(label="Generate Text", command=self.generate_text_local)
        ai_menu.add_command(label="Summarize Text", command=self.summarize_text)
        ai_menu.add_command(label="Analyze Sentiment", command=self.analyze_sentiment)
        ai_menu.add_command(label="Get Recommendation", command=self.get_recommendation)

        # Settings Menu
        settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Customize Colors", command=self.customize_colors)

        # Grammar Check Menu
        grammar_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_bar.add_cascade(label="Grammar Check", menu=grammar_menu)
        grammar_menu.add_command(label="Check Grammar", command=self.check_grammar)

    # ----------------- AI & Recommendations -----------------
    def get_recommendation(self):
        new_note = simpledialog.askstring("Recommendation", "Enter your note to get a recommendation:")
        if new_note and new_note.strip():
            recommendations = self.recommender.recommend(new_note, top_n=2)
            rec_text = "\n\n".join(recommendations)
            messagebox.showinfo("Recommended Note", f"Recommended note(s):\n\n{rec_text}")
        else:
            messagebox.showwarning("Warning", "Please enter a note to get a recommendation.")

    def analyze_sentiment(self):
        text = self.text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter some text to analyze.")
            return
        try:
            result = self.sentiment_analyzer.analyze(text)
            messagebox.showinfo("Sentiment Analysis Result", result)
        except Exception as e:
            messagebox.showerror("Sentiment Analysis Error", f"An error occurred: {e}")

    def summarize_text(self):
        text = self.text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter text to summarize.")
            return

        try:
            summarizer = ModelManager.get_summarizer()
            result = summarizer(text, max_length=150, min_length=30, do_sample=False)[0]['summary_text']
            self.text.insert(tk.END, "\n\n--- Summary ---\n" + result + "\n")
        except Exception as e:
            messagebox.showerror("Summarization Error", f"An error occurred: {e}")

    def generate_text_local(self):
        prompt = simpledialog.askstring("Generate Text", "Enter a prompt:")
        if not prompt or not prompt.strip():
            return

        try:
            text_generator = ModelManager.get_text_generator()
            result = text_generator(
                prompt,
                max_new_tokens=150,
                temperature=0.7,
                top_k=50,
                top_p=0.9,
                repetition_penalty=1.5,
                num_return_sequences=1,
                truncation=True,
                do_sample=True,
                return_full_text=False,
                pad_token_id=50256
            )

            if isinstance(result, list) and len(result) > 0:
                generated_text = result[0].get("generated_text", "")
            elif isinstance(result, dict):
                generated_text = result.get("generated_text", "")
            else:
                generated_text = str(result)

            if "\n\n" in generated_text:
                generated_text = generated_text.split("\n\n")[0]
            if "<|endoftext|>" in generated_text:
                generated_text = generated_text.split("<|endoftext|>")[0]

            if generated_text:
                self.text.insert(tk.END, "\n" + generated_text + "\n")
            else:
                messagebox.showwarning("Warning", "No text was generated. Try a different prompt.")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    # ----------------- File Operations -----------------
    def new_file(self):
        self.text.delete("1.0", "end")
        self.title("SYNCSPACE")

    def open_file(self):
        file = filedialog.askopenfile(parent=self, mode="r", encoding="utf-8", errors="replace", title="Open a file")
        if file:
            contents = file.read()
            self.text.delete("1.0", "end")
            self.text.insert("1.0", contents)
            self.title(os.path.basename(file.name) + " - SYNCSPACE")
            file.close()

    def save_file(self):
        file = filedialog.asksaveasfile(
            mode="w",
            encoding="utf-8",
            defaultextension=".txt",
            filetypes=[("Text Documents", "*.txt"), ("All Files", "*.*")]
        )
        if file:
            contents = self.text.get("1.0", "end-1c")
            file.write(contents)
            self.title(os.path.basename(file.name) + " - SYNCSPACE")
            file.close()

    def txt_to_pdf(self, txt_content, pdf_filename):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)

        for line in txt_content.splitlines():
            clean_line = line.encode('latin-1', 'replace').decode('latin-1')
            pdf.cell(0, 10, text=clean_line, new_x="LMARGIN", new_y="NEXT")

        pdf.output(pdf_filename)

    def export_as_pdf(self):
        text_content = self.text.get("1.0", "end-1c")
        if not text_content.strip():
            messagebox.showwarning("Warning", "There is no text to export.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")]
        )
        if file_path:
            try:
                self.txt_to_pdf(text_content, file_path)
                messagebox.showinfo("Success", f"PDF saved as:\n{file_path}")
            except Exception as e:
                messagebox.showerror("PDF Export Error", f"An error occurred: {e}")

    # ----------------- Edit Operations -----------------
    def cut(self):
        self.text.event_generate("<<Cut>>")

    def copy(self):
        self.text.event_generate("<<Copy>>")

    def paste(self):
        self.text.event_generate("<<Paste>>")

    def find(self):
        find_str = simpledialog.askstring("Find", "Enter text to find:")
        if find_str:
            self.text.tag_remove('found', '1.0', tk.END)
            self.text.tag_config('found', background='yellow', foreground='black')
            start = '1.0'
            while True:
                start = self.text.search(find_str, start, stopindex=tk.END)
                if not start:
                    break
                lastidx = f"{start}+{len(find_str)}c"
                self.text.tag_add('found', start, lastidx)
                start = lastidx

    def check_grammar(self):
        self.grammar_checker.check_grammar()

    # ----------------- View Operations -----------------
    def light_mode(self):
        self.bg_color = "white"
        self.fg_color = "black"
        self.apply_custom_colors()

    def dark_mode(self):
        self.bg_color = "#1e1e1e"
        self.fg_color = "#ffff66"
        self.apply_custom_colors()

    def zoom_in(self, event=None):
        current_font = self.text.cget('font').split()
        size = int(current_font[1]) if len(current_font) > 1 else 12
        self.text.config(font=("Arial", size + 2))

    def zoom_out(self, event=None):
        current_font = self.text.cget('font').split()
        size = int(current_font[1]) if len(current_font) > 1 else 12
        if size > 8:
            self.text.config(font=("Arial", size - 2))

    def change_font_size(self, size):
        self.text.config(font=("Arial", int(size)))

    def change_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color")[1]
        if color:
            self.fg_color = color
            self.apply_custom_colors()

    def customize_colors(self):
        bg = colorchooser.askcolor(title="Select Background Color")[1]
        fg = colorchooser.askcolor(title="Select Text Color")[1]
        if bg and fg:
            self.bg_color = bg
            self.fg_color = fg
            self.apply_custom_colors()

    def apply_custom_colors(self):
        self.text.config(bg=self.bg_color, fg=self.fg_color)
        self.config(bg=self.bg_color)

    def show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    def insert_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.gif")])
        if not file_path:
            return

        try:
            image = Image.open(file_path)
            image.thumbnail((250, 250))
            photo = ImageTk.PhotoImage(image)

            image_label = tk.Label(self.text, image=photo, bg=self.bg_color)
            image_label.image = photo
            self.images.append(photo)

            self.text.window_create(tk.END, window=image_label)
            self.text.insert(tk.END, '\n')
        except Exception as e:
            messagebox.showerror("Image Insertion Error", f"An error occurred: {e}")

    # ----------------- Drive Operations -----------------
    def connect_to_drive(self):
        self.drive_handler.connect_to_drive()

    def upload_to_drive(self):
        self.drive_handler.upload_to_drive()

    def download_from_drive(self):
        self.drive_handler.download_from_drive()

    # ----------------- Password Operations -----------------
    def add_password(self):
        site = simpledialog.askstring("Add Password", "Enter the site or service name:")
        password = simpledialog.askstring("Add Password", "Enter the password:")
        if site and password:
            self.password_manager.add_password(site, password)
            messagebox.showinfo("Password Manager", f"Password saved for: {site}")

    def retrieve_password(self):
        site = simpledialog.askstring("Retrieve Password", "Enter the site or service name:")
        if site:
            password = self.password_manager.get_password(site)
            if password:
                messagebox.showinfo("Password Manager", f"Password for {site}:\n{password}")
            else:
                messagebox.showwarning("Password Not Found", f"No password found for: {site}")

    def logout(self):
        messagebox.showinfo("Logout", "You have successfully logged out.")
        self.quit()


# ===================== AI CLASS FOR BACKWARD COMPATIBILITY =====================
class AI:
    def __init__(self, text_widget=None):
        self.text = text_widget
        self._generator = None

    @property
    def generator(self):
        if self._generator is None:
            self._generator = ModelManager.get_text_generator()
        return self._generator

    def summarize(self):
        if not self.text:
            return
        text = self.text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter text to summarize.")
            return

        try:
            summarizer = ModelManager.get_summarizer()
            summary = summarizer(text, max_length=100, min_length=30, do_sample=False)
            if isinstance(summary, list) and len(summary) > 0:
                summary_text = summary[0].get('summary_text', '')
            elif isinstance(summary, dict):
                summary_text = summary.get('summary_text', '')
            else:
                summary_text = str(summary)
            self.text.insert(tk.END, "\n\nSummary:\n" + summary_text)
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def generate(self, prompt, max_length=50):
        result = self.generator(prompt, max_length=max_length, num_return_sequences=1)
        return result[0]['generated_text']


if __name__ == "__main__":
    app = SYNCSPACE()
    app.mainloop()

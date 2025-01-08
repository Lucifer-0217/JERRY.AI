import os
import sounddevice as sd
import queue
import threading
import json
import sqlite3
import subprocess
import struct
from vosk import Model, KaldiRecognizer
from llama_index import ServiceContext, GPTSimpleVectorIndex
from llama_index import Document
from TTS.api import TTS
from pvporcupine import create as porcupine_create
from googletrans import Translator
import mysql.connector
import tkinter as tk
from tkinter import messagebox
import time

# --- Vosk Speech-to-Text Setup ---
model = Model("model")  # Vosk model path
recognizer = KaldiRecognizer(model, 16000)
audio_queue = queue.Queue()


# Audio Callback for Vosk
def callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(bytes(indata))


# --- Llama NLP Setup ---
llama_api_key = "your_llama_api_key"  # Replace with your Llama API key
llama_api_url = "your_llama_api_url"  # Replace with your Llama API URL
service_context = ServiceContext.from_defaults(api_key=llama_api_key, api_url=llama_api_url)


# --- Coqui TTS Setup ---
tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)

# --- Google Translate Setup ---
translator = Translator()


# --- SQLite Database Setup for Reminders ---
def create_reminder_db():
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (task TEXT, time TEXT)''')
    conn.commit()
    conn.close()


def add_reminder(task, time):
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("INSERT INTO reminders (task, time) VALUES (?, ?)", (task, time))
    conn.commit()
    conn.close()


def check_reminders():
    conn = sqlite3.connect('reminders.db')
    c = conn.cursor()
    c.execute("SELECT * FROM reminders")
    reminders = c.fetchall()
    conn.close()
    return reminders


# --- SQLite Database Setup for Memory ---
def create_memory_db():
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()


def save_to_memory(key, value):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO memory (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def retrieve_from_memory(key):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute("SELECT value FROM memory WHERE key=?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


# --- Function to Detect Wake Word using Porcupine ---
def wake_word_detection():
    porcupine = porcupine_create(keywords=["jerry"])  # Set "Jerry AI" as wake word
    with sd.RawInputStream(samplerate=16000, blocksize=512, dtype='int16', channels=1) as stream:
        while True:
            pcm = stream.read(512)[0]
            pcm = struct.unpack_from("h" * 512, pcm)
            if porcupine.process(pcm) >= 0:
                print("Wake word 'Jerry AI' detected!")
                return True


# --- Function to Convert Speech to Text ---
def listen_to_user():
    print("Listening...")
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                           channels=1, callback=callback):
        while True:
            data = audio_queue.get()
            if recognizer.AcceptWaveform(data):
                result = recognizer.Result()
                result = json.loads(result)
                if result['text']:
                    return result['text']


# --- Function to Process User Input through Llama API ---
def get_response_from_llama(user_input, context=None):
    response = service_context.query(user_input)  # Use Llama API query method
    return response.response


# --- Function to Convert Text to Speech ---
def speak_response(response_text):
    tts.tts_to_file(text=response_text, file_path="response.wav")
    os.system("aplay response.wav")


# --- Code Generation and Execution Functions ---
def create_code_file(language, code):
    extension_mapping = {
        "c": "program.c",
        "cpp": "program.cpp",
        "python": "program.py",
        "java": "Program.java",
        "php": "program.php"
    }
    file_name = extension_mapping.get(language.lower())
    if file_name:
        with open(file_name, 'w') as file:
            file.write(code)
        print(f"{language} code saved in {file_name}")
    else:
        print("Unsupported language")


def execute_code(language):
    if language.lower() == "python":
        subprocess.run(["python3", "program.py"])
    elif language.lower() == "c":
        subprocess.run(["gcc", "program.c", "-o", "program"])
        subprocess.run(["./program"])
    elif language.lower() == "cpp":
        subprocess.run(["g++", "program.cpp", "-o", "program"])
        subprocess.run(["./program"])
    elif language.lower() == "java":
        subprocess.run(["javac", "Program.java"])
        subprocess.run(["java", "Program"])
    elif language.lower() == "php":
        subprocess.run(["php", "program.php"])
    else:
        print("Unsupported language")


def connect_to_mysql():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="your_password",
        database="your_database"
    )
    return conn


def run_mysql_query(query):
    conn = connect_to_mysql()
    cursor = conn.cursor()
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result


# --- GUI Code ---
def send_command():
    user_input = input_entry.get()
    input_entry.delete(0, tk.END)
    print(f"You said: {user_input}")

    # Memory interaction
    if "remember" in user_input:
        parts = user_input.split("remember")
        if len(parts) > 1:
            key_value = parts[1].strip().split("as")
            if len(key_value) == 2:
                key = key_value[1].strip()
                value = key_value[0].strip()
                save_to_memory(key, value)
                output_label.config(text=f"Remembered: {key} as {value}")

    elif "what do you remember about" in user_input:
        key = user_input.split("about")[-1].strip()
        value = retrieve_from_memory(key)
        if value:
            output_label.config(text=f"I remember {key} as {value}.")
        else:
            output_label.config(text=f"I don't remember anything about {key}.")

    elif "shutdown" in user_input:
        output_label.config(text="Shutting down the assistant.")
        root.quit()

    else:
        response = get_response_from_llama(user_input)  # Get response from Llama
        output_label.config(text=f"Assistant: {response}")
        speak_response(response)  # Text-to-Speech


# Initialize the main window
root = tk.Tk()
root.title("Voice Assistant")

# Input field for user commands
input_entry = tk.Entry(root, width=50)
input_entry.pack(pady=20)

# Button to send command
send_button = tk.Button(root, text="Send", command=send_command)
send_button.pack(pady=10)

# Label to display the assistant's response
output_label = tk.Label(root, text="", wraplength=400)
output_label.pack(pady=20)

# Start the assistant in a separate thread
threading.Thread(target=voice_assistant, daemon=True).start()

# Start the GUI loop
root.mainloop()

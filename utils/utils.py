import os
import json
import re
import uuid
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging
from pydub import AudioSegment
import os
import openai
import time
import azure.cognitiveservices.speech as speechsdk
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
import azure.cognitiveservices.speech as speechsdk

# Constants for file paths
EXTRACTED_TEXT_FILE = Path('text_files') / 'extracted_text.txt'
CONVERSATION_FILE = Path('text_files') / 'conversation.txt'

# Set up OpenAI authentication once in utils.py
openai.api_type = "azure"
openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
MODEL_NAME = os.getenv("AZURE_OPENAI_MODEL_NAME")

# Initialize Azure Document Intelligence client
try:
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint=os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT"),
        credential=AzureKeyCredential(os.getenv("DOCUMENTINTELLIGENCE_API_KEY"))
    )
    if not os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT") or not os.getenv("DOCUMENTINTELLIGENCE_API_KEY"):
        raise ValueError("Azure Document Intelligence configuration is incomplete.")
except Exception as e:
    print(f"Error initializing Azure Document Intelligence client: {e}")
    document_intelligence_client = None

# Initialize Azure Speech Service config
try:
    speech_config = speechsdk.SpeechConfig(subscription=os.getenv("SPEECH_KEY_NEW"), region="swedencentral") #
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

except Exception as e:
    print(f"Error initializing Azure Speech Service config: {e}")
    speech_config = None

if not all([openai.api_base, openai.api_version, openai.api_key, MODEL_NAME]):
    raise ValueError("Azure OpenAI configuration is incomplete.")

def generate_conversation(text_content, process_id):
    """Generates a conversation using OpenAI's chat completion."""
    conversation_file = f"static/conversations/conversation_{process_id}.txt"
    prompt = f"""
    Generate a podcast conversation between two speakers discussing the following content:
    {text_content}

    The podcast should be brief and start with a quick introduction to the topic.
    Then, the two speakers should have a lively discussion covering the most important points.
    The two speakers should have different speaking styles.

    Provide the conversation in the following format:

    **Speaker1:** [Speaker 1's dialogue]
    **Speaker2:** [Speaker 2's dialogue]

    Keep each speaker's part short, so that speakers often switch.
    Do not give the Speakers any names. Use "Speaker1" and "Speaker2" as placeholders.
    Ensure the total length is within 15000 tokens.
    """

    try:
        response = openai.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a podcast script generator."},
                {"role": "user", "content": prompt}
            ]
        )
        conversation = response.choices[0].message.content.strip()
        print("Conversation generated by OpenAI.")
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None

    # Save conversation to file with timestamp
    try:
        with open(conversation_file, "w", encoding='utf-8') as f:
            f.write(conversation)
        print(f"Conversation saved to {conversation_file}")
    except Exception as e:
        print(f"Failed to save conversation file: {e}")
        return None

    return conversation

def extract_text_from_pdf(pdf_path):
    if not document_intelligence_client:
        print("Document Intelligence client is not initialized.")
        return ''

    print("Extracting text with Azure Document Intelligence")
    try:
        with open(pdf_path, "rb") as f:
            poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-layout", analyze_request=f, content_type="application/octet-stream"
            )
        result: AnalyzeResult = poller.result()
        # operation_id = poller.details["operation_id"]

        extracted_text = ''

        for page in result.pages:
            for line in page.lines:
                print(line.content)
                extracted_text += line.content + ' '

        print("Text extracted from PDF successfully.")
        return extracted_text.strip()
    except FileNotFoundError:
        print(f"PDF file not found at {pdf_path}.")
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
    return ''

def extract_text_from_pdf_pypdf2(pdf_path):
    """Extracts text from a PDF file using PyPDF2 as a fallback method."""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        print("Text extracted from PDF successfully using PyPDF2.")
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF using PyPDF2: {e}")
        return ''
    

def extract_text_from_website(url):
    """
    Fetches the content of the website at the given URL and extracts meaningful text.
    """
    try:
        logging.info(f"Fetching website content from URL: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PodcastGenerator/1.0; +http://yourdomain.com/bot)"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses

        # Check if the content type is HTML
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type:
            logging.error(f"URL does not point to an HTML page. Content-Type: {content_type}")
            return None

    except requests.RequestException as e:
        logging.error(f"Error fetching website content: {e}")
        return None

    # Parse HTML content
    soup = BeautifulSoup(response.text, 'html.parser')

    # Remove scripts, styles, and other non-text elements
    for script in soup(["script", "style", "header", "footer", "nav", "aside"]):
        script.decompose()

    # Extract text
    text = soup.get_text(separator='\n')

    # Collapse multiple newlines into single ones
    lines = [line.strip() for line in text.splitlines()]
    chunks = [phrase for line in lines for phrase in line.split("  ") if phrase]
    clean_text = '\n'.join(chunks)

    logging.info("Text extraction from website successful.")
    return clean_text


def transcribe_audio(audio_path):
    """
    Transcribes the audio at the given path using Azure's Fast Transcription API.
    """
    try:
        api_url = f"https://{os.getenv('SPEECH_REGION_WE')}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe?api-version=2024-05-15-preview"
        subscription_key = os.getenv('SPEECH_KEY_WE')

        headers = {
            'Ocp-Apim-Subscription-Key': subscription_key,
            'Accept': 'application/json'
        }

        # Prepare the multipart form data
        files = {
            'audio': open(audio_path, 'rb'),
            'definition': ('', json.dumps({
                "locales": ["en-US"],
                "profanityFilterMode": "Masked",
                "channels": [0]
            }), 'application/json')
        }

        response = requests.post(api_url, headers=headers, files=files)

        if response.status_code != 200:
            print(f"Transcription API error: {response.text}")
            return None

        transcription_result = response.json()

        # Extract the combined transcription text
        combined_phrases = transcription_result.get('combinedPhrases', [])
        if combined_phrases:
            transcription_text = ' '.join([phrase['text'] for phrase in combined_phrases])
            return transcription_text.strip()
        else:
            print("No transcription phrases found.")
            return None

    except Exception as e:
        print(f"Error during transcription: {e}")
        return None


def generate_answer(question, context):
    """
    Generates a brief answer to the question based on the provided context using GPT-4.
    """
    prompt = f"""
    Answer the following question based on the provided context.
    If the answer is not present in the context, please just state this.

    Context:
    {context}

    Question:
    {question}

    Answer:
    """

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response.choices[0].message.content.strip()
        print("Answer generated by OpenAI.")
        return answer
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return None

def synthesize_speech(conversation, process_id, speaker1_voice, speaker2_voice):
    if not speech_config:
        print("Speech configuration is not set up properly.")
        return None

    # Define voices for speakers based on user selection
    voices = {
        'Speaker1': speaker1_voice,
        'Speaker2': speaker2_voice
    }

    # Split conversation into lines
    lines = conversation.strip().split('\n')

    # Create a single speech synthesizer instance
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    # Prepare directories for audio segments within static/audio
    audio_segments_dir = Path('static') / 'audio' / f"audio_segments_{process_id}"
    try:
        audio_segments_dir.mkdir(parents=True, exist_ok=True)
        print(f"Audio segments directory created at {audio_segments_dir}")
    except Exception as e:
        print(f"Error creating audio segments directory {audio_segments_dir}: {e}")
        return None

    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        # Ignore lines that are action descriptions or annotations
        if re.match(r'^\*\*\[.*\]\*\*$', line.strip()):
            continue

        # Define the path for each audio segment
        audio_filename = f"ssml_output_{i}.wav"
        audio_filename_path = audio_segments_dir / audio_filename

        if audio_filename_path.exists():
            print(f"Audio segment {audio_filename_path} already exists. Skipping synthesis.")
            continue

        # Match lines with format "**SpeakerName:** dialogue"
        match = re.match(r'^\*+(\w+):\*+\s*(.*)', line)
        if not match:
            match = re.match(r'^(\w+):\s*(.*)', line)

        if match:
            speaker = match.group(1)
            text = match.group(2)
            voice = voices.get(speaker, 'en-US-OnyxMultilingualNeuralHD')

            ssml = f"""
            <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
                <voice name='{voice}'>
                    <p>
                        {text}
                    </p>
                </voice>
            </speak>
            """
            print(f"Synthesizing line {i}: {ssml.strip()}")

            try:
                result = synthesizer.speak_ssml_async(ssml).get()
            except Exception as e:
                print(f"Speech synthesis error for line {i}: {e}")
                return None

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                try:
                    with audio_filename_path.open("wb") as audio_file:
                        audio_file.write(result.audio_data)
                    print(f"Speech synthesized and saved to {audio_filename_path}")
                except Exception as e:
                    print(f"Error saving audio segment {audio_filename_path}: {e}")
                    return None
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                print(f"Speech synthesis canceled: {cancellation_details.reason}")
                if cancellation_details.reason == speechsdk.CancellationReason.Error and cancellation_details.error_details:
                    print(f"Error details: {cancellation_details.error_details}")
                return None

    # Combine the audio segments
    combined_audio = AudioSegment.silent(duration=0)
    try:
        audio_files = sorted(
            [f for f in audio_segments_dir.iterdir() if f.suffix == '.wav'],
            key=lambda x: int(re.findall(r'\d+', x.name)[0])
        )
    except Exception as e:
        print(f"Error listing audio segments in {audio_segments_dir}: {e}")
        return None

    for audio_file_path in audio_files:
        try:
            audio_segment = AudioSegment.from_file(audio_file_path, format="wav")
            combined_audio += audio_segment
        except Exception as e:
            print(f"Error loading audio segment {audio_file_path.name}: {e}")
            continue

    # Generate timestamp for the final audio file
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    audio_filename = f"podcast_{timestamp}_{process_id}.wav"
    output_file_path = Path('static') / audio_filename

    try:
        combined_audio.export(output_file_path, format='wav')
        print(f"Combined audio exported to {output_file_path}")
    except Exception as e:
        print(f"Error exporting combined audio: {e}")
        return None

    # Convert the Path to a relative POSIX path for URL usage
    audio_file_relative = output_file_path.relative_to('static').as_posix()
    print(f"Audio file relative path: {audio_file_relative}")

    cleanup_old_files()
    return audio_file_relative

def split_text_into_sentences(text):
    """
    Splits text into chunks of at least 3 sentences using regular expressions.
    """
    # # Step 1: Split the text into individual sentences
    # sentences = re.findall(r'[^.!?]+[.!?]+', text) or [text]

    # # Step 2: Group sentences into chunks of at least 3 sentences
    # chunks = []
    # temp_chunk = []

    # for i, sentence in enumerate(sentences):
    #     temp_chunk.append(sentence.strip())
        
    #     # If we have 3 sentences in the temp_chunk or it's the last sentence, form a chunk
    #     if len(temp_chunk) >= 3 or i == len(sentences) - 1:
    #         chunks.append(' '.join(temp_chunk))  # Combine the sentences into a chunk
    #         temp_chunk = []  # Reset the temp_chunk
    chunks = [text]

    return chunks

import threading

# Semaphore to limit concurrent synthesis requests
MAX_CONCURRENT_REQUESTS = 5  # Adjust based on your Azure subscription limits
synthesizer_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

def synthesize_text_stream(text, process_id, voice_name, max_retries=3, initial_backoff=5):
    """
    Splits the text into sentences and synthesizes each sentence.
    Yields each synthesized audio fragment as bytes for streaming.
    Implements a retry mechanism to handle throttling errors.
    """
    if not speech_config:
        print("Speech configuration is not set up properly.")
        return

    # Acquire semaphore before proceeding
    with synthesizer_semaphore:
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

        # Split text into sentences
        sentences = split_text_into_sentences(text)

        for i, sentence in enumerate(sentences, start=1):
            retries = 0
            while retries <= max_retries:
                ssml = f"""
                <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
                    <voice name='{voice_name}'>
                        <p>{sentence}</p>
                    </voice>
                </speak>
                """
                print(f"Synthesizing sentence {i} (Attempt {retries + 1}): {sentence.strip()}")

                try:
                    result = synthesizer.speak_ssml_async(ssml).get()

                    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                        yield result.audio_data
                        print(f"Synthesized sentence {i} successfully.")
                        break  # Exit retry loop for this sentence

                    elif result.reason == speechsdk.ResultReason.Canceled:
                        cancellation_details = result.cancellation_details
                        print(f"Speech synthesis canceled: {cancellation_details.reason}")
                        if cancellation_details.reason == speechsdk.CancellationReason.Error and cancellation_details.error_details:
                            error_details = cancellation_details.error_details
                            print(f"Error details: {error_details}")
                            if "Error code: 4429" in error_details:
                                # Throttling error, implement retry
                                retries += 1
                                if retries > max_retries:
                                    print(f"Exceeded maximum retries for sentence {i}. Skipping.")
                                    break
                                backoff_time = initial_backoff * retries  # Exponential backoff
                                print(f"Throttling detected. Retrying in {backoff_time} seconds...")
                                time.sleep(backoff_time)
                                continue
                            else:
                                # Other errors, do not retry
                                print(f"Non-throttling error encountered. Skipping sentence {i}.")
                                break
                        else:
                            # Other cancellation reasons
                            print(f"Cancellation reason: {cancellation_details.reason}. Skipping sentence {i}.")
                            break

                except Exception as e:
                    print(f"Exception during speech synthesis for sentence {i}: {e}")
                    retries += 1
                    if retries > max_retries:
                        print(f"Exceeded maximum retries for sentence {i} due to exception. Skipping.")
                        break
                    backoff_time = initial_backoff * retries
                    print(f"Exception encountered. Retrying in {backoff_time} seconds...")
                    time.sleep(backoff_time)
                    continue
                
def save_text_to_file(text, file_path):
    """Utility function to save text to a file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Text successfully saved to {file_path}")
    except Exception as e:
        print(f"Error saving text to {file_path}: {e}")

def load_text_from_file(file_path):
    """Utility function to load text from a file."""
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            print(f"Text successfully loaded from {file_path}")
            return text
        else:
            print(f"File {file_path} does not exist. Returning empty string.")
            return ''
    except Exception as e:
        print(f"Error loading text from {file_path}: {e}")
        return ''

def cleanup_old_files():
    """Cleans up old files."""
    audio_segments_parent = Path('static') / 'audio'
    for dir in audio_segments_parent.glob('audio_segments_*'):
        #if dir.is_dir() and datetime.fromtimestamp(dir.stat().st_mtime) < threshold:
            try:
                shutil.rmtree(dir)
                logging.info(f"Deleted old audio segments directory: {dir}")
            except Exception as e:
                logging.error(f"Error deleting directory {dir}: {e}")
                
def cleanup_temp_file(file_path):
    """Removes the temporary audio file."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Temporary file {file_path} removed.")
    except Exception as e:
        print(f"Error removing temporary file {file_path}: {e}")
from flask import Flask, render_template, request, url_for, session, jsonify
import os
from dotenv import load_dotenv
import openai
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
import re
import uuid
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import logging

load_dotenv()

app = Flask(__name__)
app.secret_key = 'your-secret-keyx'  # Replace with a secure secret key
app.config['UPLOAD_FOLDER'] = 'uploads'



# Initialize Azure OpenAI client
try:
    openai.api_type = "azure"
    openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
    openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
    MODEL_NAME = os.getenv("AZURE_OPENAI_MODEL_NAME")
    if not all([openai.api_base, openai.api_version, openai.api_key, MODEL_NAME]):
        raise ValueError("Azure OpenAI configuration is incomplete.")
except Exception as e:
    print(f"Error initializing Azure OpenAI client: {e}")
    MODEL_NAME = None

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

# Define available voices (Option 1: Hardcoded)
AVAILABLE_VOICES = [
    {'name': 'en-US-OnyxMultilingualNeuralHD', 'display_name': 'Onyx Multilingual'},
    {'name': 'en-US-GuyNeural', 'display_name': 'Guy'},
    {'name': 'en-US-JennyNeural', 'display_name': 'Jenny'},
    {'name': 'en-US-AriaNeural', 'display_name': 'Aria'},
    {'name': 'en-US-LiamNeural', 'display_name': 'Liam'},
    # Add more voices as needed
]

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    conversation = ''
    text_content = ''
    audio_file = ''
    selected_voice1 = AVAILABLE_VOICES[0]['name']  # Default to first voice
    selected_voice2 = AVAILABLE_VOICES[1]['name']  # Default to second voice

    text_content = load_text_from_file(EXTRACTED_TEXT_FILE)
    print(f"Text content loaded from file: {text_content}")
    
    if request.method == 'POST':
        print("POST request received.")
        print("Form data:", request.form)  # Debug statement to inspect form data

        action = request.form.get('action')

        if action == 'upload_pdf':
                print("Upload PDF Form Submitted")
                # Handle PDF Upload
                pdf_file = request.files.get('pdf_file')
                if pdf_file and pdf_file.filename != '':
                    # Generate a unique filename with timestamp and UUID
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    unique_id = uuid.uuid4().hex
                    filename = f"{timestamp}_{unique_id}_{pdf_file.filename}"
                    pdf_path = Path(app.config['UPLOAD_FOLDER']) / filename
                    pdf_file.save(pdf_path)
                    session['pdf_path'] = str(pdf_path)
                    error = 'PDF uploaded successfully. You can now convert it to text.'
                    print(f"PDF uploaded and saved to {pdf_path}")
                else:
                    error = 'No PDF file selected for upload.'
                    print("No PDF file selected for upload.")

        elif action == 'convert_pdf':
                print("Convert PDF Form Submitted")
                # Handle PDF to Text Conversion
                pdf_path = session.get('pdf_path', None)
                if not pdf_path:
                    error = 'No PDF file path found in session. Please upload a PDF first.'
                    print("No PDF file path found in session for conversion.")
                elif not Path(pdf_path).exists():
                    error = f'PDF file not found at {pdf_path}. Please upload the PDF again.'
                    print(f"PDF file not found at {pdf_path}.")
                else:
                    # Check if user chose to use Azure Document Intelligence
                    use_azure = request.form.get('use_azure_doc_intelligence') == 'on'
                    if use_azure:
                        if not document_intelligence_client:
                            error = 'Document Intelligence client is not initialized.'
                            print("Document Intelligence client is not initialized.")
                        else:
                            # Extract text from PDF using Azure Document Intelligence
                            text_content = extract_text_from_pdf(pdf_path)
                            if text_content:
                                save_text_to_file(text_content, EXTRACTED_TEXT_FILE)  # Save to file
                                session['extracted_text'] = text_content
                                error = 'PDF converted to text successfully using Azure Document Intelligence.'
                                print("PDF converted to text successfully using Azure Document Intelligence.")
                            else:
                                error = 'Failed to extract text from PDF using Azure Document Intelligence.'
                                print("Failed to extract text from PDF using Azure Document Intelligence.")
                    else:
                        # Use alternative method (PyPDF2)
                        text_content = extract_text_from_pdf_pypdf2(pdf_path)
                        if text_content:
                            save_text_to_file(text_content, EXTRACTED_TEXT_FILE)  # Save to file
                            session['extracted_text'] = text_content
                            error = 'PDF converted to text successfully using alternative method.'
                            print("PDF converted to text successfully using alternative method.")
                        else:
                            error = 'Failed to extract text from PDF using alternative method.'
                            print("Failed to extract text from PDF using alternative method.")

        elif action == 'generate_outline':
                print("Generate Outline Form Submitted")

                # Handle Outline Generation
                if not MODEL_NAME:
                    error = 'OpenAI model is not configured properly.'
                    print("OpenAI model is not configured properly.")
                else:
                    # Retrieve extracted text from the form
                    text_content = request.form.get('text_content', '').strip()
                    print(f"Text content retrieved: {text_content}")

                    if not text_content:
                        error = 'Text content is empty. Please upload and convert a PDF or enter text.'
                        print("Text content is empty when attempting to generate outline.")
                    else:
                        # Ensure text content length is within the character limit
                        MAX_TEXT_LENGTH = 15000
                        if len(text_content) > MAX_TEXT_LENGTH:
                            text_content = text_content[:MAX_TEXT_LENGTH]
                            error = f'Text content truncated to {MAX_TEXT_LENGTH} characters.'
                            print(f"Text content truncated to {MAX_TEXT_LENGTH} characters.")

                        # Generate a new podcast conversation using OpenAI
                        process_id = str(uuid.uuid4())  # Always create a new unique process ID
                        print("Calling OpenAI API to generate a new conversation...")
                        conversation = generate_conversation(text_content, process_id)

                        if not conversation:
                            error = 'Failed to generate conversation.'
                            print("Failed to generate conversation.")
                        else:
                            # Save the newly generated conversation to session and file
                            session['conversation'] = conversation
                            save_text_to_file(conversation, CONVERSATION_FILE)
                            print("New conversation stored in session and saved to file.")

        elif action == 'generate_audio':
                # Handle Audio Generation
                selected_voice1 = request.form.get('speaker1_voice', AVAILABLE_VOICES[0]['name'])
                selected_voice2 = request.form.get('speaker2_voice', AVAILABLE_VOICES[1]['name'])
                conversation = request.form.get('conversation_text', '')

                if not conversation.strip():
                    error = 'Conversation text is empty. Please generate the outline first.'
                    print("Conversation text is empty when attempting to generate audio.")
                else:
                    if not speech_config:
                        error = 'Speech configuration is not set up properly.'
                        print("Speech configuration is not set up properly.")
                    else:
                        process_id = session.get('process_id', str(uuid.uuid4()))
                        session['process_id'] = process_id  # Update or set process_id in session

                        # Synthesize speech from conversation
                        try:
                            audio_file = synthesize_speech(conversation, process_id, selected_voice1, selected_voice2)
                        except Exception as e:
                            error = f"An unexpected error occurred during speech synthesis: {e}"
                            print(f"Unexpected error during speech synthesis: {e}")

                        if not audio_file:
                            error = 'Failed to synthesize speech.'
                        else:
                            session['audio_file'] = audio_file

        # Handle Extract Text from Website
        elif action == 'extract_website':
                website_url = request.form.get('website_url', '').strip()
                if not website_url:
                    error = 'No website URL provided.'
                else:
                    if not re.match(r'^https?:\/\/\S+\.\S+', website_url):
                        error = 'Invalid URL format. Please enter a valid website URL.'
                    else:
                        extracted_text = extract_text_from_website(website_url)
                        if extracted_text:
                            save_text_to_file(extracted_text, EXTRACTED_TEXT_FILE)  # Save to file
                            session['extracted_text'] = extracted_text
                            error = 'Text extracted from website successfully.'
                        else:
                            error = 'Failed to extract text from the provided website.'
        else:
                error = 'Invalid form submission.'

    # If no conversation is in the session, load it from the file (on GET requests or when first loading the page)
    conversation = session.get('conversation', '') or load_text_from_file(CONVERSATION_FILE)

    return render_template('index.html',
                           error=error,
                           conversation=conversation,
                           text_content=text_content,
                           audio_file=session.get('audio_file', ''),
                           available_voices=AVAILABLE_VOICES,
                           selected_voice1=session.get('speaker1_voice', AVAILABLE_VOICES[0]['name']),
                           selected_voice2=session.get('speaker2_voice', AVAILABLE_VOICES[1]['name']))

@app.route('/autosave', methods=['POST'])
def autosave():
    try:
        # Get the text and the type (extracted_text or conversation)
        text = request.form.get('text', '')
        text_type = request.form.get('text_type')

        # Based on the text_type, save the text to the appropriate file
        if text_type == 'extracted_text':
            save_text_to_file(text, EXTRACTED_TEXT_FILE)
        elif text_type == 'conversation':
            save_text_to_file(text, CONVERSATION_FILE)
        else:
            return jsonify({'status': 'error', 'message': 'Invalid text type'}), 400

        return jsonify({'status': 'success', 'message': 'Text autosaved successfully'}), 200
    except Exception as e:
        print(f"Error in autosave: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
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

def extract_text_from_pdf(pdf_path):
    if not document_intelligence_client:
        print("Document Intelligence client is not initialized.")
        return ''

    print("Extracting text with Azure Document Intelligence")
    try:
        with open(pdf_path, "rb") as f:
            # Corrected the model name from "prebuilt-layout" to "prebuilt-document"
            poller = document_intelligence_client.begin_analyze_document(
                "prebuilt-document", analyze_request=f, content_type="application/octet-stream"
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


def generate_conversation(text_content, process_id):
    conversation_file = f"static/conversations/conversation_{process_id}.txt"
    prompt = f"""
    Generate a podcast conversation between two speakers discussing the following content:
    {text_content}

    The podcast should be brief and start with an introduction explaining the topic and its relevance.
    Then, the two speakers should have a lively discussion covering the most important points.
    The two speakers should have different speaking styles.

    Provide the conversation in the following format:

    **Speaker1:** [Speaker 1's dialogue]
    **Speaker2:** [Speaker 2's dialogue]
    ...

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


from pathlib import Path  # Add this import at the top of your file

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
        # Skip empty lines
        if not line.strip():
            continue

        # Ignore lines that are action descriptions or annotations
        if re.match(r'^\*\*\[.*\]\*\*$', line.strip()):
            continue

        # Define the path for each audio segment
        audio_filename = f"ssml_output_{i}.wav"
        audio_filename_path = audio_segments_dir / audio_filename

        if audio_filename_path.exists():
            # Skip synthesizing this segment if it already exists
            print(f"Audio segment {audio_filename_path} already exists. Skipping synthesis.")
            continue

        # Match lines with format "**SpeakerName:** dialogue"
        match = re.match(r'^\*+(\w+):\*+\s*(.*)', line)
        if not match:
            # Try matching lines without '**', e.g., "SpeakerName: dialogue"
            match = re.match(r'^(\w+):\s*(.*)', line)

        if match:
            speaker = match.group(1)
            text = match.group(2)
            voice = voices.get(speaker, 'en-US-OnyxMultilingualNeuralHD')  # Default voice if speaker not found
            #voice = 'en-US-OnyxMultilingualNeuralHD'
            # Construct SSML with the desired voice
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
                result = speech_synthesizer.speak_ssml_async(ssml).get()
            except Exception as e:
                print(f"Speech synthesis error for line {i}: {e}")
                return None

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                # Save the audio data to a file
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
                if (cancellation_details.reason == speechsdk.CancellationReason.Error and
                    cancellation_details.error_details):
                    print(f"Error details: {cancellation_details.error_details}")
                    print("Did you set the speech resource key and region values?")
                return None  # Exit on error
        else:
            # Line does not match expected format, skip or handle accordingly
            print(f"Line {i} does not match expected format and will be skipped.")
            continue

    # Now combine the audio segments
    combined_audio = AudioSegment.silent(duration=0)

    # Get list of audio segment files in order
    try:
        audio_files = sorted(
            [f for f in audio_segments_dir.iterdir() if f.suffix == '.wav'],
            key=lambda x: int(re.findall(r'\d+', x.name)[0])  # Sort based on the number in filename
        )
    except Exception as e:
        print(f"Error listing audio segments in {audio_segments_dir}: {e}")
        return None

    for audio_file_path in audio_files:
        if not audio_file_path.exists():
            print(f"Audio segment file {audio_file_path} is missing. Skipping.")
            continue
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
    return audio_file_relative  # Return relative path from 'static'

# Constants for file paths
EXTRACTED_TEXT_FILE = Path('text_files') /  'extracted_text.txt'
CONVERSATION_FILE = Path('text_files') /  'conversation.txt'

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
    # Define the age threshold (e.g., 1 day)
    threshold = datetime.now() - timedelta(days=1)

    # Cleanup audio segments
    audio_segments_parent = Path('static') / 'audio'
    for dir in audio_segments_parent.glob('audio_segments_*'):
        #if dir.is_dir() and datetime.fromtimestamp(dir.stat().st_mtime) < threshold:
            try:
                shutil.rmtree(dir)
                logging.info(f"Deleted old audio segments directory: {dir}")
            except Exception as e:
                logging.error(f"Error deleting directory {dir}: {e}")



if __name__ == '__main__':
    # Ensure all necessary directories exist
    for folder in ['uploads', 'static/conversations', 'static/audio', 'text_files']:
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
                print(f"Created directory: {folder}")
            except Exception as e:
                print(f"Error creating directory {folder}: {e}")
                
                
    app.run(debug=True)
    

from flask import Flask, render_template, request, url_for, session, jsonify, send_file, Response, stream_with_context
import os
from dotenv import load_dotenv
import re
import uuid
from pathlib import Path
from datetime import datetime
from pathlib import Path  
from werkzeug.utils import secure_filename

# Import utility functions and constants
from utils import (
    extract_text_from_pdf_pypdf2,
    extract_text_from_website,
    extract_text_from_pdf,
    generate_conversation,
    synthesize_speech,
    synthesize_text_stream,
    cleanup_temp_file,
    save_text_to_file,
    load_text_from_file,
    cleanup_old_files,
    EXTRACTED_TEXT_FILE,
    CONVERSATION_FILE,
    transcribe_audio,
    generate_answer
)

load_dotenv()
cleanup_old_files()

app = Flask(__name__)
app.secret_key = 'your-secret-keyx'  # Replace with a secure secret key
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['VOICE_SAMPLE_DIR'] = "static/voice_samples"

# Define available voices (Option 1: Hardcoded)
AVAILABLE_VOICES = [
    {'name': 'en-US-OnyxMultilingualNeuralHD', 'display_name': 'Onyx Multilingual'},
    {'name': 'en-US-GuyNeural', 'display_name': 'Guy'},
    {'name': 'en-US-JennyNeural', 'display_name': 'Jenny'},
    {'name': 'en-US-AriaNeural', 'display_name': 'Aria'},
    {'name': 'en-CA-LiamNeural', 'display_name': 'Liam'},
    # Add more voices as needed
]

@app.route('/', methods=['GET'])
def index():
    error = None
    conversation = session.get('conversation', '') or load_text_from_file(CONVERSATION_FILE)
    text_content = session.get('extracted_text', '') or load_text_from_file(EXTRACTED_TEXT_FILE)
    audio_file = session.get('audio_file', '')

    return render_template('index.html',
                           error=error,
                           conversation=conversation,
                           text_content=text_content,
                           audio_file=audio_file,
                           available_voices=AVAILABLE_VOICES,
                           selected_voice1=session.get('speaker1_voice', AVAILABLE_VOICES[0]['name']),
                           selected_voice2=session.get('speaker2_voice', AVAILABLE_VOICES[1]['name']))

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    try:
        pdf_file = request.files.get('pdf_file')
        if pdf_file and pdf_file.filename != '':
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            unique_id = uuid.uuid4().hex
            filename = f"{timestamp}_{unique_id}_{pdf_file.filename}"
            pdf_path = Path(app.config['UPLOAD_FOLDER']) / filename
            pdf_file.save(pdf_path)
            session['pdf_path'] = str(pdf_path)
            message = 'PDF uploaded successfully. You can now convert it to text.'
            print(f"PDF uploaded and saved to {pdf_path}")
            return jsonify({'status': 'success', 'message': message})
        else:
            error = 'No PDF file selected for upload.'
            print("No PDF file selected for upload.")
            return jsonify({'status': 'error', 'message': error})
    except Exception as e:
        error = f"Error during PDF upload: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error})

@app.route('/convert_pdf', methods=['POST'])
def convert_pdf():
    try:
        pdf_path = session.get('pdf_path', None)
        if not pdf_path:
            error = 'No PDF file path found in session. Please upload a PDF first.'
            print("No PDF file path found in session for conversion.")
            return jsonify({'status': 'error', 'message': error})
        elif not Path(pdf_path).exists():
            error = f'PDF file not found at {pdf_path}. Please upload the PDF again.'
            print(f"PDF file not found at {pdf_path}.")
            return jsonify({'status': 'error', 'message': error})
        else:
            use_azure = request.form.get('use_azure_doc_intelligence') == 'true'
            if use_azure:
                text_content = extract_text_from_pdf(pdf_path)
                if text_content:
                    save_text_to_file(text_content, EXTRACTED_TEXT_FILE)
                    session['extracted_text'] = text_content
                    message = 'PDF converted to text successfully using Azure Document Intelligence.'
                    print("PDF converted to text successfully using Azure Document Intelligence.")
                    return jsonify({'status': 'success', 'message': message, 'text_content': text_content})
                else:
                    error = 'Failed to extract text from PDF using Azure Document Intelligence.'
                    print("Failed to extract text from PDF using Azure Document Intelligence.")
                    return jsonify({'status': 'error', 'message': error})
            else:
                text_content = extract_text_from_pdf_pypdf2(pdf_path)
                if text_content:
                    save_text_to_file(text_content, EXTRACTED_TEXT_FILE)
                    session['extracted_text'] = text_content
                    message = 'PDF converted to text successfully using alternative method.'
                    print("PDF converted to text successfully using alternative method.")
                    return jsonify({'status': 'success', 'message': message, 'text_content': text_content})
                else:
                    error = 'Failed to extract text from PDF using alternative method.'
                    print("Failed to extract text from PDF using alternative method.")
                    return jsonify({'status': 'error', 'message': error})
    except Exception as e:
        error = f"Error during PDF conversion: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error})

@app.route('/generate_outline', methods=['POST'])
def generate_outline():
    try:
        text_content = request.form.get('text_content', '').strip()
        print(f"Text content retrieved: {text_content}")

        if not text_content:
            error = 'Text content is empty. Please upload and convert a PDF or enter text.'
            print("Text content is empty when attempting to generate outline.")
            return jsonify({'status': 'error', 'message': error})
        else:
            MAX_TEXT_LENGTH = 15000
            if len(text_content) > MAX_TEXT_LENGTH:
                text_content = text_content[:MAX_TEXT_LENGTH]
                error = f'Text content truncated to {MAX_TEXT_LENGTH} characters.'
                print(f"Text content truncated to {MAX_TEXT_LENGTH} characters.")

            process_id = str(uuid.uuid4())
            print("Calling OpenAI API to generate a new conversation...")
            conversation = generate_conversation(text_content, process_id)

            if not conversation:
                error = 'Failed to generate conversation.'
                print("Failed to generate conversation.")
                return jsonify({'status': 'error', 'message': error})
            else:
                session['conversation'] = conversation
                save_text_to_file(conversation, CONVERSATION_FILE)
                print("New conversation stored in session and saved to file.")
                return jsonify({'status': 'success', 'conversation': conversation, 'message': 'Conversation generated successfully.'})
    except Exception as e:
        error = f"Error during conversation generation: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error})

@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    try:
        selected_voice1 = request.form.get('speaker1_voice', AVAILABLE_VOICES[0]['name'])
        selected_voice2 = request.form.get('speaker2_voice', AVAILABLE_VOICES[1]['name'])
        conversation = request.form.get('conversation_text', '')

        if not conversation.strip():
            error = 'Conversation text is empty. Please generate the outline first.'
            print("Conversation text is empty when attempting to generate audio.")
            return jsonify({'status': 'error', 'message': error})
        else:

            process_id = session.get('process_id', str(uuid.uuid4()))
            session['process_id'] = process_id

            # Synthesize speech using the utility function
            audio_file = synthesize_speech(conversation, process_id, selected_voice1, selected_voice2)
            if not audio_file:
                error = 'Failed to synthesize speech.'
                return jsonify({'status': 'error', 'message': error})
            
            # Store audio file path in session
            session['audio_file'] = audio_file
            return jsonify({'status': 'success', 'audio_file': audio_file, 'message': 'Audio generated successfully.'})
    except Exception as e:
        error = f"Error during audio generation: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error})
    
@app.route('/get_voice_sample', methods=['POST'])
def get_voice_sample():
    try:
        # Retrieve voice name from the request
        data = request.get_json()
        voice_name = data.get('voice_name')

        if not voice_name:
            return jsonify({'status': 'error', 'message': 'Voice name not provided'}), 400
        
        # Ensure the directory for storing voice samples exists
        os.makedirs(app.config['VOICE_SAMPLE_DIR'], exist_ok=True)
 
        # Define the path for the voice sample
        sanitized_voice_name = secure_filename(voice_name)  # Use a secure filename
        sample_file_path = os.path.join(app.config['VOICE_SAMPLE_DIR'], f"{sanitized_voice_name}_sample.wav")

        # Check if the sample file already exists
        if os.path.exists(sample_file_path):
            print(f"Using cached voice sample for: {voice_name}")
            # If the sample exists, return it directly
            with open(sample_file_path, 'rb') as audio_file:
                return Response(audio_file.read(), mimetype='audio/wav')

        # If the sample doesn't exist, synthesize it
        sample_text = "Hi there, I'd love to be your podcast host!"
        audio_chunks = []

        # Generate the voice sample using synthesize_text_stream
        for audio_data in synthesize_text_stream(sample_text, '', voice_name):
            if audio_data:
                audio_chunks.append(audio_data)

        if not audio_chunks:
            return jsonify({'status': 'error', 'message': 'Failed to generate voice sample'}), 500

        # Combine the audio chunks into one bytes object
        combined_audio_data = b''.join(audio_chunks)

        # Save the synthesized audio to a file for future use
        with open(sample_file_path, 'wb') as audio_file:
            audio_file.write(combined_audio_data)

        # Return the combined audio data as a response
        return Response(combined_audio_data, mimetype='audio/wav')

    except Exception as e:
        error = f"Error generating voice sample: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error}), 500

@app.route('/extract_website', methods=['POST'])
def extract_website():
    try:
        website_url = request.form.get('website_url', '').strip()
        if not website_url:
            error = 'No website URL provided.'
            return jsonify({'status': 'error', 'message': error})
        else:
            if not re.match(r'^https?:\/\/\S+\.\S+', website_url):
                error = 'Invalid URL format. Please enter a valid website URL.'
                return jsonify({'status': 'error', 'message': error})
            else:
                extracted_text = extract_text_from_website(website_url)
                if extracted_text:
                    save_text_to_file(extracted_text, EXTRACTED_TEXT_FILE)
                    session['extracted_text'] = extracted_text
                    message = 'Text extracted from website successfully.'
                    return jsonify({'status': 'success', 'text_content': extracted_text, 'message': message})
                else:
                    error = 'Failed to extract text from the provided website.'
                    return jsonify({'status': 'error', 'message': error})
    except Exception as e:
        error = f"Error during website text extraction: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error})


@app.route('/autosave', methods=['POST'])
def autosave():
    try:
        data = request.get_json()
        text = data.get('text', '')
        text_type = data.get('text_type')

        if text_type == 'extracted_text':
            save_text_to_file(text, EXTRACTED_TEXT_FILE)
            session['extracted_text'] = text  # Save to session as well
        elif text_type == 'conversation':
            save_text_to_file(text, CONVERSATION_FILE)
            session['conversation'] = text  # Save to session as well
        else:
            return jsonify({'status': 'error', 'message': 'Invalid text type'}), 400

        return jsonify({'status': 'success', 'message': 'Text autosaved successfully'}), 200
    except Exception as e:
        print(f"Error in autosave: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/process_question', methods=['POST'])
def process_question():
    print("Processing question...")
    # Ensure the request contains the audio data
    if 'audio_data' not in request.files:
        return Response("No audio_data part in the request.", status=400)

    audio_file = request.files['audio_data']

    if audio_file.filename == '':
        return Response("No selected file.", status=400)

    # Save the uploaded audio file temporarily
    process_id = uuid.uuid4().hex  # Unique ID for this process
    temp_audio_path = f"temp_audio_{process_id}.wav"
    audio_file.save(temp_audio_path)

    # Transcribe the audio to text
    transcription = transcribe_audio(temp_audio_path)
    if not transcription:
        cleanup_temp_file(temp_audio_path)
        return Response("Failed to transcribe audio.", status=500)

    print(f"Transcription: {transcription}")

    # Generate a response using OpenAI GPT-4
    
    context = request.form.get('text_content', '').strip()
    
    if not context:
        context = "Default context if none available."

    answer = generate_answer(transcription, context)
    if not answer:
        cleanup_temp_file(temp_audio_path)
        return Response("Failed to generate answer.", status=500)

    print(f"Generated Answer: {answer}")
    
    # retrieve speaker voice 1
    speaker_voice = request.form.get('speaker1_voice', AVAILABLE_VOICES[0]['name'])
    import time
    # 5 seconds wait
    time.sleep(5)

    # Define a generator to stream audio fragments
    def generate_audio_stream():
        try:
            for audio_data in synthesize_text_stream(answer, process_id, speaker_voice):
                if audio_data:
                    yield audio_data
        except Exception as e:
            print(f"Error during audio streaming: {e}")

    # Cleanup temporary audio recording after processing
    cleanup_temp_file(temp_audio_path)

    return Response(stream_with_context(generate_audio_stream()), mimetype='audio/wav')


# Constants for file paths
EXTRACTED_TEXT_FILE = Path('text_files') /  'extracted_text.txt'
CONVERSATION_FILE = Path('text_files') /  'conversation.txt'

if __name__ == '__main__':
    # Ensure all necessary directories exist
    for folder in ['uploads', 'static/conversations', 'static/audio', 'text_files', 'static/voice_samples']:
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
                print(f"Created directory: {folder}")
            except Exception as e:
                print(f"Error creating directory {folder}: {e}")
                
                
    app.run(debug=True)
    

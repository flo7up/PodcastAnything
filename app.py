from flask import Flask, render_template, request, url_for, make_response, session, jsonify, send_file, Response, stream_with_context
import os
from dotenv import load_dotenv
import re
import uuid
from pathlib import Path
from datetime import datetime
from pathlib import Path  
from werkzeug.utils import secure_filename

# Import utility functions and constants utils.py in folder utils

from utils.utils import (
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
app.secret_key = 'your-secret-keyx123'  
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['VOICE_SAMPLE_DIR'] = "static/voice_samples"
app.config['EXTRACTED_TEXT_FILE'] = 'extracted_text.txt'  

# Define available voices (Option 1: Hardcoded)
AVAILABLE_VOICES = [
    {'name': 'en-US-GuyNeural', 'display_name': 'Guy'},
    {'name': 'en-US-JennyNeural', 'display_name': 'Jenny'},
    {'name': 'en-US-AriaNeural', 'display_name': 'Aria'},
    {'name': 'en-CA-LiamNeural', 'display_name': 'Liam'},
    {'name': 'en-US-OnyxMultilingualNeuralHD', 'display_name': 'Onyx Multilingual'}
    # Add more voices as needed
]

@app.route('/', methods=['GET'])
def index():
    error = None
    conversation = session.get('conversation', '') or load_text_from_file(CONVERSATION_FILE)
    text_content = session.get('extracted_text', '') or load_text_from_file(EXTRACTED_TEXT_FILE)
    audio_file = session.get('audio_file', '')
    if audio_file and os.path.exists(os.path.join('static', audio_file)):
        audio_exists = True
    else:
        audio_exists = False
        audio_file = None  # Ensure audio_file is None if the file doesn't exist
        
    return render_template('index.html',
                           error=error,
                           conversation=conversation,
                           text_content=text_content,
                           audio_file=audio_file,
                           available_voices=AVAILABLE_VOICES,
                           selected_voice1=session.get('speaker1_voice', AVAILABLE_VOICES[0]['name']),
                           selected_voice2=session.get('speaker2_voice', AVAILABLE_VOICES[1]['name']), 
                           audio_exists=audio_exists)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf'}


@app.route('/upload_and_convert_pdf', methods=['POST'])
def upload_and_convert_pdf():
    try:
        # Check if the POST request has the file part
        if 'pdf_file' not in request.files:
            error = 'No PDF file part in the request.'
            print(error)
            return jsonify({'status': 'error', 'message': error}), 400

        pdf_file = request.files['pdf_file']

        # If user does not select file, browser may submit an empty part without filename
        if pdf_file.filename == '':
            error = 'No PDF file selected for upload.'
            print(error)
            return jsonify({'status': 'error', 'message': error}), 400

        if pdf_file and allowed_file(pdf_file.filename):
            # Generate a unique filename
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            unique_id = uuid.uuid4().hex
            filename = f"{timestamp}_{unique_id}_{secure_filename(pdf_file.filename)}"
            pdf_path = Path(app.config['UPLOAD_FOLDER']) / filename

            # Save the PDF file
            pdf_file.save(pdf_path)
            session['pdf_path'] = str(pdf_path)
            print(f"PDF uploaded and saved to {pdf_path}")

            # Retrieve the 'use_azure_doc_intelligence' flag
            use_azure = request.form.get('use_azure_doc_intelligence') == 'true'

            # Convert PDF to text based on the selected method
            if use_azure:
                text_content = extract_text_from_pdf(pdf_path)
                method_used = 'Azure Document Intelligence'
            else:
                text_content = extract_text_from_pdf_pypdf2(pdf_path)
                method_used = 'Alternative Method'

            if text_content:
                # Save the extracted text to a file (optional)
                text_file_path = Path(app.config['EXTRACTED_TEXT_FILE'])
                save_text_to_file(text_content, text_file_path)

                # Store the extracted text in the session
                session['extracted_text'] = text_content
                message = f'PDF uploaded and converted to text successfully using {method_used}.'
                print(message)

                return jsonify({
                    'status': 'success',
                    'message': message,
                    'text_content': text_content
                })
            else:
                error = f'Failed to extract text from PDF using {method_used}.'
                print(error)
                return jsonify({'status': 'error', 'message': error}), 500
        else:
            error = 'Invalid file type. Only PDF files are allowed.'
            print(error)
            return jsonify({'status': 'error', 'message': error}), 400

    except Exception as e:
        error = f"Error during upload and conversion: {e}"
        print(error)
        return jsonify({'status': 'error', 'message': error}), 500

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
    print("Generating audio from conversation text...")
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
    try:
        # Ensure the request contains the audio data
        if 'audio_data' not in request.files:
            return jsonify({'status': 'error', 'message': 'No audio_data part in the request.'}), 400

        audio_file = request.files['audio_data']

        if audio_file.filename == '':
            return jsonify({'status': 'error', 'message': 'No selected file.'}), 400

        # Save the uploaded audio file temporarily
        process_id = uuid.uuid4().hex  # Unique ID for this process
        temp_audio_path = f"temp_audio_{process_id}.wav"
        audio_file.save(temp_audio_path)

        # Transcribe the audio to text
        transcription = transcribe_audio(temp_audio_path)
        if not transcription:
            cleanup_temp_file(temp_audio_path)
            return jsonify({'status': 'error', 'message': 'Failed to transcribe audio.'}), 500

        print(f"Transcription: {transcription}")

        # Generate a response using OpenAI GPT-4
        context = request.form.get('text_content', '').strip()

        if not context:
            context = "Default context if none available."

        answer = generate_answer(transcription, context)
        if not answer:
            cleanup_temp_file(temp_audio_path)
            return jsonify({'status': 'error', 'message': 'Failed to generate answer.'}), 500

        print(f"Generated Answer: {answer}")

        # Retrieve speaker voice (using speaker1_voice as default)
        speaker_voice = request.form.get('speaker1_voice', AVAILABLE_VOICES[0]['name'])

        # Synthesize the entire answer
        audio_chunks = list(synthesize_text_stream(answer, process_id, speaker_voice))

        if not audio_chunks:
            cleanup_temp_file(temp_audio_path)
            return jsonify({'status': 'error', 'message': 'Failed to generate audio.'}), 500

        # Combine the audio chunks
        combined_audio_data = b''.join(audio_chunks)

        # Return the audio data as a response
        response = make_response(combined_audio_data)
        response.headers.set('Content-Type', 'audio/mpeg')  # Adjust MIME type if using MP3
        response.headers.set('Content-Disposition', 'attachment', filename='answer.mp3')

        # Cleanup temporary audio recording after processing
        cleanup_temp_file(temp_audio_path)

        return response

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        print(error_message)
        return jsonify({'status': 'error', 'message': error_message}), 500


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
    


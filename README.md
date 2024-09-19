
# Podcast Anything (Protoype)

This project demonstrates the use of AI to turn any information into a podcast.
The project utilizes HTML/Javascript frontend with a Python/Flask backend and different Azure AI services.
The process of creating this project heavily relied on OpenAI o1-preview and o1-mini to showcase the efficiency gains when prototyping with AI.

## Project Features

The application offers three modes for input:

1. **Fetch text from a website**
2. **Upload a PDF document**
3. **Manually insert text**

The text is then processed to generate a podcast outline, and audio is synthesized using Azure Speech Services.

### Azure Services Used

- **[Azure Document Intelligence](https://learn.microsoft.com/en-us/azure/ai-form-recognizer/)**: (Optional) For processing and extracting information from PDF documents.
- **[Azure OpenAI GPT-4](https://learn.microsoft.com/en-us/azure/cognitive-services/openai/)**: (Required) For creating the podcast outline from the provided text.
- **[Azure Speech Service](https://learn.microsoft.com/en-us/azure/cognitive-services/speech-service/)**: (Required) To generate synthetic voices, with support for regions like Sweden Central (e.g., OpenAI voices available in Sweden).

### Installation

To install the required dependencies, run the following command:

```bash
pip install -r requirements.txt
```

### Configuration

Ensure you have an `.env` file in the root directory with the following configuration:

```bash
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_MODEL_NAME=

# Azure Document Intelligence
DOCUMENTINTELLIGENCE_ENDPOINT=
DOCUMENTINTELLIGENCE_API_KEY=

# Azure Speech Service
SPEECH_KEY=
SPEECH_REGION="swedencentral"
```

### Application Architecture

- **Backend**: Python/Flask
- **Frontend**: JavaScript

### Running the App

To run the application locally, execute the following command:

```bash
python app.py
```

### Project Demo Screenshot

![Project Screenshot](screenshots/app_screenshot.png)

---


# AI Podcast Outline Generator

This project demonstrates the use of AI to generate podcast outlines from text, utilizing a Python/Flask backend and a JavaScript frontend. The application showcases how AI tools can expedite coding workflows with rapid prototyping, leveraging models like OpenAI o1-preview and o1-mini.

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

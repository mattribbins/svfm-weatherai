# Weather AI TTS generator for SVFM
This is a weather bulletin generator for Somer Valley FM. It will take the upcoming forecast from the Met Office API and attempt to generate a bulletin, with Text-To-Speech from Google Cloud APIs.

# External requirements
You will require the following:
* Google Cloud Text-To-Speech API
* Met Office Data Hub Site Specific API

# Configuration
Copy `config.example.yaml` to `config.yaml` and modify config as follows:

|Key|Example Value|Notes|
|---|-----|-----|
|`google_oauth_creds`|`./credentials.json`|Google Cloud API credentials. This needs to have rights to the Text-To-Speech API|
|`metoffice_api_key`|API Key|API key to the Met Office Data Hub Site Specific API|
|`lat`|`51.2852`|Latitude|
|`long`|`-2.4859`|Longitude|
|`output_file`|`./out.wav`|Location to save the TTS bulletin|
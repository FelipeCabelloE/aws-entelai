# aws-entelai
A POC web application focusing on merging aws polly and transcribe with [entelai's](https://entelai.com/en/) api

### Installation
1. Clone this repository:
`git clone https://github.com/FelipeCabelloE/aws-entelai.git`

2. Install the Python packages:
`pip install -r requirements.txt`

3. Add your API keys to `app.py`:
##TODO update the requirements to showcase aws and entelais keys

`OPENAI_API_KEY = "YOUR API KEY HERE"`.   
`ELEVENLABS_API_KEY = "YOUR API KEY HERE"`

### Usage
1. Start the Flask server: `python app.py` or `flask run`
2. Open your web browser and navigate to http://localhost:5000.
3. Click the “Record” button to start recording audio. Speak into your microphone and then click the button again when you’re done. The transcription will appear in the text box.
4. Alternatively, type your question into the text box and click the “Ask” button to submit your question and generate a response.
5. The response will appear in the area below the audio player. It will begin playing and typing once it is ready.


### Credits
This project is a fork of Artificial Ignorance's hugh, using Flask, OpenAI’s Whisper, OpenAI’s ChatGPT, and ElevenLabs. 

### License
This project is licensed under the MIT License - see the LICENSE file for details.

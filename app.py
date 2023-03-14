import openai
import os
import requests
import uuid
from flask import Flask, request, jsonify, send_file, render_template, Response

from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError
from src import aws_transcribe 
from src import entelai_parser
# Add your OpenAI API key
OPENAI_API_KEY = ""
openai.api_key = OPENAI_API_KEY

# Add your ElevenLabs API key
ELEVENLABS_API_KEY = ""
ELEVENLABS_VOICE_STABILITY = 0.30
ELEVENLABS_VOICE_SIMILARITY = 0.75

# Choose your favorite ElevenLabs voice
ELEVENLABS_VOICE_NAME = "Lucia"
ELEVENLABS_ALL_VOICES = []


# Mapping the output format used in the client to the content type for the
# response
AUDIO_FORMATS = {"ogg_vorbis": "audio/ogg",
                 "mp3": "audio/mpeg",
                 "pcm": "audio/wave; codecs=1"}

# Create a client using the credentials and region defined in the adminuser
# section of the AWS credentials and configuration files
session = Session(profile_name="amazonpoly-felipecabello")
polly = session.client("polly")
transcribe_client = session.client('transcribe')
s3_client = session.client('s3')


app = Flask(__name__)


# Simple exception class
class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


# Register error handler
@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response





def transcribe_audio(filename: str) -> str:
    """Transcribe audio to text.
    Sends audifile to s3, starts a transcription job, then waits for it to finnish and sends back the answer

    :param filename: The path to an audio file.
    :returns: The transcribed text of the file.
    :rtype: str

    """
    bucket_name = 'entelai-transcribe-polly-flaskdemo'
    response = s3_client.upload_file(filename, bucket_name, filename)
    media_uri = f's3://{bucket_name}/{filename}'
    job_name = f'{filename[9:]}'
    aws_transcribe.start_job(job_name=job_name, media_uri=media_uri, media_format='ogg', language_code='es-ES', transcribe_client=transcribe_client)
    transcribe_waiter = aws_transcribe.TranscribeCompleteWaiter(transcribe_client)
    transcribe_waiter.wait(job_name)
    job_simple = aws_transcribe.get_job(job_name, transcribe_client)
    transcript_simple = requests.get(
        job_simple['Transcript']['TranscriptFileUri']).json()

    return transcript_simple['results']['transcripts'][0]['transcript']
    


def generate_reply(conversation: list) -> str:
    """Generate an entelai response.

    :param conversation: A list of previous user and assistant messages.
    :returns: The ChatGPT response.
    :rtype: str

    """
    response = openai.ChatCompletion.create(
      model="gpt-3.5-turbo",
      messages=[
            {"role": "system", "content": "You are a helpful assistant."},
        ] + conversation
    )
    return response["choices"][0]["message"]["content"]


def generate_audio(text: str, output_path: str = "") -> str:
    """Converts

    :param text: The text to convert to audio.
    :type text : str
    :param output_path: The location to save the finished mp3 file.
    :type output_path: str
    :returns: The output path for the successfully saved file.
    :rtype: str

    """
    voices = ELEVENLABS_ALL_VOICES
    try:
        voice_id = next(filter(lambda v: v["name"] == ELEVENLABS_VOICE_NAME, voices))["voice_id"]
    except StopIteration:
        voice_id = voices[0]["voice_id"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "content-type": "application/json"
    }
    data = {
        "text": text,
        "voice_settings": {
            "stability": ELEVENLABS_VOICE_STABILITY,
            "similarity_boost": ELEVENLABS_VOICE_SIMILARITY,
        }
    }
    response = requests.post(url, json=data, headers=headers)
    with open(output_path, "wb") as output:
        output.write(response.content)
    return output_path


@app.route('/')
def index():
    """Render the index page."""
    return render_template('index.html', voice=ELEVENLABS_VOICE_NAME)


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """Transcribe the given audio to text using Whisper."""
    if 'file' not in request.files:
        return 'No file found', 400
    file = request.files['file']
    recording_file = f"{uuid.uuid4()}.ogg"
    recording_path = f"uploads/{recording_file}"
    os.makedirs(os.path.dirname(recording_path), exist_ok=True)
    file.save(recording_path)
    ##file information
    import filetype
    kind = filetype.guess(recording_path)
    if kind is None:
        print('Cannot guess file type!')
    else:
        print('File extension: %s' % kind.extension)
        print('File MIME type: %s' % kind.mime)
    transcription = transcribe_audio(recording_path)
    return jsonify({'text': transcription})


@app.route('/ask', methods=['POST'])
def ask():
    """Generate a entelai response from the given conversation, then convert it to audio using ElevenLabs."""
    conversation = request.get_json(force=True).get("conversation", "")
    reply = generate_reply(conversation)
    reply_file = f"{uuid.uuid4()}.mp3"
    reply_path = f"outputs/{reply_file}"
    os.makedirs(os.path.dirname(reply_path), exist_ok=True)
    generate_audio(reply, output_path=reply_path)
    return jsonify({'text': reply, 'audio': f"/listen/{reply_file}"})


@app.route('/listen/<filename>')
def listen(filename):
    """Return the audio file located at the given filename."""
    return send_file(f"outputs/{filename}", mimetype="audio/mp3", as_attachment=False)


if ELEVENLABS_API_KEY:
    if not ELEVENLABS_ALL_VOICES:
        ELEVENLABS_ALL_VOICES = get_voices()
    if not ELEVENLABS_VOICE_NAME:
        ELEVENLABS_VOICE_NAME = ELEVENLABS_ALL_VOICES[0]["name"]

if __name__ == '__main__':
    app.run(debug=True)

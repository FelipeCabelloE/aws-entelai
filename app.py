import openai
import os
import requests
import uuid
from flask import Flask, request, jsonify, send_file, render_template, Response, session, flash, redirect, abort
from flask_session import Session as Sess
from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError
from src import aws_transcribe 
from src import entelai_parser


# Choose your favorite entelai voice
POLLY_VOICE = "Lucia"



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



############## Login ##########
@app.route('/')
def index():
    """Render the index page."""
    if not Sess.get('logged_in'):
        return render_template('login.html')
    else:
        return render_template('index.html', voice=POLLY_VOICE)



@app.route('/login', methods=['POST'])
def do_admin_login():
    if request.form['password'] == 'password' and request.form['username'] == 'admin':
        session['logged_in'] = True
        return index()
    else:
        flash('wrong password!')
        return index()














###############





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
    

@app.route('/reply', methods=['POST'])
def generate_reply():
    """Generate an entelai response.

    :param conversation: A list of previous user and assistant messages.
    :returns: The ChatGPT response.
    :rtype: str

    """
    text = request.get_json()['text']
    response = entelai_parser.entelai_post_request(text).json()
    entelai_text = response["messages"][0]["text"]
    return jsonify({'text': entelai_text})



    
@app.route('/read', methods=['GET'])
def read():
    """Handles routing for reading text (speech synthesis)"""
    # Get the parameters from the query string
    try:
        outputFormat = request.args.get('outputFormat')
        text = request.args.get('text')
        voiceId = request.args.get('voiceId')
    except TypeError:
        raise InvalidUsage("Wrong parameters", status_code=400)

    # Validate the parameters, set error flag in case of unexpected
    # values
    if len(text) == 0 or len(voiceId) == 0 or \
            outputFormat not in AUDIO_FORMATS:
        raise InvalidUsage("Wrong parameters", status_code=400)
    else:
        try:
            # Request speech synthesis
            response = polly.synthesize_speech(Text=text,
                                               VoiceId=voiceId,
                                               OutputFormat=outputFormat)
        except (BotoCoreError, ClientError) as err:
            # The service returned an error
            raise InvalidUsage(str(err), status_code=500)

        return send_file(response.get("AudioStream"),
                         AUDIO_FORMATS[outputFormat])
    
    




@app.route('/transcribe', methods=['POST'])
def transcribe():
    """Transcribe the given audio to text using transcribe."""
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



if __name__ == '__main__':
    app.secret_key = os.urandom(12)
    app.run(debug=True)

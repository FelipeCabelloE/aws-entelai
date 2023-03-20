import openai
import os
import requests
import uuid
from flask import Flask, request, jsonify, send_file, render_template, Response, session, flash, redirect, abort, url_for
import flask_login
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



############## Login ########## https://pythonspot.com/login-authentication-with-flask/


app.secret_key = os.urandom(12)
login_manager = flask_login.LoginManager()
login_manager.init_app(app)


# Our mock database.
users = {'Penpal0647': {'password': 'GwbB4QNfDkiWgo9Z5WeV78uEq3cNMv'}}

class User(flask_login.UserMixin):
    pass


@login_manager.user_loader
def user_loader(email):
    if email not in users:
        return

    user = User()
    user.id = email
    return user


@login_manager.request_loader
def request_loader(request):
    email = request.form.get('email')
    if email not in users:
        return

    user = User()
    user.id = email
    return user



@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    
    if request.method == 'GET':
        return '''
               <form action='login' method='POST'>
                <input type='text' name='email' id='email' placeholder='username'/>
                <input type='password' name='password' id='password' placeholder='password'/>
                <input type='submit' name='submit'/>
               </form>
               '''
               
    email = request.form['email']
    if email in users and request.form['password'] == users[email]['password']:
        user = User()
        user.id = email
        flask_login.login_user(user)
        return redirect(url_for('index'))

    return 'Bad login'


@app.route('/index')
@flask_login.login_required
def index():
    """Render the index page."""
    return render_template('index.html', voice=POLLY_VOICE)






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
@flask_login.login_required
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
@flask_login.login_required
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
@flask_login.login_required
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
@flask_login.login_required
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
@flask_login.login_required
def listen(filename):
    """Return the audio file located at the given filename."""
    return send_file(f"outputs/{filename}", mimetype="audio/mp3", as_attachment=False)



if __name__ == '__main__':
    
    app.run(host='0.0.0.0', port=5000)

from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit
import subprocess

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Fonction pour lister uniquement les périphériques audio de sortie
def list_audio_outputs():
    result = subprocess.run(["SwitchAudioSource", "-t", "output", "-a"], capture_output=True, text=True)
    outputs = result.stdout.strip().split("\n")
    return outputs

# Fonction pour changer la source audio de sortie
def change_audio_output(source_name):
    result = subprocess.run(
        ["SwitchAudioSource", "-t", "output", "-s", source_name],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

# Fonction pour exécuter une commande AppleScript
def run_applescript(script):
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

@socketio.on('connect')
def handle_connect():
    # Envoyer les données initiales
    emit('audio_outputs', {"outputs": list_audio_outputs()})
    emit('current_track', {"track_info": get_current_track()})
    emit('volume', {"volume": get_current_volume()})

@socketio.on('spotify_command')
def handle_spotify_command(data):
    command = data['command']
    if command == 'play_pause':
        script = 'tell application "Spotify" to playpause'
    elif command == 'next':
        script = 'tell application "Spotify" to next track'
    elif command == 'previous':
        script = 'tell application "Spotify" to previous track'
    
    run_applescript(script)
    # Renvoyer la track mise à jour
    emit('current_track', {"track_info": get_current_track()})

@socketio.on('set_volume')
def handle_set_volume(data):
    new_volume = data['volume']
    if 0 <= new_volume <= 100:
        script = f'set volume output volume {new_volume}'
        run_applescript(script)
        emit('volume', {"volume": new_volume})

@socketio.on('set_audio_output')
def handle_set_audio_output(data):
    source_name = data['source_name']
    success = change_audio_output(source_name)
    emit('audio_output_changed', {"success": success, "source": source_name})

def get_current_track():
    script = '''
    tell application "Spotify"
        if player state is playing then
            set trackInfo to "Now Playing: " & name of current track & " by " & artist of current track
        else
            set trackInfo to "Spotify is not playing"
        end if
    end tell
    '''
    return run_applescript(script)

def get_current_volume():
    script = 'output volume of (get volume settings)'
    return int(run_applescript(script))

@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5100)

from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit
import subprocess
import json
import platform
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Ajouter l'état global
current_state = {
    'volume': 0,
    'audio_output': None,
    'track_info': None
}

# Détection du système d'exploitation
SYSTEM = platform.system()

def run_command(command):
    """Exécute une commande système de manière unifiée"""
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode == 0
    except Exception as e:
        print(f"Error running command: {e}")
        return str(e), False

# Fonction pour lister uniquement les périphériques audio de sortie
def list_audio_outputs():
    if SYSTEM == "Darwin":  # macOS
        result, _ = run_command(["SwitchAudioSource", "-t", "output", "-a"])
        return result.split("\n")
    elif SYSTEM == "Windows":
        # Utiliser PowerShell pour lister les périphériques audio
        cmd = ['powershell', '-command', 
            "Get-AudioDevice -Playback | Select-Object -ExpandProperty Name"]
        result, _ = run_command(cmd)
        return result.split("\n")
    return []

# Fonction pour changer la source audio de sortie
def change_audio_output(source_name):
    if SYSTEM == "Darwin":
        _, success = run_command(["SwitchAudioSource", "-t", "output", "-s", source_name])
        return success
    elif SYSTEM == "Windows":
        # Changer la sortie audio sous Windows
        cmd = ['powershell', '-command', 
            f'Set-AudioDevice -Name "{source_name}"']
        _, success = run_command(cmd)
        return success
    return False

# Fonction pour exécuter une commande AppleScript
def run_applescript(script):
    if SYSTEM == "Darwin":
        result, _ = run_command(["osascript", "-e", script])
        return result
    elif SYSTEM == "Windows":
        # Convertir les commandes AppleScript en commandes Windows équivalentes
        if "Spotify" in script:
            if "playpause" in script:
                keys = "{MEDIA_PLAY_PAUSE}"
            elif "next track" in script:
                keys = "{MEDIA_NEXT_TRACK}"
            elif "previous track" in script:
                keys = "{MEDIA_PREV_TRACK}"
            cmd = ['powershell', '-command', 
                f'$wshell = New-Object -ComObject wscript.shell; $wshell.SendKeys("{keys}")']
            run_command(cmd)
            return "Command executed"
    return "Unsupported operation"

@socketio.on('connect')
def handle_connect():
    current_state['volume'] = get_current_volume()
    emit('volume', {"volume": current_state['volume']})
    emit('audio_outputs', {"outputs": list_audio_outputs()})
    emit('current_track', {"track_info": get_current_track()})

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
        set_volume(new_volume)
        current_state['volume'] = new_volume
        socketio.emit('volume', {"volume": new_volume})

@socketio.on('set_audio_output')
def handle_set_audio_output(data):
    source_name = data['source_name']
    success = change_audio_output(source_name)
    emit('audio_output_changed', {"success": success, "source": source_name})

def get_current_track():
    if SYSTEM == "Darwin":
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
    elif SYSTEM == "Windows":
        # Obtenir les infos Spotify via Windows
        cmd = ['powershell', '-command', '''
            $spotify = Get-Process spotify -ErrorAction SilentlyContinue
            if ($spotify) {
                $title = (Get-Process spotify).MainWindowTitle
                if ($title -eq "") { "Spotify is not playing" } else { "Now Playing: $title" }
            } else { "Spotify is not running" }
        ''']
        result, _ = run_command(cmd)
        return result
    return "Unsupported platform"

def get_current_volume():
    if SYSTEM == "Darwin":
        script = 'output volume of (get volume settings)'
        result = run_applescript(script)
        return int(result) if result.isdigit() else 0
    elif SYSTEM == "Windows":
        cmd = ['powershell', '-command', 
            "Get-AudioDevice -Playback | Select-Object -ExpandProperty Volume"]
        result, _ = run_command(cmd)
        try:
            return int(float(result))
        except:
            return 0
    return 0

def set_volume(volume):
    if SYSTEM == "Darwin":
        script = f'set volume output volume {volume}'
        run_applescript(script)
    elif SYSTEM == "Windows":
        cmd = ['powershell', '-command', 
            f'Set-AudioDevice -Volume {volume}']
        run_command(cmd)

def get_system_equalizer():
    try:
        # Stocker les valeurs dans une variable globale
        global current_eq_values
        if not hasattr(get_system_equalizer, 'current_eq_values'):
            get_system_equalizer.current_eq_values = {
                "32Hz": 0, "64Hz": 0, "125Hz": 0, "250Hz": 0, "500Hz": 0,
                "1kHz": 0, "2kHz": 0, "4kHz": 0, "8kHz": 0, "16kHz": 0
            }
        
        bands = [
            {"name": "32Hz", "freq": 32, "value": get_system_equalizer.current_eq_values["32Hz"]},
            {"name": "64Hz", "freq": 64, "value": get_system_equalizer.current_eq_values["64Hz"]},
            {"name": "125Hz", "freq": 125, "value": get_system_equalizer.current_eq_values["125Hz"]},
            {"name": "250Hz", "freq": 250, "value": get_system_equalizer.current_eq_values["250Hz"]},
            {"name": "500Hz", "freq": 500, "value": get_system_equalizer.current_eq_values["500Hz"]},
            {"name": "1kHz", "freq": 1000, "value": get_system_equalizer.current_eq_values["1kHz"]},
            {"name": "2kHz", "freq": 2000, "value": get_system_equalizer.current_eq_values["2kHz"]},
            {"name": "4kHz", "freq": 4000, "value": get_system_equalizer.current_eq_values["4kHz"]},
            {"name": "8kHz", "freq": 8000, "value": get_system_equalizer.current_eq_values["8kHz"]},
            {"name": "16kHz", "freq": 16000, "value": get_system_equalizer.current_eq_values["16kHz"]}
        ]
        return bands
    except Exception as e:
        print(f"Error getting equalizer: {e}")
        return []

def set_system_equalizer_band(band_name, value):
    try:
        # Mettre à jour la valeur stockée
        get_system_equalizer.current_eq_values[band_name] = value
        
        # Construire la commande pour modifier l'égaliseur système
        cmd = ['osascript', '-e', f'''
            tell application "System Events"
                tell process "Audio MIDI Setup"
                    set value of slider "{band_name}" of window 1 to {value}
                end tell
            end tell
        ''']
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(f"Setting {band_name} to {value}dB - Result: {result.stdout}")
        
        # Retourner toutes les bandes avec leurs valeurs actuelles
        return True
    except Exception as e:
        print(f"Error setting equalizer: {e}")
        return False

@socketio.on('get_equalizer')
def handle_get_equalizer():
    emit('equalizer_bands', {"bands": get_system_equalizer()})

@socketio.on('set_equalizer_band')
def handle_set_equalizer_band(data):
    band_name = data['band']
    value = float(data['value'])
    if -12 <= value <= 12:
        success = set_system_equalizer_band(band_name, value)
        print(f"Setting {band_name} to {value}dB - Success: {success}")
        # Renvoyer toutes les bandes mises à jour
        emit('equalizer_updated', {
            "success": success,
            "bands": get_system_equalizer()
        })

@app.route('/')
def home():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=5100)

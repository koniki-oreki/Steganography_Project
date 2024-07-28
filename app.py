import os
import shutil
from stegano import lsb
from pydub import AudioSegment
from flask import Flask, request, render_template, send_file, redirect, url_for
from werkzeug.utils import secure_filename
import subprocess

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
MAPPINGS_FOLDER = 'mappings'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'mp4', 'avi', 'mov', 'mkv', 'wav', 'mp3', 'flac', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.config['MAPPINGS_FOLDER'] = MAPPINGS_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clear_static_folder():
    for filename in os.listdir(app.config['STATIC_FOLDER']):
        file_path = os.path.join(app.config['STATIC_FOLDER'], filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

def clear_uploads_folder():
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/select/<steganography_type>', methods=['GET'])
def select(steganography_type):
    if steganography_type not in ['image', 'audio', 'text']:
        return redirect(url_for('index'))
    return render_template('select.html', steganography_type=steganography_type)

@app.route('/encode', methods=['POST'])
def encode():
    print(request.form)
    steganography_type = request.form['type']
    file = request.files['file']
    message = request.form['message']
    save_path = request.form.get('save_path', '').strip()

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        encoded_file_path = None
        pass_key = None

        # Process encoding based on type
        if steganography_type == 'image':
            encoded_file_path = encode_image(file_path, message)
        elif steganography_type == 'video':
            encoded_file_path, pass_key = encode_video(file_path, message)
        elif steganography_type == 'audio':
            encoded_file_path = encode_audio(file_path, message)
        elif steganography_type == 'text':
            encoded_file_path = encode_text(file_path, message)

        # Save the encoded file to the specified path
        if save_path and encoded_file_path:
            if not os.path.isabs(save_path):
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], save_path)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            os.rename(encoded_file_path, save_path)
            encoded_file_path = save_path

        # If video, show pass key in result.html
        if steganography_type == 'video' and pass_key is not None:
            return render_template('result.html', pass_key=pass_key, file_path=encoded_file_path)

        # For other types, download the file directly
        if encoded_file_path:
            return send_file(encoded_file_path, as_attachment=True)

    return 'Invalid file type or no file uploaded.'

@app.route('/download', methods=['GET'])
def download_file():
    file_path = request.args.get('file_path', None)
    if file_path :
        return send_file(file_path, as_attachment=True)
    return 'File not found.'

@app.route('/decode', methods=['POST'])
def decode():
    steganography_type = request.form['type']
    file = request.files['file']

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        if steganography_type == 'image':
            message = decode_image(file_path)
        elif steganography_type == 'video':
            message = decode_video(file_path)
        elif steganography_type == 'audio':
            message = decode_audio(file_path)
        elif steganography_type == 'text':
            message = decode_text(file_path)

        clear_static_folder()
        clear_uploads_folder()

        return render_template('result.html', message=message, steganography_type=steganography_type)
    

# Image Steganography
def encode_image(file_path, message):
    secret = lsb.hide(file_path, message)
    secret.save(file_path)
    return file_path

def decode_image(file_path):
    return lsb.reveal(file_path)

# Video Steganography
def extract_frames(video_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    command = [
        'ffmpeg',
        '-i', video_path,
        os.path.join(output_dir, 'frame_%04d.png')
    ]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error extracting frames: {e}")
        raise

def encode_text_in_frames(frames_dir, text):
    frame_files = sorted(os.listdir(frames_dir))
    for i, letter in enumerate(text):
        if i >= len(frame_files):
            break
        frame_file = frame_files[i]
        frame_path = os.path.join(frames_dir, frame_file)
        encoded_img = lsb.hide(frame_path, letter)
        encoded_img.save(frame_path)

def frames_to_video(frames_dir, output_video_path, frame_rate=30):
    command = [
        'ffmpeg',
        '-framerate', str(frame_rate),
        '-i', os.path.join(frames_dir, 'frame_%04d.png'),
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        output_video_path
    ]
    print(f"Running ffmpeg command: {' '.join(command)}")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error converting frames to video: {e}")
        raise
def encode_video(input_video_path, message):
    mappings_folder = os.path.join(app.config['MAPPINGS_FOLDER'], os.path.basename(input_video_path))
    frames_folder = os.path.join(mappings_folder, 'frames')

    extract_frames(input_video_path, frames_folder)
    encode_text_in_frames(frames_folder, message)
    
    output_video_path = os.path.join(app.config['STATIC_FOLDER'], os.path.basename(input_video_path))
    frames_to_video(frames_folder, output_video_path)
    
    # Calculate the pass key
    pass_key = len(message) ^ 7777

    # Return the output video path and pass key
    return output_video_path, pass_key

def decode_text_from_frames(frames_dir, text_length):
    frame_files = sorted(os.listdir(frames_dir))
    decoded_message = ""
    for i in range(text_length):
        frame_file = frame_files[i]
        frame_path = os.path.join(frames_dir, frame_file)
        decoded_letter = lsb.reveal(frame_path)
        if decoded_letter:
            decoded_message += decoded_letter
    return decoded_message


def decode_video(input_video_path):
    mappings_folder = os.path.join(app.config['MAPPINGS_FOLDER'], os.path.basename(input_video_path))
    frames_folder = os.path.join(mappings_folder, 'frames')
    
    text_length = int(request.form['pass_key']) ^ 7777  # Retrieve the pass_key from the form
    decoded_message = decode_text_from_frames(frames_folder, text_length)
    try:
        shutil.rmtree(frames_folder)
        shutil.rmtree(mappings_folder)
    except Exception as e:
        print(f"Error during cleanup: {e}")
    
    return decoded_message if decoded_message else 'No message found.'

# Audio Steganography
def encode_audio(file_path, message):
    audio = AudioSegment.from_file(file_path)
    encoded_audio = encode_message_in_audio(audio, message)
    encoded_audio.export(file_path, format='wav')
    return file_path

def encode_message_in_audio(audio, message):
    raw_data = bytearray(audio.raw_data)
    message_binary = ''.join(format(ord(char), '08b') for char in message) + '00000000'

    if len(message_binary) > len(raw_data) * 8:
        raise ValueError("Message is too long for the provided audio file.")

    for i, bit in enumerate(message_binary):
        byte_index = i // 8
        bit_index = i % 8
        byte = raw_data[byte_index]
        raw_data[byte_index] = (byte & ~(1 << bit_index)) | (int(bit) << bit_index)

    encoded_audio = AudioSegment(
        raw_data,
        frame_rate=audio.frame_rate,
        sample_width=audio.sample_width,
        channels=audio.channels
    )

    return encoded_audio

def decode_message_from_audio(audio):
    raw_data = bytearray(audio.raw_data)
    extracted_bits = []

    for byte in raw_data:
        for bit_index in range(8):
            extracted_bits.append(str((byte >> bit_index) & 1))

    binary_message = ''.join(extracted_bits)
    
    decoded_message = ''
    for i in range(0, len(binary_message), 8):
        byte = binary_message[i:i+8]
        if len(byte) == 8:
            char = chr(int(byte, 2))
            if char == '\x00':
                break
            decoded_message += char

    return decoded_message

def decode_audio(file_path):
    audio = AudioSegment.from_file(file_path)
    return decode_message_from_audio(audio)

# Text Steganography
def encode_text(file_path, message):
    with open(file_path, 'w') as file:
        file.write(message)
    return file_path

def decode_text(file_path):
    with open(file_path, 'r') as file:
        return file.read() 

@app.errorhandler(405)
def method_not_allowed(e):
    print( "Method Not Allowed. Please use POST request.", 405)

if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True)
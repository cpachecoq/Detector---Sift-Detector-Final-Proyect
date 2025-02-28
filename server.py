from flask import Flask, Response, render_template_string, request, jsonify
import cv2
import numpy as np
import os
import psutil
import time

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Aumenta el tamaño máximo a 100MB

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

sift = cv2.SIFT_create()

REFERENCE_WIDTH = 300
REFERENCE_HEIGHT = 300

reference_images = {
    'maiz': cv2.imread('maiz.jpg', cv2.IMREAD_GRAYSCALE),
    'mascara': cv2.imread('mascara.png', cv2.IMREAD_GRAYSCALE)
}
reference_descriptors = {}

for key, img in reference_images.items():
    if img is not None:
        img = cv2.resize(img, (REFERENCE_WIDTH, REFERENCE_HEIGHT))
        keypoints, descriptors = sift.detectAndCompute(img, None)
        reference_descriptors[key] = (keypoints, descriptors)
        reference_images[key] = img  
        print(f"🔍 {key}: {len(keypoints)} keypoints detectados en la imagen de referencia")

frame_count = 0
start_time = time.time()
total_data_sent = 0

@app.route('/')
def index():
    return render_template_string("""
    <html>
        <head>
            <title>Streaming de Video Procesado</title>
            <script>
                function updateStats() {
                    fetch('/stats')
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('ram_usage').innerText = 'RAM: ' + data.ram + ' MB';
                            document.getElementById('fps').innerText = 'FPS: ' + data.fps;
                            document.getElementById('bandwidth').innerText = 'Ancho de Banda: ' + data.bandwidth + ' KB/s';
                        });
                }
                setInterval(updateStats, 1000);
            </script>
        </head>
        <body>
            <h1>Streaming en Tiempo Real del Video Procesado</h1>
            <p id="ram_usage">RAM: Cargando...</p>
            <p id="fps">FPS: Cargando...</p>
            <p id="bandwidth">Ancho de Banda: Cargando...</p>
            <img src="/video_feed" width="840" height="680">
        </body>
    </html>
    """)

@app.route('/upload_video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return "No se recibió ningún video", 400
    
    file = request.files['video']
    video_path = os.path.join(UPLOAD_FOLDER, "uploaded_video.mp4")
    file.save(video_path)
    print("Video recibido y guardado en", video_path)
    return "Video subido correctamente", 200

def generate_frames():
    global frame_count, total_data_sent, start_time
    cap = cv2.VideoCapture(os.path.join(UPLOAD_FOLDER, "uploaded_video.mp4"))
    bf = cv2.BFMatcher()
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
        
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        keypoints_frame, descriptors_frame = sift.detectAndCompute(gray_frame, None)
        
        if descriptors_frame is not None:
            for key, (keypoints_ref, descriptors_ref) in reference_descriptors.items():
                if descriptors_ref is not None:
                    matches = bf.knnMatch(descriptors_ref, descriptors_frame, k=2)
                    good_matches = [m for m, n in matches if m.distance < 0.6 * n.distance]
                    frame = cv2.drawMatches(reference_images[key], keypoints_ref, frame, keypoints_frame, good_matches, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        total_data_sent += len(frame_bytes)
        frame_count += 1
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stats')
def stats():
    global frame_count, total_data_sent, start_time
    elapsed_time = time.time() - start_time
    if elapsed_time == 0:
        elapsed_time = 0.0001  # Para evitar división por cero
    ram_usage = psutil.virtual_memory().used / (1024 * 1024)  # Convertir a MB
    fps = frame_count / elapsed_time
    bandwidth = (total_data_sent / 1024) / elapsed_time  # Convertir a KB/s
    
    return jsonify({
        "ram": round(ram_usage, 2),
        "fps": round(fps, 2),
        "bandwidth": round(bandwidth, 2)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

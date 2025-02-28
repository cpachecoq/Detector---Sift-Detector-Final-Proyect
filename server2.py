from flask import Flask, Response, render_template_string, request, jsonify
import cv2
import numpy as np
import os
import psutil
import time
import joblib
from skimage.feature import hog

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # Aumenta el tamaño máximo a 100MB

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

#  Cargar modelo SVM entrenado
modelo = joblib.load("modelo_svm_hog5.pkl")

#  Parámetros HOG (Mismos usados en el entrenamiento)
hog_params = {
    "orientations": 12,
    "pixels_per_cell": (8, 8),
    "cells_per_block": (2, 2),
    "block_norm": "L2-Hys"
}

#  Función para detección con ventana deslizante (Sliding Window Multi-Escala)
def detect_with_sliding_window(frame, step_size=146, scales=[(710, 710)]):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detections = []

    for window_size in scales:  # Solo ventanas grandes
        for y in range(0, gray.shape[0] - window_size[1], step_size):
            for x in range(0, gray.shape[1] - window_size[0], step_size):
                roi = gray[y:y+window_size[1], x:x+window_size[0]]
                roi_resized = cv2.resize(roi, (64, 64))  # 🔹 Mantener tamaño HOG

                features = hog(roi_resized, **hog_params)
                features = np.array(features).reshape(1, -1)

                prediction = modelo.predict(features)[0]
                if prediction == 0 or prediction == 1:  # Solo marcar si es válido
                    detections.append((x, y, window_size[0], window_size[1], prediction))

    return detections

frame_count = 0
start_time = time.time()
total_data_sent = 0

def generate_frames():
    global frame_count, total_data_sent, start_time
    cap = cv2.VideoCapture(os.path.join(UPLOAD_FOLDER, "uploaded_video.mp4"))
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        #  Aplicar detección con Sliding Window
        detections = detect_with_sliding_window(frame)

        for (x, y, w, h, label) in detections:
            color = (0, 255, 0) if label == 0 else (0, 0, 255)  
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, "Ganado" if label == 0 else "Radiacion", (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        total_data_sent += len(frame_bytes)
        frame_count += 1
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

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
    print(" Video recibido y guardado en", video_path)
    return "Video subido correctamente", 200

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stats')
def stats():
    global frame_count, total_data_sent, start_time
    elapsed_time = time.time() - start_time
    if elapsed_time == 0:
        elapsed_time = 0.0001  
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

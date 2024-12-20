from flask import Flask, request, jsonify, render_template
from PIL import Image
from queue import Queue
from threading import Thread
from transformers import BlipProcessor, BlipForConditionalGeneration
import argostranslate.package
import argostranslate.translate
import os

app = Flask(__name__)

# Создание папки для загрузки изображений, если ее нет
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Загрузка и установка пакета Argos Translate
argostranslate.package.update_package_index()
available_packages = argostranslate.package.get_available_packages()
package_to_install = next(
    filter(
        lambda x: x.from_code == 'en' and x.to_code == 'ru', available_packages
    )
)
argostranslate.package.install_from_path(package_to_install.download())

# Инициализация модели и процессора
processor = BlipProcessor.from_pretrained(
    "Salesforce/blip-image-captioning-large", cache_dir='/app/cache', local_files_only=True)
model = BlipForConditionalGeneration.from_pretrained(
    "Salesforce/blip-image-captioning-large", cache_dir='/app/cache',local_files_only=True).to("cuda")

# Инициализация очереди и функции-обработчика
MAX_QUEUE_SIZE = 10
image_queue = Queue()


def worker(image_queue):
    while True:
        data = image_queue.get()
        print(data, flush=True)

        if data is None:
            break
        img_path, text_queue = data
        
        print(img_path, flush=True)
        # Проверка существования файла
        if not os.path.exists(img_path,):
            print(f"File not found: {img_path}", flush=True)
            text_queue.put("Error: File not found")
            image_queue.task_done()
            continue

        try:
            raw_image = Image.open(img_path).convert('RGB')
            text = "a photography of"
            print(raw_image, text, flush=True)
            inputs = processor(raw_image, text, return_tensors="pt").to("cuda")
            out = model.generate(**inputs)
            text = processor.decode(out[0], skip_special_tokens=True)

            translatedText = argostranslate.translate.translate(text, 'en', 'ru')
            text_queue.put(translatedText)
        except Exception as e:
            print(f"Error while processing image: {str(e)}", flush=True)
            text_queue.put("Error: " + str(e))
        
        image_queue.task_done()


Thread(target=worker, daemon=True, args=(image_queue,)).start()


@app.route("/image", methods=["POST"])
def process_image():

    if image_queue.qsize() >= MAX_QUEUE_SIZE:
        return "Queue is full", 503

    try:
        file = request.files["file"]
        
        img_path = os.path.join(UPLOAD_FOLDER, file.filename)
        print(f"Saving image to: {img_path}")
        file.save(img_path)
        print("File saved successfully")

        text_queue = Queue()
        image_queue.put((img_path, text_queue))
        print('put')
        text = text_queue.get()

        return jsonify({"caption": text}), 200

    except Exception as e:
        print(f"Error while processing file: {str(e)}")
        return str(e), 500

@app.route("/ui", methods=["GET"])
def ui():
    return render_template("upload.html")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5050)


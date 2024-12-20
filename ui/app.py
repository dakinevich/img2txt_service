from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
import requests
import threading
import uuid  # Добавлено для генерации уникальных ID
import mysql.connector
import logging
from datetime import timedelta

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = 'your_secret_key'  # Set a secret key for session management
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=3)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Fixed credentials
USERNAME = 'admin'
PASSWORD = 'password'

# Хранение карточек в памяти с уникальным ID
# Database connection setup
db_config = {
    'user': 'carduser',
    'password': 'cardpassword',
    'host': 'database',
    'database': 'carddb'
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

def save_card_to_db(image_filename, description):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cards (image_filename, description) VALUES (%s, %s)",
        (image_filename, description)
    )
    conn.commit()
    cursor.close()
    conn.close()

def update_card_description(card_id, description):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cards SET description = %s WHERE id = %s",
        (description, card_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def delete_card_from_db(card_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Retrieve the image filename before deleting the record
        cursor.execute("SELECT image_filename FROM cards WHERE id = %s", (card_id,))
        result = cursor.fetchone()
        if result:
            image_filename = result[0]
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            
            # Delete the record from the database
            cursor.execute("DELETE FROM cards WHERE id = %s", (card_id,))
            conn.commit()
            
            # Delete the image file from the file system
            if os.path.exists(image_path):
                os.remove(image_path)
            else:
                logging.warning(f"File {image_path} not found.")
        
        # Close the database connection
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Error deleting card {card_id}: {e}")

def get_all_cards():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cards")
    cards = cursor.fetchall()
    cursor.close()
    conn.close()
    return cards

def process_image(image_filename, image_path):
    with open(image_path, 'rb') as file:
        response = requests.post('http://host.docker.internal:5050/image', files={'file': file})
    
    description = response.json().get('caption', 'Нет описания')

    # Update the card with the obtained description
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cards SET description = %s WHERE image_filename = %s",
        (description, image_filename)
    )
    conn.commit()
    cursor.close()
    conn.close()

@app.before_request
def check_session():
    session.permanent = True  
    allow = request.path.startswith('/login') or request.path.startswith('/static')
    if 'logged_in' not in session and not allow:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == USERNAME and password == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        images = request.files.getlist('images')
        allowed_extensions = {'jpg', 'jpeg', 'png', 'heif', 'heic'}
        responses = []

        for image in images:
            if image and image.filename.split('.')[-1].lower() in allowed_extensions:
                image_filename = str(uuid.uuid4()) + "_" + image.filename
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                image.save(image_path)
                
                # Save card to database without specifying the id
                save_card_to_db(image_filename, 'Загрузка...')
                
                # Start background processing
                thread = threading.Thread(target=process_image, args=(image_filename, image_path))
                thread.start()
                
                responses.append({'image': image_filename, 'description': 'Загрузка...'})

        return jsonify(responses)

    cards = get_all_cards()
    return render_template('index.html', cards=cards)

@app.route('/delete/<string:card_id>')
def delete(card_id):
    delete_card_from_db(card_id)
    return redirect(url_for('index'))

@app.route('/get_description/<string:card_id>')
def get_description(card_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT description FROM cards WHERE id = %s", (card_id,))
    card = cursor.fetchone()
    cursor.close()
    conn.close()
    if card:
        return jsonify({'description': card['description']})
    return jsonify({'description': 'Не найдено'}), 404

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM cards WHERE description LIKE %s", ('%' + query + '%',))
    cards = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', cards=cards)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)

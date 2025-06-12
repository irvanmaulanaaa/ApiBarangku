from flask import Flask, jsonify, request, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from dotenv import load_dotenv
from datetime import datetime


# load environment variables
load_dotenv()

# create an instance
app = Flask(__name__)
CORS(app)

# db config
DB_USER = os.getenv('MYSQL_USER')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD')
DB_HOST = os.getenv('MYSQL_HOST')
DB_PORT = os.getenv('MYSQL_PORT', 3306) # Provide a default for port
DB_NAME = os.getenv('MYSQL_DB')

# create database
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# create database object
db = SQLAlchemy(app)

# make sure uploads folder exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# create model
class Barang(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(225), nullable=False)
    image_path = db.Column(db.String(225), nullable=True)
    nama_barang = db.Column(db.String(225), nullable=False)
    kategori = db.Column(db.String(225), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'imageUrl': f'{request.host_url.rstrip('/')}/{self.image_path}' if self.image_path else None,
            'namaBarang': self.nama_barang,
            'kategori': self.kategori,
            'jumlah': self.jumlah
        }

# create db
with app.app_context():
    db.create_all()


# utility function
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


    
def get_user_email_or_401():
    email = request.headers.get('Authorization')
    if not email:
        return None, {'status': 'error', 
                      'message': 'Anda harus login terlebih dahulu'}, 401
    return email, None, None

def get_barang_or_404(id, email):
    barang = Barang.query.filter_by(id=id).first()
    if not barang:
        return None, {'status': 'error', 'message': 'Barang tidak ditemukan'}, 404

    if barang.user_id == email or email == '__admin__':
        return barang, None, None
    
    return None, {'status': 'error', 
                  'message': "Forbidden: Anda tidak memiliki akses"}, 403


def save_image(image, email): # Removed 'index' parameter
    if image and image.filename and allowed_file(image.filename):
        extension = image.filename.rsplit('.', 1)[1].lower()
        
        # Generate a unique filename using timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        # Use a sanitized version of the email for the filename
        sanitized_email_prefix = email.split('@')[0].replace('.', '_').replace('-', '_') 
        filename = f'{sanitized_email_prefix}_{timestamp}.{extension}'
        
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(image_path)

        return f'static/uploads/{filename}'
    return None 

    
def delete_image_file(image_path):
    if image_path:
        full_path = os.path.join(app.root_path, image_path.lstrip('/'))
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception as e:
            abort(500, description=f'Failed to delete image file: {str(e)}')


# routes

# https://www.barangku.com/
@app.route('/')
def home():
    return jsonify({
        'message': 'Selamat datang di API Barangku'
    }), 200


# (GET) https://www.barangku.com/barangku
@app.route('/barangku', methods=['GET'])
def get_all_barang():
    email = request.headers.get('Authorization')

    if not email:
        return jsonify([])
    
    if (email == '__admin__'):
        query = Barang.query
    else:
        query = Barang.query.filter_by(user_id=email)
    
    barang = query.all()

    return jsonify([b.to_dict() for b in barang]), 200


# (GET) https://www.barangku.com/barang/78
@app.route('/barangku/<int:id>', methods=['GET'])
def get_barang(id):
    email, error_data, status_code = get_user_email_or_401()
    if error_data:
        return jsonify(error_data), status_code
    
    barang, error_data, status_code = get_barang_or_404(id, email)

    if error_data:
        return jsonify(error_data), status_code

    if not barang:
        return jsonify({'status': 'error', 'message': 'Barang tidak ditemukan'}), 404
    
    return jsonify(barang.to_dict())


# (POST) https://www.barangku.com/barangku
@app.route('/barangku', methods=['POST'])
def add_barang():
    email, error_data, status_code = get_user_email_or_401()
    if error_data:
        return jsonify(error_data), status_code
    
    # use multipart/form-data -> image + form fields
    image = request.files.get('image')  # .get() if theres no file then None

    nama_barang = request.form.get('namaBarang')
    kategori = request.form.get('kategori')
    jumlah = request.form.get('jumlah', type=int)

    if not all([nama_barang, kategori, jumlah]):
        return jsonify({'status': 'error',
                        'message': 'Data tidak boleh kosong'}), 400
    
    image_path = None
    if image and image.filename:
        if allowed_file(image.filename):
            index = Barang.query.filter_by(user_id=email).count()
            image_path = save_image(image, email)
        else:
            return jsonify({'status': 'error',
                            'message': 'Format gambar salah (hanya JPG, JPEG, PNG)'}), 400
    
    # insert to db
    barang = Barang(
        user_id = email,
        image_path = image_path,
        nama_barang = nama_barang,
        kategori = kategori,
        jumlah = jumlah
    )

    db.session.add(barang)
    db.session.commit()

    return jsonify({'status': 'success', 'id': barang.id}), 201


# (PUT) https://www.barangku.com/barangku/201
@app.route('/barangku/<int:id>', methods=['PUT'])
def update_reading(id):
    email, error_data, status_code = get_user_email_or_401()
    if error_data:
        return jsonify(error_data), status_code

    barang, error_data, status_code = get_barang_or_404(id, email)
    if error_data:
        return jsonify(error_data), status_code
    
    barang.nama_barang = request.form.get('namaBarang')
    barang.kategori = request.form.get('kategori')
    barang.jumlah = request.form.get('jumlah', type=int)

    # update to db
    db.session.commit()

    return jsonify({'status': 'success', 
                    'message': 'Barang updated'})
    

# (DELETE) https://www.barangku.com/barangku/900
@app.route('/barangku/<int:id>', methods=['DELETE'])
def delete_barang(id):
    email, error_data, status_code = get_user_email_or_401()
    if error_data:
        return jsonify(error_data), status_code

    barang, error_data, status_code = get_barang_or_404(id, email)
    if error_data:
        return jsonify(error_data), status_code
    
    # remove the actual image ppath
    if barang.image_path:
        delete_image_file(barang.image_path)
    
    # delete resource in db
    db.session.delete(barang)
    db.session.commit()

    return jsonify({'status': 'success',
                    'message': 'Barang terhapus'})
    


if __name__ == '__main__':
    app.run(debug=True)
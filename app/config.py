import os

class Config:
    # SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')
    SECRET_KEY = 'supersecretkey123'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///users.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "messenger.db")

engine = create_engine(f'sqlite:///{db_path}', 
                       echo=False, 
                       connect_args={'check_same_thread': False})

Base = declarative_base()
Session = sessionmaker(bind=engine)


class Users(Base, UserMixin):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    nickname = Column(String(50), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)

    def set_password(self, password):
        """Хешування пароля для безпеки"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Перевірка введеного пароля"""
        return check_password_hash(self.password_hash, password)

class Friends(Base):
    __tablename__ = 'friends'
    
    id = Column(Integer, primary_key=True)
    sender = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(Boolean, default=False)

    sender_user = relationship("Users", foreign_keys=[sender])
    recipient_user = relationship("Users", foreign_keys=[recipient])

class Messages(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    sender = Column(Integer, ForeignKey('users.id'), nullable=False)
    recipient = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_text = Column(Text, nullable=False)
    status_check = Column(Boolean, default=False) 

    sender_user = relationship("Users", foreign_keys=[sender])

Base.metadata.create_all(engine)

if __name__ == "__main__":
    print(f"Базу даних налаштовано за шляхом: {db_path}")
import os
import bcrypt
from datetime import datetime
from sqlalchemy import create_engine, String, Integer, ForeignKey, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship, sessionmaker, DeclarativeBase

DATABASE_URL = "sqlite:///online_restaurant.db"
engine = create_engine(DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Users(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(50), unique=True)

    orders = relationship("Orders", back_populates='user')
    reservations = relationship("Reservation", back_populates='user')

    # Flask-Login requirements
    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return str(self.id)

    def set_password(self, password: str):
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str):
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))

class Menu(Base):
    __tablename__ = "menu"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    weight: Mapped[str] = mapped_column(String)
    ingredients: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    price: Mapped[int] = mapped_column()
    discount: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    file_name: Mapped[str] = mapped_column(String)

class Orders(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_list: Mapped[dict] = mapped_column(JSON)
    order_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    
    user = relationship("Users", back_populates="orders")

class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(primary_key=True)
    time_start: Mapped[datetime] = mapped_column(DateTime)
    type_table: Mapped[str] = mapped_column(String)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    
    user = relationship("Users", back_populates="reservations")

if __name__ == '__main__':
    if os.path.exists("online_restaurant.db"):
        os.remove("online_restaurant.db")
    Base.metadata.create_all(engine)
    
    # Створюємо дефолтного адміна
    with Session() as db:
        admin = Users(nickname="Admin", email="admin@restaurant.com")
        admin.set_password("admin123")
        db.add(admin)
        db.commit()
    print("✅ База оновлена. Адмін: Admin / Пароль: admin123")
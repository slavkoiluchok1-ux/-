from sqlalchemy import create_engine, String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship, sessionmaker, DeclarativeBase

engine = create_engine("sqlite:///shoe_store.db", echo=False)
Session = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    price: Mapped[float] = mapped_column(Float)
    image_filename: Mapped[str] = mapped_column(String(255))
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="product")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(100))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product: Mapped["Product"] = relationship("Product", back_populates="orders")

def init_db():
    Base.metadata.create_all(engine)
    with Session() as session:
        if session.query(Product).count() == 0:
            products = [
                Product(name="Nike Air Max", description="Класика для бігу", price=4300, image_filename="nike_air_max.png"),
                Product(name="Adidas Ultraboost", description="Максимальний комфорт", price=3100, image_filename="adidas_ultraboost.png"),
                Product(name="Puma RS-X", description="Вуличний стиль", price=3750, image_filename="puma_rsx.png"),
                Product(name="Reebok Classic", description="Ретро дизайн", price=2900, image_filename="reebok_classic.png"),
                Product(name="New Balance 574", description="Стиль та зручність", price=4100, image_filename="nb_574.png"),
                Product(name="Asics Gel", description="Для довгих прогулянок", price=5200, image_filename="asics_gel.png")
            ]
            session.add_all(products)
            session.commit()
            print("База даних створена і заповнена!")

if __name__ == "__main__":
    init_db()
from __future__ import annotations

import enum
import re
import unicodedata

import bcrypt
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    value = value.strip("-_")
    return value or "tag"


class ProductType(str, enum.Enum):
    PHYSICAL = "physical"
    DIGITAL = "digital"
    GAME_ITEM = "game_item"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    display_name = Column(String(120), nullable=True)
    phone = Column(String(50), nullable=True)
    viber = Column(String(80), nullable=True)
    telegram = Column(String(80), nullable=True)
    instagram = Column(String(80), nullable=True)
    whatsapp = Column(String(80), nullable=True)
    public_email = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    specialty = Column(String(200), nullable=True)
    experience = Column(String(255), nullable=True)
    skills = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    products = relationship("Product", back_populates="seller", foreign_keys="Product.user_id")
    reviews = relationship("Review", back_populates="user")
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="reporter", foreign_keys="Report.reporter_id")
    complaints = relationship("Report", back_populates="reporter", foreign_keys="Report.reporter_id")
    favorites = relationship("Favorite", back_populates="user")
    cart_items = relationship("CartItem", back_populates="user")
    orders = relationship("Order", back_populates="user")

    def set_password(self, raw_password: str) -> None:
        self.hashed_password = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, raw_password: str) -> bool:
        if not self.hashed_password:
            return False
        return bcrypt.checkpw(raw_password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @property
    def role(self) -> str:
        if self.is_superuser:
            return "superadmin"
        if self.is_admin:
            return "admin"
        return "user"

    @property
    def profile_display_name(self) -> str:
        return (self.display_name or self.username).strip() if self.display_name else self.username


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(250), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Integer, nullable=False, default=0)
    sale_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    sku = Column(String(120), nullable=True)
    product_type = Column(
        SAEnum(ProductType, values_callable=lambda enum_cls: [item.value for item in enum_cls], native_enum=False),
        nullable=False,
        default=ProductType.PHYSICAL,
    )
    is_draft = Column(Boolean, nullable=False, default=False)
    attributes = Column(JSON, nullable=True)
    digital_content = Column(Text, nullable=True)
    weight_dimensions = Column(String(200), nullable=True)
    shipping_options = Column(String(250), nullable=True)
    platform_server = Column(String(200), nullable=True)
    rarity = Column(String(120), nullable=True)
    execution_time = Column(String(200), nullable=True)
    seller_phone = Column(String(80), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sales_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    seller = relationship("User", back_populates="products", foreign_keys=[user_id])
    media = relationship("ProductMedia", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="product", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="product", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="product", cascade="all, delete-orphan")
    cart_items = relationship("CartItem", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")
    tags = relationship(
        "Tag",
        secondary="product_tags",
        back_populates="products",
        lazy="selectin",
    )

    @property
    def stock(self) -> int:
        return int(self.quantity or 0)

    @stock.setter
    def stock(self, value: int) -> None:
        self.quantity = int(value or 0)

    @property
    def owner_id(self) -> int:
        return int(self.user_id)


product_tags = Table(
    "product_tags",
    Base.metadata,
    Column("product_id", ForeignKey("products.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    products = relationship(
        "Product",
        secondary="product_tags",
        back_populates="tags",
    )


class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    media_type = Column(String(20), nullable=False)

    product = relationship("Product", back_populates="media")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product = relationship("Product", back_populates="reviews")
    user = relationship("User", back_populates="reviews")
    media = relationship("ReviewMedia", back_populates="review", cascade="all, delete-orphan")


class ReviewMedia(Base):
    __tablename__ = "review_media"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("reviews.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    media_type = Column(String(20), nullable=False)

    review = relationship("Review", back_populates="media")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    product = relationship("Product", back_populates="comments")
    user = relationship("User", back_populates="comments")
    reports = relationship("Report", back_populates="comment", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reported_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    reason = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    reporter = relationship("User", foreign_keys=[reporter_id], back_populates="reports")
    reported_user = relationship("User", foreign_keys=[reported_user_id], back_populates=None)
    product = relationship("Product", back_populates="reports")
    comment = relationship("Comment", back_populates="reports")


Complaint = Report


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorite_user_product"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    user = relationship("User", back_populates="favorites")
    product = relationship("Product", back_populates="favorites")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_price = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="created")
    delivery_address = Column(String(500), nullable=False, default="")
    payment_method = Column(String(100), nullable=False, default="Оплата при отриманні")
    phone = Column(String(50), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price_at_purchase = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    title = Column(String(200), nullable=True)
    specialty = Column(String(200), nullable=True)
    experience_years = Column(String(80), nullable=True)
    experience = Column(String(255), nullable=True)
    skills = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    cv_file_path = Column(String(500), nullable=True)
    public_contacts = Column(Text, nullable=True)

    display_name = Column(String(120), nullable=True)
    phone = Column(String(50), nullable=True)
    viber = Column(String(80), nullable=True)
    telegram = Column(String(80), nullable=True)
    instagram = Column(String(80), nullable=True)
    whatsapp = Column(String(80), nullable=True)
    public_email = Column(String(255), nullable=True)

    status = Column(String(30), default="pending", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", backref="resume")

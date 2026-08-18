from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserLogin(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    is_active: bool = True
    is_admin: bool = False
    is_superuser: bool = False
    display_name: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None


class UserPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    phone: Optional[str] = None
    viber: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    whatsapp: Optional[str] = None
    public_email: Optional[str] = None
    bio: Optional[str] = None
    specialty: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None


class ResumeCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: Optional[str] = None
    specialty: Optional[str] = None
    experience_years: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    bio: Optional[str] = None
    summary: Optional[str] = None
    public_contacts: Optional[str] = None
    cv_file_path: Optional[str] = None
    status: Optional[str] = "pending"

    @field_validator(
        "title",
        "specialty",
        "experience_years",
        "experience",
        "skills",
        "bio",
        "summary",
        "public_contacts",
        "cv_file_path",
        "status",
    )
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: Optional[str] = None
    specialty: Optional[str] = None
    experience_years: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    bio: Optional[str] = None
    summary: Optional[str] = None
    public_contacts: Optional[str] = None
    cv_file_path: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = None
    viber: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    whatsapp: Optional[str] = None
    public_email: Optional[str] = None
    bio: Optional[str] = None
    specialty: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None

    @field_validator(
        "display_name",
        "phone",
        "viber",
        "telegram",
        "instagram",
        "whatsapp",
        "public_email",
        "bio",
        "specialty",
        "experience",
        "skills",
    )
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


UserProfileUpdate = UserUpdate


class ProductMediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    file_path: str
    media_type: Literal["photo", "video"]


class ProductMediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    file_path: str
    media_type: Literal["photo", "video"]


class ProductCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=250)
    description: str = Field(..., min_length=5)
    price: int = Field(..., ge=0)
    quantity: int = Field(..., ge=0)
    seller_phone: Optional[str] = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price: int
    quantity: int
    seller_phone: Optional[str] = None
    user_id: int
    sales_count: int = 0
    created_at: Optional[datetime] = None
    media: list[ProductMediaResponse] = Field(default_factory=list)


class ProductListOut(ProductResponse):
    image_url: Optional[str] = None
    average_rating: float = 0.0


class ProductOut(ProductListOut):
    pass


class ReviewMediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_id: int
    file_path: str
    media_type: Literal["photo", "video"]


class ReviewMediaOut(ReviewMediaResponse):
    pass


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    user_id: int
    rating: int
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
    username: Optional[str] = None
    media: list[ReviewMediaResponse] = Field(default_factory=list)


class ReviewOut(ReviewResponse):
    pass


class ProductDetailOut(ProductListOut):
    media: list[ProductMediaOut] = Field(default_factory=list)
    reviews: list[ReviewOut] = Field(default_factory=list)


class CartItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    item_id: int | None = None
    product_id: int | None = None
    quantity: int


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: int
    quantity: int
    product: Optional[ProductListOut] = None


class FavoriteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    product_id: int
    product: Optional[ProductListOut] = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    product_id: int
    quantity: int
    price_at_purchase: float
    product_title: Optional[str] = None
    product_image: Optional[str] = None


class OrderCreate(BaseModel):
    delivery_address: str = Field(..., min_length=3, max_length=500)
    payment_method: str = Field(default="Оплата при отриманні", max_length=100)
    phone: str = Field(..., min_length=5, max_length=50)


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    total_price: float
    status: str = "created"
    delivery_address: Optional[str] = None
    payment_method: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    items: list[OrderItemOut] = Field(default_factory=list)


class OrderStatusUpdate(BaseModel):
    status: Literal["created", "completed", "cancelled"]


class ComplaintCreate(BaseModel):
    product_id: int
    reason: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=2000)


class ComplaintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_id: int
    target_type: str
    target_id: int
    reason: str
    subject: Optional[str] = None
    object_label: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
    status: str = "opened"
    user_id: Optional[int] = None
    product_id: Optional[int] = None
    username: Optional[str] = None
    user_email: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None


class ComplaintOut(ComplaintResponse):
    pass


class ResumeCreate(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = None
    viber: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    whatsapp: Optional[str] = None
    public_email: Optional[str] = None
    bio: Optional[str] = None
    specialty: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    status: Optional[str] = "pending"


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    display_name: Optional[str] = None
    phone: Optional[str] = None
    viber: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    whatsapp: Optional[str] = None
    public_email: Optional[str] = None
    bio: Optional[str] = None
    specialty: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None


class StatsOut(BaseModel):
    total_revenue: int
    total_orders: int


class MessageResponse(BaseModel):
    message: str


class UploadResponse(BaseModel):
    url: str

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductType(str, Enum):
    PHYSICAL = "physical"
    DIGITAL = "digital"
    GAME = "game"
    GAME_ITEM = "game_item"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_names(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("birth_date", mode="before")
    @classmethod
    def parse_birth_date(cls, value):
        if value in (None, ""):
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    return datetime.strptime(cleaned, fmt).date()
                except ValueError:
                    continue
            return date.fromisoformat(cleaned)
        return value


class UserLogin(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    is_age_locked: bool = False
    is_active: bool = True
    is_admin: bool = False
    is_superuser: bool = False
    is_banned: bool = False
    banned_until: Optional[datetime] = None
    tg_link_code: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    has_sales: bool = False


class UserPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    is_age_locked: bool = False
    tg_link_code: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    viber: Optional[str] = None
    telegram: Optional[str] = None
    instagram: Optional[str] = None
    whatsapp: Optional[str] = None
    public_email: Optional[str] = None
    bio: Optional[str] = None
    specialty: Optional[str] = None
    experience: Optional[str] = None
    skills: Optional[str] = None
    has_sales: bool = False


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
    model_config = ConfigDict(extra="ignore")

    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


UserProfileUpdate = UserUpdate


class UserRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_admin: bool = False


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


MAX_SQLITE_INT = 2_147_483_647


class CategoryBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=100)
    icon: Optional[str] = None
    parent_id: Optional[int] = None


class CategoryOut(CategoryBase):
    id: int
    children: list["CategoryOut"] = Field(default_factory=list)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=100)
    icon: Optional[str] = None
    parent_id: Optional[int] = None


class ProductCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=250)
    description: str = Field(..., min_length=5)
    price: int = Field(..., ge=0, le=MAX_SQLITE_INT)
    quantity: int = Field(..., ge=0, le=MAX_SQLITE_INT)
    seller_phone: Optional[str] = None
    category: Optional[str] = None
    category_id: Optional[int] = None
    category_slug: Optional[str] = None
    product_type: ProductType = ProductType.PHYSICAL
    sku: Optional[str] = Field(default=None, max_length=80)
    sale_price: Optional[int] = Field(default=None, ge=0, le=MAX_SQLITE_INT)
    is_draft: bool = False
    tags: Optional[str] = None
    attributes: Optional[str] = None
    digital_content: Optional[str] = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    price: int = Field(..., ge=0, le=MAX_SQLITE_INT)
    quantity: int = Field(..., ge=0, le=MAX_SQLITE_INT)
    stock: int = Field(..., ge=0, le=MAX_SQLITE_INT)
    in_stock: bool = False
    is_available: bool = False
    seller_phone: Optional[str] = None
    user_id: int
    category_id: Optional[int] = None
    sales_count: int = 0
    product_type: ProductType = ProductType.PHYSICAL
    sku: Optional[str] = None
    sale_price: Optional[int] = None
    is_draft: bool = False
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    digital_content: Optional[str] = None
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


class SellerSalesItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    product_id: int
    title: str
    image_url: Optional[str] = None
    quantity: int
    price_per_item: float
    total_amount: float
    sold_at: Optional[datetime] = None


class SellerSalesAnalyticsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_profit: float
    sold_count: int
    items: list[SellerSalesItemOut] = Field(default_factory=list)


class OrderStatusUpdate(BaseModel):
    status: Literal["created", "new", "paid", "shipped", "completed", "cancelled"]


class ReportCreate(BaseModel):
    reported_user_id: Optional[int] = None
    product_id: Optional[int] = None
    comment_id: Optional[int] = None
    reason: Literal[
        "Шахрайство",
        "Спам / Спам-акаунт",
        "Невідповідність товару",
        "Нецензурна лексика",
        "Інше",
    ] = Field(...)
    details: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_target(self):
        if not any([self.reported_user_id is not None, self.product_id is not None, self.comment_id is not None]):
            raise ValueError("Хоча б одне з полів reported_user_id, product_id або comment_id має бути заповнене.")
        return self


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_id: int
    reported_user_id: Optional[int] = None
    product_id: Optional[int] = None
    comment_id: Optional[int] = None
    reason: str
    details: Optional[str] = None
    status: str = "pending"
    created_at: Optional[datetime] = None
    reporter_username: Optional[str] = None
    reported_username: Optional[str] = None
    product_title: Optional[str] = None
    comment_preview: Optional[str] = None


class ComplaintCreate(BaseModel):
    target_type: str = Field(default="product")
    target_id: Optional[int] = None
    product_id: Optional[int] = None
    target_user_id: Optional[int] = None
    reason: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=2000)


class ComplaintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reporter_id: int
    target_type: str
    target_id: int
    target_user_id: Optional[int] = None
    target_user_role: Optional[str] = None
    target_user_is_superuser: bool = False
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
    user_role: Optional[str] = None
    user_is_superuser: bool = False
    title: Optional[str] = None
    text: Optional[str] = None
    target_text: Optional[str] = None


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

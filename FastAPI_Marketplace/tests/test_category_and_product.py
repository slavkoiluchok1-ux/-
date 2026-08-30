import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from main import app
from database import async_session, ensure_schema
from models import Category, Product, ProductType, User
from routers.catalog import _coerce_product_type, resolve_category_id
from auth_utils import create_access_token


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_product_type_coercion():
    assert _coerce_product_type('physical') == 'physical'
    assert _coerce_product_type('digital') == 'digital'
    assert _coerce_product_type('game_item') == 'game_item'
    assert _coerce_product_type('game') == 'game_item'
    assert _coerce_product_type('Ігри') == 'game_item'
    assert _coerce_product_type('Акаунти') == 'game_item'
    assert _coerce_product_type('Софт') == 'digital'
    assert _coerce_product_type('Курси') == 'digital'
    assert _coerce_product_type(None) == 'physical'


@pytest.mark.anyio
async def test_category_resolution():
    await ensure_schema()
    async with async_session() as db:
        # Test resolution for subcategories
        cat_auto_parts = await resolve_category_id(db, category='auto_parts')
        assert cat_auto_parts is not None

        cat_smartphones = await resolve_category_id(db, category='smartphones')
        assert cat_smartphones is not None

        cat_games = await resolve_category_id(db, category='games')
        assert cat_games is not None

        cat_accounts = await resolve_category_id(db, category='accounts')
        assert cat_accounts is not None

        cat_software = await resolve_category_id(db, category='software')
        assert cat_software is not None

        cat_courses = await resolve_category_id(db, category='courses')
        assert cat_courses is not None

        cat_furniture = await resolve_category_id(db, category='furniture')
        assert cat_furniture is not None

        # Test resolution for parent categories
        cat_electronics = await resolve_category_id(db, category='electronics')
        assert cat_electronics is not None

        cat_digital_goods = await resolve_category_id(db, category='digital_goods')
        assert cat_digital_goods is not None

        # Test resolution by ID
        cat_by_id = await resolve_category_id(db, category_id=str(cat_games))
        assert cat_by_id == cat_games


@pytest.mark.anyio
async def test_create_and_edit_product_flow():
    await ensure_schema()

    async with async_session() as db:
        user = await db.scalar(select(User).where(User.username == 'testuser_seller'))
        if not user:
            user = User(
                username='testuser_seller',
                email='seller@example.com',
                display_name='Test Seller',
                is_active=True,
            )
            user.set_password('sellerpassword123')
            db.add(user)
            await db.commit()
            await db.refresh(user)

        user_id = user.id

    token = create_access_token(user_id)
    cookies = {'access_token': token, 'csrf_token': 'test_csrf_token'}
    headers = {'Authorization': f'Bearer {token}', 'X-CSRF-Token': 'test_csrf_token', 'X-Requested-With': 'XMLHttpRequest'}

    from httpx._transports.asgi import ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test', cookies=cookies) as client:
        # 1. Create a game product
        response = await client.post(
            '/api/v1/products',
            data={
                'title': 'Steam Account CS2',
                'description': 'Повний доступ до акаунту з іграми',
                'price': '450',
                'quantity': '5',
                'category': 'accounts',
                'product_type': 'game_item',
                'digital_content': 'login:pass:secret_key',
                'seller_phone': '+380991234567',
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data['title'] == 'Steam Account CS2'
        assert data['product_type'] == 'game_item'
        assert data['category_id'] is not None
        product_id = data['id']

        # 2. Create a physical electronics product
        response2 = await client.post(
            '/api/v1/products',
            data={
                'title': 'iPhone 15 Pro',
                'description': 'Новий смартфон у коробці',
                'price': '35000',
                'quantity': '2',
                'category': 'smartphones',
                'product_type': 'physical',
            },
            headers=headers,
        )
        assert response2.status_code == 201, response2.text
        data2 = response2.json()
        assert data2['title'] == 'iPhone 15 Pro'
        assert data2['product_type'] == 'physical'

        # 3. Edit the first product via POST /products/{id}/edit
        edit_response = await client.post(
            f'/products/{product_id}/edit',
            data={
                'title': 'Steam Account CS2 + Prime',
                'description': 'Оновлений опис акаунту',
                'price': '500',
                'quantity': '4',
                'category': 'games',
                'product_type': 'game_item',
                'seller_phone': '+380991234567',
                'digital_content': 'updated_login:pass',
            },
            headers=headers,
            follow_redirects=False,
        )
        assert edit_response.status_code in [200, 303], edit_response.text

        # Verify edited values in DB
        async with async_session() as db:
            p = await db.get(Product, product_id)
            assert p.title == 'Steam Account CS2 + Prime'
            assert p.price == 500
            assert p.quantity == 4
            assert p.product_type == 'game_item'
            assert p.digital_content == 'updated_login:pass'

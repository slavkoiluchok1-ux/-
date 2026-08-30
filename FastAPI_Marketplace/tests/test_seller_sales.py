from schemas import UserPublic


def test_user_public_includes_has_sales_flag():
    profile = UserPublic.model_validate(
        {
            "id": 1,
            "username": "seller",
            "email": "seller@example.com",
            "has_sales": True,
        }
    )

    assert profile.has_sales is True
    assert profile.model_dump()["has_sales"] is True

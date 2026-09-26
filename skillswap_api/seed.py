from sqlalchemy.orm import Session
from src.database.models import User, Skill, Exchange, Review, SkillLevel, ExchangeStatus
from src.database.db import SessionLocal

def seed_database():
    db = SessionLocal()

    try:
        users = [
            User(username="alex_dev", email="alex@example.com", full_name="Олександр Петренко",
                 bio="Python розробник, люблю музику"),
            User(username="maria_music", email="maria@example.com", full_name="Марія Коваленко",
                 bio="Викладач музики, хочу вивчити програмування"),
            User(username="ivan_sport", email="ivan@example.com", full_name="Іван Шевченко",
                 bio="Тренер з плавання, цікавлюся технологіями")
        ]

        db.add_all(users)
        db.commit()

        for user in users:
            db.refresh(user)

        skills = [
            Skill(title="Python програмування", description="Навчу основам Python, Django, FastAPI",
                  category="programming", level=SkillLevel.advanced, can_teach=True, want_learn=False),
            Skill(title="Гра на гітарі", description="Можу навчити грати на гітарі з нуля",
                  category="music", level=SkillLevel.intermediate, can_teach=True, want_learn=False),
            Skill(title="Плавання", description="Навчу правильній техніці плавання",
                  category="sports", level=SkillLevel.expert, can_teach=True, want_learn=False),
            Skill(title="Англійська мова", description="Хочу покращити розмовну англійську",
                  category="languages", level=SkillLevel.beginner, can_teach=False, want_learn=True)
        ]

        db.add_all(skills)
        db.commit()

        for skill in skills:
            db.refresh(skill)

        for i in range(min(len(users), len(skills))):
            users[i].skills.append(skills[i])

        db.commit()

        exchange1 = Exchange(
            sender_id=users[0].id,
            receiver_id=users[1].id,
            skill_id=skills[1].id,
            message="Привіт! Хочу навчитися грати на гітарі, можу навчити Python",
            hours_proposed=5,
            status=ExchangeStatus.completed
        )

        exchange2 = Exchange(
            sender_id=users[1].id,
            receiver_id=users[0].id,
            skill_id=skills[0].id,
            message="Давай обмінюємося знаннями!",
            hours_proposed=5,
            status=ExchangeStatus.pending
        )

        db.add_all([exchange1, exchange2])
        db.commit()

        db.refresh(exchange1)
        db.refresh(exchange2)

        review1 = Review(
            exchange_id=exchange1.id,
            reviewer_id=users[0].id,
            reviewed_id=users[1].id,
            rating=5,
            comment="Чудовий викладач! Дуже терпляче пояснює"
        )

        review2 = Review(
            exchange_id=exchange1.id,
            reviewer_id=users[1].id,
            reviewed_id=users[0].id,
            rating=5,
            comment="Відмінно пояснює програмування, рекомендую!"
        )

        db.add_all([review1, review2])
        db.commit()

        print("База даних успішно заповнена тестовими даними!")

    except Exception as e:
        print(f"Помилка при заповненні бази даних: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
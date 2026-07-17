# Файл: reset_db.py
from online_restaurant_db import Session, Users, Orders, Reservation

def reset_accounts():
    print("--- ЗАПУСК ПРОЦЕСУ ОЧИЩЕННЯ ДАНИХ ---")
    confirm = input("Ви впевнені, що хочете видалити ВСІ акаунти та замовлення? (y/n): ")
    
    if confirm.lower() == 'y':
        with Session() as db:
            try:
                # Видаляємо замовлення та бронювання (вони прив'язані до юзерів)
                db.query(Orders).delete()
                db.query(Reservation).delete()
                # Видаляємо всіх користувачів
                db.query(Users).delete()
                
                db.commit()
                print("СИСТЕМА СКИНУТА: Всі акаунти та історія видалені.")
            except Exception as e:
                db.rollback()
                print(f"ПОМИЛКА при скиданні: {e}")
    else:
        print("Скасовано.")

if __name__ == "__main__":
    reset_accounts()
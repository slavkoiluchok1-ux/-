from online_restaurant_db import Session, Menu

# Відкриваємо сесію для роботи з базою
session = Session()

def fill_menu():
    print("⏳ Починаю оновлення бази даних страв...")
    
    try:
        # Очищаємо старі дані, щоб завантажити нові з правильними картинками
        session.query(Menu).delete()
        print("🗑️ Старе меню очищено.")

        new_dishes = [
            Menu(
                name="Український борщ",
                weight="450",
                ingredients="Яловичина, буряк, капуста, картопля, морква, сметана, зелень",
                description="Класичний домашній борщ на наваристому м'ясному бульйоні. Подається зі сметаною.",
                price=145,
                discount=10,
                file_name="borscht.png"  # Точна назва твого файлу
            ),
            Menu(
                name="Паста зі спаржею та томатами",
                weight="320",
                ingredients="Паста твердих сортів, свіжа спаржа, томати чері, оливкова олія, часник, пармезан",
                description="Легка італійська паста з обсмаженою спаржею та соковитими томатами під сиром пармезан.",
                price=190,
                discount=0,
                file_name="pasta.png"
            ),
            Menu(
                name="Стейк з молодими овочами",
                weight="300/150",
                ingredients="Яловичина (вирізка), бейбі-картопля, томати чері, фірмовий соус",
                description="Соковитий стейк просмаження Medium, приготовлений на грилі. Подається з печеною картоплею.",
                price=450,
                discount=0,
                file_name="steak.png"
            ),
            Menu(
                name="Кутя Різдвяна",
                weight="250",
                ingredients="Пшениця, мак, волоський горіх, мед квітковий, родзинки",
                description="Традиційна святкова страва з добірної пшениці з додаванням меду, горіхів та маку.",
                price=95,
                discount=0,
                file_name="kutia.png"
            ),
            Menu(
                name="Великий м'ясний сет",
                weight="950",
                ingredients="Свинячий шашлик, курячі крильця, ковбаски-гриль, кукурудза, соус BBQ",
                description="Велика тарілка асорті з різних видів м'яса на грилі. Ідеально підходить для компанії.",
                price=820,
                discount=5,
                file_name="meat_set.png"
            ),
            Menu(
                name="Велика закусочна тарілка",
                weight="800",
                ingredients="М'ясна нарізка, сири, фрукти, грисіні, мед",
                description="Розкішне асорті делікатесів для компанії: м'ясо, сири, фрукти та хрусткі палички.",
                price=620,
                discount=0,
                file_name="image copy.png"
            ),
            Menu(
                name="М'ясне асорті 'Для компанії'",
                weight="1200",
                ingredients="Ребра свинячі, домашні ковбаски, підчеревина, кукурудза гриль, соус BBQ",
                description="Величезна порція м'яса на грилі для справжніх гурманів.",
                price=850,
                discount=5,
                file_name="image copy 2.png"
            ),
            Menu(
                name="Середземноморська дошка",
                weight="350",
                ingredients="Прошуто, салямі, грисіні, оливки, томати чері, свіжа зелень",
                description="Вишукана закуска до вина або аперитив перед основною стравою.",
                price=320,
                discount=0,
                file_name="image copy 3.png"
            ),
            Menu(
                name="Асорті гриль 'Велике застілля'",
                weight="1500",
                ingredients="Шашлик, стейки, ребра, запечена картопля, овочі гриль, фірмові соуси",
                description="Максимальний набір м'ясних страв приготованих на відкритому вогні.",
                price=1200,
                discount=15,
                file_name="image copy 4.png"
            ),
            Menu(
                name="Лосось на зеленій спаржі",
                weight="280",
                ingredients="Філе лосося, молода спаржа, вершково-зелений соус, лимон",
                description="Ніжне філе риби з легкою овочевою підкладкою. Справжній фітнес-вибір.",
                price=480,
                discount=0,
                file_name="image copy 5.png"
            ),
            Menu(
                name="Ребра з ікорними млинцями",
                weight="400",
                ingredients="Свинячі ребра гриль, міні-млинці, червона ікра, свіжий кріп",
                description="Унікальне поєднання ситних ребер та делікатесних млинців.",
                price=390,
                discount=0,
                file_name="image copy 6.png"
            ),
            Menu(
                name="Азійська засмажка з рисом",
                weight="350",
                ingredients="М'ясний фарш, болгарський перець, квасоля, перець чилі, білий рис",
                description="Пікантна страва в стилі WOK з насиченим смаком спецій та сої.",
                price=195,
                discount=5,
                file_name="image copy 7.png"
            ),
            Menu(
                name="Овочеве соті на сковорідці",
                weight="300",
                ingredients="Солодкий перець, помідори, цибуля, кабачок, часниковий соус",
                description="Легка овочева закуска, приготована за технологією швидкого обсмаження.",
                price=160,
                discount=0,
                file_name="image copy 8.png"
            ),
            Menu(
                name="М'ясні рулетики з грибами",
                weight="350",
                ingredients="Свинина, печериці, сир моцарела, вершковий соус, зелень",
                description="Домашні крученики з грибною начинкою у ніжному білому соусі.",
                price=280,
                discount=0,
                file_name="image copy 10.png"
            )
        ]

        session.add_all(new_dishes)
        session.commit()
        print(f"✅ Успішно додано {len(new_dishes)} страв у меню!")

    except Exception as e:
        session.rollback()
        print(f"❌ Помилка під час заповнення: {e}")
    finally:
        session.close()
        print("🔌 З'єднання з базою закрито.")

if __name__ == "__main__":
    fill_menu()
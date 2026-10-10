import json
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand
from portfolio.models import Project, Skill, Experience, Testimonial, PricingPackage, BlogCategory, BlogTag, BlogPost
from django.contrib.auth.models import User
from django.utils.text import slugify


def get_github_project_items():
    url = 'https://api.github.com/repos/slavkoiluchok1-ux/-/contents'
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return []

    projects = []
    descriptions = {
        'firstProj': 'Проєкт із базовою структурою Django для практики розробки веб-додатків і роботи з шаблонами.',
        'library_proj': 'Система для бібліотеки з моделями книг, читачів та основними CRUD-операціями.',
        'library_system': 'Рішення для управління бібліотекою з каталогом, користувачами та видачею книг.',
        'student_management': 'Менеджмент студентських даних із зручною структурою і логікою роботи з інформаційними записами.',
        'messenger_project': 'Проєкт для практики створення веб-інтерфейсів і роботи з даними у форматі мессенджер-типу.',
        'online_restaurant': 'Веб-сайт ресторану з меню, формами замовлення та адаптивним дизайном.',
        'weather_proj': 'Практичний проєкт для роботи з даними та простим UI, який демонструє інтеграцію з зовнішніми джерелами.',
        'trchnoblog': 'Блог-платформа для демонстрації контенту та новин у зручному веб-інтерфейсі.',
        'core': 'Основа Django-проєкту з типово налаштованим додатком та маршрутами.',
    }
    dates = {
        'firstProj': '2024-07-10',
        'library_proj': '2024-08-18',
        'library_system': '2024-08-30',
        'student_management': '2024-10-02',
        'messenger_project': '2024-10-20',
        'online_restaurant': '2024-09-15',
        'weather_proj': '2024-09-05',
        'trchnoblog': '2024-10-10',
        'core': '2024-06-01',
    }

    for item in data:
        if item.get('type') == 'dir' and item.get('name') not in {'instance'}:
            name = item['name']
            title = name.replace('_', ' ').replace('-', ' ').title()
            projects.append({
                'title': title,
                'description': descriptions.get(name, f'Проєкт {title} із репозиторію, готовий для демонстрації.'),
                'technologies': 'Python, Django, HTML, CSS',
                'date': dates.get(name, '2024-01-01'),
                'github': f'https://github.com/slavkoiluchok1-ux/-/tree/main/{name}',
            })
    return projects


def get_featured_project_items():
    repository = 'https://github.com/slavkoiluchok1-ux/-/tree/main'
    return [
        {
            'title': 'FastAPI Marketplace',
            'description': 'Маркетплейс на FastAPI з автентифікацією, каталогом товарів, категоріями, кошиком, обраним, замовленнями, відгуками та адміністративними маршрутами.',
            'technologies': 'Python, FastAPI, SQLAlchemy, Alembic, JWT, SQLite/PostgreSQL',
            'date': '2025-01-20',
            'github': f'{repository}/astapi-marketpla',
        },
        {
            'title': 'Сайт-портфоліо',
            'description': 'Повноцінний Django-сайт портфоліо з проєктами, навичками, досвідом, блогом, тарифами, аналітикою та формою брифу із email-підтвердженням.',
            'technologies': 'Python, Django, SQLite, Bootstrap, Email',
            'date': '2025-02-15',
            'github': f'{repository}/portfolio_project',
        },
        {
            'title': 'Music Studio',
            'description': 'Django-застосунок для авторизації користувачів і додавання кількох пісень через formset у персональній музичній студії.',
            'technologies': 'Python, Django, SQLite, Bootstrap, Forms',
            'date': '2025-02-01',
            'github': f'{repository}/music_project',
        },
        {
            'title': 'ServiceDesk',
            'description': 'Сервіс підтримки з ролями клієнта, працівника й адміністратора, заявками, відповідями, статусами, статистикою та завантаженням зображень.',
            'technologies': 'Python, FastAPI, SQLAlchemy, Jinja2, JWT, SQLite',
            'date': '2025-01-10',
            'github': f'{repository}/servicedesk_project',
        },
        {
            'title': 'SkillSwap API',
            'description': 'API для обміну навичками з користувачами, навичками, обмінами, відгуками та статистикою, організоване за repository і routes шарами.',
            'technologies': 'Python, FastAPI, SQLAlchemy, Alembic, Pydantic',
            'date': '2024-12-20',
            'github': f'{repository}/skillswap_api',
        },
        {
            'title': 'Online Restaurant',
            'description': 'Вебзастосунок ресторану з меню, кошиком, оформленням замовлень, бронюванням столиків, авторизацією та адміністративним керуванням.',
            'technologies': 'Python, Flask, SQLite, HTML, CSS',
            'date': '2024-11-20',
            'github': f'{repository}/online_restaurant',
        },
        {
            'title': 'TechnoBlog',
            'description': 'Django-блог із розділами, сторінками статей, статичними файлами та окремими стилями й JavaScript для інтерфейсу.',
            'technologies': 'Python, Django, SQLite, HTML, CSS, JavaScript',
            'date': '2024-10-10',
            'github': f'{repository}/trchnoblog',
        },
        {
            'title': 'Messenger Project',
            'description': 'Навчальний messenger-проєкт із реєстрацією, авторизацією, профілем, друзями, запитами та повідомленнями.',
            'technologies': 'Python, Flask, SQLite, Jinja2, HTML, CSS',
            'date': '2024-10-20',
            'github': f'{repository}/messenger_project',
        },
        {
            'title': 'Library System',
            'description': 'Система управління бібліотекою з моделями предметної області та базовою структурою Django-застосунку.',
            'technologies': 'Python, Django, SQLite, ORM',
            'date': '2024-08-30',
            'github': f'{repository}/library_system',
        },
        {
            'title': 'Student Management',
            'description': 'Django-проєкт для зберігання й керування даними студентів через моделі, міграції та адміністративну панель.',
            'technologies': 'Python, Django, SQLite, Django Admin',
            'date': '2024-10-02',
            'github': f'{repository}/student_management',
        },
        {
            'title': 'Weather Project',
            'description': 'Невеликий застосунок для роботи з погодними даними, конфігурацією та окремою моделлю збереження інформації.',
            'technologies': 'Python, Flask, SQLite, HTML',
            'date': '2024-09-05',
            'github': f'{repository}/weather_proj',
        },
        {
            'title': 'Games Catalog',
            'description': 'Django-каталог ігор із деталями, новинами, файлами для завантаження, зображеннями та медіа-файлами.',
            'technologies': 'Python, Django, SQLite, Media Files, HTML',
            'date': '2024-09-25',
            'github': f'{repository}/proj',
        },
    ]


class Command(BaseCommand):
    help = 'Seed the portfolio with content based on existing workspace projects'

    def handle(self, *args, **options):
        Project.objects.all().delete()
        Skill.objects.all().delete()
        Experience.objects.all().delete()
        Testimonial.objects.all().delete()
        PricingPackage.objects.all().delete()
        BlogCategory.objects.all().delete()
        BlogTag.objects.all().delete()
        BlogPost.objects.all().delete()
        User.objects.filter(username='admin').delete()

        admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'admin12345')

        for item in get_featured_project_items():
            Project.objects.create(**item)

        skills = [
            ('Python', 9, 'backend'),
            ('Django', 4, 'backend'),
            ('HTML/CSS', 8, 'frontend'),
            ('JavaScript', 4, 'frontend'),
            ('SQLite/PostgreSQL', 7, 'database'),
            ('Git & GitHub', 5, 'devops'),
            ('Bootstrap', 5, 'frontend'),
            ('API інтеграції', 7, 'backend'),
            ('Комунікація', 8, 'soft'),
            ('Командна робота', 8, 'soft'),
            ('Вирішення проблем', 8, 'soft'),
            ('Тайм-менеджмент', 8, 'soft'),
            ('Адаптивність', 7, 'soft'),
            ('Самонавчання', 8, 'soft'),
            ('Увага до деталей', 8, 'soft'),
            ('Лідерські якості', 9, 'soft'),
            ('Креативність', 8, 'soft'),
            ('Емпатія', 8, 'soft'),
            ('Критичне мислення', 8, 'soft'),
            ('Відповідальність', 8, 'soft'),
        ]
        for name, level, category in skills:
            Skill.objects.create(name=name, level=level, category=category)

        Experience.objects.create(
            position='Python/Django Developer',
            company='Freelance',
            period='2023 — тепер',
            description='Розробка веб-сервісів, портфоліо, CRM-інструментів і автоматизаційних рішень.'
        )
        Testimonial.objects.create(
            client_name='Олександр',
            company='Startup',
            quote='Чудовий баланс між швидкістю, дизайном та функціональністю.',
            rating=5
        )

        PricingPackage.objects.create(title='Базовий', price=300, description='Підходить для landing page', features='Адаптивний дизайн\nБазова SEO-оптимізація\n1 етап зворотного зв’язку', popular=False)
        PricingPackage.objects.create(title='Стандарт', price=800, description='Оптимальний варіант для бізнес-сайту', features='Повноцінний сайт\nФорми та інтеграції\nПідтримка 1 місяць', popular=True)
        PricingPackage.objects.create(title='Преміум', price=1800, description='Для складних продуктів і інструментів', features='Розширена логіка\nAPI інтеграції\nАвтоматизація бізнес-процесів', popular=False)

        category = BlogCategory.objects.create(name='Python', slug='python')
        tag = BlogTag.objects.create(name='Django', slug='django')
        BlogPost.objects.create(
            title='Як я створив свій перший Django-портфоліо',
            slug='yak-ya-stvoriv-sviy-pershiy-django-portfolio',
            excerpt='Короткий шлях від ідеї до готового сайту з формами та стилізацією.',
            content='У цій статті розповім про процес створення портфоліо на Django: від моделей до шаблонів і адаптивного дизайну.',
            category=category,
            author=admin_user,
            is_published=True,
        ).tags.add(tag)

        self.stdout.write(self.style.SUCCESS('Portfolio seeded successfully'))

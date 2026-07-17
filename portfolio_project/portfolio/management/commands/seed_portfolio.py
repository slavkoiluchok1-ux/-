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

        projects = get_github_project_items()
        if not projects:
            projects = [
                {
                    'title': 'Django-портфоліо',
                    'description': 'Мій навчальний веб-портфоліо на Django з адаптивним UI, формами замовлення та сучасним дизайном.',
                    'technologies': 'Python, Django, Bootstrap',
                    'date': '2024-11-15',
                    'github': 'https://github.com/slavkoiluchok1-ux/-.git',
                },
                {
                    'title': 'Firstproj',
                    'description': 'Проєкт із базовою структурою Django для практики розробки веб-додатків і роботи з шаблонами.',
                    'technologies': 'Python, Django, HTML',
                    'date': '2024-07-10',
                    'github': 'https://github.com/slavkoiluchok1-ux/-.git',
                },
            ]

        for item in projects[:6]:
            Project.objects.create(**item)

        skills = [
            ('Python', 9, 'backend'),
            ('Django', 8, 'backend'),
            ('HTML/CSS', 8, 'frontend'),
            ('JavaScript', 7, 'frontend'),
            ('SQLite/PostgreSQL', 7, 'database'),
            ('Git & GitHub', 8, 'devops'),
            ('Bootstrap', 8, 'frontend'),
            ('API інтеграції', 7, 'backend'),
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

from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from django.contrib.auth.models import User


class Skill(models.Model):
    CATEGORY_CHOICES = [
        ('frontend', 'Фронтенд'),
        ('backend', 'Бекенд'),
        ('database', 'База даних'),
        ('devops', 'DevOps'),
        ('other', 'Інше'),
    ]
    name = models.CharField('Назва', max_length=100)
    level = models.IntegerField('Рівень', validators=[MinValueValidator(1), MaxValueValidator(10)])
    category = models.CharField('Категорія', max_length=50, choices=CATEGORY_CHOICES)

    class Meta:
        verbose_name = 'Навичка'
        verbose_name_plural = 'Навички'
        ordering = ['category', '-level']

    def __str__(self):
        return self.name

class Project(models.Model):
    title = models.CharField('Назва', max_length=200)
    description = models.TextField('Опис')
    technologies = models.CharField('Технології', max_length=200)
    date = models.DateField('Дата', blank=True, null=True, help_text='Дата завершення проекту')
    image = models.ImageField('Зображення', upload_to='projects/', blank=True, null=True)
    github = models.URLField('GitHub посилання', blank=True)

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекти'
        ordering = ['-date', 'title']

    def __str__(self):
        return self.title

class Experience(models.Model):
    position = models.CharField('Посада', max_length=100)
    company = models.CharField('Компанія', max_length=100)
    period = models.CharField('Період', max_length=100)
    description = models.TextField('Опис')

    class Meta:
        verbose_name = 'Досвід'
        verbose_name_plural = 'Досвід'
        ordering = ['-id']

    def __str__(self):
        return f"{self.position} at {self.company}"


class Testimonial(models.Model):
    client_name = models.CharField('Ім’я клієнта', max_length=100)
    company = models.CharField('Компанія', max_length=100, blank=True)
    quote = models.TextField('Відгук')
    rating = models.PositiveIntegerField('Рейтинг', validators=[MinValueValidator(1), MaxValueValidator(5)])

    class Meta:
        verbose_name = 'Відгук'
        verbose_name_plural = 'Відгуки'
        ordering = ['-id']

    def __str__(self):
        return self.client_name


class Order(models.Model):
    STATUS_CHOICES = [
        ('new', 'Нова'),
        ('in_progress', 'В обробці'),
        ('completed', 'Завершена'),
        ('cancelled', 'Скасована'),
    ]

    project_name = models.CharField('Назва проєкту', max_length=200)
    budget = models.PositiveIntegerField('Бюджет, USD')
    deadline = models.DateField('Термін')
    description = models.TextField('Опис замовлення')
    contact_name = models.CharField('Ім’я контакту', max_length=100)
    contact_email = models.EmailField('Email контакту')
    contact_phone = models.CharField('Телефон контакту', max_length=20)
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField('Створено', default=timezone.now)

    class Meta:
        verbose_name = 'Замовлення'
        verbose_name_plural = 'Замовлення'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project_name} ({self.contact_name})"


class PricingPackage(models.Model):
    title = models.CharField('Назва пакету', max_length=100)
    price = models.PositiveIntegerField('Ціна, USD')
    description = models.TextField('Опис')
    features = models.TextField('Особливості')
    popular = models.BooleanField('Популярний', default=False)

    class Meta:
        verbose_name = 'Пакет послуг'
        verbose_name_plural = 'Пакети послуг'
        ordering = ['price']

    def __str__(self):
        return self.title


class BlogCategory(models.Model):
    name = models.CharField('Категорія', max_length=100)
    slug = models.SlugField('Slug', unique=True)

    class Meta:
        verbose_name = 'Категорія блогу'
        verbose_name_plural = 'Категорії блогу'

    def __str__(self):
        return self.name


class BlogTag(models.Model):
    name = models.CharField('Тег', max_length=50)
    slug = models.SlugField('Slug', unique=True)

    class Meta:
        verbose_name = 'Тег блогу'
        verbose_name_plural = 'Теги блогу'

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    title = models.CharField('Заголовок', max_length=200)
    slug = models.SlugField('Slug', unique=True)
    excerpt = models.TextField('Короткий опис', blank=True)
    content = models.TextField('Текст статті')
    category = models.ForeignKey(BlogCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    tags = models.ManyToManyField(BlogTag, blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_posts', null=True, blank=True)
    created_at = models.DateTimeField('Опубліковано', default=timezone.now)
    updated_at = models.DateTimeField('Оновлено', auto_now=True)
    is_published = models.BooleanField('Опубліковано', default=True)

    class Meta:
        verbose_name = 'Стаття блогу'
        verbose_name_plural = 'Статті блогу'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class BlogComment(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
    author_name = models.CharField('Ім’я автора', max_length=100)
    comment = models.TextField('Коментар')
    created_at = models.DateTimeField('Створено', default=timezone.now)

    class Meta:
        verbose_name = 'Коментар'
        verbose_name_plural = 'Коментарі'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author_name} on {self.post.title}"


class PageView(models.Model):
    page = models.CharField('Сторінка', max_length=200)
    viewed_at = models.DateTimeField('Перегляд', default=timezone.now)

    class Meta:
        verbose_name = 'Перегляд сторінки'
        verbose_name_plural = 'Перегляди сторінок'
        ordering = ['-viewed_at']

    def __str__(self):
        return self.page
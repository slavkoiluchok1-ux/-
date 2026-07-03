from django.db import models

class Author(models.Model):
    name = models.CharField(max_length=100, verbose_name="Ім'я автора")
    country = models.CharField(max_length=50, verbose_name="Країна")
    birth_year = models.IntegerField(verbose_name="Рік народження")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Автор"
        verbose_name_plural = "Автори"
        ordering = ['name']

class Book(models.Model):
    title = models.CharField(max_length=200, verbose_name="Назва книги")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, verbose_name="Автор")
    isbn = models.CharField(max_length=13, unique=True, verbose_name="ISBN")
    pages = models.PositiveIntegerField(verbose_name="Кількість сторінок")
    publication_year = models.IntegerField(verbose_name="Рік публікації")
    is_available = models.BooleanField(default=True, verbose_name="Доступна")

    def __str__(self):
        return f"{self.title} - {self.author.name}"

    class Meta:
        verbose_name = "Книга"
        verbose_name_plural = "Книги"
        ordering = ['-publication_year']

class Reader(models.Model):
    name = models.CharField(max_length=100, verbose_name="Ім'я читача")
    email = models.EmailField(verbose_name="Email")
    books = models.ManyToManyField(Book, through='Loan', verbose_name="Книги")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Читач"
        verbose_name_plural = "Читачі"
        ordering = ['name']

class Loan(models.Model):
    reader = models.ForeignKey(Reader, on_delete=models.CASCADE, verbose_name="Читач")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, verbose_name="Книга")
    loan_date = models.DateField(auto_now_add=True, verbose_name="Дата позики")
    return_date = models.DateField(blank=True, null=True, verbose_name="Дата повернення")

    def __str__(self):
        return f"{self.reader.name} позичив {self.book.title}"

    class Meta:
        verbose_name = "Позика"
        verbose_name_plural = "Позики"
        ordering = ['-loan_date']
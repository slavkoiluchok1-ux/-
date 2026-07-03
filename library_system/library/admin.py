from django.contrib import admin
from .models import Author, Book, Reader, Loan

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ['name', 'country', 'birth_year']
    search_fields = ['name']
    list_filter = ['country']

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'isbn', 'pages', 'publication_year', 'is_available']
    search_fields = ['title', 'author__name', 'isbn']
    list_filter = ['is_available', 'publication_year']

@admin.register(Reader)
class ReaderAdmin(admin.ModelAdmin):
    list_display = ['name', 'email']
    search_fields = ['name', 'email']

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['reader', 'book', 'loan_date', 'return_date']
    search_fields = ['reader__name', 'book__title']
    list_filter = ['loan_date', 'return_date']
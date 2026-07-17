from django.contrib import admin
from .models import Student

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'age', 'is_active', 'registration_date')
    list_filter = ('course', 'is_active')
    search_fields = ('name', 'email')
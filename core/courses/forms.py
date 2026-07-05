import re
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Course

class StudentRegistrationForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    age = forms.IntegerField()
    phone = forms.CharField(max_length=13)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError("Цей логін уже зайнятий.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("Цей email вже зареєстрований.")
        return email

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age is None or age < 12 or age > 18:
            raise ValidationError("Вік повинен бути від 12 до 18 років.")
        return age

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if not re.match(r'^\+380\d{9}$', phone):
            raise ValidationError("Телефон має бути у форматі +380XXXXXXXXX.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError("Паролі не збігаються.")
        return cleaned_data

class CourseSelectionForm(forms.Form):
    course = forms.ModelChoiceField(queryset=Course.objects.all(), required=True, label="Курс")
    priority = forms.IntegerField(min_value=1, max_value=3, required=True, label="Пріоритет")

class BaseCourseSelectionFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        courses = []
        priorities = []
        for form in self.forms:
            if not form.cleaned_data:
                continue
            course = form.cleaned_data.get('course')
            priority = form.cleaned_data.get('priority')
            if course:
                if course in courses:
                    raise ValidationError("Курси не можуть повторюватись у formset.")
                courses.append(course)
            if priority:
                if priority in priorities:
                    raise ValidationError("Пріоритети мають бути унікальними (1,2,3).")
                priorities.append(priority)
        if sorted(priorities) != [1, 2, 3]:
            raise ValidationError("Ви повинні обрати пріоритети 1, 2 та 3 без повторень.")

CourseSelectionFormSet = forms.formset_factory(
    CourseSelectionForm,
    formset=BaseCourseSelectionFormSet,
    extra=3,
    max_num=3,
    min_num=3,
    validate_min=True
)
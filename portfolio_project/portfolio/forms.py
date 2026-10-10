from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from .models import BlogComment, Order, OrderFile, Testimonial

User = get_user_model()


class ClientRegistrationForm(forms.Form):
    first_name = forms.CharField(
        label='Ваше ім’я',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'name'}),
    )
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )
    password_confirm = forms.CharField(
        label='Повторіть пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise ValidationError('Акаунт із таким email уже існує.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        email = cleaned_data.get('email')
        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', 'Паролі не збігаються.')
        if password and email:
            candidate = User(username=email, email=email, first_name=cleaned_data.get('first_name', ''))
            try:
                validate_password(password, candidate)
            except ValidationError as error:
                self.add_error('password', error)
        return cleaned_data

    def save(self):
        email = self.cleaned_data['email']
        return User.objects.create_user(
            username=email,
            email=email,
            first_name=self.cleaned_data['first_name'],
            password=self.cleaned_data['password'],
        )


class ClientAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'current-password'}),
    )

    def clean_username(self):
        return self.cleaned_data['username'].strip().lower()


class OrderForm(forms.ModelForm):
    min_budget = forms.IntegerField(widget=forms.HiddenInput, required=False, initial=0)
    total_hours = forms.FloatField(widget=forms.HiddenInput, required=False, initial=0)
    total_days = forms.IntegerField(widget=forms.HiddenInput, required=False, initial=0)
    min_deadline = forms.DateField(widget=forms.HiddenInput, required=False)
    development_level = forms.ChoiceField(
        choices=[('', '—'), ('base', 'Базовий'), ('standard', 'Стандартний'), ('premium', 'Преміум')],
        widget=forms.HiddenInput, required=False
    )
    pricing_details = forms.CharField(widget=forms.HiddenInput, required=False)
    extra_files = forms.FileField(
        label='Додаткові файли',
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        required=False,
        help_text='Можна завантажити кілька файлів: ТЗ, макети, скріншоти тощо'
    )

    class Meta:
        model = Order
        fields = [
            'project_name',
            'budget',
            'deadline',
            'description',
            'reference_image',
            'contact_name',
            'contact_email',
            'contact_phone',
        ]
        widgets = {
            'project_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Назва або короткий опис', 'required': True, 'autocomplete': 'off'}),
            'budget': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Наприклад, 1000', 'id': 'id_budget', 'min': '100', 'required': True}),
            'deadline': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_deadline'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 7, 'placeholder': 'Опишіть цілі проєкту, потрібні сторінки, функції, стиль і бажаний результат', 'id': 'id_description', 'required': True}),
            'reference_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'contact_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ваше ім’я', 'required': True, 'autocomplete': 'name'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com', 'required': True, 'autocomplete': 'email'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+380 ...', 'autocomplete': 'tel'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'extra_files' in self.fields:
            self.fields['extra_files'].widget.attrs['multiple'] = True

    def clean_description(self):
        description = self.cleaned_data.get('description', '')
        if len(description.split()) < 8:
            raise forms.ValidationError('Опис має містити щонайменше 8 слів.')
        return description

    def clean(self):
        cleaned_data = super().clean()
        budget = cleaned_data.get('budget')
        min_budget = int(cleaned_data.get('min_budget') or 0)
        deadline = cleaned_data.get('deadline')
        min_deadline = cleaned_data.get('min_deadline')
        if min_budget > 0 and budget is not None and budget < min_budget:
            self.add_error('budget', f'Бюджет не може бути меншим за мінімальний ({min_budget} USD), який розраховано в прайсі. Можна лише збільшити.')
        if min_deadline and deadline:
            if deadline < min_deadline:
                from django.utils.formats import date_format
                self.add_error('deadline', f'Термін не може бути раніше мінімального ({date_format(min_deadline)}), розрахованого в прайсі.')
        return cleaned_data

    def clean_pricing_details(self):
        import json
        raw = self.cleaned_data.get('pricing_details') or '{}'
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def save(self, commit=True, user=None):
        order = super().save(commit=False)
        if user is not None and user.is_authenticated:
            order.user = user
        order.min_budget = int(self.cleaned_data.get('min_budget') or 0)
        order.total_hours = float(self.cleaned_data.get('total_hours') or 0)
        order.total_days = int(self.cleaned_data.get('total_days') or 0)
        order.development_level = self.cleaned_data.get('development_level') or None
        order.pricing_details = self.cleaned_data.get('pricing_details') or {}
        if commit:
            order.save()
            extra_files = self.files.getlist('extra_files')
            for f in extra_files:
                if f.size:
                    OrderFile.objects.create(order=order, file=f)
        return order


class BlogCommentForm(forms.ModelForm):
    class Meta:
        model = BlogComment
        fields = ['author_name', 'comment']
        widgets = {
            'author_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Ваше ім'я"}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Ваш коментар'}),
        }

    def clean_comment(self):
        comment = self.cleaned_data.get('comment', '')
        if len(comment.strip()) < 10:
            raise forms.ValidationError('Коментар має бути щонайменше 10 символів.')
        return comment


class TestimonialForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=[(value, f'{value} з 5') for value in range(1, 6)],
        coerce=int,
        empty_value=None,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Рейтинг',
    )

    class Meta:
        model = Testimonial
        fields = ['client_name', 'company', 'quote', 'rating']
        widgets = {
            'client_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Ваше ім'я"}),
            'company': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Компанія або проєкт'}),
            'quote': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Розкажіть про ваш досвід співпраці'}),
        }

    def clean_quote(self):
        quote = self.cleaned_data.get('quote', '')
        if len(quote.strip()) < 10:
            raise forms.ValidationError('Відгук має бути щонайменше 10 символів.')
        return quote

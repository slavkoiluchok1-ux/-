from django import forms
from django.core.validators import MinValueValidator
from .models import BlogComment, Order


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'project_name',
            'budget',
            'deadline',
            'description',
            'contact_name',
            'contact_email',
            'contact_phone',
        ]
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Опишіть ваш проєкт, цілі, стиль та потрібні функції'}),
        }

    def clean_description(self):
        description = self.cleaned_data.get('description', '')
        if len(description.split()) < 8:
            raise forms.ValidationError('Опис має містити щонайменше 8 слів.')
        return description

    def clean_budget(self):
        budget = self.cleaned_data.get('budget')
        if budget is not None and budget < 100:
            raise forms.ValidationError('Бюджет має бути не менше 100 USD.')
        return budget


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

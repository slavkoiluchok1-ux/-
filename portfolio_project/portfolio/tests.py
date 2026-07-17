from django.test import TestCase
from django.core import mail
from django.urls import reverse

from .forms import OrderForm
from .models import Order


class OrderFormTests(TestCase):
    def test_order_form_rejects_short_description(self):
        form = OrderForm(data={
            'project_name': 'Сайт для компанії',
            'budget': 1200,
            'deadline': '2026-12-31',
            'description': 'Коротко',
            'contact_name': 'Олена',
            'contact_email': 'olena@example.com',
            'contact_phone': '+380501112233',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('description', form.errors)

    def test_order_form_accepts_valid_data(self):
        form = OrderForm(data={
            'project_name': 'Сайт для компанії',
            'budget': 1200,
            'deadline': '2026-12-31',
            'description': 'Потрібен сучасний сайт з адаптивним дизайном і формою зв’язку.',
            'contact_name': 'Олена',
            'contact_email': 'olena@example.com',
            'contact_phone': '+380501112233',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_order_submission_creates_order_and_sends_emails(self):
        response = self.client.post(reverse('portfolio:order_brif'), {
            'project_name': 'Магазин',
            'budget': 2500,
            'deadline': '2026-12-31',
            'description': 'Потрібна повноцінна сторінка для запуску нового продукту з адаптивним дизайном.',
            'contact_name': 'Ігор',
            'contact_email': 'ihor@example.com',
            'contact_phone': '+380671112233',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)

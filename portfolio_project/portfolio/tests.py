from django.test import TestCase
from django.core import mail
from django.urls import reverse
from django.contrib.auth import get_user_model

from .forms import OrderForm
from .models import Order, Testimonial

User = get_user_model()


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

    def test_contacts_submission_creates_testimonial(self):
        response = self.client.post('/contacts/', {
            'client_name': 'Марія',
            'company': 'Studio',
            'quote': 'Дуже сподобався результат роботи та комунікація.',
            'rating': 5,
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, '/contacts/')
        testimonial = Testimonial.objects.get()
        self.assertFalse(testimonial.is_published)


class ClientAccountTests(TestCase):
    def test_client_can_register_and_is_logged_in(self):
        response = self.client.post(reverse('portfolio:client_register'), {
            'first_name': 'Олена',
            'email': 'olena.client@example.com',
            'password': 'Safe-Client-Passphrase-482!',
            'password_confirm': 'Safe-Client-Passphrase-482!',
        })

        self.assertRedirects(response, reverse('portfolio:my_orders'))
        self.assertTrue(User.objects.filter(email='olena.client@example.com').exists())
        self.assertEqual(response.wsgi_request.user.email, 'olena.client@example.com')

    def test_client_can_login_with_email(self):
        User.objects.create_user(
            username='login.client@example.com',
            email='login.client@example.com',
            password='Safe-Client-Passphrase-482!',
        )

        response = self.client.post(reverse('portfolio:client_login'), {
            'username': 'login.client@example.com',
            'password': 'Safe-Client-Passphrase-482!',
        })

        self.assertRedirects(response, reverse('portfolio:my_orders'))

    def test_logged_in_order_is_attached_to_client_account(self):
        user = User.objects.create_user(
            username='client@example.com',
            email='client@example.com',
            password='Safe-Client-Passphrase-482!',
        )
        self.client.force_login(user)

        response = self.client.post(reverse('portfolio:order_brif'), {
            'project_name': 'Клієнтський сайт',
            'budget': 1200,
            'deadline': '2026-12-31',
            'description': 'Потрібен сайт із каталогом, формою зв’язку та адаптивним дизайном для клієнтів.',
            'contact_name': 'Олена',
            'contact_email': 'client@example.com',
            'contact_phone': '+380501112233',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get().user, user)

    def test_my_orders_only_shows_orders_owned_by_signed_in_user(self):
        client_user = User.objects.create_user(username='one@example.com', email='one@example.com', password='Safe-Client-Passphrase-482!')
        other_user = User.objects.create_user(username='two@example.com', email='two@example.com', password='Safe-Client-Passphrase-482!')
        Order.objects.create(
            user=client_user,
            project_name='Моє замовлення',
            budget=500,
            deadline='2026-12-31',
            description='Потрібен сайт із головною сторінкою, формою заявки та контактною інформацією.',
            contact_name='Перший клієнт',
            contact_email=client_user.email,
            contact_phone='+380501112233',
        )
        Order.objects.create(
            user=other_user,
            project_name='Чуже замовлення',
            budget=700,
            deadline='2026-12-31',
            description='Потрібен каталог послуг з пошуком, фільтрами та формою зворотного зв’язку.',
            contact_name='Другий клієнт',
            contact_email=other_user.email,
            contact_phone='+380671112233',
        )
        self.client.force_login(client_user)

        response = self.client.get(reverse('portfolio:my_orders'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Моє замовлення')
        self.assertNotContains(response, 'Чуже замовлення')

    def test_my_orders_requires_authentication(self):
        response = self.client.get(reverse('portfolio:my_orders'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('portfolio:client_login'), response.url)

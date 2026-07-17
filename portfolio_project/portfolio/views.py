import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.db.models import Count, Max
from django.db.models.functions import ExtractMonth

logger = logging.getLogger(__name__)

from .forms import OrderForm, BlogCommentForm
from .models import Project, Skill, Experience, Testimonial, Order, PricingPackage, BlogPost, BlogCategory, BlogTag, PageView


def home(request):
    track_page(request, 'home')
    projects = Project.objects.all().order_by('-date', 'title')
    skills = Skill.objects.all().order_by('category', '-level')
    experiences = Experience.objects.all()
    testimonials = Testimonial.objects.all()
    return render(request, 'portfolio/home.html', {
        'projects': projects,
        'skills': skills,
        'experiences': experiences,
        'testimonials': testimonials,
        'order_form': OrderForm(),
    })


def project_catalog(request):
    track_page(request, 'projects')
    technology = request.GET.get('technology', '')
    projects = Project.objects.all().order_by('-date', 'title')
    if technology:
        projects = projects.filter(technologies__icontains=technology)
    technologies = sorted({p.technologies.split(',')[0].strip() for p in Project.objects.all() if p.technologies})
    return render(request, 'portfolio/projects.html', {
        'projects': projects,
        'technologies': technologies,
        'selected_technology': technology,
    })


def project_detail(request, pk):
    track_page(request, f'project-{pk}')
    project = get_object_or_404(Project, pk=pk)
    return render(request, 'portfolio/project_detail.html', {
        'project': project,
    })


def skills(request):
    track_page(request, 'skills')
    skills = Skill.objects.all().order_by('category', '-level')
    return render(request, 'portfolio/skills.html', {
        'skills': skills,
    })


def contacts(request):
    track_page(request, 'contacts')
    experiences = Experience.objects.all()
    testimonials = Testimonial.objects.all()
    return render(request, 'portfolio/contacts.html', {
        'experiences': experiences,
        'testimonials': testimonials,
    })


def pricing(request):
    track_page(request, 'pricing')
    packages = PricingPackage.objects.all()
    return render(request, 'portfolio/pricing.html', {'packages': packages})


def blog_list(request):
    track_page(request, 'blog')
    category_slug = request.GET.get('category')
    tag_slug = request.GET.get('tag')
    posts = BlogPost.objects.filter(is_published=True)
    if category_slug:
        posts = posts.filter(category__slug=category_slug)
    if tag_slug:
        posts = posts.filter(tags__slug=tag_slug)
    categories = BlogCategory.objects.all()
    tags = BlogTag.objects.all()
    return render(request, 'portfolio/blog.html', {
        'posts': posts,
        'categories': categories,
        'tags': tags,
        'selected_category': category_slug,
        'selected_tag': tag_slug,
    })


def blog_detail(request, slug):
    track_page(request, f'blog-{slug}')
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    comment_form = BlogCommentForm()
    if request.method == 'POST':
        comment_form = BlogCommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.post = post
            comment.save()
            return redirect('portfolio:blog_detail', slug=slug)
    comments = post.comments.all().order_by('-created_at')
    return render(request, 'portfolio/blog_detail.html', {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
    })


def analytics(request):
    track_page(request, 'analytics')
    popular_projects = Order.objects.values('project_name').annotate(order_count=Count('id')).order_by('-order_count')[:5]
    monthly_raw = Order.objects.annotate(month=ExtractMonth('created_at')).values('month').annotate(count=Count('id')).order_by('month')
    max_month_count = max([item['count'] for item in monthly_raw], default=1)
    MONTH_NAMES = ['Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень', 'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень']
    monthly_orders = [
        {
            'month': MONTH_NAMES[item['month'] - 1] if item['month'] else 'Невідомий',
            'count': item['count'],
            'percent': round(item['count'] / max_month_count * 100),
        }
        for item in monthly_raw
    ]
    page_views_raw = PageView.objects.values('page').annotate(count=Count('id')).order_by('-count')[:10]
    max_page_views = max([item['count'] for item in page_views_raw], default=1)
    page_views = [
        {
            'page': item['page'],
            'count': item['count'],
            'percent': round(item['count'] / max_page_views * 100),
        }
        for item in page_views_raw
    ]
    return render(request, 'portfolio/analytics.html', {
        'popular_projects': popular_projects,
        'monthly_orders': monthly_orders,
        'page_views': page_views,
    })


def order_brif(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save()
            send_order_emails(order)
            return redirect('portfolio:order_thanks')
    else:
        form = OrderForm()
    return render(request, 'portfolio/order_brif.html', {'form': form})


def order_thanks(request):
    return render(request, 'portfolio/order_thanks.html')


def track_page(request, page_name):
    PageView.objects.create(page=page_name)


def send_order_emails(order):
    subject_client = 'Підтвердження заявки на розробку'
    html_client = render_to_string('portfolio/emails/client_confirmation.html', {'order': order})
    text_client = f"Дякуємо за заявку {order.contact_name}! Ми отримали ваші дані."

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@portfolio.local')
    connection = get_connection()

    try:
        msg_client = EmailMultiAlternatives(subject_client, text_client, from_email, [order.contact_email], connection=connection)
        msg_client.attach_alternative(html_client, 'text/html')
        msg_client.send()

        subject_admin = f'Нове замовлення: {order.project_name}'
        html_admin = render_to_string('portfolio/emails/admin_notification.html', {'order': order})
        text_admin = f'Отримано нове замовлення від {order.contact_name}.'

        msg_admin = EmailMultiAlternatives(subject_admin, text_admin, from_email, [from_email], connection=connection)
        msg_admin.attach_alternative(html_admin, 'text/html')
        msg_admin.send()
    except Exception as e:
        logger.warning('Email sending failed, falling back to console backend: %s', e)
        console_connection = get_connection(backend='django.core.mail.backends.console.EmailBackend')
        msg_client = EmailMultiAlternatives(subject_client, text_client, from_email, [order.contact_email], connection=console_connection)
        msg_client.attach_alternative(html_client, 'text/html')
        msg_client.send()

        msg_admin = EmailMultiAlternatives(subject_admin, text_admin, from_email, [from_email], connection=console_connection)
        msg_admin.attach_alternative(html_admin, 'text/html')
        msg_admin.send()

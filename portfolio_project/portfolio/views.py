import logging

from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives, get_connection
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Count, Max
from django.db.models.functions import ExtractMonth

logger = logging.getLogger(__name__)

from .forms import OrderForm, BlogCommentForm, TestimonialForm, ClientRegistrationForm, ClientAuthenticationForm
from .models import Project, Skill, Experience, Testimonial, Order, PricingPackage, BlogPost, BlogCategory, BlogTag, PageView


def _enrich_project_techs(project):
    raw = getattr(project, 'technologies', '') or ''
    parts = [t.strip() for t in raw.split(',') if t.strip()]
    project.tech_list = parts
    project.tech_visible = parts[:3]
    project.tech_hidden = parts[3:]
    project.tech_hidden_count = len(project.tech_hidden)
    return project


_SKILL_ICONS = {
    'frontend': '🎨',
    'backend': '⚙️',
    'database': '💾',
    'devops': '🔧',
    'soft': '🤝',
    'other': '✨',
}


def _enrich_skill(skill):
    skill.icon = _SKILL_ICONS.get(skill.category, '✨')
    return skill


def home(request):
    track_page(request, 'home')
    projects = [_enrich_project_techs(p) for p in Project.objects.all().order_by('-date', 'title')]
    skills = [_enrich_skill(s) for s in Skill.objects.all().order_by('category', '-level')]
    experiences = Experience.objects.all()
    testimonials = Testimonial.objects.filter(is_published=True)
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
    qs = Project.objects.all().order_by('-date', 'title')
    if technology:
        qs = qs.filter(technologies__icontains=technology)
    projects = [_enrich_project_techs(p) for p in qs]
    techs_set = set()
    for p in Project.objects.all():
        if p.technologies:
            for t in p.technologies.split(','):
                t = t.strip()
                if t:
                    techs_set.add(t)
    for required in ('Python', 'Django', 'SQL', 'Bootstrap', 'Email'):
        techs_set.add(required)
    technologies = sorted(techs_set)
    return render(request, 'portfolio/projects.html', {
        'projects': projects,
        'technologies': technologies,
        'selected_technology': technology,
    })


def project_detail(request, pk):
    track_page(request, f'project-{pk}')
    project = _enrich_project_techs(get_object_or_404(Project, pk=pk))
    return render(request, 'portfolio/project_detail.html', {
        'project': project,
    })


def skills(request):
    track_page(request, 'skills')
    TECH_CATEGORIES = {'frontend', 'backend', 'database', 'devops', 'other'}
    all_skills = [_enrich_skill(s) for s in Skill.objects.all()]
    tech_skills = [s for s in all_skills if s.category in TECH_CATEGORIES]
    soft_skills = [s for s in all_skills if s.category == 'soft']
    return render(request, 'portfolio/skills.html', {
        'skills': all_skills,
        'tech_skills': tech_skills,
        'soft_skills': soft_skills,
    })


def contacts(request):
    track_page(request, 'contacts')
    experiences = Experience.objects.all()
    testimonials = Testimonial.objects.filter(is_published=True)
    testimonial_form = TestimonialForm(request.POST or None)
    if request.method == 'POST' and testimonial_form.is_valid():
        testimonial = testimonial_form.save(commit=False)
        testimonial.is_published = False
        testimonial.save()
        messages.success(request, 'Дякуємо! Відгук надіслано на перевірку.')
        return redirect('portfolio:contacts')

    return render(request, 'portfolio/contacts.html', {
        'experiences': experiences,
        'testimonials': testimonials,
        'testimonial_form': testimonial_form,
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
            'month_short': (MONTH_NAMES[item['month'] - 1][:3] + '.') if item['month'] else '—',
            'count': item['count'],
            'percent': round(item['count'] / max_month_count * 100),
            'height_pct': max(6, round(item['count'] / max_month_count * 100)),
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
    total_orders = Order.objects.count()
    total_views = PageView.objects.count()
    top_page = page_views[0] if page_views else None
    top_project = popular_projects[0] if popular_projects else None
    return render(request, 'portfolio/analytics.html', {
        'popular_projects': popular_projects,
        'monthly_orders': monthly_orders,
        'page_views': page_views,
        'total_orders': total_orders,
        'total_views': total_views,
        'top_page': top_page,
        'top_project': top_project,
    })


def _get_safe_redirect(request, default='portfolio:home'):
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return reverse(default)


def order_brif(request):
    if request.method == 'POST':
        form = OrderForm(request.POST, request.FILES)
        if form.is_valid():
            order = form.save(user=request.user)
            send_order_emails(order)
            return redirect('portfolio:order_thanks')
    else:
        form = OrderForm()
    return render(request, 'portfolio/order_brif.html', {'form': form})
order_brif = login_required(login_url='portfolio:client_login')(order_brif)


def client_register(request):
    form = ClientRegistrationForm(request.POST or None)
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('portfolio:my_orders')
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        auth_login(request, user)
        safe_next = next_url if (next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})) else reverse('portfolio:my_orders')
        return redirect(safe_next)
    return render(request, 'portfolio/account_register.html', {
        'form': form,
        'next_url': request.GET.get('next', ''),
    })


def client_login(request):
    form = ClientAuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        auth_login(request, form.get_user())
        safe_next = _get_safe_redirect(request, default='portfolio:my_orders')
        return redirect(safe_next)
    return render(request, 'portfolio/account_login.html', {
        'form': form,
        'next_url': request.GET.get('next', ''),
    })


def client_logout(request):
    if request.method == 'POST':
        auth_logout(request)
    return redirect('portfolio:home')


@login_required(login_url='portfolio:client_login')
def my_orders(request):
    qs = request.user.portfolio_orders.prefetch_related('files').all()
    orders = []
    import os
    for order in qs:
        items = []
        total_price = 0
        total_hours = 0.0
        details = order.pricing_details or {}
        raw_items = details.get('items') or []
        for it in raw_items:
            price = float(it.get('price') or 0)
            hours = float(it.get('hours') or 0)
            total_price += price
            total_hours += hours
            items.append({
                'name': it.get('name', ''),
                'section': it.get('section', ''),
                'style': it.get('style', ''),
                'description': it.get('description', ''),
                'price': int(price),
                'hours': round(hours, 1),
            })
        level_name = details.get('levelName') or order.get_development_level_display() or ''
        files_pretty = []
        for f in order.files.all():
            files_pretty.append({
                'url': f.file.url,
                'name': os.path.basename(f.file.name),
                'uploaded_at': f.uploaded_at,
            })
        orders.append({
            'pk': order.pk,
            'project_name': order.project_name,
            'created_at': order.created_at,
            'status': order.status,
            'get_status_display': order.get_status_display(),
            'budget': order.budget,
            'min_budget': order.min_budget or 0,
            'deadline': order.deadline,
            'get_development_level_display': order.get_development_level_display(),
            'development_level': order.development_level,
            'total_hours': order.total_hours or 0,
            'total_days': order.total_days or 0,
            'description': order.description,
            'contact_name': order.contact_name,
            'contact_email': order.contact_email,
            'contact_phone': order.contact_phone,
            'reference_image': order.reference_image,
            'files_pretty': files_pretty,
            'structure_items': items,
            'structure_total_price': int(total_price),
            'structure_total_hours': round(total_hours, 1),
            'structure_level_name': level_name,
        })
    return render(request, 'portfolio/my_orders.html', {'orders': orders})


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

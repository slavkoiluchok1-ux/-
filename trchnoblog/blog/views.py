from django.shortcuts import render

def home_viev(request):
    context = { 
        'blog_name': 'Technoblog',
        'description': 'Сучасний блог про технології, програмування та розробку'
    }
    return render(request, 'blog/home.html', context)

def check_experience(request):
    experience_years = None
    if request.method == "POST":
        experience_years = int(request.POST.get("years", 0))
    return render(request, "blog/experience.html", {"years": experience_years})

def popular_posts(request):
    posts_data = [
        {"title": "Вивчаємо Python", "views": 1520},
        {"title": "Django для початківців", "views": 980},
        {"title": "JavaScript ES6", "views": 1340},
        {"title": "React Hooks", "views": 760},
        {"title": "Machine Learning", "views": 2100},
    ]
    return render(request, "blog/popular.html", {"blog_title": "Популярні статті TechBlog", "posts": posts_data})


def about_view(request):
    context = {
        'team': [
            {'name': 'Ярослав', 'role': 'Backend Developer', 'bio': 'Створює надійну архітектуру та логіку серверної частини.'},
            {'name': 'Степан', 'role': 'QA Engineer & Content Manager', 'bio': 'Стежить за якістю коду та наповнює блог цікавими статтями.'}
        ]
    }
    return render(request, 'blog/about.html', context)

def contact_view(request):
    context = {
        'email': 'contact@techblog.lviv.ua',
        'phone': '+380 93 123 4567',
        'address': 'Україна, м. Львів, вул. Наукова'
    }
    return render(request, 'blog/contact.html', context)
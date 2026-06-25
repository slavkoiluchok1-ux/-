from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.home_viev, name='home'),
    path('experience/', views.check_experience, name='experience'),
    path('popular/', views.popular_posts, name='popular'),
    path('about/', views.about_view, name='about'),
    path('contact/', views.contact_view, name='contact'),
]
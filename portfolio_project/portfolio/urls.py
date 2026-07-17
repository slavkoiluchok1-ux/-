from django.urls import path
from . import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.home, name='home'),
    path('projects/', views.project_catalog, name='projects'),
    path('projects/<int:pk>/', views.project_detail, name='project_detail'),
    path('skills/', views.skills, name='skills'),
    path('contacts/', views.contacts, name='contacts'),
    path('pricing/', views.pricing, name='pricing'),
    path('blog/', views.blog_list, name='blog'),
    path('blog/<slug:slug>/', views.blog_detail, name='blog_detail'),
    path('analytics/', views.analytics, name='analytics'),
    path('brief/', views.order_brif, name='order_brif'),
    path('thanks/', views.order_thanks, name='order_thanks'),
]

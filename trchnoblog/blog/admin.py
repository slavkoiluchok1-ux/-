import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import Article, Tag


@admin.action(description='Mark selected articles as featured')
def make_featured(modeladmin, request, queryset):
    queryset.update(is_featured=True)


@admin.action(description='Reset views counter for selected articles')
def reset_views(modeladmin, request, queryset):
    queryset.update(views=0)


@admin.action(description='Export selected articles to CSV')
def export_as_csv(modeladmin, request, queryset):
    field_names = ['title', 'author', 'views', 'likes', 'is_featured', 'published_at']

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=articles.csv'

    writer = csv.writer(response)
    writer.writerow(field_names)

    for article in queryset:
        writer.writerow([
            article.title,
            article.author,
            article.views,
            article.likes,
            article.is_featured,
            article.published_at.isoformat(),
        ])

    return response


class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'views', 'likes', 'is_featured', 'published_at']
    list_filter = ['is_featured', 'published_at', 'author', 'tags']
    search_fields = ['title', 'content']
    list_editable = ['is_featured']
    filter_horizontal = ['tags']
    readonly_fields = ['views', 'likes']
    actions = [make_featured, reset_views, export_as_csv]


class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'color']
    search_fields = ['name']


admin.site.register(Article, ArticleAdmin)
admin.site.register(Tag, TagAdmin)

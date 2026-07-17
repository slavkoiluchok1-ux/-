from django.contrib import admin
from .models import Project, Skill, Experience, Testimonial, Order, PricingPackage, BlogCategory, BlogTag, BlogPost, BlogComment, PageView


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'technologies', 'date', 'github')
    list_editable = ('technologies', 'github')
    search_fields = ('title', 'technologies')
    list_filter = ('date',)
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'technologies', 'date', 'image', 'github')
        }),
    )


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'level')
    list_editable = ('category', 'level')
    list_filter = ('category',)
    search_fields = ('name',)


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ('position', 'company', 'period')
    search_fields = ('position', 'company')
    list_editable = ('period',)
    list_filter = ('company',)


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('client_name', 'company', 'rating')
    list_editable = ('rating',)
    search_fields = ('client_name', 'company')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('project_name', 'contact_name', 'budget', 'deadline', 'status', 'created_at')
    list_filter = ('status', 'deadline')
    search_fields = ('project_name', 'contact_name', 'contact_email')
    list_editable = ('status',)


@admin.register(PricingPackage)
class PricingPackageAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'popular')
    list_editable = ('price', 'popular')


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


@admin.register(BlogTag)
class BlogTagAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_published', 'created_at')
    list_filter = ('category', 'is_published')
    search_fields = ('title', 'content')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'author_name', 'created_at')


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ('page', 'viewed_at')
    list_filter = ('viewed_at',)

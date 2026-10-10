from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from .models import Project, Skill, Experience, Testimonial, Order, OrderFile, PricingPackage, BlogCategory, BlogTag, BlogPost, BlogComment, PageView


class OrderFileInline(admin.TabularInline):
    model = OrderFile
    extra = 0
    fields = ('file_link', 'uploaded_at')
    readonly_fields = ('file_link', 'uploaded_at')

    def file_link(self, obj):
        if obj and obj.file:
            return format_html(
                '<a href="{}" target="_blank" class="button" style="padding:4px 10px;">📄 {} · {}</a>',
                obj.file.url,
                obj.file.name.split('/')[-1],
                self._human_size(getattr(obj.file, 'size', 0)),
            )
        return '—'
    file_link.short_description = 'Файл'

    def _human_size(self, b):
        if not b: return '0 B'
        kb = b / 1024
        if kb < 1024: return f'{kb:.1f} KB'
        return f'{kb / 1024:.1f} MB'


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
    list_display = ('client_name', 'company', 'rating', 'is_published')
    list_editable = ('rating', 'is_published')
    list_filter = ('is_published', 'rating')
    search_fields = ('client_name', 'company')
    actions = ['publish_selected']

    def publish_selected(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f'Опубліковано {updated} відгуків')
    publish_selected.short_description = '✅ Опублікувати вибрані'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderFileInline]
    list_display = ('project_name', 'contact_name', 'budget', 'min_budget', 'total_hours', 'total_days', 'deadline', 'min_date_col', 'level_col', 'status', 'created_at')
    list_filter = ('status', 'development_level', 'deadline', 'created_at')
    search_fields = ('project_name', 'contact_name', 'contact_email', 'contact_phone')
    list_editable = ('status',)
    readonly_fields = ('created_at', 'min_budget', 'total_hours', 'total_days', 'development_level', 'pricing_details_pretty', 'files_count')
    fieldsets = (
        ('Основне', {
            'fields': ('project_name', 'description', 'status', 'created_at', 'reference_image')
        }),
        ('Деталі з прайсу', {
            'classes': ('collapse',),
            'fields': ('min_budget', 'budget', 'development_level', 'total_hours', 'total_days', 'deadline', 'pricing_details_pretty', 'files_count'),
        }),
        ('Контакти', {
            'fields': ('contact_name', 'contact_email', 'contact_phone')
        }),
    )

    def level_col(self, obj):
        mapping = {
            'base': '<span style="color:#5d7a14;background:rgba(199,227,117,.18);padding:2px 8px;border-radius:6px;">Базовий</span>',
            'standard': '<span style="color:#7a5b06;background:rgba(246,213,106,.30);padding:2px 8px;border-radius:6px;">Стандартний</span>',
            'premium': '<span style="color:#b0306b;background:rgba(255,156,191,.30);padding:2px 8px;border-radius:6px;">Преміум</span>',
        }
        return mark_safe(mapping.get(obj.development_level, '—'))
    level_col.short_description = 'Рівень'

    def min_date_col(self, obj):
        if obj.total_days:
            from datetime import timedelta
            return (obj.created_at + timedelta(days=obj.total_days)).date()
        return obj.deadline
    min_date_col.short_description = 'Орієнтовний кінець'

    def files_count(self, obj):
        return obj.files.count()
    files_count.short_description = 'Файлів додано'

    def pricing_details_pretty(self, obj):
        if not obj.pricing_details:
            return '—'
        data = obj.pricing_details if isinstance(obj.pricing_details, dict) else {}
        items = data.get('items') or []
        level_name = data.get('levelName') or obj.get_level_display() or '—'
        rows = format_html_join(
            '',
            '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td>'
            '<td style="text-align:right">{} $</td><td style="text-align:right">{} год</td></tr>',
            (
                (
                    index + 1,
                    item.get('name', ''),
                    item.get('section', ''),
                    item.get('style') or 'За замовчуванням',
                    item.get('price', 0),
                    item.get('hours', 0),
                )
                for index, item in enumerate(items)
            ),
        )
        total_price = sum(int(i.get('price') or 0) for i in items)
        total_hours = sum(float(i.get('hours') or 0) for i in items)
        return format_html(
            '<div style="font-size:13px">'
            '<p><strong>Рівень:</strong> {} · <strong>Загалом:</strong> {} $ · <strong>Годин:</strong> {}</p>'
            '<table style="border-collapse:collapse;width:100%;max-width:720px">'
            '<thead><tr style="background:#fafaf2">'
            '<th style="padding:6px 8px;border:1px solid #eee;">#</th>'
            '<th style="padding:6px 8px;border:1px solid #eee;">Назва</th>'
            '<th style="padding:6px 8px;border:1px solid #eee;">Розділ</th>'
            '<th style="padding:6px 8px;border:1px solid #eee;">Вигляд</th>'
            '<th style="padding:6px 8px;border:1px solid #eee;text-align:right">Ціна</th>'
            '<th style="padding:6px 8px;border:1px solid #eee;text-align:right">Час</th></tr></thead>'
            '<tbody>{}</tbody>'
            '<tfoot><tr style="background:#f1ede3;font-weight:700">'
            '<td style="padding:6px 8px;border:1px solid #eee;" colspan="4">РАЗОМ</td>'
            '<td style="padding:6px 8px;border:1px solid #eee;text-align:right">{} $</td>'
            '<td style="padding:6px 8px;border:1px solid #eee;text-align:right">{} год</td>'
            '</tr></tfoot></table></div>',
            level_name, total_price, round(total_hours, 1),
            rows,
            total_price, round(total_hours, 1),
        )
    pricing_details_pretty.short_description = 'Склад проєкту (з прайсу)'


@admin.register(OrderFile)
class OrderFileAdmin(admin.ModelAdmin):
    list_display = ('order', 'file', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('order__project_name',)


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
    list_editable = ('is_published',)


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ('post', 'author_name', 'created_at')


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ('page', 'viewed_at')
    list_filter = ('viewed_at',)

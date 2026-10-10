from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0004_testimonial_is_published'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='reference_image',
            field=models.ImageField(blank=True, null=True, upload_to='orders/references/', verbose_name='Референс'),
        ),
    ]
from .models import Order


def admin_orders(request):
    if request.path.startswith('/admin/') and request.user.is_staff:
        return {'admin_orders': Order.objects.all()[:5]}
    return {}

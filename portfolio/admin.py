from django.contrib import admin
from .models import Asset, Price, Portfolio, Holding

admin.site.register(Asset)
admin.site.register(Price)
admin.site.register(Portfolio)
admin.site.register(Holding)
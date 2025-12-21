from django.contrib import admin

from mixengine.models import Sample, ProductOrder, ProductMixResult


class SampleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "lot_number",
        "production_date",
        "cp",
        "fat",
        "tvbn",
        "ash",
        "ffa",
        "moisture",
        "fiber",

        "bags_available",
        "used_quantity",
        "remaining_quantity",
        "last_updated"
    ]


class ProductOrderAdmin(admin.ModelAdmin):
    list_display = [
        "target_cp",
        "total_bags",
        "created_at",
    ]


class ProductMixResultAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "sample",
        "bags_used",
    ]


admin.site.register(Sample, SampleAdmin)
admin.site.register(ProductOrder, ProductOrderAdmin)
admin.site.register(ProductMixResult, ProductMixResultAdmin)

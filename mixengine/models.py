from django.db import models


class Sample(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    lot_number = models.CharField(max_length=100, null=True, blank=True)
    production_date = models.DateField(null=True, blank=True)

    # Nutritional values
    cp = models.FloatField(help_text="Crude Protein %", null=True, blank=True)
    fat = models.FloatField(null=True, blank=True)
    tvbn = models.FloatField(null=True, blank=True)
    ash = models.FloatField(null=True, blank=True)
    ffa = models.FloatField(null=True, blank=True)
    moisture = models.FloatField(null=True, blank=True)
    fiber = models.FloatField(null=True, blank=True)

    # Stock/usage tracking
    bags_available = models.IntegerField(null=True, blank=True)
    used_quantity = models.FloatField(null=True, blank=True, default=0)   # total dispatched
    remaining_quantity = models.FloatField(null=True, blank=True)         # auto-updated
    last_updated = models.DateTimeField(auto_now=True)                    # value change recent date

    def save(self, *args, **kwargs):
        if self.bags_available is not None and self.used_quantity is not None:
            self.remaining_quantity = self.bags_available - self.used_quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (Lot: {self.lot_number}, CP: {self.cp}%)"


class ProductOrder(models.Model):
    target_cp = models.FloatField(null=True, blank=True)
    total_bags = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"Order {self.id} - Target CP: {self.target_cp}, Total Bags: {self.total_bags}"


class ProductMixResult(models.Model):
    order = models.ForeignKey(ProductOrder, on_delete=models.CASCADE, related_name="mix", null=True, blank=True)
    sample = models.ForeignKey(Sample, on_delete=models.CASCADE, null=True, blank=True)
    bags_used = models.FloatField(null=True, blank=True)

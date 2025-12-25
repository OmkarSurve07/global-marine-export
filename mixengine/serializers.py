from rest_framework import serializers

from mixengine.models import Sample, ProductOrder, ProductMixResult
from mixengine.utils.mix_optimizer import optimize_mix


class SampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sample
        fields = '__all__'


class ProductOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductOrder
        fields = ['id', 'target_cp', 'total_bags']


class ProductMixResultSerializer(serializers.ModelSerializer):
    sample = SampleSerializer()

    class Meta:
        model = ProductMixResult
        fields = ['sample', 'bags_used']


class ProductOrderCreateSerializer(serializers.Serializer):
    total_bags = serializers.IntegerField()
    target_cp = serializers.FloatField(required=False)
    target_fat = serializers.FloatField(required=False)
    target_tvbn = serializers.FloatField(required=False)
    target_ash = serializers.FloatField(required=False)
    target_ffa = serializers.FloatField(required=False)
    target_moisture = serializers.FloatField(required=False)
    target_fiber = serializers.FloatField(required=False)
    fixed_samples = serializers.DictField(
        child=serializers.FloatField(),
        required=False,
        help_text="Dict of {sample_name: bags_to_use}"
    )

    def validate(self, data):
        if data['total_bags'] <= 0:
            raise serializers.ValidationError("Total bags must be > 0")

        if not Sample.objects.exists():
            raise serializers.ValidationError("No samples found. Please add sample data first.")

        # Ensure at least one target parameter is provided
        if not any([
            data.get("target_cp"),
            data.get("target_fat"),
            data.get("target_tvbn"),
            data.get("target_ash"),
            data.get("target_ffa"),
            data.get("target_moisture"),
            data.get("target_fiber")
        ]):
            raise serializers.ValidationError(
                "At least one nutritional target (CP, Fat, TVBN, Ash, FFA, Moisture, Fiber) is required."
            )

        # Min/Max validation for nutritional fields
        field_mapping = {
            "target_cp": "cp",
            "target_fat": "fat",
            "target_tvbn": "tvbn",
            "target_ash": "ash",
            "target_ffa": "ffa",
            "target_moisture": "moisture",
            "target_fiber": "fiber",
        }

        for target_field, sample_field in field_mapping.items():
            target_value = data.get(target_field)
            if target_value is not None:
                values = list(
                    Sample.objects.values_list(sample_field, flat=True).exclude(**{f"{sample_field}__isnull": True})
                )
                if values:
                    min_val, max_val = min(values), max(values)
                    if target_value < min_val or target_value > max_val:
                        raise serializers.ValidationError(
                            f"{target_field.replace('target_', '').upper()} target {target_value} is not achievable. "
                            f"Available range: {min_val} – {max_val}"
                        )

        data = super().validate(data)

        # New: Check fixed_samples against remaining_quantity
        samples = list(Sample.objects.all())
        fixed_samples = data.get('fixed_samples', {}) or {}
        for key, val in fixed_samples.items():
            if key.upper() == "F/M":
                matching_indices = [i for i, s in enumerate(samples) if "FISH MEAL" in s.name.upper()]
            elif key.upper() == "HYPRO":
                matching_indices = [i for i, s in enumerate(samples) if "HYPRO" in s.name.upper()]
            else:
                matching_indices = [i for i, s in enumerate(samples) if key.upper() in s.name.upper()]
            if matching_indices:
                sum_remaining = sum(max(0, samples[i].remaining_quantity) for i in matching_indices)
                if sum_remaining < val:
                    # Don't raise error; we'll handle in save with a message
                    data['insufficient_stock'] = {key: {'required': val, 'available': sum_remaining}}

        return data

    def save(self, **kwargs):
        data = self.validated_data
        total_bags = data.pop('total_bags')
        fixed_samples = data.pop('fixed_samples', {}) or {}
        insufficient_stock = data.pop('insufficient_stock', None)  # From validate

        if insufficient_stock:
            messages = []
            for key, info in insufficient_stock.items():
                messages.append(f"Not enough {key}: required {info['required']}, available {info['available']}")
            return {
                "success": False,
                "message": "Request can't be completed because " + "; ".join(messages)
            }

        samples = list(Sample.objects.all())
        # Run optimization
        result = optimize_mix(samples, total_bags, fixed_samples=fixed_samples, **data)

        if not result['success']:
            raise serializers.ValidationError("Optimization failed. Please adjust your input.")

        # Map targets for response (strip 'target_', uppercase keys)
        targets = {k.replace("target_", "").upper(): v for k, v in self.validated_data.items() if
                   k.startswith('target_') and v is not None}

        # Create order
        order = ProductOrder.objects.create(
            target_cp=data.get("target_cp"),
            total_bags=total_bags
        )

        # Loop over samples and update stock
        for i, sample in enumerate(samples):
            bags_used = result['bags_used'][i]
            if bags_used > 0:
                ProductMixResult.objects.create(
                    order=order,
                    sample=sample,
                    bags_used=bags_used,
                    # is_fixed=sample.name in fixed_samples
                )

                sample.used_quantity += bags_used
                sample.remaining_quantity = sample.bags_available - sample.used_quantity
                sample.save(update_fields=["used_quantity", "remaining_quantity"])

        # Calculate variances
        final_values = result['final_values']  # Assuming lower keys like 'cp'
        variances = {k: round(final_values.get(k.lower(), 0) - v, 2) for k, v in targets.items()}

        return {
            "order_id": order.id,
            "total_bags": total_bags,
            "targets": targets,
            "final_values": result['final_values'],
            "variances": variances,
            "mix": ProductMixResultSerializer(
                ProductMixResult.objects.filter(order=order), many=True
            ).data
        }

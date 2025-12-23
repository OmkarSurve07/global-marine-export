import os
import pandas as pd
from celery import shared_task
from django.db import transaction
from .models import Sample  # Import your Sample model


@shared_task(bind=True)
def process_sample_upload(self, file_path):
    """
    Background task to process the uploaded CSV/Excel file.
    """
    created = 0
    updated = 0
    chunksize = 1000  # Process in chunks to handle large files

    try:
        if file_path.endswith('.csv'):
            reader = pd.read_csv(file_path, chunksize=chunksize)
        elif file_path.endswith('.xlsx'):
            df = pd.read_excel(file_path)
            reader = [df]  # Single chunk for Excel (or implement chunking if needed)
        else:
            raise ValueError("Unsupported file format.")

        required_columns = ['Sample', 'Date', 'Lot.No', 'M', 'CP', 'FAT',
                            'TVBN', 'Ash', 'FFA', 'Bags', 'Fiber']

        for chunk in reader:
            if not all(col in chunk.columns for col in required_columns):
                raise ValueError("Missing required columns.")

            with transaction.atomic():
                for _, row in chunk.iterrows():
                    date_value = pd.to_datetime(row['Date'], format='%d.%m.%Y', errors='coerce')
                    production_date = None if pd.isna(date_value) else date_value.date()

                    obj, is_created = Sample.objects.update_or_create(
                        name=row['Sample'],
                        lot_number=row['Lot.No'],
                        defaults={
                            'production_date': production_date,
                            'moisture': row['M'],
                            'cp': row['CP'],
                            'fat': row['FAT'],
                            'tvbn': row['TVBN'],
                            'ash': row['Ash'],
                            'ffa': row['FFA'],
                            'bags_available': row['Bags'],
                            'fiber': row['Fiber'],
                        }
                    )
                    if is_created:
                        created += 1
                    else:
                        updated += 1

        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

        return {
            "status": "success",
            "created": created,
            "updated": updated,
            "total_processed": created + updated
        }

    except Exception as e:
        # Update task state for error
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise  # Let Celery handle the failure
